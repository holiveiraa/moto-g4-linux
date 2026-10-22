#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Isolated real Tk/tmux checks; fake credential and audio, no external API."""
import array
import importlib.machinery
import importlib.util
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time
import tkinter as tk
import wave


def main():
    os.environ['DISPLAY'] = ':9'
    name = 'moto-voice-review-' + str(os.getpid())
    loader = importlib.machinery.SourceFileLoader('voice_ui_test', str(Path(os.environ.get('MOTO_UI_REVIEW_DIR', '/usr/sbin')) / 'moto-shell'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    ui = importlib.util.module_from_spec(spec)
    loader.exec_module(ui)
    ui.SOCKET = '/run/' + name + '.sock'
    ui.Shell.write_geometry = lambda self: None
    ui.Shell.vpn_worker = lambda self: None
    ui.Shell.refresh_tmux = lambda self: None
    shell = None
    real_run = subprocess.run

    def run(*args):
        return real_run(['tmux', '-L', name, *args], capture_output=True, text=True, timeout=3)

    def widgets(parent):
        for child in parent.winfo_children():
            yield child
            yield from widgets(child)

    try:
        with tempfile.TemporaryDirectory(prefix='moto-voice-review-', dir='/run') as temp:
            folder = Path(temp)
            assert run('-f', '/dev/null', 'new-session', '-d', '-s', 'moto', '-n', 'test',
                       '/bin/sh', '-c', 'stty -echo -icanon; cat > ' + str(folder/'received')).returncode == 0
            shell = ui.Shell()
            shell.keys.send = lambda *args: (_ for _ in ()).throw(AssertionError('Form text leaked to terminal'))
            shell.device = ui.panel_module.services.snapshot()
            shell.device['ssh_auth'] = {}
            p = shell.panel
            v = p.voice
            backend = ui.panel_module.voice_module.voice
            backend.CONFIG = folder/'config/groq.json'
            backend.capture_device = lambda: ''

            def visible(name):
                shell.root.update()
                import importlib.util
                layout_spec = importlib.util.spec_from_file_location('layout_review', Path(__file__).with_name('review-layout.py'))
                layout = importlib.util.module_from_spec(layout_spec)
                layout_spec.loader.exec_module(layout)
                layout.reachable(p)
                real_run(['xwd', '-root', '-silent', '-out', '/tmp/moto-voice-'+name+'.xwd'], check=True)

            p.home()
            visible('home')
            v.home()
            visible('unavailable')
            v.configure()
            visible('key')
            assert p.entry.cget('show')
            key = 'gsk_' + 'testOnly'*6
            for char in key:
                # Exercise the same one-shot Shift path as the touch keyboard.
                shell.emit('mod:Shift') if char.isupper() else None
                shell.emit(char.lower() if char.isupper() else char)
            assert p.entry.get() == key
            shell.emit('Return')
            assert backend.settings()['api_key'] == key
            assert not p.entry.get(), 'Saved credential must not remain in the Entry'
            visible('key-saved')
            print('PASS: masked key form, real keyboard and atomic private save; no terminal leakage')

            v.target = [run('display-message', '-p', '#{pane_id}').stdout.strip(), 'test']
            v.transcript = 'Olá, ação no Example server.'
            v.review()
            visible('review')
            shell.emit('mod:Ctrl')
            shell.emit('a')
            shell.emit('x')
            assert p.entry.get('1.0', 'end-1c') == 'x'
            shell.emit('BackSpace')
            for char in 'teste':
                shell.emit(char)
            assert p.entry.get('1.0', 'end-1c') == 'teste'
            print('PASS: editable review, selection, erase and insertion through touch keyboard')

            def private_tmux(args, *more, **kwargs):
                args = list(args)
                if args[:3] == ['tmux', '-L', 'moto']:
                    args[2] = name
                return real_run(args, *more, **kwargs)
            backend.subprocess.run = private_tmux
            try:
                payload = 'Olá, ação!\r\nsegunda linha\x1b\x00'
                backend.insert_text(v.target[0], payload)
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline and (not (folder/'received').exists() or not (folder/'received').stat().st_size):
                    time.sleep(.05)
                assert (folder/'received').read_bytes() == backend.safe_text(payload).encode('utf-8')
                assert run('list-buffers').stdout.strip() == ''
                print('PASS: real tmux paste preserves UTF-8; no CR/LF/ESC or automatic Enter; temporary buffer removed')
            finally:
                backend.subprocess.run = real_run

            path = folder/'fixture.wav'
            with wave.open(str(path), 'wb') as stream:
                stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
                stream.writeframes(array.array('h', (int(1000*math.sin(i*.1)) for i in range(16000))).tobytes())
            class FixtureRecorder:
                recording = False
                path = None
                meter = .4
                def start(self):
                    self.recording = True
                    self.started = time.monotonic()
                    self.path = path
                def stop(self):
                    self.recording = False
                    return self.path
                def discard(self):
                    self.recording = False
            v.recorder = FixtureRecorder()
            backend.capture_device = lambda: 'fixture'
            backend.pane_target = lambda: v.target
            v.start()
            visible('record')
            v.stop()
            deadline = time.monotonic() + 3
            while v.stopping and time.monotonic() < deadline:
                shell.root.update()
                time.sleep(.02)
            assert not v.stopping and p.page == 'voice-ready'
            visible('ready')
            p.home()
            assert not v.recorder.recording
            print('PASS: recording/ready layout fits; leaving stops capture (synthetic fixture, not hardware validation)')
    finally:
        if shell:
            shell.close_menu()
            shell.sock.close()
            shell.root.destroy()
            Path(ui.SOCKET).unlink(missing_ok=True)
        real_run(['tmux', '-L', name, 'kill-server'], capture_output=True)


if __name__ == '__main__':
    main()
