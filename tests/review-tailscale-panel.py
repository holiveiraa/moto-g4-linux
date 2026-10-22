#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Isolated :9 UI test. Uses fake login links and never modifies a real VPN."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import subprocess
import time
import tkinter as tk
from unittest.mock import patch


def main():
    os.environ['DISPLAY'] = ':9'
    loader = importlib.machinery.SourceFileLoader('ui', str(Path(os.environ.get('MOTO_UI_REVIEW_DIR', '/usr/sbin')) / 'moto-shell'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    ui = importlib.util.module_from_spec(spec)
    loader.exec_module(ui)
    ui.SOCKET = '/run/moto-vpn-review.sock'
    ui.Shell.write_geometry = lambda self: None
    ui.Shell.vpn_worker = lambda self: None
    ui.Shell.refresh_tmux = lambda self: None
    shell = ui.Shell()
    services = ui.panel_module.services
    url = 'https://login.tailscale.com/a/example-test-only'

    def widgets(parent):
        for child in parent.winfo_children():
            yield child
            yield from widgets(child)

    def texts():
        return [w.cget('text') for w in widgets(shell.panel.body)
                if isinstance(w, (tk.Button, tk.Label))]

    def visible(name):
        shell.root.update()
        layout_spec = importlib.util.spec_from_file_location('layout_review', Path(__file__).with_name('review-layout.py'))
        layout = importlib.util.module_from_spec(layout_spec)
        layout_spec.loader.exec_module(layout)
        layout.reachable(shell.panel)
        subprocess.run(['xwd', '-root', '-silent', '-out', '/tmp/moto-vpn-' + name + '.xwd'], check=True)

    try:
        # Fresh install: daemon needs login but has not generated a URL yet.
        # Run the real UI action/worker, with only the external login stubbed.
        shell.device = {'vpn': services.tailscale_view({'BackendState': 'NeedsLogin'})}
        shell.panel.vpn()
        visible('first-use')
        assert shell.panel.photo is None
        connect = next(w for w in widgets(shell.panel.body)
                       if isinstance(w, tk.Button) and w.cget('text') == 'Gerar QR de autorização')
        login = services.tailscale_view({'BackendState': 'NeedsLogin', 'AuthURL': url})
        with patch.object(services, 'tailscale_connect', return_value=login) as begin_login:
            connect.invoke()
            deadline = time.monotonic()+3
            while shell.panel.photo is None and time.monotonic() < deadline:
                shell.root.update(); time.sleep(.02)
            begin_login.assert_called_once_with()
            assert shell.panel.photo is not None
        assert shell.device['vpn']['url'] == url
        print('PASS: first use without login URL generates the QR through the on-device action; real identity untouched')
        shell.panel.vpn()
        visible('qr')
        assert shell.panel.photo is not None
        assert url not in texts(), 'Link must be collapsed by default'
        assert not list(Path('/run').glob('moto-vpn-*.png')), 'Temporary QR leaked'
        shell.panel.show_auth_link()
        visible('link')
        assert url in texts()
        print('PASS: real QR rendering, collapsed link, layout fits 1080x1920; QR file removed')

        shell.device['vpn'] = services.tailscale_view({'BackendState': 'Running', 'AuthURL': url,
            'Self': {'Online': True}, 'TailscaleIPs': ['100.64.0.1']})
        shell.panel.update()
        visible('connected')
        assert 'VPN ativa' in texts() and url not in texts()
        assert not any('Abrir SSH' in text for text in texts())
        print('PASS: completed login automatically removes QR and keeps VPN separate without reconnecting')

        shell.device['vpn'] = services.tailscale_view({'BackendState': 'Running',
            'Self': {'Online': False}, 'TailscaleIPs': ['100.64.0.1'],
            'Health': ['Network map response timeout']})
        shell.panel.update()
        visible('degraded')
        assert 'VPN com conexão instável' in texts()
        assert 'Reconectar sem recadastrar' in texts()
        assert not any('Gerar QR' in text for text in texts())
        print('PASS: degraded control-plane connection retains SSH and offers identity-preserving recovery')

        shell.device['ssh_auth'] = {'url': url, 'pane': '%99'}
        shell.panel.auth_link_visible = False
        shell.panel.update()
        visible('ssh-auth')
        assert shell.panel.page == 'ssh-auth'
        assert 'Seu Moto já está na VPN.' in texts()
        assert url not in texts()
        shell.panel.show_auth_link()
        visible('ssh-auth-link')
        assert url in texts()
        shell.device['ssh_auth'] = {}
        shell.panel.update()
        assert shell.menu is None
        print('PASS: pending SSH security check opens a separate QR and returns to the terminal when cleared')
    finally:
        shell.sock.close()
        shell.root.destroy()
        Path(ui.SOCKET).unlink(missing_ok=True)


if __name__ == '__main__':
    main()
