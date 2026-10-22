#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build/test a public-source snapshot on Linux. Never connects to a handset/server."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

PROJECT=Path(__file__).resolve().parents[1]


def linux_work(path):
    path=Path(path).expanduser().resolve()
    if sys.platform!='linux' or str(path).startswith(('/mnt/c/','/mnt/d/','/mnt/e/')):
        raise ValueError('Build on the Linux filesystem, for example ~/moto-g4-work.')
    if path==PROJECT or PROJECT.is_relative_to(path) or path.is_relative_to(PROJECT):
        raise ValueError('Use a build folder outside the source checkout.')
    return path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-root',type=Path,default=Path.home()/'moto-g4-work/companion-builds')
    parser.add_argument('--target',choices=('host','aarch64-unknown-linux-musl'),default='host')
    args=parser.parse_args()
    root=linux_work(args.work_root)
    pins=json.loads((PROJECT/'companion/toolchains.json').read_text())
    version=subprocess.check_output(['rustc','--version'],text=True).split()[1]
    if version!=pins['rust']:
        raise SystemExit('Use Rust '+pins['rust']+' (see companion/toolchains.json).')
    if args.target!='host':
        zig=os.environ.get('CARGO_ZIGBUILD_ZIG_PATH') or shutil.which('zig')
        if not zig or subprocess.check_output([zig,'version'],text=True).strip()!=pins['zig']:
            raise SystemExit('Use Zig '+pins['zig']+' (see companion/toolchains.json).')
        cross=subprocess.check_output(['cargo-zigbuild','--version'],text=True).strip().split()[-1]
        if cross!=pins['cargo_zigbuild']:
            raise SystemExit('Use cargo-zigbuild '+pins['cargo_zigbuild']+'.')
    subprocess.run([sys.executable,str(PROJECT/'scripts/check-repository.py')],check=True)
    work=root/(time.strftime('%Y%m%d-%H%M%S')+'-'+os.urandom(4).hex())
    source=work/'source'
    subprocess.run([sys.executable,str(PROJECT/'scripts/export-source.py'),'--output',str(source)],check=True)
    snapshot=hashlib.sha256()
    for item in sorted(source.rglob('*')):
        if item.is_file():
            snapshot.update(item.relative_to(source).as_posix().encode()+b'\0')
            snapshot.update(hashlib.sha256(item.read_bytes()).digest())
    crate=source/'companion'
    for command in (['cargo','fmt','--all','--check'],['cargo','test','--locked'],['cargo','clippy','--locked','--all-targets','--','-D','warnings']):
        subprocess.run(command,cwd=crate,check=True)
    command=['cargo','build','--release','--locked']
    if args.target!='host':
        command=['cargo','zigbuild','--release','--locked','--target',args.target]
    subprocess.run(command,cwd=crate,check=True)
    binary=crate/'target'
    if args.target!='host': binary=binary/args.target
    binary=binary/'release/moto-hermes'
    result=work/'artifact'; result.mkdir()
    shutil.copy2(binary,result/'moto-hermes')
    shutil.copy2(crate/'Cargo.lock',result/'Cargo.lock')
    shutil.copy2(source/'LICENSE',result/'LICENSE')
    # Keep declared license expressions and every bundled license/notice file
    # found in dependency sources. This is provenance, not a legal certification.
    metadata=json.loads(subprocess.check_output(['cargo','metadata','--locked','--format-version','1'],cwd=crate))
    inventory=[]
    for package in metadata['packages']:
        item={key:package.get(key) for key in ('name','version','license','source','repository')}
        inventory.append(item)
        package_root=Path(package['manifest_path']).parent
        if package['source'] is None: continue
        for candidate in package_root.rglob('*'):
            if candidate.is_file() and not candidate.is_symlink() and candidate.name.lower().startswith(('license','licence','copying','notice')):
                relative=candidate.relative_to(package_root)
                target=result/'dependency-notices'/(package['name']+'-'+package['version'])/relative
                target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(candidate,target)
    (result/'dependency-licenses.json').write_text(json.dumps(inventory,indent=2)+'\n')
    digest=hashlib.sha256((result/'moto-hermes').read_bytes()).hexdigest()
    manifest={'target':args.target,'rust':version,'sha256':digest,'bytes':(result/'moto-hermes').stat().st_size,
              'public_source_sha256':snapshot.hexdigest(),
              'cargo_lock_sha256':hashlib.sha256((crate/'Cargo.lock').read_bytes()).hexdigest(),
              'validation':'host offline tests passed; device runtime/audio/server login remain separate acceptance gates',
              'toolchain_pins':pins}
    (result/'build.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Built artifact:',result)
    print('SHA256:',digest)
    print('No device/server writes or publication performed.')


if __name__=='__main__': main()
