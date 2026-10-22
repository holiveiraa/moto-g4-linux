# SPDX-License-Identifier: MIT
"""ALSA playback controls enabled only by a validated hardware route profile."""
import array
import fcntl
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import wave

PROFILE = Path('/etc/moto-audio.json')
VOLUME_STATE = Path('/var/lib/moto-audio-volume.json')


def profile():
    try:
        value = json.loads(PROFILE.read_text())
        playback = value.get('playback', '')
        if not value.get('validated') or not (playback == 'moto_speaker' or re.fullmatch(r'hw:\d+,\d+', playback)):
            raise ValueError()
        return value
    except (OSError, ValueError, TypeError, AttributeError):
        raise RuntimeError('Áudio indisponível: falta inicializar e validar a rota do alto-falante.') from None


def volume(change):
    with open('/run/moto-volume.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _volume(change)


def _volume(change):
    value = profile()
    controls = value.get('volume_controls', [])
    if not controls:
        raise RuntimeError('Falta configurar o controle de volume desta placa.')
    for control in controls:
        name, minimum, maximum = control['name'], int(control['min']), int(control['max'])
        if not isinstance(name, str) or not 0 <= minimum < maximum <= 255:
            raise RuntimeError('Perfil de volume inválido.')
        card = str(int(value.get('card', 0)))
        result = subprocess.run(['amixer', '-c', card, 'cget', 'name=' + name], capture_output=True, text=True, timeout=2)
        found = re.search(r': values=(\d+)', result.stdout)
        if result.returncode or not found:
            raise RuntimeError('O controle de volume não está disponível.')
        current = int(found.group(1))
        target = max(minimum, min(maximum, current + (1 if change > 0 else -1) * max(1, (maximum-minimum)//20)))
        result = subprocess.run(['amixer', '-c', card, 'cset', 'name=' + name, str(target)], capture_output=True, timeout=2)
        if result.returncode:
            raise RuntimeError('Não foi possível alterar o volume.')
    percent = round(100 * (target-minimum) / (maximum-minimum))
    previous = VOLUME_STATE.read_text() if VOLUME_STATE.exists() else ''
    content = json.dumps({'percent': percent}) + '\n'
    if content != previous:
        temporary = VOLUME_STATE.with_suffix('.tmp')
        temporary.write_text(content)
        os.replace(temporary, VOLUME_STATE)
    return 'Volume · %d%%' % percent


def test_speaker():
    value = profile()
    rate, duration = 48000, .6
    # Low digital amplitude; mixer/amp limits must also be validated separately.
    samples = array.array('h', (int(4000 * math.sin(2*math.pi*660*i/rate) * min(1, i/500, (int(rate*duration)-i)/500))
                               for i in range(int(rate*duration))))
    with tempfile.TemporaryDirectory(prefix='moto-som-', dir='/run') as folder:
        path = Path(folder) / 'teste.wav'
        with wave.open(str(path), 'wb') as stream:
            stream.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
            stream.writeframes(samples.tobytes())
        result = subprocess.run(['aplay', '-D', value['playback'], str(path)], capture_output=True, timeout=5)
        if result.returncode:
            raise RuntimeError('Não foi possível reproduzir nesta saída.')
    return 'Tom reproduzido. Confirme se ouviu o som no alto-falante.'
