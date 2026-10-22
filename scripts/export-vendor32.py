#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""On-device: copy only the transitive OEM library closure for the FPC button.

Requires stock system mounted READ-ONLY at /mnt/stock-system, and scanelf.
The result is private device firmware/support code, never a public artifact.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

stock = Path('/mnt/stock-system')
destination = Path('/opt/moto/vendor32')
destination.mkdir(parents=True, exist_ok=True)
(destination/'lib').mkdir(exist_ok=True)
pending, done = ['lib_fpc_tac_shared.so'], set()
while pending:
    name = pending.pop()
    if name in done:
        continue
    if not re.fullmatch(r'[A-Za-z0-9_.+-]+', name):
        raise ValueError('Invalid shared-library name')
    source = next((p for p in (stock/'lib'/name, stock/'vendor/lib'/name) if p.is_file()), None)
    if source is None:
        raise FileNotFoundError(name)
    shutil.copy2(source, destination/'lib'/name)
    result = subprocess.check_output(['scanelf', '-BF', '%n', str(source)], text=True).strip().split()
    if result and not result[0].startswith('/'):
        pending.extend(result[0].split(','))
    done.add(name)
shutil.copy2(stock/'bin/linker', destination/'linker')
manifest = {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(destination.rglob('*')) if p.is_file()}
(destination/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
print('Private FPC ABI closure:', len(done), 'libraries,', sum(p.stat().st_size for p in destination.rglob('*') if p.is_file()), 'bytes')
