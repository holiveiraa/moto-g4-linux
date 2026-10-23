#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Capture synthetic terminal/panel previews in a disposable Xvfb container.

Never run this against a person's desktop. See docs/screenshots.md.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import tkinter as tk

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('MOTO_SHOWCASE_ISOLATED') != '1' or not os.environ.get('DISPLAY'):
        raise SystemExit('Use a disposable container/private Xvfb; set MOTO_SHOWCASE_ISOLATED=1.')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    server = 'moto-showcase-'+str(os.getpid())
    real_run = subprocess.run
    shell = terminal = None

    def tmux(*arguments):
        return real_run(['tmux', '-L', server, *arguments],
                        capture_output=True, text=True, check=True, timeout=3)

    def remap(arguments, *more, **kwargs):
        arguments = list(arguments)
        if arguments[:3] == ['tmux', '-L', 'moto']:
            arguments[2] = server
        return real_run(arguments, *more, **kwargs)

    with tempfile.TemporaryDirectory(prefix=server) as folder:
        private = Path(folder)
        os.environ['MOTO_UX_CONFIG'] = str(private/'ux.json')
        (private/'ux.json').write_text(json.dumps({'theme': 'moto', 'keyboard': 'terminal'}))
        spec = importlib.util.spec_from_file_location('showcase_ui', ROOT/'native/moto-shell.py')
        ui = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ui)
        ui.SOCKET = str(private/'control.sock')
        light = private/'brightness'
        light.write_text('110')
        ui.LIGHT = light
        ui.Shell.write_geometry = lambda self: None
        ui.Shell.vpn_worker = lambda self: None
        ui.Shell.tmux = lambda self, *arguments: tmux(*arguments)
        ui.panel_module.hermes_module.backend.CONFIG = private/'hermes.json'
        # All owners' state is replaced before constructing the UI.
        original_store = ui.panel_module.hosts.HostStore
        class SyntheticHostStore(original_store):
            def __init__(self, path=None):
                super().__init__(private/'hosts.json')
        ui.panel_module.hosts.HostStore = SyntheticHostStore
        ui.panel_module.voice_module.voice.CONFIG = private/'groq.json'
        demo = private/'demo.py'
        demo.write_text(
            'import sys,time\n'
            'print("\\033[2J\\033[H\\033[1;32mMoto G4 Linux\\033[0m\\n")\n'
            'print("Alpine Linux | aarch64\\n")\n'
            'print("demo@server.example:~ $ tmux ls")\n'
            'print("work: 2 windows (attached)\\n")\n'
            'print("demo@server.example:~ $ printf hello")\n'
            'print("hello\\n")\n'
            'sys.stdout.write("\\033[32mdemo@server.example:~ $ \\033[0m"); sys.stdout.flush()\n'
            'time.sleep(120)\n')
        tmux('-f', '/dev/null', 'new-session', '-d', '-s', 'moto', '-n', 'server',
             'python3 '+str(demo))
        tmux('set-option', '-g', 'status', 'off')
        tmux('new-window', '-d', '-t', 'moto', '-n', 'local', 'sleep 120')
        argv = ui.experience.terminal_argv()
        argv = argv[:argv.index('-e')]+['-e', 'tmux', '-L', server, 'attach', '-t', 'moto']
        terminal = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            time.sleep(.5)
            subprocess.run = remap
            shell = ui.Shell()
            panel = shell.panel
            panel.host_store = ui.panel_module.hosts.HostStore(private/'hosts.json')
            shell.device = {
                'battery': '78', 'charging': 'Discharging',
                'wifi': {'ssid': 'Rede de teste', 'wpa_state': 'COMPLETED'},
                'vpn': {'title': 'Conectada'}, 'ssh_auth': {},
            }
            errors = []
            shell.root.report_callback_exception = lambda kind, error, trace: errors.append(error)

            def pump(seconds=.4):
                end = time.monotonic()+seconds
                while time.monotonic() < end:
                    shell.root.update()
                    if errors:
                        raise errors.pop(0)
                    time.sleep(.005)

            def capture(name):
                pump()
                real_run(['xwd', '-root', '-silent', '-out', str(output/(name+'.xwd'))], check=True)

            shell.refresh_tmux_once()
            shell.toast_until = 0
            capture('terminal')
            panel.refresh_volume = lambda force=False: panel.volume_label.configure(text='Volume  65%')
            panel.home()
            pump()
            assert panel.page == 'home'
            buttons = [widget for widget in panel.body.winfo_children() if isinstance(widget, tk.Button)]
            hermes = next(widget for widget in buttons if widget.cget('text').startswith('Hermes'))
            assert hermes.winfo_viewable()
            assert hermes.winfo_rooty()+hermes.winfo_height() < panel.footer.winfo_rooty()
            capture('panel')
            panel.appearance.show()
            panel.appearance.preview('paper')
            capture('appearance')
            print('Captured real UI with synthetic state; no SSH connection, audio or account used.')
        finally:
            subprocess.run = real_run
            if shell:
                shell.close_menu()
                shell.quick_voice.close()
                shell.root.destroy()
            if terminal:
                terminal.terminate()
                terminal.wait(timeout=3)
            tmux('kill-server')


if __name__ == '__main__':
    main()
