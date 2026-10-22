#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Windows-only test orchestrator. Paramiko fixture serves no OS shell/account.

Dev-only dependency: paramiko 3.5.1 in .private/ssh-test-deps. The server binds
Windows loopback; a temporary maintenance SSH tunnel reaches it from the Moto.
"""
import json
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
import time

project = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(project/'.private/ssh-test-deps'))
import paramiko

password = secrets.token_urlsafe(24)
key = paramiko.RSAKey.generate(2048)
stop = threading.Event()


class Fixture(paramiko.ServerInterface):
    def get_allowed_auths(self, username): return 'password'
    def check_auth_password(self, username, supplied):
        return paramiko.AUTH_SUCCESSFUL if username == 'fixtureuser' and supplied == password else paramiko.AUTH_FAILED
    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED if kind == 'session' else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED
    def check_channel_exec_request(self, channel, command):
        return command == b'fixture-command'


def handle(connection):
    transport = paramiko.Transport(connection)
    try:
        transport.add_server_key(key); transport.start_server(server=Fixture())
        channel = transport.accept(15)
        if channel is None: return
        time.sleep(.1)
        channel.sendall(b'SSH_PASSWORD_OK\n'); channel.send_exit_status(0)
        channel.shutdown_write()
        deadline = time.monotonic()+3
        while not channel.closed and time.monotonic()<deadline: time.sleep(.05)
    except (EOFError,OSError,paramiko.SSHException):
        pass
    finally: transport.close()


def main():
    private = project/'.private'
    config = private/'ssh-password-review.json'
    listener = socket.socket()
    listener.bind(('127.0.0.1',0)); listener.listen(8); listener.settimeout(.2)
    port = listener.getsockname()[1]
    def serve():
        while not stop.is_set():
            try: connection,_ = listener.accept()
            except socket.timeout: continue
            except OSError: break
            threading.Thread(target=handle,args=(connection,),daemon=True).start()
    threading.Thread(target=serve,daemon=True).start()
    config.write_text(json.dumps({'remote_port':40222,'password':password}))
    ssh = ['ssh.exe','-i',str(private/'device-debug-ed25519'),'-o','IdentitiesOnly=yes',
        '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(private/'device-known-hosts'),
        '-o','ConnectTimeout=10']
    tunnel = None
    try:
        subprocess.run(['pwsh','-NoProfile','-File',str(project/'scripts/device-upload.ps1'),
            '-Source',str(config),'-RemotePath','/tmp/moto-ssh-password-review.json','-Mode','600'],check=True)
        tunnel = subprocess.Popen(ssh+['-o','ExitOnForwardFailure=yes','-N',
            '-R',f'127.0.0.1:40222:127.0.0.1:{port}','root@172.16.42.1'],creationflags=subprocess.CREATE_NO_WINDOW)
        time.sleep(1)
        assert tunnel.poll() is None, 'Maintenance tunnel could not start'
        result = subprocess.run(ssh+['root@172.16.42.1',
            'MOTO_UI_REVIEW_DIR=/tmp/moto-ui-review python3 /tmp/moto-ui-review/review-ssh-password-device.py /tmp/moto-ssh-password-review.json'],timeout=100)
        return result.returncode
    finally:
        if tunnel:
            tunnel.terminate(); tunnel.wait(timeout=5)
        subprocess.run(ssh+['root@172.16.42.1','rm -f /tmp/moto-ssh-password-review.json'],timeout=15)
        config.unlink(missing_ok=True)
        stop.set(); listener.close()


if __name__ == '__main__': raise SystemExit(main())
