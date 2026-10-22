#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read-only observations of the installed shell. Does not change the screen."""
import json
import os
from pathlib import Path
import time


def find():
    for path in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            if path.read_bytes().split(b'\0')[:2] == [b'python3', b'/usr/sbin/moto-shell']:
                return path.parent
        except OSError:
            pass
    raise RuntimeError('Installed shell not found')


def sample(process):
    fields = (process/'stat').read_text().rsplit(')', 1)[1].split()
    pss = sum(int(line.split()[1]) for line in (process/'smaps').read_text().splitlines() if line.startswith('Pss:'))
    return {'ticks': int(fields[11])+int(fields[12]), 'pss_kb': pss, 'monotonic': time.monotonic()}


if __name__ == '__main__':
    process = find()
    start = sample(process)
    print(json.dumps({'pid': int(process.name), 'start': start}), flush=True)
    time.sleep(60)
    end = sample(process)
    percent = (end['ticks']-start['ticks'])/os.sysconf('SC_CLK_TCK')/(end['monotonic']-start['monotonic'])*100
    print(json.dumps({'end': end, 'cpu_one_core_percent': round(percent, 2),
                      'note': 'observational; owner may interact, not a controlled benchmark'}), flush=True)
