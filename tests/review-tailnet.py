#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""HTTP/WS confinement review in a disposable network namespace; no real VPN/account.

Requires root, NET_ADMIN, Python3, iproute2 and a built Linux moto-hermes binary.
Never run on a host or phone. See tests/README.md.
"""
import http.server
import json
import os
from pathlib import Path
import select
import socketserver
import subprocess
import tempfile
import threading
import time


def main():
    if os.environ.get('MOTO_TAILNET_REVIEW') != '1' or not Path('/.dockerenv').exists() or os.geteuid() != 0:
        raise SystemExit('Use a disposable root container with its own network namespace and NET_ADMIN.')
    if {p.name for p in Path('/sys/class/net').iterdir()} != {'lo'}:
        raise SystemExit('Disconnect the disposable container from external networks first; only lo may exist.')
    daemon = Path('/run/tailscale/tailscaled.sock')
    if daemon.exists() or Path('/sys/class/net/tailscale0').exists():
        raise SystemExit('Refusing an existing Tailscale daemon/interface.')
    binary = os.environ['MOTO_HERMES_BINARY']
    state = {'BackendState': 'Running', 'TUN': True,
             'Peer': {'fixture': {'Online': True, 'TailscaleIPs': ['100.64.0.10']}}}
    counts = {'http': 0, 'ws': 0}

    class Local(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.path == '/localapi/v0/status'
            data = json.dumps(state).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        def log_message(self, *args):
            pass

    class UnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
        daemon_threads = True

    class Remote(http.server.BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        def handle(self):
            try:
                super().handle()
            except (ConnectionResetError, BrokenPipeError):
                pass  # The worker deliberately closes rejected WS connections.
        def do_GET(self):
            if self.path == '/':
                counts['http'] += 1
                data = b'<script>window.__HERMES_SESSION_TOKEN__="fixture-token";</script>'
                self.send_response(200)
            else:
                assert self.path.startswith('/api/ws?')
                assert self.headers.get('Upgrade', '').lower() == 'websocket'
                counts['ws'] += 1
                # Receiving the actual Upgrade proves the bound WS TCP path.
                # Chat/frame semantics are exercised by the strict Rust fixture.
                data = b'fixture deliberately ends before WS handshake'
                self.send_response(400)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        def log_message(self, *args):
            pass

    def ip(*arguments):
        subprocess.run(['ip', *arguments], check=True, capture_output=True)

    daemon.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    local = UnixServer(str(daemon), Local)
    remote = http.server.ThreadingHTTPServer(('0.0.0.0', 0), Remote)
    for server in (local, remote):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    created = False
    try:
        ip('link', 'add', 'tailscale0', 'type', 'dummy')
        created = True
        ip('address', 'add', '100.64.0.10/32', 'dev', 'tailscale0')
        ip('link', 'set', 'tailscale0', 'up')
        with tempfile.TemporaryDirectory(prefix='moto-tailnet-review-') as folder:
            config = Path(folder)/'hermes.json'
            config.write_text(json.dumps({'server_url': 'http://100.64.0.10:'+str(remote.server_port)+'/',
                                          'auto_speak': False}))
            config.chmod(0o600)

            process = subprocess.Popen([binary, '--stdio', '--config', str(config)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            def event():
                if not select.select([process.stdout], [], [], 8)[0]:
                    raise AssertionError('fixture child deadline')
                return json.loads(process.stdout.readline())

            def connect():
                process.stdin.write(b'{"cmd":"connect"}\n')
                process.stdin.flush()
                deadline = time.monotonic()+10
                while time.monotonic() < deadline:
                    result = event()
                    if result['event'] == 'error':
                        return result
                raise AssertionError('missing fixture error')
            assert event()['event'] == 'ready'
            connect()
            assert counts == {'http': 1, 'ws': 1}, counts
            connect()
            assert counts == {'http': 2, 'ws': 2}, counts
            print('PASS: peer-verified HTTP and actual WS Upgrade reach the synthetic peer.')
            original = dict(counts)
            state['BackendState'] = 'Stopped'
            assert 'Tailscale' in connect()['text']
            assert counts == original
            state['BackendState'] = 'Running'
            state['Peer']['fixture']['TailscaleIPs'] = ['100.64.0.11']
            assert 'Tailscale' in connect()['text']
            assert counts == original
            state['Peer']['fixture']['TailscaleIPs'] = ['100.64.0.10']
            ip('link', 'set', 'tailscale0', 'down')
            connect()
            assert counts == original
            ip('link', 'set', 'tailscale0', 'name', 'moto-review')
            ip('link', 'set', 'moto-review', 'up')
            # Same target still reachable, but the trusted interface is gone:
            # HTTP must not fall back to the alternative route/device.
            connect()
            assert counts == original
            process.kill()
            process.wait(timeout=3)
            print('PASS: same worker/HTTP pool refuses stopped VPN, unknown peer and down/missing TUN; no new HTTP/WS via alternative route.')
    finally:
        if 'process' in locals() and process.poll() is None:
            process.kill()
            process.wait(timeout=3)
        if created:
            name = 'tailscale0' if Path('/sys/class/net/tailscale0').exists() else 'moto-review'
            ip('link', 'delete', name)
        local.shutdown()
        local.server_close()
        remote.shutdown()
        remote.server_close()
        daemon.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
