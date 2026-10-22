# SPDX-License-Identifier: MIT
"""Bounded ALSA recording and Groq dictation; credentials never enter argv/logs."""
import array
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
import wave

CONFIG = Path('/root/.config/moto-linux/groq.json')
MODEL = 'whisper-large-v3-turbo'
API = 'https://api.groq.com/openai/v1/'
MAX_SECONDS = 60
MAX_BYTES = 7 * 1024 * 1024


def settings():
    try:
        value = json.loads(CONFIG.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save_key(key):
    key = key.strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{20,256}', key):
        raise ValueError('Confira a chave: cole somente o token da Groq, sem espaços.')
    CONFIG.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    CONFIG.parent.chmod(0o700)
    fd, name = tempfile.mkstemp(prefix='.groq-', dir=CONFIG.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump({'api_key': key, 'model': MODEL, 'language': 'pt'}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, CONFIG)
        directory = os.open(CONFIG.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(name).unlink(missing_ok=True)


def remove_key():
    CONFIG.unlink(missing_ok=True)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(path, data=None, content_type=None, timeout=25):
    key = settings().get('api_key', '')
    if not key:
        raise RuntimeError('Cadastre sua chave Groq em Configurar ditado.')
    headers = {'Authorization': 'Bearer ' + key, 'User-Agent': 'MotoLinux/0.1',
               'Accept': 'application/json'}
    if content_type:
        headers['Content-Type'] = content_type
    req = Request(API + path, data=data, headers=headers)
    try:
        with build_opener(NoRedirect()).open(req, timeout=timeout) as response:
            raw = response.read(512 * 1024 + 1)
        if len(raw) > 512 * 1024:
            raise RuntimeError('Resposta grande demais. O áudio foi preservado para tentar novamente.')
        return json.loads(raw)
    except HTTPError as exc:
        # Do not display upstream bodies: they can echo request/credential data.
        messages = {401: 'Chave recusada pela Groq. Confira ou substitua a chave.',
                    403: 'A conta Groq não autorizou esta operação.',
                    413: 'Áudio grande demais. Grave um trecho menor.',
                    429: 'Limite da Groq atingido. Aguarde e tente novamente.',
                    400: 'A Groq recusou o formato do áudio ou os parâmetros.'}
        raise RuntimeError(messages.get(exc.code, 'Groq indisponível (HTTP %d). Tente novamente.' % exc.code)) from None
    except (URLError, OSError, TimeoutError):
        raise RuntimeError('Sem resposta da Groq. Confira o Wi-Fi; tente novamente quando conectar.') from None
    except (ValueError, UnicodeError):
        raise RuntimeError('Resposta inválida da Groq. Tente novamente.') from None


def test_key():
    value = request('models')
    models = value.get('data', []) if isinstance(value, dict) else []
    if not any(m.get('id') == MODEL for m in models if isinstance(m, dict)):
        raise RuntimeError('Chave aceita, mas o modelo de ditado não está disponível nesta conta.')
    return 'Chave validada · modelo disponível. Nenhum áudio foi enviado.'


def transcribe(path):
    path = Path(path)
    inspect_wave(path)
    if path.stat().st_size > MAX_BYTES:
        raise RuntimeError('Gravação grande demais; limite local de 7 MB.')
    boundary = 'moto-' + uuid.uuid4().hex
    chunks = []
    for name, value in {'model': MODEL, 'language': 'pt', 'response_format': 'json',
                        'prompt': 'Codex, Tailscale, Ubuntu, Linux, SSH, Groq.'}.items():
        chunks.append(('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' %
                       (boundary, name, value)).encode())
    chunks.append(('--%s\r\nContent-Disposition: form-data; name="file"; filename="ditado.wav"\r\n'
                   'Content-Type: audio/wav\r\n\r\n' % boundary).encode())
    chunks.extend([path.read_bytes(), ('\r\n--%s--\r\n' % boundary).encode()])
    value = request('audio/transcriptions', b''.join(chunks), 'multipart/form-data; boundary=' + boundary, 60)
    text = value.get('text', '') if isinstance(value, dict) else ''
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError('Nenhuma fala reconhecida. Grave novamente, mais perto do microfone.')
    return text.strip()


def inspect_wave(path):
    try:
        with wave.open(str(path), 'rb') as audio:
            duration = audio.getnframes() / audio.getframerate()
            if (audio.getsampwidth() != 2 or audio.getnchannels() not in (1, 2)
                    or not .25 <= duration <= MAX_SECONDS + 1):
                raise ValueError()
            raw = audio.readframes(min(audio.getnframes(), audio.getframerate() * MAX_SECONDS))
    except (OSError, ValueError, EOFError, wave.Error):
        raise RuntimeError('Gravação inválida ou muito curta. Grave novamente.') from None
    samples = array.array('h', raw)
    if not samples:
        raise RuntimeError('A captura não produziu amostras de áudio.')
    rms = math.sqrt(sum(v*v for v in samples) / len(samples))
    if max(abs(v) for v in samples) < 24 or rms < 4:
        raise RuntimeError('Áudio praticamente silencioso. Confira o microfone e grave novamente.')
    return {'seconds': duration, 'rms': rms, 'peak': max(abs(v) for v in samples)}


def capture_device():
    try:
        lines = Path('/proc/asound/pcm').read_text().splitlines()
    except OSError:
        lines = []
    # Prefer multimedia PCM, not voice-call/hostless/compressed DSP interfaces.
    for line in lines:
        if 'capture' not in line or not re.match(r'^\d+-\d+:', line):
            continue
        if re.search(r'\b(?:multi ?media1|usb audio)\b', line, re.I):
            card, device = line.split(':', 1)[0].split('-')
            return 'hw:%d,%d' % (int(card), int(device))
    return ''


class Recorder:
    def __init__(self):
        self.process = None
        self.folder = None
        self.path = None
        self.started = 0
        self.meter = 0.0
        self.error = ''

    @property
    def recording(self):
        return self.process is not None and self.process.poll() is None

    def start(self):
        if self.recording:
            return
        device = capture_device()
        if not device:
            raise RuntimeError('Microfone indisponível: a placa de áudio ainda não inicializou.')
        self.discard()
        self.folder = tempfile.TemporaryDirectory(prefix='moto-ditado-', dir='/run')
        os.chmod(self.folder.name, 0o700)
        self.path = Path(self.folder.name) / 'voz.wav'
        self.error = ''
        self.started = time.monotonic()
        # 48 kHz is native to many QDSP PCM paths; Groq performs downsampling.
        self.process = subprocess.Popen(['arecord', '-D', device, '-t', 'wav', '-f', 'S16_LE',
                                         '-r', '48000', '-c', '1', '-d', str(MAX_SECONDS), str(self.path)],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        threading.Thread(target=self._meter, daemon=True).start()

    def _meter(self):
        process, path = self.process, self.path
        while process.poll() is None:
            try:
                with path.open('rb') as stream:
                    stream.seek(max(44, path.stat().st_size - 9600))
                    raw = stream.read(9600)
                raw = raw[:len(raw)//2*2]
                samples = array.array('h', raw)
                rms = math.sqrt(sum(v*v for v in samples) / max(1, len(samples)))
                self.meter = min(1.0, rms / 4500)
            except OSError:
                pass
            time.sleep(.12)
        process.stderr.read()  # Never leak ALSA diagnostics into the credential UI.
        if process.returncode not in (0, 1, -signal.SIGINT):
            self.error = 'Não foi possível capturar áudio nesta entrada.'

    def stop(self):
        process, path = self.process, self.path
        if process is not None and process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        if not path or not path.is_file():
            raise RuntimeError(self.error or 'Ainda não há gravação.')
        return path

    def discard(self):
        process, folder = self.process, self.folder
        self.process, self.folder, self.path = None, None, None
        if process is not None and process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        if folder:
            folder.cleanup()
        self.meter = 0.0


def safe_text(text):
    # Shells without bracketed paste must not execute embedded CR/LF or escapes.
    return ' '.join(''.join(' ' if c.isspace() else '' if unicodedata.category(c).startswith('C')
                            else c for c in text).split())[:20000]


def pane_target():
    result = subprocess.run(['tmux', '-L', 'moto', 'display-message', '-p', '-t', 'moto',
                             '#{pane_id}|#{window_name}'], capture_output=True, text=True, timeout=2)
    fields = result.stdout.strip().split('|', 1)
    if result.returncode or len(fields) != 2 or not re.fullmatch(r'%\d+', fields[0]):
        raise RuntimeError('Nenhum terminal disponível para receber o ditado.')
    return fields


def insert_text(target, text):
    text = safe_text(text)
    if not text:
        raise RuntimeError('O texto está vazio.')
    if not re.fullmatch(r'%\d+', target):
        raise ValueError('Terminal inválido')
    result = subprocess.run(['tmux', '-L', 'moto', 'list-panes', '-a', '-F', '#{pane_id}'],
                            capture_output=True, text=True, timeout=2)
    if result.returncode or target not in result.stdout.splitlines():
        raise RuntimeError('A aba de destino foi fechada. Escolha outra aba e abra o ditado novamente.')
    name = 'moto-ditado-' + uuid.uuid4().hex
    loaded = False
    try:
        result = subprocess.run(['tmux', '-L', 'moto', 'load-buffer', '-b', name, '-'],
                                input=text.encode('utf-8'), capture_output=True, timeout=2)
        if result.returncode:
            raise RuntimeError('Não foi possível preparar o texto para o terminal.')
        loaded = True
        subprocess.run(['tmux', '-L', 'moto', 'send-keys', '-t', target, '-X', 'cancel'],
                       capture_output=True, timeout=2)
        result = subprocess.run(['tmux', '-L', 'moto', 'paste-buffer', '-p', '-d', '-b', name, '-t', target],
                                capture_output=True, timeout=2)
        if result.returncode:
            raise RuntimeError('Não foi possível inserir; o texto continua disponível para revisão.')
    finally:
        if loaded:
            subprocess.run(['tmux', '-L', 'moto', 'delete-buffer', '-b', name],
                           capture_output=True, timeout=2)


if __name__ == '__main__':
    if sys.argv[1:] != ['save-key-stdin']:
        raise SystemExit('Use save-key-stdin; a chave deve chegar pela entrada padrão.')
    try:
        incoming = json.loads(sys.stdin.buffer.read(2048))
        save_key(incoming['api_key'])
    except (OSError, ValueError, KeyError, TypeError):
        raise SystemExit('Não foi possível salvar a chave.') from None
    print('Chave salva no Moto. Nenhuma chave foi exibida.')
