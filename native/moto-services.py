# SPDX-License-Identifier: MIT
"""Native device services. Wi-Fi uses the upstream control socket, never a shell.

Secrets travel over a root-only local socket, not process arguments or logs.
The UI calls slow operations on a worker thread; it stays responsive offline.
"""
import hashlib
from functools import lru_cache
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import shlex
import socket
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlsplit


def command(*args, timeout=4):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError((result.stderr.strip() or result.stdout.strip() or 'Comando falhou')[-300:])
    return result.stdout.strip()


class WPA:
    def __enter__(self):
        self.folder = tempfile.TemporaryDirectory(prefix='moto-wpa-', dir='/run')
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.sock.bind(self.folder.name + '/ctrl')
        self.sock.settimeout(4)
        self.sock.connect('/run/wpa_supplicant/wlan0')
        return self

    def __exit__(self, *args):
        self.sock.close()
        self.folder.cleanup()

    def ask(self, value, ok=False):
        self.sock.send(value.encode())
        answer = self.sock.recv(65536).decode(errors='replace').strip()
        if answer.startswith(('FAIL', 'UNKNOWN COMMAND')) or (ok and answer != 'OK'):
            # Never echo a command: SET_NETWORK may contain a credential.
            raise RuntimeError('O serviço Wi-Fi recusou a operação')
        return answer

    def status(self):
        return dict(line.split('=', 1) for line in self.ask('STATUS').splitlines() if '=' in line)


def wifi_scan():
    with WPA() as wpa:
        try:
            wpa.ask('SCAN', ok=True)
        except RuntimeError:
            pass  # A firmware scan may already be pending.
        time.sleep(2)
        rows = []
        seen = set()
        for line in wpa.ask('SCAN_RESULTS').splitlines()[1:]:
            fields = line.split('\t', 4)
            if len(fields) != 5 or not fields[4]:
                continue
            bssid, frequency, signal_dbm, flags, ssid = fields
            encoded = _wifi_module().ssid_bytes('"'+ssid+'"')
            secure = 'PSK' in flags
            kind = 'psk' if secure else 'other' if any(s in flags for s in ('WPA', 'WEP', 'EAP')) else 'open'
            if (encoded, kind) in seen:
                continue
            seen.add((encoded, kind))
            try:
                ssid = encoded.decode('utf-8')
                printable = all(c.isprintable() for c in ssid)
            except UnicodeError:
                ssid, printable = encoded.decode('utf-8', errors='replace'), False
            supported = 'PSK' in flags or not any(s in flags for s in ('WPA', 'WEP', 'EAP'))
            rows.append({'ssid': ssid, 'ssid_hex': encoded.hex(), 'signal': int(signal_dbm), 'secure': secure,
                         'supported': supported and printable, 'band': '5 GHz' if int(frequency) > 4900 else '2,4 GHz'})
        return sorted(rows, key=lambda row: -row['signal'])[:12]


@lru_cache(maxsize=1)
def _wifi_module():
    spec = importlib.util.spec_from_file_location('moto_wifi', Path(__file__).with_name('moto-wifi.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wifi_profiles():
    return _wifi_module().WifiProfiles(WPA, renew=_wifi_dhcp)


def wifi_saved():
    return wifi_profiles().profiles()


def wifi_connect_saved(profile):
    return wifi_profiles().connect_saved(profile)


def wifi_save():
    return wifi_profiles().save()


def wifi_forget(profile):
    return wifi_profiles().forget(profile)


def wifi_join(ssid, password, secure=True, hidden=False):
    return wifi_profiles().connect_new(ssid, password, secure, hidden)


def wifi_connect(ssid, password, secure=True):
    # Compatibility for existing callers; the UI uses structured results.
    return wifi_join(ssid, password, secure)['message']


def _wifi_dhcp():
    # Start a fresh DHCP discovery when changing subnets. USB stays untouched.
    pidfile = Path('/run/udhcpc-wlan0.pid')
    if pidfile.exists():
        pid = int(pidfile.read_text())
        try:
            if 'udhcpc' in Path(f'/proc/{pid}/cmdline').read_text():
                os.kill(pid, signal.SIGUSR2)
                os.kill(pid, signal.SIGUSR1)
        except FileNotFoundError:
            pidfile.unlink(missing_ok=True)
    if not pidfile.exists():
        command('udhcpc', '-b', '-i', 'wlan0', '-p', str(pidfile), '-t', '5', '-T', '2', timeout=15)
    os.sync()


def tailscale_auth_url(value):
    """Accept only the official login URL, and never expose a stale URL as login."""
    if not isinstance(value, str) or len(value) > 2048 or any(c.isspace() for c in value):
        return ''
    try:
        url = urlsplit(value)
        if (url.scheme == 'https' and url.hostname == 'login.tailscale.com'
                and url.port in (None, 443) and url.username is None and url.password is None
                and url.path.startswith('/')):
            return value
    except ValueError:
        pass
    return ''


def tailscale_view(result, wifi_connected=None):
    own = result.get('Self') or {}
    state = result.get('BackendState', 'Indisponível')
    health = [s for s in (result.get('Health') or []) if isinstance(s, str)]
    expired = own.get('Expired') is True
    peers = sorted((p for p in (result.get('Peer') or {}).values() if p.get('Online')),
                   key=lambda p: p.get('HostName', ''))
    ip = next(iter(result.get('TailscaleIPs') or []), '')
    view = {'state': state, 'url': '', 'ip': ip, 'health': health,
            'name': own.get('HostName', 'moto-g4-linux'),
            'online': own.get('Online'), 'expired': expired,
            'key_expiry': own.get('KeyExpiry') or '', 'connected': False,
            'can_ssh': state == 'Running' and bool(ip) and not expired,
            'peers': [{'name': p.get('HostName', ''), 'ip': next(iter(p.get('TailscaleIPs') or []), '')}
                      for p in peers[:8]]}
    if state == 'NeedsLogin':
        kind, title = 'login', 'Autorizar este Moto'
        detail = 'Use o QR abaixo. A identidade fica salva no aparelho após autorizar.'
        view['url'] = tailscale_auth_url(result.get('AuthURL', ''))
    elif state == 'NeedsMachineAuth':
        kind, title = 'approval', 'Aguardando aprovação do aparelho'
        detail = 'O login foi feito. Um administrador precisa aprovar este Moto no Tailscale.'
    elif state == 'Stopped':
        kind, title = 'paused', 'VPN pausada neste Moto'
        detail = 'Toque em Retomar. Pausar não apaga o cadastro.'
    elif state == 'Running' and expired:
        kind, title = 'expired', 'O cadastro precisa ser renovado'
        detail = 'A chave foi marcada como expirada pelo Tailscale. Toque em Conectar para verificar o login.'
    elif wifi_connected is False:
        kind, title = 'network', 'Conecte o Wi-Fi primeiro'
        detail = 'Uma queda de Wi-Fi não exige cadastrar o Moto novamente.'
    elif state == 'Running' and own.get('Online') is True:
        view['connected'] = True
        kind, title = ('warning', 'VPN ativa · há um aviso') if health else ('connected', 'VPN ativa')
        detail = 'Seu cadastro está salvo. Você já pode abrir uma conexão SSH.'
    elif state == 'Running' and own.get('Online') is False:
        kind, title = 'degraded', 'VPN com conexão instável'
        detail = 'O cadastro está salvo, mas o servidor de coordenação não responde. Conexões SSH existentes ainda podem funcionar.'
    elif state in ('Running', 'Starting'):
        kind, title = 'connecting', 'Reconectando à sua rede'
        detail = 'Aguarde a rede responder. O cadastro será preservado.'
    else:
        kind, title = 'unavailable', 'Serviço Tailscale indisponível'
        detail = 'Não foi possível confirmar a conexão. Isso não significa que o cadastro expirou.'
    view.update(kind=kind, title=title, detail=detail)
    return view


def tailscale_state(wifi_connected=None):
    try:
        # Some CLI failures still include a valid JSON status on stdout.
        process = subprocess.run(['tailscale', 'status', '--json'], capture_output=True,
                                 text=True, timeout=4)
        result = json.loads(process.stdout)
        if not isinstance(result, dict):
            raise ValueError('Invalid status')
        return tailscale_view(result, wifi_connected)
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired):
        return tailscale_view({}, wifi_connected)


_tailscale_connect_lock = threading.Lock()


def tailscale_connect():
    if not _tailscale_connect_lock.acquire(blocking=False):
        raise RuntimeError('Uma conexão já está em andamento. Aguarde alguns segundos.')
    try:
        # Keep existing policy and identity. No logout, force-reauth or key reset.
        try:
            command('tailscale', 'up', '--accept-dns=false', '--accept-routes=false', '--netfilter-mode=off',
                    '--hostname=moto-g4-linux', '--timeout=8s', timeout=12)
        except (RuntimeError, subprocess.TimeoutExpired):
            state = tailscale_state()
            if state['kind'] != 'unavailable':
                return state
            raise RuntimeError('O serviço não respondeu. Confira o Wi-Fi e tente novamente; seu cadastro foi preservado.') from None
        state = tailscale_state()
        return state
    finally:
        _tailscale_connect_lock.release()


def tailscale_reconnect():
    if not _tailscale_connect_lock.acquire(blocking=False):
        raise RuntimeError('Uma conexão já está em andamento. Aguarde alguns segundos.')
    try:
        # Restart only the local daemon; never Wi-Fi, logout, keys or remote policy.
        command('rc-service', 'moto-tailscale', 'restart', timeout=18)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            state = tailscale_state()
            if state['kind'] in ('connected', 'warning', 'login', 'approval', 'paused'):
                return state
            time.sleep(.5)
        return tailscale_state()
    finally:
        _tailscale_connect_lock.release()


def ssh_auth_url_from_pane(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()][-6:]
    if not lines or not any('Tailscale SSH requires an additional check.' in line for line in lines):
        return ''
    match = re.fullmatch(r'# To authenticate, visit: (https://\S+)', lines[-1])
    return tailscale_auth_url(match.group(1)) if match else ''


def ssh_auth_request():
    """Read only the active SSH pane's pending check, never archive terminal text."""
    try:
        fields = command('tmux', '-L', 'moto', 'display-message', '-p', '-t', 'moto',
                         '#{pane_id}|#{pane_current_command}|#{@moto_ssh_mode}|#{pane_start_command}', timeout=1).split('|', 3)
        if len(fields) == 4:
            pane, process, mode, started = fields
        else:
            pane, process, started = fields
            mode = ''
        # The app's noninteractive launcher retains ash as foreground group
        # leader on this old kernel even while its SSH child awaits approval.
        args = shlex.split(started)
        managed = (mode in ('ssh', 'tailscale') and len(args) == 2
                   and args[0] == '/usr/sbin/moto-ssh-launch'
                   and re.fullmatch(r'(?:[a-f0-9]{32}|[a-z][a-z0-9_-]{0,31})', args[1]))
        if (process not in ('ssh', 'tailscale', 'ash', 'sh', 'python3') or not re.fullmatch(r'%\d+', pane)
                or not managed):
            return {}
        text = command('tmux', '-L', 'moto', 'capture-pane', '-p', '-J', '-S', '-12',
                       '-t', pane, timeout=1)
        url = ssh_auth_url_from_pane(text)
        return {'url': url, 'pane': pane} if url else {}
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired):
        return {}


def volume(change):
    if not Path('/proc/asound/cards').exists() or 'no soundcards' in Path('/proc/asound/cards').read_text():
        return 'Áudio indisponível · driver em desenvolvimento'
    spec = importlib.util.spec_from_file_location('moto_audio', Path(__file__).with_name('moto-audio.py'))
    audio = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audio)
    return audio.volume(change)


def read(path, default='?'):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return default


def snapshot():
    try:
        with WPA() as wpa:
            wifi = wpa.status()
    except (OSError, RuntimeError):
        wifi = {}
    memory = dict(line.split(':', 1) for line in read('/proc/meminfo', '').splitlines() if ':' in line)
    mem = lambda key: int(memory.get(key, '0 kB').strip().split()[0]) // 1024
    disk = os.statvfs('/')
    return {'wifi': wifi, 'vpn': tailscale_state(wifi.get('wpa_state') == 'COMPLETED'),
            'ssh_auth': ssh_auth_request(), 'battery': read('/sys/class/power_supply/battery/capacity'),
            'charging': read('/sys/class/power_supply/battery/status'),
            'temperature': int(read('/sys/class/power_supply/battery/temp', '0')) / 10,
            'ram_free': mem('MemAvailable') or mem('MemFree'), 'ram_total': mem('MemTotal'),
            'disk_free': disk.f_bavail * disk.f_frsize // (1024 ** 2),
            'uptime': int(float(read('/proc/uptime', '0').split()[0])),
            'persistent': Path('/etc/moto-persistent').exists(),
            'audio': Path('/dev/snd/controlC0').exists()}
