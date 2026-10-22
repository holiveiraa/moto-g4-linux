#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Lifecycle for the optional native OEM-ABI finger-detection service."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

PROGRAM = '/usr/sbin/moto-fingerprint-button'


def pids():
    result = []
    for path in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            if path.read_bytes().split(b'\0')[0] == PROGRAM.encode():
                result.append(int(path.parent.name))
        except (OSError, ValueError):
            pass
    return result


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else 'status'
    current = pids()
    if command == 'status':
        print('FPC detection service:', 'running, physical validation pending' if current else 'stopped')
    elif command == 'stop':
        for pid in current:
            os.kill(pid, signal.SIGTERM)
        for _ in range(60):
            if not pids():
                print('FPC stopped cleanly')
                return
            time.sleep(.1)
        raise RuntimeError('FPC did not complete its cleanup')
    elif command == 'start':
        if current:
            print('FPC already running')
            return
        if not Path('/opt/moto/vendor32/linker').is_file():
            raise RuntimeError('Private vendor ABI bundle missing')
        env = dict(os.environ, LD_LIBRARY_PATH='/opt/moto/vendor32/lib')
        with open('/tmp/fingerprint-button.log', 'w') as log:
            p = subprocess.Popen([PROGRAM], env=env, stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=log, start_new_session=True)
        time.sleep(.5)
        if p.poll() is not None:
            raise RuntimeError('FPC startup failed; see /tmp/fingerprint-button.log')
        print('FPC detection armed; physical tap still requires validation')
    else:
        raise ValueError('Expected start, stop or status')


if __name__ == '__main__':
    main()
