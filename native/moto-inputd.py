#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Athene's Android MT protocol -> standard Linux touchscreen; physical keys.

Only the first contact controls the pointer. Other fingers cannot teleport it.
No touch coordinates or terminal text are logged. Requires Linux 64-bit evdev.
"""
import os
import json
from pathlib import Path
import selectors
import signal
import socket
import struct
import time

EVENT = struct.Struct('@llHHi')
NAME = 'Moto Linux Touch'
LINK = Path('/dev/input/moto-touch')
SOCKET = '/run/moto-ux.sock'


def ioctl_u(n):
    return (1 << 30) | (4 << 16) | (ord('U') << 8) | n


def devices():
    result = {}
    for p in Path('/sys/class/input').glob('event*/device/name'):
        result[p.read_text().strip()] = '/dev/input/' + p.parents[1].name
    return result


def seed_contacts(fd, contacts):
    """evdev suppresses unchanged coordinates/slot numbers, even on a new tap.

    Initialize cached MT axes through ioctls so the first tap after a service
    restart works even at the exact position of the previous tap.
    """
    import fcntl
    info = bytearray(24)
    fcntl.ioctl(fd, (2 << 30) | (24 << 16) | (ord('E') << 8) | (0x40 + 47), info)
    value, minimum, maximum, _, _, _ = struct.unpack('6i', info)
    contacts.slot = value
    count = maximum + 1
    if not (0 < count <= 64):
        raise RuntimeError('Unexpected touchscreen slot count')
    for axis, name in ((53, 'x'), (54, 'y')):
        data = bytearray(struct.pack(f'{count+1}i', axis, *([0] * count)))
        request = (2 << 30) | (len(data) << 16) | (ord('E') << 8) | 0x0a
        fcntl.ioctl(fd, request, data)
        values = struct.unpack(f'{count+1}i', data)[1:]
        for slot, coordinate in enumerate(values):
            contacts.slots.setdefault(slot, {'id': -1})[name] = coordinate


class Contacts:
    def __init__(self):
        self.slot = 0
        self.slots = {}
        self.primary = None
        self.down = False
        self.dropped = False

    def feed(self, kind, code, value):
        if kind == 0 and code == 3:  # SYN_DROPPED: release; wait for clean frame
            self.slots.clear()
            self.primary = None
            self.dropped = True
            was = self.down
            self.down = False
            return [(1, 330, 0), (0, 0, 0)] if was else []
        if self.dropped:
            if kind == 0 and code == 0:
                self.dropped = False
            return []
        if kind == 3:
            if code == 47:
                self.slot = value
            elif code in (53, 54, 57):
                state = self.slots.setdefault(self.slot, {'id': -1})
                state[{53: 'x', 54: 'y', 57: 'id'}[code]] = value
            return []
        if kind != 0 or code != 0:
            return []
        active = {s: v for s, v in self.slots.items() if v.get('id', -1) >= 0}
        out = []
        if self.primary is not None and self.primary not in active:
            if self.down:
                out += [(1, 330, 0), (0, 0, 0)]
            self.primary = None
            self.down = False
            # Don't turn a remaining second finger into a fresh click.
            self.primary = -1 if active else None
        if self.primary == -1 and not active:
            self.primary = None
        if self.primary is None and active:
            self.primary = next(iter(active))
        if self.primary in active:
            point = active[self.primary]
            if 'x' in point and 'y' in point:
                if not self.down:
                    out.append((1, 330, 1))
                out += [(3, 0, point['x']), (3, 1, point['y']), (0, 0, 0)]
                self.down = True
        return out


class Gestures:
    """Tap focuses; vertical drag scrolls tmux; a held touch selects text.

    Keyboard and system menus are passed through immediately. Only a contact
    that STARTS inside the terminal can become a scroll gesture.
    """
    def __init__(self, action):
        self.action = action
        self.state = {}
        self.mode = None
        self.x = self.y = 0
        self.origin = (0, 0)
        self.anchor_y = 0
        self.started = 0
        self.pending = []

    def set_state(self, state):
        self.state = state

    def held(self, now):
        if self.mode == 'pending' and now - self.started >= .45:
            self.mode = 'select'
            data, self.pending = self.pending, []
            return data
        return []

    def feed(self, frame, now):
        down = (1, 330, 1) in frame
        up = (1, 330, 0) in frame
        for typ, code, value in frame:
            if typ == 3 and code == 0:
                self.x = value
            if typ == 3 and code == 1:
                self.y = value
        if down:
            inside = self.state.get('top', 0) <= self.y < self.state.get('bottom', 0)
            inside = inside and not self.state.get('menu', False)
            self.mode = 'pending' if inside else 'pointer'
            self.origin = (self.x, self.y)
            self.anchor_y = self.y
            self.started = now
            self.pending = list(frame) if inside else []
            return [] if inside else frame
        mode = self.mode
        if mode == 'pending':
            dx, dy = self.x - self.origin[0], self.y - self.origin[1]
            if abs(dy) > 30 and abs(dy) > abs(dx) * 1.2:
                self.mode = 'scroll'
                self.pending = []
            elif abs(dx) > 30:
                self.mode = 'select'
                data, self.pending = self.pending + frame, []
                if up:
                    self.mode = None
                return data
            elif up:
                data, self.pending = self.pending + frame, []
                self.mode = None
                return data
        if self.mode == 'scroll':
            distance = self.y - self.anchor_y
            while abs(distance) >= 36:
                self.action('scroll-up' if distance > 0 else 'scroll-down')
                self.anchor_y += 36 if distance > 0 else -36
                distance = self.y - self.anchor_y
            if up:
                self.mode = None
            return []
        if mode == 'pending':
            return self.held(now)
        if up:
            self.mode = None
        return frame


def main():
    import fcntl
    lock = open('/run/moto-inputd.lock', 'w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    found = devices()
    touch = os.open(found['synaptics_dsx_i2c'], os.O_RDONLY | os.O_NONBLOCK)
    output = os.open('/dev/uinput', os.O_WRONLY | os.O_NONBLOCK)
    for bit in (0, 1, 3):
        fcntl.ioctl(output, ioctl_u(100), bit)
    fcntl.ioctl(output, ioctl_u(101), 330)  # BTN_TOUCH
    fcntl.ioctl(output, ioctl_u(110), 1)    # INPUT_PROP_DIRECT
    maxima, minima = [0] * 64, [0] * 64
    for axis, source in ((0, 53), (1, 54)):
        fcntl.ioctl(output, ioctl_u(103), axis)
        info = bytearray(24)
        fcntl.ioctl(touch, (2 << 30) | (24 << 16) | (ord('E') << 8) | (0x40 + source), info)
        _, minima[axis], maxima[axis], _, _, _ = struct.unpack('6i', info)
    descriptor = struct.pack('80sHHHHi', NAME.encode(), 3, 0x18d1, 1, 1, 0)
    descriptor += struct.pack('256i', *(maxima + minima + [0] * 128))
    os.write(output, descriptor)
    fcntl.ioctl(output, 0x5501)  # UI_DEV_CREATE, works on kernel 3.10
    for _ in range(50):
        path = devices().get(NAME)
        if path and Path(path).exists():
            LINK.unlink(missing_ok=True)
            LINK.symlink_to(path)
            break
        time.sleep(.05)
    else:
        raise RuntimeError('uinput touchscreen did not appear')
    print('Touch adapter ready:', path, flush=True)
    sel = selectors.DefaultSelector()
    sel.register(touch, selectors.EVENT_READ, 'touch')
    opened = [touch]
    for name in ('qpnp_pon', 'gpio-keys', 'fpc1020', 'qwerty'):
        if name in found:
            fd = os.open(found[name], os.O_RDONLY | os.O_NONBLOCK)
            opened.append(fd)
            sel.register(fd, selectors.EVENT_READ, name)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    control = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    control_path = Path('/run/moto-input.sock')
    control_path.unlink(missing_ok=True)
    control.bind(str(control_path))
    os.chmod(control_path, 0o600)
    control.setblocking(False)
    sel.register(control, selectors.EVENT_READ, 'control')
    contacts, pressed = Contacts(), {}
    seed_contacts(touch, contacts)
    def cleanup(*_):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)
    def action(command):
        try:
            sock.sendto(command.encode(), SOCKET)
        except (FileNotFoundError, ConnectionRefusedError):
            pass
    gestures = Gestures(action)
    def emit(events):
        if events:
            data = memoryview(b''.join(EVENT.pack(0, 0, *event) for event in events))
            # uinput on this 3.10 kernel consumes exactly ONE input_event per
            # write, unlike modern implementations. Never drop a short write.
            while data:
                written = os.write(output, data)
                if written <= 0:
                    raise RuntimeError('uinput write made no progress')
                data = data[written:]
    try:
        blocked = False
        checked_light = 0
        while True:
            ready = sel.select(.02)
            now = time.monotonic()
            if now - checked_light > .1:
                checked_light = now
                try:
                    screen_off = int(Path('/sys/class/leds/lcd-backlight/brightness').read_text()) == 0
                except OSError:
                    screen_off = False
                try:
                    gestures.set_state(json.loads(Path('/run/moto-ux.json').read_text()))
                except (OSError, ValueError):
                    gestures.set_state({})
                if screen_off != blocked:
                    if contacts.down:
                        emit([(1, 330, 0), (0, 0, 0)])
                    contacts = Contacts()
                    seed_contacts(touch, contacts)
                    gestures = Gestures(action)
                    blocked = screen_off
            if not blocked:
                emit(gestures.held(now))
            for key, _ in ready:
                if key.data == 'control':
                    command = control.recv(128)
                    if command == b'recalibrate':
                        emit([(1, 330, 0), (0, 0, 0)])
                        reset = Path('/sys/devices/soc.0/78b7000.i2c/i2c-3/3-0020/f54/reset')
                        reset.write_text('1')
                        # Drain reset-era frames before rebuilding the cache.
                        try:
                            while os.read(touch, EVENT.size * 64):
                                pass
                        except BlockingIOError:
                            pass
                        contacts = Contacts()
                        seed_contacts(touch, contacts)
                        gestures = Gestures(action)
                        print('Touch recalibrated after wake', flush=True)
                    continue
                data = os.read(key.fd, EVENT.size * 64)
                for _, _, kind, code, value in EVENT.iter_unpack(data):
                    if key.data == 'touch':
                        if blocked:
                            continue
                        frame = contacts.feed(kind, code, value)
                        if kind == 0 and code == 3:
                            # Lost events cancel a pending tap, never invent one.
                            gestures = Gestures(action)
                            emit(frame)
                            seed_contacts(touch, contacts)
                        elif frame:
                            emit(gestures.feed(frame, time.monotonic()))
                    elif kind == 1:
                        if value == 1:
                            pressed[(key.data, code)] = time.monotonic()
                        if code in (114, 115) and value in (1, 2):
                            action('volume-down' if code == 114 else 'volume-up')
                        elif code == 116 and value == 0:
                            duration = time.monotonic() - pressed.pop((key.data, code), time.monotonic())
                            action('power-menu' if duration >= 1.2 else 'screen-toggle')
                        elif code == 143 and value == 1:
                            action('home')
    finally:
        fcntl.ioctl(output, 0x5502)
        os.close(output)
        LINK.unlink(missing_ok=True)
        control_path.unlink(missing_ok=True)
        for fd in opened:
            os.close(fd)


if __name__ == '__main__':
    main()
