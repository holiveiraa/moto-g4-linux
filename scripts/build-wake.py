#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build the pinned local wake recognizer on Linux; never installs on a device."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def fetch(url, target, expected, maximum):
    if target.exists() and digest(target) == expected:
        return
    temporary = target.with_name(target.name+'.partial-'+os.urandom(8).hex())
    try:
        request = urllib.request.Request(url, headers={'User-Agent':'Moto-G4-Linux-build'})
        with urllib.request.urlopen(request, timeout=60) as source, temporary.open('xb') as output:
            size = 0
            while block := source.read(1024*1024):
                size += len(block)
                if size > maximum:
                    raise ValueError('Downloaded input exceeds its bound.')
                output.write(block)
        if digest(temporary) != expected:
            raise ValueError('Downloaded input failed SHA256 verification: '+target.name)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-root', type=Path, default=Path.home()/'moto-g4-work/wake-builds')
    parser.add_argument('--target', choices=('host','aarch64-linux-musl'), default='aarch64-linux-musl')
    args = parser.parse_args()
    root = args.work_root.expanduser().resolve()
    if sys.platform != 'linux' or str(root).startswith('/mnt/') or root == ROOT or root.is_relative_to(ROOT) or ROOT.is_relative_to(root):
        raise SystemExit('Use a separate build directory on the Linux filesystem.')
    zig = os.environ.get('CARGO_ZIGBUILD_ZIG_PATH') or shutil.which('zig')
    pins = json.loads((ROOT/'companion/wake/pins.json').read_text())
    model_license = ROOT/'LICENSES/whisper-model-MIT.txt'
    if digest(model_license) != pins['model_license_sha256']:
        raise SystemExit('Preserved model license failed its pinned hash.')
    vad_license = ROOT/'LICENSES/silero-vad-MIT.txt'
    if digest(vad_license) != pins['vad_license_sha256']:
        raise SystemExit('Preserved VAD license failed its pinned hash.')
    tools = json.loads((ROOT/'companion/toolchains.json').read_text())
    if not zig or subprocess.check_output([zig,'version'],text=True).strip() != tools['zig']:
        raise SystemExit('Use pinned Zig '+tools['zig']+'.')
    if not shutil.which('cmake') or not shutil.which('make'):
        raise SystemExit('Install CMake >=3.20 and make on the build host.')
    target = args.target
    if target == 'host':
        if platform.machine() not in ('x86_64','aarch64'):
            raise SystemExit('Host build supports x86_64/aarch64 Linux.')
        target = platform.machine()+'-linux-musl'
    root.mkdir(parents=True, exist_ok=True)
    cache = root/'cache'
    cache.mkdir(exist_ok=True)
    archive = cache/('whisper-'+pins['whisper_tag']+'.tar.gz')
    fetch('https://github.com/ggml-org/whisper.cpp/archive/refs/tags/'+pins['whisper_tag']+'.tar.gz',
          archive, pins['source_archive_sha256'], 30*1024*1024)
    model = cache/pins['model']
    fetch('https://huggingface.co/ggerganov/whisper.cpp/resolve/'+pins['model_revision']+'/'+pins['model'],
          model, pins['model_sha256'], 40*1024*1024)
    vad_model = cache/pins['vad_model']
    fetch('https://huggingface.co/ggml-org/whisper-vad/resolve/'+pins['vad_model_revision']+'/'+pins['vad_model'],
          vad_model, pins['vad_model_sha256'], 2*1024*1024)
    work = root/(time.strftime('%Y%m%d-%H%M%S')+'-'+os.urandom(4).hex())
    work.mkdir()
    with tarfile.open(archive) as source:
        source.extractall(work/'upstream', filter='data')
    upstream = next((work/'upstream').iterdir())
    own = work/'source'
    shutil.copytree(ROOT/'companion/wake', own)
    for name, compiler in [('cc','cc'),('cxx','c++')]:
        wrapper = work/(name+'.sh')
        # Zig calls ARM's baseline cortex_a53, whereas CMake emits armv8-a.
        wrapper.write_text('#!/bin/bash\nargs=()\nfor arg in "$@"; do\n'
            ' if [[ "$arg" == "-march=armv8-a" ]]; then args+=("-mcpu=cortex_a53"); else args+=("$arg"); fi\ndone\n'
            'exec '+shlex.quote(str(zig))+' '+compiler+' -target '+target+' "${args[@]}"\n')
        wrapper.chmod(0o700)
    command = ['cmake','-S',str(own),'-B',str(work/'build'),'-G','Unix Makefiles',
        '-DCMAKE_BUILD_TYPE=Release','-DCMAKE_SYSTEM_NAME=Linux',
        '-DCMAKE_SYSTEM_PROCESSOR='+('aarch64' if target.startswith('aarch64') else 'x86_64'),
        '-DCMAKE_C_COMPILER='+str(work/'cc.sh'),'-DCMAKE_CXX_COMPILER='+str(work/'cxx.sh'),
        '-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY','-DCMAKE_EXE_LINKER_FLAGS=-static -s',
        '-DWHISPER_SOURCE_DIR='+str(upstream)]
    if target.startswith('aarch64'):
        command.append('-DGGML_CPU_ARM_ARCH=armv8-a')
    subprocess.run(command, check=True)
    subprocess.run(['cmake','--build',str(work/'build'),'--parallel','4'], check=True)
    artifact = work/'artifact'
    artifact.mkdir()
    shutil.copy2(work/'build/moto-wake', artifact/'moto-wake')
    shutil.copy2(work/'build/moto-vad', artifact/'moto-vad')
    shutil.copy2(model, artifact/model.name)
    shutil.copy2(vad_model, artifact/vad_model.name)
    shutil.copy2(ROOT/'LICENSE', artifact/'PROJECT-LICENSE')
    shutil.copy2(model_license, artifact/'MODEL-LICENSE')
    shutil.copy2(vad_license, artifact/'VAD-MODEL-LICENSE')
    for file in upstream.rglob('*'):
        if file.is_file() and not file.is_symlink() and file.name.lower().startswith(('license','copying','notice')):
            destination = artifact/'upstream-notices'/file.relative_to(upstream)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, destination)
    result = {'target':target, 'inputs':pins,
              'zig':tools['zig'],
              'cmake':subprocess.check_output(['cmake','--version'],text=True).splitlines()[0],
              'configuration':{'build_type':'Release','static':True,'openmp':False,
                               'native_cpu_detection':False,'gpu':False,
                               'arm_baseline':'armv8-a / cortex_a53' if target.startswith('aarch64') else None},
              'helper_sha256':digest(artifact/'moto-wake'),
              'helper_bytes':(artifact/'moto-wake').stat().st_size,
              'model_bytes':model.stat().st_size,
              'source_sha256':digest(own/'wake.cpp'),
              'vad_source_sha256':digest(own/'vad.cpp'),
              'vad_helper_sha256':digest(artifact/'moto-vad'),
              'vad_helper_bytes':(artifact/'moto-vad').stat().st_size,
              'validation':'Compiled only. Wake accuracy, latency and heat need device measurement.'}
    (artifact/'build.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Built local recognizer:', artifact)
    print('No device/server writes or publication performed.')


if __name__ == '__main__':
    main()
