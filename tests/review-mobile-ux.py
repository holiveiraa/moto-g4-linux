#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""On-device Xvfb integration: xterm PTY bytes + taps on the actual mobile UI.

Runs exclusively on DISPLAY :9, never sends keystrokes to the user's :0 session.
Needs test-only xvfb; packages used by the product are unchanged by this script.
"""
import importlib.machinery
import importlib.util
import os
import statistics
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def run():
    os.environ['DISPLAY'] = ':9'
    loader = importlib.machinery.SourceFileLoader('moto_shell', '/usr/sbin/moto-shell')
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix='moto-ux-check-') as directory:
        folder = Path(directory)
        capture = folder / 'capture.py'
        received = folder / 'received'
        ready = folder / 'ready'
        capture.write_text('import os,tty\nfrom pathlib import Path\n'
                           'tty.setraw(0)\n'
                           f'Path({str(ready)!r}).touch()\n'
                           f'with open({str(received)!r}, "wb", buffering=0) as out:\n'
                           ' while True:\n  out.write(os.read(0,4096))\n')
        term = subprocess.Popen(['xterm', '-title', 'Moto isolated UX check',
                                 '-xrm', 'XTerm*metaSendsEscape: true', '-xrm', 'XTerm*altSendsEscape: true',
                                 '-xrm', 'XTerm*backarrowKey: false', '-e', sys.executable, str(capture)])
        ui = None
        try:
            for _ in range(100):
                if ready.exists():
                    break
                time.sleep(.05)
            assert ready.exists(), 'Test terminal did not start'
            keys = module.Keys()
            # All printable ASCII, Ctrl-C/Ctrl-D, Alt, Tab, Esc, navigation.
            expected = ''.join(chr(n) for n in range(32, 127)).encode()
            for char in expected.decode():
                keys.send(char)
                time.sleep(.005)
            sequence = [('c', ['Control_L']), ('d', ['Control_L']), ('x', ['Alt_L']),
                        ('Tab', []), ('Escape', []), ('Up', []), ('Down', []),
                        ('Left', []), ('Right', []), ('BackSpace', [])]
            expected += b'\x03\x04\x1bx\t\x1b\x1b[A\x1b[B\x1b[D\x1b[C\x7f'
            for key, modifiers in sequence:
                keys.send(key, modifiers)
                time.sleep(.02)
            time.sleep(.2)
            actual = received.read_bytes()
            assert actual == expected, f'PTY key mismatch: {actual!r} != {expected!r}'
            print('PASS: all printable ASCII, Ctrl-C/D, Alt, Tab, Esc, four arrows, erase')
            # Separate shell UI process so its Tk loop can handle real pointer events.
            # Use a different socket: leave the live hardware buttons on :0 untouched.
            launcher = folder / 'ui.py'
            launcher.write_text(f'import sys\nsys.path.insert(0,{str(folder)!r})\n'
                                f'source=open("/usr/sbin/moto-shell").read().replace("/run/moto-ux.sock", {str(folder / "ui.sock")!r}).replace("/run/moto-ux.json", {str(folder / "ui.json")!r}).replace("/run/moto-input.sock", {str(folder / "input.sock")!r})\n'
                                'source=source.replace("[\'tmux\', \'-L\', \'moto\'", "[\'tmux\', \'-L\', \'moto-review\'")\n'
                                '__file__="/usr/sbin/moto-shell"\nexec(source)\n')
            ui = subprocess.Popen([sys.executable, str(launcher)])
            time.sleep(1)
            def tap(x, y):
                subprocess.run(['xdotool', 'mousemove', str(x), str(y), 'click', '1'], check=True)
                time.sleep(.14)
            # q, Shift, a, Ctrl, c, symbols, !, Return.
            for x, y in [(55,1476), (64,1720), (64,1598), (340,1232), (422,1720),
                         (65,1842), (55,1354), (974,1842)]:
                tap(x, y)
            actual = received.read_bytes()[len(expected):]
            assert actual == b'qA\x03!\r', f'UI tap mismatch: {actual!r}'
            print('PASS: actual UI pointer taps -> xterm bytes, one-shot Shift/Ctrl, symbol layer, Enter')
            tap(65, 1842)  # back to ABC
            pointer = module.C.CDLL('libXtst.so.6')
            pointer.XTestFakeMotionEvent.argtypes = [module.C.c_void_p, module.C.c_int, module.C.c_int, module.C.c_int, module.C.c_ulong]
            pointer.XTestFakeButtonEvent.argtypes = [module.C.c_void_p, module.C.c_uint, module.C.c_int, module.C.c_ulong]
            delays = []
            start_len = len(received.read_bytes())
            for n in range(30):
                start = time.perf_counter()
                pointer.XTestFakeMotionEvent(keys.d, -1, 64, 1598, 0)
                pointer.XTestFakeButtonEvent(keys.d, 1, 1, 0)
                pointer.XTestFakeButtonEvent(keys.d, 1, 0, 0)
                keys.x.XFlush(keys.d)
                while received.stat().st_size < start_len + n + 1:
                    assert time.perf_counter() - start < 1, 'Keyboard stalled'
                    time.sleep(.001)
                delays.append((time.perf_counter() - start) * 1000)
            assert received.read_bytes()[start_len:] == b'a' * 30
            print(f'UI software path, 30 taps, no loss: median {statistics.median(delays):.1f} ms; p95 {sorted(delays)[28]:.1f} ms (excludes hardware scan/display)')
        finally:
            if ui:
                ui.terminate()
                ui.wait(timeout=3)
            term.terminate()
            term.wait(timeout=3)


if __name__ == '__main__':
    run()
