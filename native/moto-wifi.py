# SPDX-License-Identifier: MIT
"""Saved Wi-Fi profile operations over the existing wpa_supplicant socket.

Public profile dictionaries contain no credentials. IDs are verified against
their SSID/security fingerprint immediately before a mutation.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import re
import subprocess
import time
import uuid


def ssid_bytes(value):
    if not value.startswith('"'):
        try:
            return bytes.fromhex(value)
        except ValueError:
            raise RuntimeError('O serviço retornou um nome de rede inválido.') from None
    if not value.endswith('"'):
        raise RuntimeError('O serviço retornou um nome de rede inválido.')
    raw, result, i = value[1:-1].encode('utf-8'), bytearray(), 0
    escapes = {ord('n'): 10, ord('r'): 13, ord('t'): 9, ord('e'): 27}
    while i < len(raw):
        if raw[i] == 92 and i+1 < len(raw):
            if raw[i+1] == ord('x') and i+3 < len(raw):
                try:
                    result.append(int(raw[i+2:i+4], 16)); i += 4; continue
                except ValueError:
                    pass
            result.append(escapes.get(raw[i+1], raw[i+1])); i += 2
        else:
            result.append(raw[i]); i += 1
    return bytes(result)


def fingerprint(profile):
    return tuple(profile.get(key) for key in ('ssid_hex', 'key_mgmt', 'bssid', 'hidden', 'tag'))


class WifiProfiles:
    def __init__(self, factory, config='/etc/wpa_supplicant.conf', lock='/run/moto-wifi.lock', renew=None):
        self.factory, self.config, self.lock = factory, Path(config), Path(lock)
        self.renew = renew or (lambda: None)

    @contextmanager
    def transaction(self):
        with self.lock.open('a') as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('Já existe uma operação Wi-Fi em andamento.') from None
            with self.factory() as wpa:
                yield wpa

    @staticmethod
    def get(wpa, ident, field, default=''):
        try:
            return wpa.ask(f'GET_NETWORK {ident} {field}')
        except RuntimeError:
            return default

    def profiles(self, wpa=None):
        if wpa is None:
            with self.factory() as connection:
                return self.profiles(connection)
        result = []
        for row in wpa.ask('LIST_NETWORKS').splitlines()[1:]:
            columns = row.split('\t')
            if len(columns) < 4 or not columns[0].isdigit():
                continue
            ident, flags = columns[0], columns[-1]
            raw = self.get(wpa, ident, 'ssid')
            if not raw:
                continue
            encoded = ssid_bytes(raw)
            if not 1 <= len(encoded) <= 32:
                continue
            mode = self.get(wpa, ident, 'key_mgmt', 'UNKNOWN')
            try:
                priority = int(self.get(wpa, ident, 'priority', '0'))
            except ValueError:
                priority = 0
            result.append({'id': ident, 'ssid_hex': encoded.hex(),
                'ssid': ''.join(c if c.isprintable() else '�' for c in encoded.decode('utf-8', errors='replace')),
                'key_mgmt': mode, 'secure': mode != 'NONE',
                'supported': mode == 'NONE' or 'WPA-PSK' in mode.split(),
                'bssid': self.get(wpa, ident, 'bssid', 'any'),
                'hidden': self.get(wpa, ident, 'scan_ssid', '0') == '1',
                'tag': self.get(wpa, ident, 'id_str'),
                'priority': priority, 'enabled': '[DISABLED]' not in flags,
                'current': '[CURRENT]' in flags})
        return sorted(result, key=lambda profile: (not profile['current'], -profile['priority'], int(profile['id'])))

    def verified(self, wpa, requested):
        if not isinstance(requested, dict) or not re.fullmatch(r'\d+', str(requested.get('id', ''))):
            raise ValueError('Perfil de rede inválido.')
        profile = next((row for row in self.profiles(wpa) if row['id'] == requested['id']), None)
        if profile is None or fingerprint(profile) != fingerprint(requested):
            raise RuntimeError('Essa rede mudou. Atualize a lista antes de conectar.')
        return profile

    @staticmethod
    def restore_enabled(wpa, before, selected=None):
        for row in before:
            enable = row['enabled'] or row['id'] == selected
            wpa.ask(('ENABLE_NETWORK ' if enable else 'DISABLE_NETWORK ') + row['id'], ok=True)

    def restore(self, wpa, before, status):
        previous = status.get('id')
        if previous in {row['id'] for row in before}:
            wpa.ask('SELECT_NETWORK ' + previous, ok=True)
        self.restore_enabled(wpa, before)
        if previous is None and status.get('wpa_state') in ('DISCONNECTED', 'INACTIVE', 'INTERFACE_DISABLED'):
            wpa.ask('DISCONNECT', ok=True)

    def save(self, wpa=None):
        if wpa is None:
            with self.transaction() as connection:
                return self.save(connection)
        try:
            if self.config.exists():
                self.config.chmod(0o600)
            wpa.ask('SET update_config 1', ok=True)
            wpa.ask('SAVE_CONFIG', ok=True)
            self.config.chmod(0o600)
        except (RuntimeError, OSError):
            return False
        return True

    def select(self, wpa, ident, before, status, created=False):
        was_current = status.get('id') == ident and status.get('wpa_state') == 'COMPLETED'
        try:
            if not was_current:
                wpa.ask('SELECT_NETWORK ' + ident, ok=True)
                deadline = time.monotonic()+35
                while time.monotonic() < deadline:
                    state = wpa.status()
                    if state.get('wpa_state') == 'COMPLETED' and state.get('id') == ident:
                        break
                    time.sleep(.5)
                else:
                    raise RuntimeError('Não conectou. A rede anterior será restaurada. Você pode atualizar a senha.')
            self.restore_enabled(wpa, before, selected=ident)
        except (RuntimeError, OSError):
            try:
                if created:
                    wpa.ask('REMOVE_NETWORK ' + ident, ok=True)
                self.restore(wpa, before, status)
            except (RuntimeError, OSError):
                raise RuntimeError('A tentativa falhou e a rede anterior não respondeu. Use Wi-Fi para reconectar.') from None
            raise
        saved = self.save(wpa)
        warning = ''
        try:
            if not was_current:
                self.renew()
        except (RuntimeError, OSError, ValueError, subprocess.SubprocessError):
            warning = ' Aguardando endereço IP; confira os detalhes da rede.'
        return {'connected': True, 'saved': saved, 'id': ident,
                'message': ('Conectado e salvo.' if saved else 'Conectado, mas não foi possível salvar. Toque em Salvar novamente.') + warning}

    def connect_saved(self, requested):
        with self.transaction() as wpa:
            profile = self.verified(wpa, requested)
            if not profile['supported']:
                raise RuntimeError('Esse perfil usa uma autenticação ainda não suportada pela interface.')
            before, status = self.profiles(wpa), wpa.status()
            return self.select(wpa, profile['id'], before, status)

    def connect_new(self, ssid, password, secure=True, hidden=False):
        encoded = ssid.encode('utf-8')
        if not 1 <= len(encoded) <= 32 or any(c in ssid for c in '\x00\r\n'):
            raise ValueError('O nome da rede deve ter de 1 a 32 bytes, sem quebras de linha.')
        if secure and not (8 <= len(password.encode()) <= 63 or re.fullmatch(r'[a-fA-F0-9]{64}', password)):
            raise ValueError('A senha WPA2 precisa de 8 a 63 bytes.')
        with self.transaction() as wpa:
            before, status = self.profiles(wpa), wpa.status()
            ident = wpa.ask('ADD_NETWORK')
            if not ident.isdigit():
                raise RuntimeError('Não foi possível criar a rede.')
            try:
                wpa.ask(f'SET_NETWORK {ident} ssid {encoded.hex()}', ok=True)
                wpa.ask(f'SET_NETWORK {ident} key_mgmt ' + ('WPA-PSK' if secure else 'NONE'), ok=True)
                if secure:
                    psk = password if len(password) == 64 else hashlib.pbkdf2_hmac('sha1', password.encode(), encoded, 4096, 32).hex()
                    wpa.ask(f'SET_NETWORK {ident} psk {psk}', ok=True)
                if hidden:
                    wpa.ask(f'SET_NETWORK {ident} scan_ssid 1', ok=True)
                wpa.ask(f'SET_NETWORK {ident} priority 10', ok=True)
                wpa.ask(f'SET_NETWORK {ident} id_str "moto-{uuid.uuid4().hex}"', ok=True)
            except (RuntimeError, OSError):
                wpa.ask('REMOVE_NETWORK ' + ident, ok=True)
                raise
            # Keep old profiles; equal SSIDs do not prove equivalent credentials.
            return self.select(wpa, ident, before, status, created=True)

    def forget(self, requested):
        with self.transaction() as wpa:
            profile = self.verified(wpa, requested)
            old_status = wpa.status()
            rows = self.profiles(wpa)
            old_current = next((row for row in rows if row['id'] == old_status.get('id')), None)
            old_tag, restore_tag, assigned = '', '', False
            if old_current:
                old_tag = old_current['tag']
                if old_tag in ('', '""', 'NULL'):
                    # A non-secret persistent tag makes rollback unambiguous even
                    # when IDs are renumbered and same-SSID passwords differ.
                    restore_tag = '"moto-'+uuid.uuid4().hex+'"'
                    wpa.ask(f'SET_NETWORK {old_current["id"]} id_str {restore_tag}', ok=True)
                    expected = restore_tag.strip('"')
                    restore_tag = self.get(wpa, old_current['id'], 'id_str')
                    if restore_tag.strip('"') != expected:
                        wpa.ask(f'SET_NETWORK {old_current["id"]} id_str ""', ok=True)
                        raise RuntimeError('Não foi possível preparar a recuperação. Nenhum perfil foi removido.')
                    assigned = True
                elif sum(row['tag'] == old_tag for row in rows) == 1:
                    restore_tag = old_tag
                else:
                    raise RuntimeError('Este perfil tem um identificador compartilhado. Nada foi esquecido; revise os perfis antes de remover.')
            # Do not discard a connected-but-unsaved profile during rollback.
            # Refuse removal unless the entire current state can be checkpointed.
            if not self.save(wpa):
                if assigned:
                    wpa.ask(f'SET_NETWORK {old_current["id"]} id_str ""', ok=True)
                raise RuntimeError('Não foi possível salvar um ponto de recuperação. Nenhum perfil foi removido.')
            original = self.config.read_bytes()
            wpa.ask('REMOVE_NETWORK ' + profile['id'], ok=True)
            if not self.save(wpa):
                # Restore the known private file, not credentials through UI/logs.
                temporary = self.config.with_suffix('.restore')
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(original); stream.flush(); os.fsync(stream.fileno())
                os.replace(temporary, self.config)
                wpa.ask('RECONFIGURE', ok=True)
                if old_current:
                    restored_profiles = self.profiles(wpa)
                    matches = [row for row in restored_profiles if row['tag'] == restore_tag]
                    if len(matches) != 1:
                        raise RuntimeError('Perfis restaurados, mas não foi possível identificar a conexão anterior. Escolha uma rede salva.')
                    wpa.ask('SELECT_NETWORK ' + matches[0]['id'], ok=True)
                    self.restore_enabled(wpa, restored_profiles, selected=matches[0]['id'])
                elif old_status.get('wpa_state') in ('DISCONNECTED', 'INACTIVE', 'INTERFACE_DISABLED'):
                    wpa.ask('DISCONNECT', ok=True)
                raise RuntimeError('Não foi possível esquecer a rede; a configuração salva foi restaurada.')
            os.sync()
            return 'Perfil removido. As outras redes salvas foram preservadas.'
