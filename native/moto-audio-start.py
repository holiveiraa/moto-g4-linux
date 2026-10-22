#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Initialize native athene audio before WCNSS can allocate the shared pool.

Keep the vendor firmware, PAS authentication and kernel unchanged. A failed
activation is never retried in the same boot; USB rescue starts independently.
"""
import fcntl
import json
import os
from pathlib import Path
import platform
import subprocess
import time
import wave

PROFILE = Path('/etc/moto-audio.json')
VOLUME_STATE = Path('/var/lib/moto-audio-volume.json')


def run(*args, timeout=5):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed: {result.stderr.strip()[-250:]}')
    return result.stdout


def subsystem(name):
    matches = [p.parent for p in Path('/sys/bus/msm_subsys/devices').glob('*/name')
               if p.read_text().strip() == name]
    if len(matches) != 1:
        raise RuntimeError(f'Expected one {name} subsystem')
    return matches[0]


def mount_firmware():
    if Path('/firmware/image/adsp.mdt').is_file():
        return
    devices = [p.parent.name for p in Path('/sys/class/block').glob('mmcblk0p*/uevent')
               if 'PARTNAME=modem' in p.read_text().splitlines()]
    if len(devices) != 1:
        raise RuntimeError('Firmware partition is ambiguous or missing')
    Path('/firmware').mkdir(exist_ok=True)
    run('mount', '-t', 'ext4', '-o', 'ro,noload', '/dev/' + devices[0], '/firmware')
    if not Path('/firmware/image/adsp.mdt').is_file():
        raise RuntimeError('ADSP firmware missing')


def initialize():
    if os.geteuid() or platform.machine() != 'aarch64':
        raise RuntimeError('Requires native ARM64 root session')
    if not Path('/proc/device-tree/model').read_bytes().startswith(b'Athene'):
        raise RuntimeError('Unsupported hardware')
    profile = json.loads(PROFILE.read_text())
    if profile.get('model') != 'athene-cs35l34' or not profile.get('validated'):
        raise RuntimeError('No validated hardware route profile')
    adsp, wcnss = subsystem('adsp'), subsystem('wcnss')
    ready = Path('/run/moto-audio-ready')
    if (ready.exists() and (adsp / 'state').read_text().strip() == 'ONLINE'
            and 'msm8952-cs35l34-snd-card' in Path('/proc/asound/cards').read_text()):
        print('Native audio already ready; active streams preserved', flush=True)
        return
    # A partial initialization must never leave a previous ready marker behind.
    # Keep the separate attempted marker: failure still requires a fresh boot.
    ready.unlink(missing_ok=True)
    if (adsp / 'state').read_text().strip() != 'ONLINE':
        if (wcnss / 'state').read_text().strip() == 'ONLINE':
            raise RuntimeError('Wi-Fi started before audio; reboot required, not retrying ADSP')
        mount_firmware()
        marker = Path('/run/moto-adsp-attempted')
        with marker.open('x') as stream:
            stream.write('Single ADSP activation for this boot\n')
        fd = os.open('/sys/kernel/boot_adsp/boot', os.O_WRONLY)
        try:
            if os.write(fd, b'1\n') != 2:
                raise RuntimeError('Incomplete ADSP activation request')
        finally:
            os.close(fd)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if 'msm8952-cs35l34-snd-card' in Path('/proc/asound/cards').read_text():
            break
        time.sleep(.2)
    else:
        raise RuntimeError('Audio card did not register')
    if (adsp / 'state').read_text().strip() != 'ONLINE':
        raise RuntimeError('ADSP is not online')
    for name, value in profile['route']:
        run('amixer', '-c', '0', 'cset', 'name=' + name, str(value))
    # Opening the softvol PCM creates its persistent card control. Only silence
    # is played before restoring the saved volume, so no default-volume burst.
    path = Path('/run/moto-audio-silence.wav')
    try:
        with wave.open(str(path), 'wb') as stream:
            stream.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
            stream.writeframes(bytes(4800 * 2))
        run('aplay', '-q', '-D', 'moto_speaker', str(path))
    finally:
        path.unlink(missing_ok=True)
    try:
        volume = int(json.loads(VOLUME_STATE.read_text())['percent'])
        if not 0 <= volume <= 100:
            raise ValueError()
    except (OSError, ValueError, KeyError, TypeError):
        volume = 70
    run('amixer', '-c', '0', 'cset', 'name=Moto Playback Volume', str(volume))
    ready.write_text('ADSP and athene routes ready\n')
    print('Native audio initialized before Wi-Fi; microphone and speaker routes ready', flush=True)


if __name__ == '__main__':
    try:
        with open('/run/moto-audio-start.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            initialize()
    except Exception as error:
        raise SystemExit('Audio startup failed: ' + str(error))
