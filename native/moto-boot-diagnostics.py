#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Bounded, private crash evidence for the experimental installed system."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

BASE = Path('/var/log/moto-boots')
LIMIT = 192 * 1024


def read(path, limit=LIMIT):
    try:
        with open(path, 'rb') as stream:
            return stream.read(limit)
    except OSError:
        return b''


def command(argv):
    try:
        return subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              timeout=4, check=False).stdout[-LIMIT:]
    except (OSError, subprocess.TimeoutExpired):
        return b'Collection unavailable\n'


def save(folder, name, data):
    temporary = folder / (name + '.tmp')
    with temporary.open('wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(folder / name)


def main():
    if not Path('/etc/moto-persistent').is_file():
        raise SystemExit('Diagnostics require the installed root filesystem')
    os.umask(0o077)
    BASE.mkdir(mode=0o700, parents=True, exist_ok=True)
    BASE.chmod(0o700)
    boot_id = read('/proc/sys/kernel/random/boot_id', 80).decode().strip()
    if not boot_id or any(c not in '0123456789abcdef-' for c in boot_id):
        raise SystemExit('Invalid boot ID')
    folder = BASE / ('boot-' + boot_id)
    folder.mkdir(mode=0o700, exist_ok=True)
    # Retain four boots; never follow directory symlinks during cleanup.
    previous = sorted((p for p in BASE.iterdir() if p != folder and
                       p.name.startswith('boot-') and p.is_dir() and not p.is_symlink()),
                      key=lambda p: p.stat().st_mtime, reverse=True)
    for old in previous[3:]:
        shutil.rmtree(old)
    save(folder, 'cmdline.txt', read('/proc/cmdline'))
    save(folder, 'early-boot.log', read('/run/early-boot.log'))
    save(folder, 'last-kmsg.txt', read('/proc/last_kmsg', 1024 * 1024))
    pstore = Path('/sys/fs/pstore')
    try:
        subprocess.run(['mount', '-t', 'pstore', 'pstore', str(pstore)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=4, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass
    if pstore.is_dir():
        for index, source in enumerate(sorted(pstore.iterdir())[:16]):
            if source.is_file() and not source.is_symlink():
                save(folder, 'pstore-{}-{}.txt'.format(index, source.name), read(source))
    started = time.monotonic()
    while True:
        state = {'epoch': time.time(), 'uptime': read('/proc/uptime', 100).decode().strip()}
        for name, path in {
            'brightness': '/sys/class/leds/lcd-backlight/brightness',
            'battery': '/sys/class/power_supply/battery/capacity',
            'temperature': '/sys/class/power_supply/battery/temp',
            'charging': '/sys/class/power_supply/battery/status',
            'ui': '/run/moto-ux.json',
        }.items():
            state[name] = read(path, 8192).decode(errors='replace').strip()
        save(folder, 'state.json', json.dumps(state, indent=2).encode())
        save(folder, 'kernel.log', command(['dmesg']))
        save(folder, 'network.txt', command(['ip', 'addr']))
        for name in ('rc.log',):
            save(folder, name, command(['tail', '-c', str(LIMIT), '/run/' + name]))
        for name in ('inputd.log', 'moto-shell.log', 'Xorg.0.log', 'display.log',
                     'dhcp.log', 'ssh.log', 'xorg-start.log', 'network.log', 'desktop.log'):
            save(folder, name, command(['tail', '-c', str(LIMIT), '/tmp/' + name]))
        directory = os.open(str(folder), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        time.sleep(15 if time.monotonic() - started < 180 else 60)


if __name__ == '__main__':
    main()
