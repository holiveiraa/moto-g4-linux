#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Real phone OpenSSH/PTY against the isolated fixture server, no real account."""
import importlib.util
import json
import os
from test_support import EXAMPLE_HOST
from pathlib import Path
import pty
import select
import signal
import sys
import tempfile
import time

root = Path(os.environ.get('MOTO_UI_REVIEW_DIR', '/usr/sbin'))
def load(name):
    spec = importlib.util.spec_from_file_location(name, root/(name+'.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module
hosts, launch = load('moto-hosts'), load('moto-ssh-launch')


def client(store, row, known, manual=False, confirm=False, typed=None):
    options, env = launch.connection_options(row, store, manual)
    # Askpass reads only this private fixture store; the real user's store is
    # never replaced. Helper fixture wrapper is installed by the test below.
    if options:
        env['SSH_ASKPASS'] = str(known.parent/'fixture-askpass')
    argv = hosts.command_argv(row)
    argv = argv[:1]+['-F','none','-o','GlobalKnownHostsFile=/dev/null',
        '-o','UserKnownHostsFile='+str(known),'-o','ConnectTimeout=5']+options+argv[1:]+['fixture-command']
    pid, fd = pty.fork()
    if pid == 0:
        os.execvpe(argv[0], argv, env)
    output, confirmed, entered = bytearray(), False, False
    deadline, status = time.monotonic()+18, None
    try:
        while time.monotonic() < deadline:
            if select.select([fd], [], [], .1)[0]:
                try: chunk = os.read(fd, 8192)
                except OSError: chunk = b''
                if chunk: output.extend(chunk)
            if confirm and not confirmed and b'Are you sure you want to continue connecting' in output:
                os.write(fd, b'yes\n'); confirmed = True
            if typed is not None and not entered and b"'s password:" in output:
                os.write(fd, typed.encode()+b'\n'); entered = True
            finished, raw = os.waitpid(pid, os.WNOHANG)
            if finished:
                status = os.waitstatus_to_exitcode(raw)
                break
        assert status is not None, 'SSH fixture timed out'
        assert b'SSH_PASSWORD_OK' in output if status == 0 else True
        return status, bytes(output), confirmed, entered
    finally:
        if status is None:
            os.kill(pid, signal.SIGKILL); os.waitpid(pid, 0)
        os.close(fd)


def main():
    config = json.loads(Path(sys.argv[1]).read_text())
    with tempfile.TemporaryDirectory(prefix='moto-ssh-password-review-', dir='/run') as temp:
        folder = Path(temp)
        store = hosts.HostStore(folder/'hosts.json')
        profile = dict(EXAMPLE_HOST, user='fixtureuser', host='127.0.0.1', port=config['remote_port'], mode='ssh')
        row = store.save(profile, password=config['password'])
        # Invoke the actual helper's answer/TTY routines, with a fixture store.
        wrapper = folder/'fixture-askpass'
        wrapper.write_text('#!/usr/bin/python3\nimport importlib.util,os,sys\n'
            'from pathlib import Path\n'
            f'root=Path({str(root)!r})\n'
            'def load(name):\n spec=importlib.util.spec_from_file_location(name,root/(name+".py")); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module\n'
            'ask,hosts=load("moto-ssh-askpass"),load("moto-hosts")\n'
            f'store=hosts.HostStore({str(store.path)!r})\n'
            'try:\n result=ask.answer(sys.argv[1],store,os.environ["MOTO_SSH_DESTINATION"],os.environ.get("SSH_ASKPASS_PROMPT",""),endpoint=os.environ.get("MOTO_SSH_ENDPOINT")); print(result if result is not None else "")\n'
            'except (OSError,RuntimeError,ValueError,KeyboardInterrupt): sys.exit(1)\n')
        wrapper.chmod(0o700)
        known = folder/'known-hosts'
        code, output, confirmed, entered = client(store,row,known,confirm=True)
        assert code == 0 and confirmed and not entered
        assert config['password'].encode() not in output
        print('PASS: real OpenSSH asks host-key confirmation via controlling TTY, then uses saved password without echo')
        code, output, confirmed, entered = client(store,row,known)
        assert code == 0 and not confirmed and not entered
        print('PASS: known host connects with saved password automatically')
        code, output, _, entered = client(store,row,known,manual=True,typed=config['password'])
        assert code == 0 and entered and config['password'].encode() not in output
        store.remove_password(row['id'])
        code, output, _, entered = client(store,row,known,typed=config['password'])
        assert code == 0 and entered and config['password'].encode() not in output
        print('PASS: manual override and empty saved password both keep normal SSH terminal authentication, no password echo')
        store.save(row,row['id'],password='wrong-fixture')
        code, output, _, _ = client(store,row,known)
        assert code != 0 and b'Permission denied' in output and b'wrong-fixture' not in output
        print('PASS: wrong saved password fails once without disclosing it')
        # A valid, different key exercises changed-host protection before login.
        import subprocess
        key = folder/'wrong-host-key'
        subprocess.run(['ssh-keygen','-q','-t','rsa','-b','2048','-N','','-f',str(key)],check=True)
        known.write_text('[127.0.0.1]:'+str(row['port'])+' '+key.with_suffix('.pub').read_text())
        code, output, _, _ = client(store,row,known)
        assert code != 0 and b'REMOTE HOST IDENTIFICATION HAS CHANGED' in output
        print('PASS: changed host key is rejected; no automatic approval')


if __name__ == '__main__': main()
