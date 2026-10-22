#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Real Tk button + private tmux PTY, synthetic speech, no API or user sessions."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import time
from types import SimpleNamespace


def main():
    os.environ['DISPLAY'] = ':9'
    name = 'moto-quick-review-' + str(os.getpid())
    real_run = subprocess.run
    shell = None

    def command(*args):
        return real_run(['tmux', '-L', name, *args], capture_output=True, text=True, timeout=3)

    def remap(args, *more, **kwargs):
        args = list(args)
        if args[:3] == ['tmux', '-L', 'moto']:
            args[2] = name
        return real_run(args, *more, **kwargs)

    try:
        with tempfile.TemporaryDirectory(prefix=name, dir='/run') as temp:
            folder = Path(temp)
            sink = folder / 'received'
            assert command('-f', '/dev/null', 'new-session', '-d', '-s', 'moto', '-n', 'example-server',
                           '/bin/sh', '-c', 'stty -echo -icanon; cat > ' + str(sink)).returncode == 0
            loader = importlib.machinery.SourceFileLoader('quick_review', str(Path(os.environ.get('MOTO_UI_REVIEW_DIR', '/usr/sbin')) / 'moto-shell'))
            spec = importlib.util.spec_from_loader(loader.name, loader)
            ui = importlib.util.module_from_spec(spec)
            loader.exec_module(ui)
            ui.SOCKET = '/run/' + name + '.sock'
            ui.Shell.write_geometry = lambda self: None
            ui.Shell.vpn_worker = lambda self: None
            ui.Shell.refresh_tmux = lambda self: None
            ui.Shell.tmux = lambda self, *args: command(*args)
            shell = ui.Shell()
            backend = ui.panel_module.voice_module.voice
            backend.settings = lambda: {'api_key': 'fixture-only'}
            backend.inspect_wave = lambda p: {'seconds': 1}
            payload = 'Olá Codex.\r\nTexto sem Enter!\x1b\x00'
            backend.transcribe = lambda p: payload
            class FixtureRecorder:
                def start(self):
                    self.recording, self.started = True, time.monotonic()
                def stop(self):
                    self.recording = False
                    return folder / 'fixture.wav'
                def discard(self):
                    self.recording = False
            backend.Recorder = FixtureRecorder
            subprocess.run = remap
            time.sleep(.1)

            def tap(action):
                box = next(b for b in shell.boxes if b[4] == action)
                event = SimpleNamespace(x=(box[0]+box[2])/2, y=(box[1]+box[3])/2)
                shell.press(event)
                shell.release(event)
                shell.root.update()

            shell.root.update()
            assert any(b[4] == 'voice' for b in shell.boxes)
            real_run(['xwd', '-root', '-silent', '-out', '/tmp/moto-quick-idle.xwd'], check=True)
            tap('voice')
            assert shell.quick_voice.state == 'recording'
            assert any(b[4] == 'voice-cancel' for b in shell.boxes)
            real_run(['xwd', '-root', '-silent', '-out', '/tmp/moto-quick-recording.xwd'], check=True)
            tap('voice')
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and (shell.quick_voice.state != 'idle' or not sink.exists() or not sink.stat().st_size):
                shell.root.update()
                time.sleep(.01)
            assert shell.quick_voice.state == 'idle'
            assert sink.read_bytes() == backend.safe_text(payload).encode('utf-8'), sink.read_bytes()
            assert not command('list-buffers').stdout.strip()
            print('PASS: actual microphone key taps, recording/cancel visuals, UTF-8 literal PTY paste; no Enter/CR/LF/ESC')
            tap('voice')
            tap('voice-cancel')
            deadline = time.monotonic() + 2
            while shell.quick_voice.state != 'idle' and time.monotonic() < deadline:
                shell.root.update()
                time.sleep(.01)
            assert shell.quick_voice.state == 'idle'
            assert sink.read_bytes() == backend.safe_text(payload).encode('utf-8')
            print('PASS: cancel returns idle without inserting more text')
    finally:
        subprocess.run = real_run
        if shell:
            shell.quick_voice.close()
            shell.sock.close()
            shell.root.destroy()
            Path(ui.SOCKET).unlink(missing_ok=True)
        real_run(['tmux', '-L', name, 'kill-server'], capture_output=True)


if __name__ == '__main__':
    main()
