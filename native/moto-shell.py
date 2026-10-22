#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Touch shell for an existing xterm: large keys, one-shot modifiers, hardware UX.

Tk draws the shell; XTest delivers real key events to xterm (including SSH/vim).
No terminal emulator, network login, or clipboard protocol is reimplemented.
"""
import ctypes as C
import importlib.machinery
import importlib.util
import json
import os
import queue
import signal
from pathlib import Path
import socket
import re
import stat
import subprocess
import threading
import time
import tkinter as tk
import tkinter.font as tkfont

BG, PANEL, KEY, FG, MUTED, ACCENT = '#0b111b', '#121d2b', '#223249', '#eef4ff', '#94a8bf', '#56dfb1'
SOCKET = '/run/moto-ux.sock'
LIGHT = Path('/sys/class/leds/lcd-backlight/brightness')
panel_loader = importlib.machinery.SourceFileLoader('moto_panel', str(Path(__file__).with_name('moto-panel.py')))
panel_spec = importlib.util.spec_from_loader(panel_loader.name, panel_loader)
panel_module = importlib.util.module_from_spec(panel_spec)
panel_loader.exec_module(panel_module)
BG, PANEL, KEY, FG, MUTED, ACCENT = panel_module.BG, panel_module.PANEL, panel_module.KEY, panel_module.FG, panel_module.MUTED, panel_module.ACCENT
tabs_loader = importlib.machinery.SourceFileLoader('moto_terminals', str(Path(__file__).with_name('moto-terminals.py')))
tabs_spec = importlib.util.spec_from_loader(tabs_loader.name, tabs_loader)
tabs_module = importlib.util.module_from_spec(tabs_spec)
tabs_loader.exec_module(tabs_module)
quick_spec = importlib.util.spec_from_file_location('moto_quick_voice', Path(__file__).with_name('moto-quick-voice.py'))
quick_module = importlib.util.module_from_spec(quick_spec)
quick_spec.loader.exec_module(quick_module)
experience = panel_module.widgets.experience
globals().update(experience.palette(experience.preferences().get('theme')))


class WakeQueue(queue.Queue):
    """Workers only enqueue and signal a socket; all Tk calls stay on its thread."""
    def __init__(self):
        super().__init__()
        self.reader, self.writer = socket.socketpair()
        self.reader.setblocking(False)
        self.writer.setblocking(False)

    def put(self, item, block=True, timeout=None):
        super().put(item, block, timeout)
        try:
            self.writer.send(b'.')
        except (BlockingIOError, OSError):
            pass

    def close(self):
        self.reader.close()
        self.writer.close()


class Keys:
    def __init__(self):
        self.x = C.CDLL('libX11.so.6')
        self.t = C.CDLL('libXtst.so.6')
        self.x.XOpenDisplay.restype = C.c_void_p
        self.d = self.x.XOpenDisplay(None)
        if not self.d:
            raise RuntimeError('No X display')
        self.x.XStringToKeysym.argtypes = [C.c_char_p]
        self.x.XStringToKeysym.restype = C.c_ulong
        self.x.XKeysymToKeycode.argtypes = [C.c_void_p, C.c_ulong]
        self.x.XKeysymToKeycode.restype = C.c_uint
        self.x.XkbKeycodeToKeysym.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_int]
        self.x.XkbKeycodeToKeysym.restype = C.c_ulong
        self.x.XSetInputFocus.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_ulong]
        self.x.XFlush.argtypes = [C.c_void_p]
        self.t.XTestFakeKeyEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
        self.target = None
        self.resolve()

    def resolve(self):
        r = subprocess.run(['xdotool', 'search', '--class', 'XTerm'], capture_output=True, text=True)
        ids = r.stdout.split()
        self.target = int(ids[-1]) if ids else None

    def send(self, key, modifiers=()):
        if not self.target:
            self.resolve()
        if not self.target:
            return
        names = {' ': 'space', '/': 'slash', '\\': 'backslash', '-': 'minus', '_': 'underscore',
                 '.': 'period', ',': 'comma', ':': 'colon', ';': 'semicolon', "'": 'apostrophe',
                 '"': 'quotedbl', '`': 'grave', '~': 'asciitilde', '|': 'bar', '=': 'equal',
                 '+': 'plus', '*': 'asterisk', '&': 'ampersand', '^': 'asciicircum', '%': 'percent',
                 '$': 'dollar', '#': 'numbersign', '@': 'at', '!': 'exclam', '?': 'question',
                 '(': 'parenleft', ')': 'parenright', '[': 'bracketleft', ']': 'bracketright',
                 '{': 'braceleft', '}': 'braceright', '<': 'less', '>': 'greater'}
        sym = self.x.XStringToKeysym(names.get(key, key).encode())
        code = self.x.XKeysymToKeycode(self.d, sym)
        if not code:
            return
        mods = list(modifiers)
        if self.x.XkbKeycodeToKeysym(self.d, code, 0, 0) != sym and self.x.XkbKeycodeToKeysym(self.d, code, 0, 1) == sym:
            if 'Shift_L' not in mods:
                mods.append('Shift_L')
        codes = [self.x.XKeysymToKeycode(self.d, self.x.XStringToKeysym(m.encode())) for m in mods]
        self.x.XSetInputFocus(self.d, self.target, 2, 0)
        try:
            for c in codes:
                self.t.XTestFakeKeyEvent(self.d, c, 1, 0)
            self.t.XTestFakeKeyEvent(self.d, code, 1, 0)
            self.t.XTestFakeKeyEvent(self.d, code, 0, 0)
        finally:
            for c in reversed(codes):
                self.t.XTestFakeKeyEvent(self.d, c, 0, 0)
            self.x.XFlush(self.d)


class Shell:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.tk.call('tk', 'scaling', 1.0)
        self.w, self.h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.keys = Keys()
        self.mods = set()
        self.symbols = False
        self.visible = True
        self.sleeping = False
        self.light = int(LIGHT.read_text()) or 160
        self.menu = None
        self.events = WakeQueue()
        self.refresh_event = threading.Event()
        self.device = {}
        self.panel = panel_module.DevicePanel(self)
        self.quick_voice = quick_module.QuickDictation(self, panel_module.voice_module.voice)
        self.active = None
        self.repeat = None
        self.repeated = False
        self.pressed_rect = None
        self.font_size = 18
        prefs = experience.preferences()
        self.theme_name = experience.theme_name(prefs.get('theme'))
        self.keyboard_page = experience.keyboard_name(prefs.get('keyboard'))
        self.font_size = experience.font_size(prefs.get('font_size', 18))
        self.header_signature = None
        self.kh = int(self.h * .415)
        self.hh = 200
        self.windows = []
        self.tabs = tabs_module.TerminalTabs(self.tmux)
        self.header_boxes = []
        self.header_pressed = None
        self.tab_font = tkfont.Font(family='DejaVu Sans', size=-23)
        self.info_font = tkfont.Font(family='DejaVu Sans', size=-22)
        self.vpn = False
        self.vpn_label = 'verificando'
        self.in_copy = False
        self.pref_path = experience.config_path()
        try:
            prefs = json.loads(self.pref_path.read_text())
            self.light = max(12, min(255, int(prefs.get('brightness', self.light))))
        except (OSError, ValueError, TypeError):
            pass
        self.header = self.window(self.w, self.hh, 0, 0)
        self.keyboard = self.window(self.w, self.kh, 0, self.h - self.kh)
        self.top = tk.Canvas(self.header, bg=BG, highlightthickness=0)
        self.top.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(self.keyboard, bg=PANEL, highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<ButtonPress-1>', self.press)
        self.canvas.bind('<ButtonRelease-1>', self.release)
        self.canvas.bind('<B1-Motion>', self.motion)
        self.top.bind('<ButtonPress-1>', self.header_press)
        self.top.bind('<ButtonRelease-1>', self.header_tap)
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        Path(SOCKET).unlink(missing_ok=True)
        self.sock.bind(SOCKET)
        os.chmod(SOCKET, 0o600)
        self.sock.setblocking(False)
        self.root.createfilehandler(self.sock, tk.READABLE, self.read_socket)
        self.root.createfilehandler(self.events.reader, tk.READABLE, self.read_events)
        self.toast = 'Ctrl / Alt / Shift: toque e depois a tecla'
        self.toast_until = time.monotonic() + 12
        self.draw()
        self.resize_terminal()
        self.root.after(100, self.poll)
        self.root.after(500, self.status)
        self.root.after(1000, self.refresh_tmux)
        threading.Thread(target=self.vpn_worker, daemon=True).start()

    def terminal_context(self):
        result = self.tmux('display-message', '-p', '-t', 'moto',
                           '#{pid}|#{pane_id}|#{pane_pid}|#{pane_current_command}|#{alternate_on}|#{pane_in_mode}|#{window_name}')
        parts = result.stdout.strip().split('|')
        if result.returncode or len(parts) != 7 or not parts[0].isdigit() or not re.fullmatch(r'%\d+', parts[1]):
            raise RuntimeError('Terminal indisponível. Volte à aba e tente novamente.')
        try:
            started = Path('/proc', parts[0], 'stat').read_text().rsplit(')', 1)[1].split()[19]
        except (OSError, IndexError):
            raise RuntimeError('Não foi possível confirmar a sessão do terminal.') from None
        return tuple(parts)+ (started,)

    def apply_theme(self, name):
        name = experience.theme_name(name)
        colors = experience.palette(name)
        self.theme_name = name
        globals().update(colors)
        for module in (panel_module, panel_module.voice_module):
            module.__dict__.update(colors)
        for module in (panel_module.widgets, panel_module.voice_module.theme):
            module.apply_theme(name)
        self.root.configure(bg=BG)
        for widget in (self.header, self.keyboard, self.top):
            widget.configure(bg=BG)
        self.canvas.configure(bg=PANEL)
        self.header_signature = None
        self.draw()
        self.status(False)
        self.theme_terminal(name)

    def theme_terminal(self, name):
        """Color output goes to our xterm's client tty, never a pane's stdin."""
        try:
            if not self.keys.target:
                return
            prop = subprocess.run(['xprop', '-id', str(self.keys.target), '_NET_WM_PID'],
                                   capture_output=True, text=True, timeout=1)
            match = re.search(r'= (\d+)\s*$', prop.stdout)
            if not match:
                return
            xpid = int(match[1])
            clients = self.tmux('list-clients', '-F', '#{client_tty}|#{client_pid}')
            for line in clients.stdout.splitlines():
                tty, sep, pid = line.partition('|')
                if not sep or not re.fullmatch(r'/dev/pts/\d+', tty) or not pid.isdigit():
                    continue
                child = int(pid)
                for _ in range(8):
                    if child == xpid:
                        break
                    fields = Path('/proc', str(child), 'stat').read_text().rsplit(')', 1)[1].split()
                    child = int(fields[1])
                    if child <= 1:
                        break
                if child != xpid or os.path.realpath('/proc/'+pid+'/fd/0') != tty:
                    continue
                expected = os.stat(tty)
                fd = os.open(tty, os.O_WRONLY | os.O_NOCTTY | os.O_NONBLOCK | os.O_NOFOLLOW)
                try:
                    actual = os.fstat(fd)
                    if stat.S_ISCHR(actual.st_mode) and actual.st_rdev == expected.st_rdev and actual.st_ino == expected.st_ino:
                        os.write(fd, experience.color_sequence(name))
                        return True
                finally:
                    os.close(fd)
        except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
            # Startup also applies the committed palette, so the UI remains usable.
            pass

    def choose_keyboard(self, value):
        self.keyboard_page = experience.keyboard_name(value)
        self.symbols = False
        try:
            experience.save_preferences({'keyboard': self.keyboard_page})
        except OSError:
            self.message('Teclado alterado; não foi possível salvar a preferência')
        self.draw()
        if self.menu and self.panel.entry is not None:
            self.panel.activate_input(self.panel.entry, reveal=False)

    def window(self, w, h, x, y):
        win = tk.Toplevel(self.root, bg=BG)
        win.overrideredirect(True)
        win.geometry(f'{w}x{h}+{x}+{y}')
        win.attributes('-topmost', True)
        return win

    def message(self, value):
        self.toast = value
        self.toast_until = time.monotonic() + 4
        self.status(False)

    def resize_terminal(self):
        if not self.keys.target:
            self.keys.resolve()
        if self.keys.target:
            height = self.h - self.hh - (self.kh if self.visible else 0)
            subprocess.run(['xdotool', 'windowmove', str(self.keys.target), '0', str(self.hh),
                            'windowsize', str(self.keys.target), str(self.w), str(height)], capture_output=True)
        self.header.lift()
        if self.visible:
            self.keyboard.lift()
        self.write_geometry()

    def write_geometry(self):
        path = Path('/run/moto-ux.json')
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps({'top': self.hh, 'bottom': self.h - (self.kh if self.visible else 0),
                                    'menu': bool(self.menu), 'sleeping': self.sleeping}))
        temp.replace(path)

    def tmux(self, *args):
        return subprocess.run(['tmux', '-L', 'moto', *args], capture_output=True, text=True, timeout=1)

    def refresh_tmux(self):
        if self.sleeping:
            self.root.after(10000, self.refresh_tmux)
            return
        try:
            self.windows = self.tabs.list()
            result = self.tmux('display-message', '-p', '-t', 'moto', '#{pane_in_mode}')
            self.in_copy = result.stdout.strip() == '1'
            self.status(False)
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            pass
        self.root.after(5000 if self.menu else 3000, self.refresh_tmux)

    def vpn_worker(self):
        while True:
            try:
                self.device = panel_module.services.snapshot()
                vpn = self.device['vpn']
                self.vpn = vpn.get('connected', False)
                self.vpn_label = {'connected': 'ativa', 'warning': 'ativa · aviso',
                                  'login': 'autorizar', 'approval': 'aguarda aprovação',
                                  'paused': 'pausada', 'network': 'sem Wi-Fi',
                                  'degraded': 'instável', 'expired': 'renovar cadastro',
                                  'connecting': 'reconectando'}.get(vpn.get('kind'), 'indisponível')
                if self.device.get('ssh_auth'):
                    self.vpn_label += ' · SSH: autorizar'
            except (OSError, ValueError, subprocess.TimeoutExpired):
                self.vpn = False
                self.vpn_label = 'indisponível'
            pending = bool(self.device.get('ssh_auth')) or (self.menu and self.panel.page == 'vpn')
            self.refresh_event.wait(30 if self.sleeping else 5 if pending else 10)
            self.refresh_event.clear()

    def draw(self):
        if not self.visible:
            return
        c = self.canvas
        c.delete('all')
        self.boxes = []
        self.key_rects = {}
        for index, (value, label) in enumerate((('terminal', 'Term'), ('code', 'Código'), ('text', 'PT'))):
            left, right = 12+index*160, 164+index*160
            c.create_rectangle(left, 8, right, 80, fill=SELECTED if self.keyboard_page == value else PANEL, outline='')
            c.create_text((left+right)/2, 44, text=label, fill=ACCENT if self.keyboard_page == value else MUTED,
                          font=('DejaVu Sans', -24, 'bold'))
            self.boxes.append((left, 8, right, 80, 'keypage:'+value))
        hint = self.quick_voice.hint() or (' + '.join(sorted(self.mods)) + ' · próxima tecla' if self.mods else 'Mic · falar e inserir sem Enter')
        self.keyboard_hint = c.create_text(self.w-24, 44, anchor='e', text=self.fit_text(hint, self.info_font, self.w-520),
                                           fill=MUTED, font=('DejaVu Sans', -20))
        rows = experience.keyboard_rows(self.keyboard_page, self.symbols)
        rows += [[('ABC' if self.symbols else '#+=', 'symbols'), ('/', '/'), ('-', '-'),
                  ('espaço', ' '), ('×', 'voice-cancel') if self.quick_voice.state != 'idle' else ('.', '.'),
                  ('', 'voice'), ('Enter ↵', 'Return')]]
        gap, top = 9, 96
        rh = (self.kh - top - 12) / len(rows)
        for ri, row in enumerate(rows):
            weights = [3 if action == ' ' else 1.65 if action == 'Return' else 1 for _, action in row]
            unit = (self.w - gap * (len(row)+1)) / sum(weights)
            x = gap
            for (label, action), weight in zip(row, weights):
                y, width = top + ri * rh, unit * weight
                selected = action.startswith('mod:') and action[4:] in self.mods
                color = ACCENT if selected or action == 'Return' else KEY
                if action == 'voice':
                    color = {'recording': '#9e3344', 'sending': '#34516b', 'retry': '#805b20',
                             'result': '#805b20', 'canceling': '#34516b'}.get(self.quick_voice.state, SELECTED)
                textcolor = BG if color == ACCENT else FG
                rectangle = c.create_rectangle(x, y, x+width, y+rh-gap, fill=color, outline='', tags=('key',))
                self.key_rects[action] = (rectangle, color)
                if len(label) == 1 and label.isalpha() and 'Shift' in self.mods:
                    label = label.upper()
                if action == 'voice':
                    cx, cy = x+width/2, y+(rh-gap)/2
                    if self.quick_voice.state == 'recording':
                        c.create_rectangle(cx-14, cy-14, cx+14, cy+14, fill=FG, outline='')
                    elif self.quick_voice.state in ('sending', 'canceling'):
                        c.create_text(cx, cy, text='···', fill=FG, font=('DejaVu Sans', -32, 'bold'))
                    else:
                        c.create_oval(cx-10, cy-23, cx+10, cy-3, fill=FG, outline='')
                        c.create_rectangle(cx-10, cy-14, cx+10, cy+6, fill=FG, outline='')
                        c.create_oval(cx-10, cy-4, cx+10, cy+14, fill=FG, outline='')
                        c.create_arc(cx-18, cy-8, cx+18, cy+25, start=180, extent=180, style='arc', outline=FG, width=3)
                        c.create_line(cx, cy+25, cx, cy+32, fill=FG, width=3)
                        c.create_line(cx-10, cy+32, cx+10, cy+32, fill=FG, width=3)
                else:
                    c.create_text(x+width/2, y+(rh-gap)/2, text=label, fill=textcolor,
                                  font=('DejaVu Sans', -32 if len(label) < 4 else -27, 'bold'))
                self.boxes.append((x, y, x+width, y+rh-gap, action))
                x += width + gap

    def hit(self, x, y):
        # The visible gutters are not dead zones. Finger drift chooses the
        # nearest key, as on a phone, instead of silently discarding a tap.
        if y < 96:
            return next((b[4] for b in self.boxes if b[0] <= x <= b[2] and b[1] <= y <= b[3]), None)
        if not (0 <= x <= self.w and 96 <= y <= self.kh):
            return None
        return min((b for b in self.boxes if b[1] >= 96), key=lambda b: max(b[0]-x, 0, x-b[2])**2 + max(b[1]-y, 0, y-b[3])**2)[4]

    def press(self, event):
        if self.menu and self.panel.entry is not None:
            self.panel.activate_input(self.panel.entry, reveal=False)
        self.active = self.hit(event.x, event.y)
        self.repeated = False
        if self.active in self.key_rects:
            rectangle, _ = self.key_rects[self.active]
            self.canvas.itemconfigure(rectangle, outline=ACCENT, width=4, fill=PRESS)
            self.pressed_rect = rectangle
        if self.active in ('BackSpace', 'Left', 'Right', 'Up', 'Down'):
            self.repeat = self.root.after(450, self.repeat_key)

    def repeat_key(self):
        if self.active:
            self.emit(self.active)
            self.repeated = True
            self.repeat = self.root.after(75, self.repeat_key)

    def motion(self, event):
        next_key = self.hit(event.x, event.y)
        if next_key != self.active:
            self.cancel_repeat()
            self.unhighlight()
            self.active = next_key
            self.repeated = False
            if next_key in self.key_rects:
                rectangle, _ = self.key_rects[next_key]
                self.canvas.itemconfigure(rectangle, outline=ACCENT, width=4, fill=PRESS)
                if next_key in ('BackSpace', 'Left', 'Right', 'Up', 'Down'):
                    self.repeat = self.root.after(450, self.repeat_key)

    def unhighlight(self):
        if self.active in self.key_rects:
            rectangle, color = self.key_rects[self.active]
            self.canvas.itemconfigure(rectangle, outline='', width=0, fill=color)
        self.pressed_rect = None

    def cancel_repeat(self):
        if self.repeat:
            self.root.after_cancel(self.repeat)
            self.repeat = None

    def release(self, event):
        self.cancel_repeat()
        self.unhighlight()
        action = self.hit(event.x, event.y)
        if action and action == self.active and not self.repeated:
            self.emit(action)
        self.active = None

    def emit(self, action):
        if action.startswith('keypage:'):
            self.choose_keyboard(action.partition(':')[2])
            return
        if action == 'voice':
            self.quick_voice.toggle()
            return
        if action == 'voice-cancel':
            self.quick_voice.cancel()
            return
        if self.menu and action == 'Escape':
            self.close_menu()
            return
        if action.startswith('mod:'):
            mod = action[4:]
            self.mods.symmetric_difference_update({mod})
            self.draw()
        elif action == 'symbols':
            self.symbols = not self.symbols
            self.draw()
        else:
            if self.menu:
                self.panel.key(action, self.mods)
                if self.mods:
                    self.mods.clear()
                    self.draw()
                return
            if len(action) == 1 and not action.isascii() and not ({'Ctrl', 'Alt'} & self.mods):
                try:
                    context = self.terminal_context()
                    self.panel.voice_backend.insert_text(context[1], action.upper() if 'Shift' in self.mods else action)
                except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired):
                    self.message('Não foi possível inserir o caractere nesta aba')
                self.mods.clear()
                self.draw()
                return
            if self.in_copy:
                self.tmux('send-keys', '-t', 'moto', '-X', 'cancel')
                self.in_copy = False
            mods = [{'Ctrl': 'Control_L', 'Alt': 'Alt_L', 'Shift': 'Shift_L'}[m] for m in self.mods]
            self.keys.send(action, mods)
            if self.mods:
                self.mods.clear()
                self.draw()

    def header_hit(self, x, y):
        return next((box[4] for box in self.header_boxes
                     if box[0] <= x < box[2] and box[1] <= y < box[3]), None)

    def header_press(self, event):
        self.header_pressed = self.header_hit(event.x, event.y)

    def header_tap(self, event):
        action = self.header_hit(event.x, event.y)
        if action is None or action != self.header_pressed:
            self.header_pressed = None
            return
        self.header_pressed = None
        if action[0] == 'panel':
            self.power_menu()
        elif action[0] == 'keyboard':
            if self.menu:
                self.close_menu()
            self.toggle_keyboard()
        elif action[0] == 'new':
            self.new_terminal()
        elif action[0] == 'select':
            self.select_terminal(action[1])
        elif action[0] == 'close':
            self.panel.close_terminal(action[1])

    def refresh_tmux_once(self):
        self.windows = self.tabs.list()
        self.status(False)

    def new_terminal(self, ssh=False, profile=None, manual=False):
        try:
            if ssh:
                if not profile:
                    raise ValueError('Escolha um destino salvo no menu SSH.')
                host = self.panel.host_store.find(profile)
                self.tabs.new(ssh=True, profile=host, manual=manual)
            else:
                self.tabs.new()
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            self.close_menu()
            self.message(str(exc))
            return
        self.close_menu()
        self.refresh_tmux_once()
        self.message('SSH aberto em nova aba' if ssh else 'Nova aba local')

    def select_terminal(self, ident):
        try:
            selected = self.tabs.select(ident)
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            self.message('Não foi possível trocar de aba')
            return
        self.close_menu()
        self.refresh_tmux_once()
        if not selected:
            self.message('Essa aba já foi fechada')

    def close_terminal(self, ident):
        try:
            closed = self.tabs.close(ident)
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            self.message(str(exc))
            return
        self.close_menu()
        self.refresh_tmux_once()
        self.message('Aba fechada' if closed else 'Essa aba já foi fechada')

    def toggle_keyboard(self):
        if self.visible and self.quick_voice.active:
            self.quick_voice.cancel()
        self.visible = not self.visible
        if self.visible:
            self.draw()
        self.keyboard.deiconify() if self.visible else self.keyboard.withdraw()
        self.resize_terminal()

    def wake(self):
        if self.sleeping:
            LIGHT.write_text(str(self.light))
            self.sleeping = False
            self.header_signature = None
            self.refresh_event.set()
            self.write_geometry()
            try:
                self.sock.sendto(b'recalibrate', '/run/moto-input.sock')
            except (FileNotFoundError, ConnectionRefusedError):
                pass
            try:
                self.refresh_tmux_once()
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                pass
            self.status(False)

    def action(self, action):
        if action == 'screen-toggle':
            if self.sleeping:
                self.wake()
            else:
                self.panel.hermes.close()
                if self.quick_voice.active:
                    self.quick_voice.cancel()
                if self.panel.voice.recorder.recording:
                    self.close_menu()
                self.light = int(LIGHT.read_text()) or self.light
                LIGHT.write_text('0')
                self.sleeping = True
                self.refresh_event.set()
                self.write_geometry()
        elif action == 'power-menu':
            self.wake()
            self.power_menu()
        elif action == 'home':
            was_sleeping = self.sleeping
            self.wake()
            if not was_sleeping:
                self.toggle_keyboard()
        elif action == 'front-hold':
            self.wake()
            self.power_menu()
        elif action == 'copy-selection':
            self.copy_selection()
        elif action == 'paste-buffer':
            self.paste_buffer()
        elif action in ('scroll-up', 'scroll-down'):
            self.tmux('copy-mode', '-t', 'moto', ';', 'send-keys', '-t', 'moto', '-X', action)
            self.in_copy = True
            self.message('Histórico · digite para voltar ao terminal')
        elif action in ('font-up', 'font-down'):
            self.wake()
            self.font_size = max(10, min(30, self.font_size + (1 if action == 'font-up' else -1)))
            # xterm's standard larger/smaller VT font actions, via Shift+keypad.
            self.keys.send('KP_Add' if action == 'font-up' else 'KP_Subtract', ['Shift_L'])
            try:
                experience.save_preferences({'font_size': self.font_size})
            except OSError:
                pass
            self.message('Fonte maior' if action == 'font-up' else 'Fonte menor')
        elif action in ('volume-up', 'volume-down'):
            def change():
                try:
                    value = panel_module.services.volume(1 if action == 'volume-up' else -1)
                except (OSError, RuntimeError, subprocess.TimeoutExpired):
                    value = 'Não foi possível alterar o volume'
                self.events.put(lambda: self.message(value))
            threading.Thread(target=change, daemon=True).start()

    def power_menu(self):
        if self.menu:
            self.close_menu()
        else:
            self.panel.home()

    def brightness(self, value, persist=True):
        self.light = value
        if not self.sleeping:
            LIGHT.write_text(str(value))
        if persist:
            experience.save_preferences({'brightness': self.light}, self.pref_path)

    def copy_selection(self):
        mode = self.tmux('display-message', '-p', '-t', 'moto', '#{pane_in_mode}').stdout.strip()
        if mode == '1':
            self.tmux('send-keys', '-t', 'moto', '-X', 'copy-selection-and-cancel')
        # tmux also copies automatically when a drag-selection is released.
        result = self.tmux('show-buffer')
        self.close_menu()
        self.message('Seleção copiada' if result.returncode == 0 and result.stdout else 'Segure e arraste no terminal para selecionar')
        self.in_copy = False

    def paste_buffer(self):
        self.tmux('send-keys', '-t', 'moto', '-X', 'cancel')
        result = self.tmux('paste-buffer', '-p', '-t', 'moto')
        self.close_menu()
        self.message('Colado' if result.returncode == 0 else 'Nada copiado ainda')
        self.in_copy = False

    def close_menu(self):
        self.panel.appearance.leave('terminal')
        self.panel.hermes.close()
        if self.menu:
            self.panel.voice.leave()
            self.menu.destroy()
            self.menu = None
            self.panel.entry = None
            self.panel.page = ''
            self.header.deiconify()
            self.visible = self.panel.restore_keyboard
            if self.visible:
                self.draw()
            self.keyboard.deiconify() if self.visible else self.keyboard.withdraw()
            self.resize_terminal()
            self.write_geometry()
            self.status(False)

    @staticmethod
    def fit_text(text, font, width):
        if font.measure(text) <= width:
            return text
        while text and font.measure(text + '…') > width:
            text = text[:-1]
        return text + '…'

    def status(self, reschedule=True):
        if reschedule:
            self.root.after(5000, self.status)
        if self.sleeping or self.menu:
            return
        try:
            battery = Path('/sys/class/power_supply/battery/capacity').read_text().strip() + '%'
            wifi = Path('/sys/class/net/wlan0/operstate').read_text().strip() == 'up'
            vpn = self.vpn
        except OSError:
            battery, wifi, vpn = '?', False, False
        c = self.top
        text = self.toast if time.monotonic() < self.toast_until else f'Wi-Fi {"conectado" if wifi else "offline"}   ·   VPN {self.vpn_label}   ·   {battery}'
        signature = (text, wifi, self.visible, self.theme_name, tuple((r['id'], r['index'], r['name'], r['active']) for r in self.windows))
        if signature == self.header_signature:
            return
        self.header_signature = signature
        c.delete('all')
        c.create_text(24, 31, anchor='w', text='moto / linux', fill=FG, font=('DejaVu Sans', -30, 'bold'))
        c.create_text(24, 76, anchor='w', text=self.fit_text(text, self.info_font, self.w-445),
                      fill=ACCENT if wifi else MUTED, font=self.info_font)
        self.header_boxes = []
        for left, right, label, action in ((self.w-405, self.w-210, 'Teclado', 'keyboard'),
                                          (self.w-200, self.w-8, 'Voltar' if self.menu else 'Painel', 'panel')):
            c.create_rectangle(left, 10, right, 88, fill=KEY, outline=BORDER)
            c.create_text((left+right)/2, 49, text=label, fill=FG, font=('DejaVu Sans', -26))
            self.header_boxes.append((left, 10, right, 88, (action,)))
        visible = self.windows[:4]
        if len(self.windows) > 4 and not any(row['active'] for row in visible):
            visible[-1] = next((row for row in self.windows if row['active']), visible[-1])
        width = (self.w - 148) / max(1, len(visible))
        for n, row in enumerate(visible):
            left, right = n*width+5, (n+1)*width-5
            close_left = right-80
            c.create_rectangle(left, 105, right, 195, fill=KEY if row['active'] else PANEL,
                               outline=ACCENT if row['active'] else BORDER, width=3 if row['active'] else 1)
            label = self.fit_text(f"{row['index']} · {row['name']}", self.tab_font, close_left-left-22)
            c.create_text(left+12, 150, anchor='w', text=label, fill=FG if row['active'] else MUTED,
                          font=self.tab_font)
            c.create_rectangle(close_left, 112, right-5, 188, fill=DANGER, outline='')
            c.create_text((close_left+right-5)/2, 150, text='×', fill=ERROR, font=('DejaVu Sans', -36))
            self.header_boxes += [(left, 105, close_left, 195, ('select', row['id'])),
                                  (close_left, 105, right, 195, ('close', row['id']))]
        c.create_rectangle(self.w-140, 105, self.w-5, 195, fill=KEY, outline=BORDER)
        c.create_text(self.w-72, 150, text='+ Nova', fill=ACCENT if len(self.windows)<4 else MUTED,
                      font=('DejaVu Sans', -25))
        self.header_boxes.append((self.w-140, 105, self.w-5, 195, ('new',)))
    def read_events(self, *_):
        for _ in range(8):
            try:
                self.events.reader.recv(4096)
            except BlockingIOError:
                break
        for _ in range(32):
            try:
                self.events.get_nowait()()
            except queue.Empty:
                break
        if not self.events.empty():
            self.root.after_idle(self.read_events)

    def read_socket(self, *_):
        try:
            for _ in range(32):
                command = self.sock.recv(256).decode(errors='ignore')
                try:
                    self.action(command)
                except (OSError, RuntimeError, subprocess.TimeoutExpired):
                    self.message('Não foi possível concluir a ação. Tente novamente.')
        except BlockingIOError:
            pass

    def poll(self):
        if not self.sleeping:
            self.panel.update()
            self.quick_voice.tick()
        recording = self.quick_voice.state == 'recording' or self.panel.voice.recorder.recording
        delay = 2000 if self.sleeping else 100 if recording else 500 if self.menu else 1000
        self.root.after(delay, self.poll)

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    shell = Shell()
    signal.signal(signal.SIGTERM, lambda *_: shell.root.quit())
    signal.signal(signal.SIGINT, lambda *_: shell.root.quit())
    try:
        shell.run()
    finally:
        shell.root.deletefilehandler(shell.sock)
        shell.root.deletefilehandler(shell.events.reader)
        shell.events.close()
        shell.quick_voice.close()
        shell.panel.voice.leave()
        shell.panel.hermes.close()
