#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Real Tk/XTest focus, caret blinking and protected input; private display :9."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import time
import tkinter as tk


def main():
    os.environ['DISPLAY'] = ':9'
    folder = Path(os.environ.get('MOTO_UI_REVIEW_DIR', '/usr/sbin'))
    loader = importlib.machinery.SourceFileLoader('focus_review', str(folder/'moto-shell'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    ui = importlib.util.module_from_spec(spec); loader.exec_module(ui)
    ui.SOCKET = '/run/moto-input-focus-review.sock'
    ui.Shell.write_geometry = lambda self: None
    ui.Shell.vpn_worker = lambda self: None
    ui.Shell.refresh_tmux = lambda self: None
    shell = ui.Shell()
    errors = []
    shell.root.report_callback_exception = lambda kind,error,trace: errors.append(error)
    shell.device = {'ssh_auth': {}}
    shell.keys.send = lambda *args: (_ for _ in ()).throw(AssertionError('Input leaked to a terminal'))
    p = shell.panel
    def pump(seconds=.08):
        deadline = time.monotonic()+seconds
        while time.monotonic() < deadline:
            shell.root.update(); time.sleep(.005)
            if errors: raise errors.pop(0)
    def active(field):
        pump()
        assert p.entry is field and field.focus_get() is field
        assert field.cget('highlightbackground') == ui.ACCENT
        assert int(field.cget('insertwidth')) >= 2
    def tap(field):
        p.scroll.reveal(field); pump()
        subprocess.run(['xdotool','mousemove',str(field.winfo_rootx()+field.winfo_width()//2),
                        str(field.winfo_rooty()+field.winfo_height()//2),'click','1'],check=True)
        pump()
    def key(action):
        box = next(box for box in shell.boxes if box[4] == action)
        subprocess.run(['xdotool','mousemove',str(round((box[0]+box[2])/2)),
                        str(round(shell.keyboard.winfo_rooty()+(box[1]+box[3])/2)),'click','1'],check=True)
        pump()
    try:
        with tempfile.TemporaryDirectory(prefix='moto-input-focus-',dir='/run') as temp:
            p.host_store = ui.panel_module.hosts.HostStore(Path(temp)/'hosts.json')
            ui.panel_module.voice_module.voice.CONFIG = Path(temp)/'groq.json'
            p.ssh.form(); pump()
            fields = list(p.inputs)
            assert len(fields) == 5
            active(fields[0])
            key('x'); active(fields[0]); assert fields[0].get() == 'x'
            tap(fields[1]); active(fields[1])
            assert fields[0].cget('highlightbackground') == ui.KEY
            key('q'); active(fields[1]); assert fields[1].get() == 'q'
            # Native physical Tab and touch keyboard Tab share the same fields.
            subprocess.run(['xdotool','key','Tab'],check=True); active(fields[2])
            key('Tab'); active(fields[3])
            key('Tab'); active(fields[4])
            assert fields[4].cget('show')
            key('p'); active(fields[4]); assert fields[4].get() == 'p'
            shell.emit('mod:Shift'); key('Tab'); active(fields[3])
            print('PASS: initial SSH focus, actual XTest taps on fields/keyboard, masked password, physical/touch Tab and Shift-Tab; no terminal input')

            # Capture one native Entry in the on/off caret phases, no typing or
            # decorative animation. XWD pixel differences prove actual blinking.
            p.entry = fields[1]; pump()
            p.entry = fields[0]; pump(.12)
            paths = [Path('/tmp/moto-input-caret-on.xwd'),Path('/tmp/moto-input-caret-off.xwd')]
            subprocess.run(['xwd','-id',str(fields[0].winfo_id()),'-silent','-out',str(paths[0])],check=True)
            pump(.60)
            subprocess.run(['xwd','-id',str(fields[0].winfo_id()),'-silent','-out',str(paths[1])],check=True)
            assert paths[0].read_bytes() != paths[1].read_bytes(), 'Native caret did not blink'
            print('PASS: native caret visibly changes pixels between on/off phases in focused field')

            p.credentials('Fixture network',True); pump()
            active(p.inputs[1]); key('s'); active(p.inputs[1])
            assert p.inputs[1].get() == 's' and p.inputs[1].cget('show')
            tap(p.inputs[0]); active(p.inputs[0])
            p.voice.configure(); pump(); active(p.inputs[0])
            key('k'); active(p.inputs[0]); assert p.inputs[0].get() == 'k' and p.inputs[0].cget('show')
            print('PASS: Wi-Fi and Groq fields get visible focus on opening and retain it through keyboard taps')

            p.voice.transcript = 'fixture words'; p.voice.target = ('%999','fixture')
            p.voice.review(); pump(); active(p.entry)
            text = p.entry
            text.mark_set('insert','1.7')
            text.tag_add('sel','1.0','1.7'); key('x'); active(text)
            assert text.get('1.0','end-1c') == 'x words', repr((text.get('1.0','end-1c'),text.tag_ranges('sel'),shell.mods,p.entry))
            key('Left'); active(text)
            assert text.index('insert') == '1.0'
            # Delayed activation must not re-focus a field from a closed page.
            p.entry = text; p.home(); pump()
            assert p.entry is None and not text.winfo_exists()
            assert p.page == 'home'
            print('PASS: multiline review has caret/focus and selection replacement; page changes cancel stale focus jobs')
    finally:
        shell.close_menu(); shell.quick_voice.close(); shell.sock.close(); shell.root.destroy()
        Path(ui.SOCKET).unlink(missing_ok=True)


if __name__ == '__main__': main()
