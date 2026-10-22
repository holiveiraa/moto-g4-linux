#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Real Tk, XTest and PTY review on :9 with private fixtures only."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import tkinter as tk
import tkinter.font as tkfont


def main():
    os.environ['DISPLAY'] = ':9'
    folder = Path(os.environ.get('MOTO_UI_REVIEW_DIR', '/usr/sbin'))
    server = 'moto-experience-review-'+str(os.getpid())
    real_run = subprocess.run
    shell = terminal = None
    def command(*args):
        return real_run(['tmux', '-L', server, *args], capture_output=True, text=True, timeout=3)
    def remap(args, *more, **kwargs):
        args = list(args)
        if args[:3] == ['tmux', '-L', 'moto']:
            args[2] = server
        return real_run(args, *more, **kwargs)
    with tempfile.TemporaryDirectory(prefix=server, dir='/run') as temp:
        private = Path(temp)
        os.environ['MOTO_UX_CONFIG'] = str(private/'ux.json')
        sink = private/'received'
        receiver = private/'receive.sh'
        receiver.write_text('#!/bin/sh\nstty -echo -icanon\ncat > '+str(sink)+'\n')
        receiver.chmod(0o700)
        assert command('-f', '/dev/null', 'new-session', '-d', '-s', 'moto', '-n', 'Fixture', str(receiver)).returncode == 0
        loader = importlib.machinery.SourceFileLoader('experience_review', str(folder/'moto-shell'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        ui = importlib.util.module_from_spec(spec)
        loader.exec_module(ui)
        layout_spec = importlib.util.spec_from_file_location('experience_layout', folder/'review-layout.py')
        layout = importlib.util.module_from_spec(layout_spec)
        layout_spec.loader.exec_module(layout)
        ui.SOCKET = str(private/'control.sock')
        light = private/'brightness'; light.write_text('100')
        ui.LIGHT = light
        ui.Shell.write_geometry = lambda self: None
        ui.Shell.vpn_worker = lambda self: None
        ui.Shell.tmux = lambda self, *args: command(*args)
        # A private xterm exercises output-only live color changes too.
        argv = ui.experience.terminal_argv()
        argv = argv[:argv.index('-e')]+['-e', 'tmux', '-L', server, 'attach', '-t', 'moto']
        terminal = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(.4)
        try:
            subprocess.run = remap
            shell = ui.Shell()
            p = shell.panel
            errors, sent = [], []
            shell.root.report_callback_exception = lambda kind, error, trace: errors.append(error)
            shell.keys.send = lambda *args: sent.append(args)
            p.host_store = ui.panel_module.hosts.HostStore(private/'hosts.json')
            p.voice_backend.CONFIG = private/'groq.json'
            shell.device = {'battery': '78', 'charging': 'Discharging', 'wifi': {'ssid': 'Rede de teste', 'wpa_state': 'COMPLETED'},
                            'vpn': {'title': 'Conectada'}, 'ssh_auth': {}, 'ram_free': 1500, 'ram_total': 1843}
            def pump(seconds=.08):
                end = time.monotonic()+seconds
                while time.monotonic() < end:
                    shell.root.update()
                    if errors:
                        raise errors.pop(0)
                    time.sleep(.005)
            def capture(name):
                pump()
                if shell.menu:
                    layout.reachable(p)
                    for button in p.footer.winfo_children():
                        if isinstance(button, tk.Button):
                            font = tkfont.Font(font=button.cget('font'))
                            assert font.measure(button.cget('text')) < button.winfo_width()-p.u(8), ('footer text clipped', button.cget('text'))
                real_run(['xwd', '-root', '-silent', '-out', '/tmp/moto-experience-'+name+'.xwd'], check=True)
            def all_widgets(parent):
                for child in parent.winfo_children():
                    yield child
                    yield from all_widgets(child)
            def labels():
                return [w.cget('text') for w in all_widgets(p.body) if isinstance(w, (tk.Label, tk.Button))]
            pump()
            shell.refresh_tmux_once()
            before = sink.read_bytes() if sink.exists() else b''
            p.appearance.show(); p.appearance.preview('paper'); pump()
            assert ui.BG == '#F4F1E9' and p.theme.BG == ui.BG
            assert ui.panel_module.voice_module.theme.BG == ui.BG
            assert p.body.cget('bg') == ui.BG
            assert shell.theme_terminal('paper'), 'No verified xterm client tty received the theme'
            capture('paper')
            p.back(); pump()
            assert shell.theme_name == 'moto'
            assert sink.read_bytes() == before, 'Theme wrote into the PTY input'
            p.appearance.show(); p.appearance.preview('midnight'); p.appearance.commit_theme(); pump()
            shell.brightness(110)
            prefs = ui.experience.preferences()
            assert prefs['theme'] == 'midnight' and prefs['brightness'] == 110
            assert (private/'ux.json').stat().st_mode & 0o777 == 0o600
            print('PASS: live theme preview/back/commit, no theme bytes in stdin, brightness preserves private preferences')
            p.home(); pump()
            assert not any(word in text for text in labels() for word in ('Ações', 'Rascunho', 'Desenvolvimento'))
            appearance_button = next(w for w in all_widgets(p.body) if isinstance(w, tk.Button) and w.cget('text').startswith('Aparência'))
            appearance_button.invoke(); pump(); assert p.page == 'appearance'
            p.back(); pump(); assert p.page == 'home'
            p.system(); shell.emit('x'); assert not sent and sink.read_bytes() == before
            print('PASS: appearance is directly on the panel; no redundant actions/draft menu; menu input cannot leak')
            p.ssh.form(); pump()
            field = p.inputs[-1]; p.entry = field
            shell.choose_keyboard('text'); shell.emit('ã'); shell.emit('ç'); pump()
            assert field.get() == 'ãç' and field.cget('show') and field.focus_get() is field
            assert not sent and sink.read_bytes() == before
            shell.close_menu(); shell.emit('é'); pump()
            assert sink.read_bytes() == 'é'.encode('utf-8')
            assert not command('list-buffers').stdout.strip()
            p.home(); capture('home')
            print('PASS: Portuguese keys retain masked-field focus and insert literal UTF-8 in terminal')
            shell.close_menu(); shell.choose_keyboard('code'); capture('keyboard-code')
            shell.choose_keyboard('text'); capture('keyboard-pt')
            shell.status(False); cached = tuple(shell.top.find_all())
            shell.status(False); assert tuple(shell.top.find_all()) == cached
            # Socket and queue readiness wake immediately even with the screen blanked.
            shell.action('screen-toggle')
            ran = []
            threading.Thread(target=lambda: shell.events.put(lambda: ran.append(time.monotonic())), daemon=True).start()
            pump(.12)
            assert ran and light.read_text() == '0'
            client = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            client.sendto(b'\xffmalformed', ui.SOCKET)
            client.sendto(b'screen-toggle', ui.SOCKET)
            started = time.monotonic(); pump(.12)
            client.close()
            assert not shell.sleeping and time.monotonic()-started < .4
            print('PASS: cached header, screen-off worker completion, malformed datagram and immediate socket wake')
            geometry, recalibrations = [], []
            old_refresh, old_socket, old_geometry = shell.refresh_tmux_once, shell.sock, shell.write_geometry
            class FixtureSocket:
                def sendto(self, *args): recalibrations.append(args)
            shell.sock = FixtureSocket()
            shell.write_geometry = lambda: geometry.append(shell.sleeping)
            def failed_refresh(): raise subprocess.TimeoutExpired('fixture-tmux', 1)
            shell.refresh_tmux_once = failed_refresh
            shell.sleeping = True
            shell.wake()
            shell.refresh_tmux_once, shell.sock, shell.write_geometry = old_refresh, old_socket, old_geometry
            assert geometry == [False] and recalibrations and light.read_text() == '110'
            scheduled = []
            old_after, old_update = shell.root.after, p.update
            shell.root.after = lambda delay, callback: scheduled.append(delay)
            p.update = lambda: None
            shell.quick_voice.state = 'retry'; shell.poll()
            assert scheduled[-1] >= 500
            shell.sleeping = True; p.voice.busy = True; shell.poll()
            assert scheduled[-1] >= 1000
            shell.root.after, p.update = old_after, old_update
            shell.sleeping = False; p.voice.busy = False; shell.quick_voice.state = 'idle'
            print('PASS: tmux timeout cannot strand screen wake; retry and blanked transcription do not retain a fast polling loop')
        finally:
            subprocess.run = real_run
            if shell:
                shell.close_menu()
                shell.quick_voice.close()
                shell.root.deletefilehandler(shell.sock)
                shell.root.deletefilehandler(shell.events.reader)
                shell.events.close(); shell.sock.close(); shell.root.destroy()
            if terminal:
                terminal.terminate(); terminal.wait(timeout=3)
            command('kill-server')


if __name__ == '__main__':
    main()
