#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Restart the GUI/input adapter without rebooting Linux or killing tmux/SSH."""
import os
from pathlib import Path
import signal
import subprocess
import time


def find(script):
    matches = []
    for p in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            args = p.read_bytes().split(b'\0')
            if len(args) > 1 and args[1] == script.encode():
                matches.append(int(p.parent.name))
        except (OSError, ValueError):
            pass
    return matches


def stop(script):
    pids = find(script)
    for pid in pids:
        if pid > 1:
            os.kill(pid, signal.SIGTERM)
    for _ in range(50):
        if not find(script):
            return
        time.sleep(.1)
    raise RuntimeError('Service did not stop: ' + script)


if __name__ == '__main__':
    persistent = Path('/etc/moto-persistent').exists()
    if persistent:
        subprocess.run(['rc-service', 'moto-desktop', 'stop'], check=True)
    stop('/usr/sbin/moto-desktop-start')
    # Xorg must release the old uinput fd before the adapter is replaced.
    time.sleep(.4)
    stop('/usr/sbin/moto-inputd')
    Path('/run/moto-desktop.pid').unlink(missing_ok=True)
    if persistent:
        subprocess.run(['rc-service', 'moto-desktop', 'start'], check=True)
        raise SystemExit(0)
    with open('/tmp/desktop.log', 'w') as log:
        p = subprocess.Popen(['/usr/sbin/moto-desktop-start'], stdin=subprocess.DEVNULL,
                             stdout=log, stderr=log, start_new_session=True)
    print('Mobile desktop starting, PID', p.pid)
