# SPDX-License-Identifier: MIT
"""Saved destinations and separately stored optional endpoint-bound passwords."""
from contextlib import contextmanager
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import tempfile
import time
import uuid

ID_PATTERN = r'(?:[a-f0-9]{32}|[a-z][a-z0-9_-]{0,31})'


def validate(value):
    if not isinstance(value, dict):
        raise ValueError('Destino SSH inválido.')
    ident = str(value.get('id', ''))
    if not re.fullmatch(ID_PATTERN, str(ident)):
        raise ValueError('Identificador de destino inválido.')
    if any(any(ord(c) < 32 or ord(c) == 127 for c in str(value.get(field, '')))
           for field in ('name', 'host', 'user')):
        raise ValueError('Nome, host e usuário não podem conter caracteres de controle.')
    name = str(value.get('name', '')).strip()
    host = str(value.get('host', '')).strip()
    user = str(value.get('user', '')).strip()
    if not 1 <= len(name) <= 60 or not all(c.isprintable() for c in name):
        raise ValueError('Use um nome de 1 a 60 caracteres, sem quebras de linha.')
    if host.startswith('[') and host.endswith(']'):
        host = host[1:-1]
    try:
        ipaddress.ip_address(host)
        valid_host = '%' not in host  # Scoped local IPv6 is a separate future feature.
    except ValueError:
        valid_host = bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,252}', host))
    if not valid_host or any(c in host for c in '\x00\r\n'):
        raise ValueError('Use um IP ou nome de host sem espaços ou opções de comando.')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]{0,63}', user):
        raise ValueError('Informe um usuário SSH válido, sem espaços ou opções.')
    raw_port = str(value.get('port', '22'))
    if not raw_port.isascii() or not raw_port.isdigit() or not 1 <= int(raw_port) <= 65535:
        raise ValueError('A porta precisa ser um número entre 1 e 65535.')
    port, mode = int(raw_port), value.get('mode', 'ssh')
    if mode not in ('ssh', 'tailscale'):
        raise ValueError('Escolha SSH ou Tailscale SSH.')
    if mode == 'tailscale' and port != 22:
        raise ValueError('Tailscale SSH usa porta 22. Para outra porta, escolha SSH.')
    used = value.get('last_used', 0)
    if not isinstance(used, (int, float)) or not 0 <= used <= 10**12:
        used = 0
    return {'id': ident, 'name': name, 'host': host, 'user': user,
            'port': port, 'mode': mode, 'last_used': int(used)}


def command_argv(profile):
    profile = validate(profile)
    if profile['mode'] == 'tailscale':
        return ['tailscale', 'ssh', profile['user']+'@'+profile['host']]
    return ['ssh', '-o', 'StrictHostKeyChecking=ask', '-p', str(profile['port']),
            '-l', profile['user'], profile['host']]


class HostStore:
    LIMIT = 64
    def __init__(self, path='/root/.config/moto-linux/hosts.json', initial=None):
        self.path = Path(path)
        self.initial = [validate(row) for row in initial or []]
        self.secret_dir = self.path.parent/'ssh-passwords'

    @staticmethod
    def endpoint(profile):
        return {key: profile[key] for key in ('host', 'user', 'port', 'mode')}

    @classmethod
    def endpoint_token(cls, profile):
        return hashlib.sha256(json.dumps(cls.endpoint(profile), sort_keys=True).encode('utf-8')).hexdigest()

    def secret_path(self, ident):
        if not re.fullmatch(ID_PATTERN, str(ident)):
            raise ValueError('Identificador de destino inválido.')
        return self.secret_dir/(ident+'.json')

    @staticmethod
    def validate_password(password):
        if not isinstance(password, str) or len(password.encode('utf-8')) > 512 or any(ord(c) < 32 or ord(c) == 127 for c in password):
            raise ValueError('A senha deve ter até 512 bytes, sem caracteres de controle.')
        return password

    def password(self, ident, expected_endpoint=None):
        # Keep metadata and credential reads consistent with edits/removals.
        with self.locked():
            return self._password(ident, expected_endpoint)

    def _password(self, ident, expected_endpoint=None):
        profile = self.find(ident)
        if expected_endpoint is not None and self.endpoint_token(profile) != expected_endpoint:
            return None
        if profile['mode'] != 'ssh':
            return None
        path = self.secret_path(ident)
        try:
            if not path.exists():
                return None
            if path.stat().st_size > 8192:
                raise ValueError()
            value = json.loads(path.read_text(encoding='utf-8'))
            if value.get('endpoint') != self.endpoint(profile):
                return None
            return self.validate_password(value['password']) or None
        except (ValueError, KeyError, TypeError, AttributeError, OSError):
            raise RuntimeError('Não foi possível ler a senha salva. Use a entrada manual ou substitua a senha.') from None

    def write_secret(self, ident, content):
        path = self.secret_path(ident)
        if content is None:
            path.unlink(missing_ok=True)
            return
        self.secret_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.secret_dir.chmod(0o700)
        fd, name = tempfile.mkstemp(prefix='.password-', dir=self.secret_dir)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(content); stream.flush(); os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)

    def remove_password(self, ident):
        with self.locked():
            self.find(ident)
            self.write_secret(ident, None)

    @contextmanager
    def locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.parent.chmod(0o700)
        fd = os.open(self.path.with_suffix('.lock'), os.O_WRONLY | os.O_CREAT, 0o600)
        with os.fdopen(fd, 'w') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield

    def list(self):
        if not self.path.exists():
            return [dict(row) for row in self.initial]
        try:
            if self.path.stat().st_size > 256*1024:
                raise ValueError()
            value = json.loads(self.path.read_text(encoding='utf-8'))
            if value.get('version') != 1 or not isinstance(value['hosts'], list) or len(value['hosts']) > self.LIMIT:
                raise ValueError()
            rows = [validate(row) for row in value['hosts']]
            if len({row['id'] for row in rows}) != len(rows):
                raise ValueError()
            return sorted(rows, key=lambda row: (-row['last_used'], row['name'].casefold()))
        except (ValueError, KeyError, TypeError, AttributeError, OSError):
            raise RuntimeError('Não foi possível ler os favoritos SSH. O arquivo foi preservado.') from None

    def find(self, ident):
        row = next((row for row in self.list() if row['id'] == ident), None)
        if row is None:
            raise RuntimeError('Esse favorito não existe mais. Atualize a lista SSH.')
        return row

    def write(self, rows):
        content = json.dumps({'version': 1, 'hosts': rows}, ensure_ascii=False, indent=2)+'\n'
        fd, name = tempfile.mkstemp(prefix='.hosts-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(content); stream.flush(); os.fsync(stream.fileno())
            os.replace(name, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY)
            try: os.fsync(directory)
            finally: os.close(directory)
        finally:
            Path(name).unlink(missing_ok=True)

    def save(self, value, ident=None, password=None):
        with self.locked():
            rows = self.list()
            old = self.find(ident) if ident is not None else None
            profile = validate(dict(value, id=ident or uuid.uuid4().hex,
                                    last_used=old['last_used'] if old else 0))
            if old:
                rows = [profile if row['id'] == ident else row for row in rows]
            else:
                if len(rows) >= self.LIMIT:
                    raise RuntimeError('Limite de 64 favoritos. Remova um antes de adicionar outro.')
                rows.append(profile)
            if password is not None:
                self.validate_password(password)
            secret_path = self.secret_path(profile['id'])
            previous = secret_path.read_bytes() if secret_path.exists() else None
            changed = old is not None and self.endpoint(old) != self.endpoint(profile)
            content = previous
            if profile['mode'] != 'ssh' or changed:
                content = None
            if password:
                if profile['mode'] != 'ssh':
                    raise ValueError('Tailscale SSH não usa senha salva. Escolha SSH para autenticação por senha.')
                content = json.dumps({'endpoint': self.endpoint(profile), 'password': password}, ensure_ascii=False).encode('utf-8')
            elif password == '':
                content = None
            self.write_secret(profile['id'], content)
            try:
                self.write(rows)
            except OSError:
                self.write_secret(profile['id'], previous)
                raise
            return profile

    def remove(self, ident):
        with self.locked():
            rows = self.list()
            if not any(row['id'] == ident for row in rows):
                raise RuntimeError('Esse favorito já foi removido.')
            self.write([row for row in rows if row['id'] != ident])
            self.write_secret(ident, None)

    def used(self, ident):
        with self.locked():
            rows = self.list()
            profile = next((row for row in rows if row['id'] == ident), None)
            if profile is None:
                raise RuntimeError('Esse favorito já foi removido.')
            profile['last_used'] = int(time.time())
            self.write(rows)
