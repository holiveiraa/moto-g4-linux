#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Real Tk/tmux, private saved-host store, fake Wi-Fi; never reaches a server."""
import copy
import importlib.machinery
import importlib.util
import os
from test_support import EXAMPLE_HOST
from pathlib import Path
import shlex
import subprocess
import tempfile
import time
import tkinter as tk


def main():
    os.environ['DISPLAY'] = ':9'
    root = Path(os.environ.get('MOTO_UI_REVIEW_DIR', '/usr/sbin'))
    loader = importlib.machinery.SourceFileLoader('connection_review', str(root/'moto-shell'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    ui = importlib.util.module_from_spec(spec)
    loader.exec_module(ui)
    server = 'connections-review-'+str(os.getpid())
    def run(*args):
        return subprocess.run(['tmux', '-L', server, *args], capture_output=True, text=True, timeout=3)
    ui.SOCKET = '/run/'+server+'.sock'
    ui.Shell.write_geometry = lambda self: None
    ui.Shell.vpn_worker = lambda self: None
    ui.Shell.tmux = lambda self, *args: run(*args)
    shell = None
    def walk(parent):
        for w in parent.winfo_children():
            yield w
            yield from walk(w)
    try:
        with tempfile.TemporaryDirectory(prefix='moto-connections-review-', dir='/run') as temp:
            folder = Path(temp)
            assert run('-f', '/dev/null', 'new-session', '-d', '-s', 'moto', '-n', 'test', '/bin/ash', '-l').returncode == 0
            shell = ui.Shell()
            callback_errors = []
            shell.root.report_callback_exception = lambda kind, value, trace: callback_errors.append(value)
            p, services = shell.panel, ui.panel_module.services
            p.host_store = ui.panel_module.hosts.HostStore(folder/'settings/hosts.json', initial=[EXAMPLE_HOST])
            sent, reused = [], []
            shell.keys.send = lambda *args: sent.append(args)
            shell.device = {'battery': '78', 'charging': 'Discharging', 'wifi': {'ssid': 'Casa de teste', 'wpa_state': 'COMPLETED'},
                'vpn': services.tailscale_view({'BackendState': 'Running', 'Self': {'Online': True}, 'TailscaleIPs': ['100.64.0.1']}), 'ssh_auth': {}}
            profile = {'id': '3', 'ssid': 'Casa de teste', 'ssid_hex': 'Casa de teste'.encode().hex(),
                       'key_mgmt': 'WPA-PSK', 'secure': True, 'supported': True, 'bssid': 'any',
                       'hidden': False, 'current': True, 'enabled': True, 'priority': 10}
            services.wifi_saved = lambda: [copy.deepcopy(profile)]
            services.wifi_scan = lambda: [{'ssid': 'Casa de teste', 'ssid_hex': profile['ssid_hex'], 'secure': True,
                                           'supported': True, 'signal': -45, 'band': '2.4 GHz'}]
            services.wifi_join = lambda *args: (_ for _ in ()).throw(AssertionError('Saved Wi-Fi asked for a password'))
            def reconnect(row):
                reused.append(copy.deepcopy(row))
                return {'connected': True, 'saved': True, 'id': row['id'], 'message': 'Conectado e salvo.'}
            services.wifi_connect_saved = reconnect
            def pump():
                shell.root.update()
                if callback_errors:
                    raise callback_errors.pop(0)
            def wait(predicate):
                deadline = time.monotonic()+3
                while not predicate() and time.monotonic() < deadline:
                    pump(); time.sleep(.02)
                assert predicate()
            def button(text, parent=None):
                return next(w for w in walk(parent or p.body) if isinstance(w, tk.Button) and text in w.cget('text'))
            def tap(widget):
                if widget.master is not p.footer:
                    p.scroll.reveal(widget)
                pump()
                x, y = widget.winfo_width()//2, widget.winfo_height()//2
                widget.event_generate('<ButtonPress-1>', x=x, y=y)
                widget.event_generate('<ButtonRelease-1>', x=x, y=y)
                pump()
            def reachable():
                layout_spec = importlib.util.spec_from_file_location('layout_review', Path(__file__).with_name('review-layout.py'))
                layout = importlib.util.module_from_spec(layout_spec)
                layout_spec.loader.exec_module(layout)
                layout.reachable(p)
            def capture(name):
                pump()
                subprocess.run(['xwd', '-root', '-silent', '-out', '/tmp/moto-connections-'+name+'.xwd'], check=True)

            p.home(); pump(); capture('home')
            assert button('Wi-Fi') and button('Tailscale') and button('SSH')
            p.vpn(); pump()
            assert not any('SSH' in w.cget('text') for w in walk(p.body) if isinstance(w, tk.Button))
            p.back(); assert p.page == 'home'
            p.wifi(); wait(lambda: bool(p.wifi_ui.saved))
            reachable(); capture('wifi')
            tap(button('Casa de teste', p.wifi_ui.saved_frame))
            assert p.page == 'wifi-saved' and p.entry is None
            tap(button('Conectar com dados salvos'))
            wait(lambda: bool(reused) and p.page == 'wifi')
            assert reused[0]['id'] == '3' and not sent
            print('PASS: separate Wi-Fi/VPN/SSH pages; saved Wi-Fi uses profile without a credential form')

            p.ssh.home(); tap(button('+ Nova conexão'))
            assert p.page == 'ssh-edit'
            entries = [w for w in walk(p.body) if isinstance(w, tk.Entry)]
            assert len(entries) == 5
            assert entries[4].cget('show') and entries[4].get() == ''
            values = ['Servidor de teste', 'host.example', 'ubuntu', '2222']
            for entry, value in zip(entries, values):
                p.entry = entry
                shell.emit('mod:Ctrl'); shell.emit('a')
                for char in value: shell.emit(char)
            tap(button('Tailscale SSH'))
            assert entries[1].get() == 'host.example' and entries[3].get() == '22'
            tap(button('SSH'))
            assert entries[3].get() == '2222'
            p.entry = entries[4]
            for char in 'fixture-password': shell.emit(char)
            reachable(); capture('ssh-form')
            tap(button('Salvar', p.footer))
            assert p.page == 'ssh-details' and not sent
            ident = p.ssh.ident
            assert p.host_store.find(ident)['port'] == 2222
            assert p.host_store.path.stat().st_mode & 0o777 == 0o600
            assert p.host_store.password(ident) == 'fixture-password' and not sent
            assert 'fixture-password' not in p.host_store.path.read_text()
            p.ssh.home(); reachable(); capture('ssh')
            print('PASS: saved-host create/form keyboard/port-mode changes; fixed Save footer; persisted private metadata')

            p.ssh.form(ident)
            entries = [w for w in walk(p.body) if isinstance(w, tk.Entry)]
            assert entries[4].get() == '' and entries[4].cget('show')
            marker = Path('/tmp/moto-no-shell-injection')
            assert not marker.exists()
            entries[0].delete(0, 'end'); entries[0].insert(0, 'demo;touch /tmp/moto-no-shell-injection')
            p.submit(); assert p.page == 'ssh-details'
            assert p.host_store.find(ident)['name'].startswith('demo;touch')
            assert p.host_store.password(ident) == 'fixture-password', 'Blank edit must preserve saved password'
            p.ssh.confirm_password_remove(ident); tap(button('Remover somente a senha'))
            assert p.host_store.password(ident) is None
            fixture = folder/'launch-probe'
            received = folder/'received-id'
            fixture.write_text('#!/bin/ash\nprintf "%s" "$1" > '+shlex.quote(str(received))+'\nexec /bin/ash -l\n')
            fixture.chmod(0o700)
            shell.tabs.launcher = str(fixture)
            before = {row['id'] for row in shell.tabs.list()}
            tap(button('Abrir em nova aba'))
            wait(lambda: received.exists())
            assert received.read_text() == ident and not marker.exists()
            after = shell.tabs.list()
            assert len(after) == len(before)+1 and shell.menu is None
            opened = next(row['id'] for row in after if row['id'] not in before)
            assert run('show-window-options', '-v', '-t', opened, '@moto_ssh_mode').stdout.strip() == 'ssh'
            p.ssh.confirm_remove(ident); tap(button('Remover favorito'))
            assert all(row['id'] != ident for row in p.host_store.list())
            assert shell.tabs.get(opened)
            print('PASS: real tmux direct launcher receives only ID; display name stays data; removing favorite preserves open tab')
    finally:
        if shell:
            shell.close_menu(); shell.quick_voice.close(); shell.sock.close(); shell.root.destroy()
            Path(ui.SOCKET).unlink(missing_ok=True)
        run('kill-server')


if __name__ == '__main__': main()
