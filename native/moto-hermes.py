# SPDX-License-Identifier: MIT
"""Private configuration and process boundary for the optional Rust companion."""
import json
import os
import stat
from pathlib import Path
import subprocess
import tempfile
import threading
from urllib.parse import urlsplit

CONFIG = Path('/root/.config/moto-linux/hermes.json')
BINARY = '/usr/local/bin/moto-hermes'
DEFAULTS = {'server_url':'https://server.example:18789/', 'user_id':'0', 'profile':'',
            'auth_origin':None, 'ca_file':None, 'auto_speak':True, 'remember_session':False}


def cleanup_listener(pid, run=Path('/run')):
    """After our child exits, remove only its known private recording file."""
    for folder in run.glob('moto-hermes-listen-'+str(int(pid))+'-*'):
        try:
            info = folder.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                continue
            (folder/'utterance.wav').unlink(missing_ok=True)
            folder.rmdir()
        except OSError:
            pass


def settings(path=None):
    try:
        target = Path(path or CONFIG)
        if target.is_symlink() or target.stat().st_size > 65536:
            return dict(DEFAULTS)
        data = json.loads(target.read_text())
        return dict(DEFAULTS, **data) if isinstance(data, dict) else dict(DEFAULTS)
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save_config(value, path=None):
    value = {key:value.get(key, default) for key, default in DEFAULTS.items()}
    parsed = urlsplit(value['server_url'])
    try:
        parsed.port
    except ValueError:
        raise ValueError('Porta do Hermes inválida.') from None
    loopback = parsed.hostname in ('127.0.0.1', 'localhost', '::1')
    if (parsed.scheme != 'https' and not (parsed.scheme == 'http' and loopback)
            or not parsed.hostname or parsed.username is not None or parsed.password is not None
            or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        raise ValueError('Use a URL HTTPS do Hermes, sem senha ou parâmetros.')
    value['server_url'] = value['server_url'].rstrip('/')+'/'
    if value['auth_origin']:
        auth = urlsplit(value['auth_origin'])
        if (auth.scheme != 'https' and not (auth.scheme == 'http' and auth.hostname in ('127.0.0.1','localhost','::1'))
                or not auth.hostname or auth.username is not None or auth.password is not None
                or auth.path not in ('','/') or auth.query or auth.fragment):
            raise ValueError('Origem do login Umbrel inválida.')
        value['auth_origin'] = value['auth_origin'].rstrip('/')+'/'
    if any(not isinstance(value[key], str) or len(value[key]) > 128
           or any(ord(c) < 32 for c in value[key]) for key in ('user_id','profile')) or not value['user_id']:
        raise ValueError('Conta ou perfil inválido.')
    target = Path(path or CONFIG)
    if any(part.is_symlink() for part in (target, *target.parents)):
        raise ValueError('A configuração privada não aceita links simbólicos.')
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    target.parent.chmod(0o700)
    fd, temporary = tempfile.mkstemp(prefix='.hermes-', dir=target.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(value, stream, ensure_ascii=False)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


class Worker:
    def __init__(self, enqueue, receive, binary=None, config=None, arguments=None):
        self.enqueue, self.receive = enqueue, receive
        self.binary, self.config = str(binary or BINARY), str(config or CONFIG)
        self.arguments = list(arguments) if arguments is not None else ['--stdio', '--config', self.config]
        self.process = None
        self.generation = 0
        self.lock = threading.Lock()

    def start(self):
        if self.process is not None and self.process.poll() is None:
            return
        self.process = subprocess.Popen([self.binary, *self.arguments],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding='utf-8', bufsize=1)
        process, generation = self.process, self.generation
        def read():
            try:
                while True:
                    line = process.stdout.readline(512*1024+1)
                    if not isinstance(line, str) or not line or len(line) > 512*1024:
                        break
                    value = json.loads(line)
                    if isinstance(value, dict):
                        self.deliver(value, generation)
            except (OSError, ValueError):
                pass
            self.deliver({'event':'exited'}, generation)
        threading.Thread(target=read, daemon=True).start()

    def deliver(self, event, generation=None):
        expected = self.generation if generation is None else generation
        def apply():
            if self.generation == expected:
                self.receive(event)
        self.enqueue(apply)

    def send(self, command):
        payload = json.dumps(command, ensure_ascii=False)+'\n'
        if len(payload.encode()) > 131072:
            raise RuntimeError('Mensagem longa demais.')
        with self.lock:
            if self.process is None or self.process.poll() is not None:
                raise RuntimeError('O app Hermes não está aberto.')
            try:
                self.process.stdin.write(payload)
                self.process.stdin.flush()
            except (OSError, ValueError):
                raise RuntimeError('O app Hermes foi encerrado.') from None

    def close(self, after_stop=None):
        self.generation += 1
        process, self.process = self.process, None
        if process is None:
            if after_stop:
                after_stop()
            return
        def stop():
            try:
                try:
                    if process.poll() is None:
                        # The shutdown deadline must also cover a full/stalled pipe.
                        fd = process.stdin.fileno()
                        os.set_blocking(fd, False)
                        try:
                            os.write(fd, b'{"cmd":"close"}\n')
                        except OSError:
                            pass
                    process.stdin.close()
                except (OSError, ValueError, TypeError):
                    pass
                try:
                    process.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try: process.wait(timeout=2)
                    except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=2)
            except (OSError, ValueError):
                pass
            finally:
                process.stdout.close()
                if self.arguments and self.arguments[0] == '--listen' and process.poll() is not None:
                    cleanup_listener(process.pid)
                if after_stop:
                    after_stop()
        threading.Thread(target=stop, daemon=True).start()
