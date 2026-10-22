#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mode=${1:-normal}
case "$mode" in normal|recovery) ;; *) exit 2 ;; esac
base=${MOTO_WORK_ROOT:-"$HOME/src/moto-g4-linux"}
revision=fd11905d61f220daf9ad69b1b26144cbc6020169
source="$base/sources/lk2nd"
mkdir -p "$base/sources" "$project/out"
if [[ ! -d "$source/.git" ]]; then
    git init -q "$source"
    git -C "$source" remote add origin https://github.com/msm8916-mainline/lk2nd.git
fi
if ! git -C "$source" cat-file -e "$revision^{commit}" 2>/dev/null; then
    git -C "$source" fetch --depth=1 origin "$revision"
fi
test "$(git -C "$source" rev-parse "$revision^{commit}")" = "$revision"
work=$(mktemp -d "$base/lk2nd-build.XXXXXXXX")
trap 'rm -rf -- "$work"' EXIT
git -C "$source" archive "$revision" | tar -x -C "$work"
cd "$work"
cp "$project/native/lk2nd-motorola-chosen.c" lk2nd/device/2nd/motorola-chosen.c
python3 - <<'PY'
from pathlib import Path
p = Path('lk2nd/device/2nd/device.c')
s = p.read_text()
s = s.replace('static void lk2nd_device2nd_update_serialno',
              'void moto_cache_chosen(const void *dtb);\n\nstatic void lk2nd_device2nd_update_serialno', 1)
s = s.replace('\n\treturn dtb;\n', '\n\tmoto_cache_chosen(dtb);\n\treturn dtb;\n', 1)
p.write_text(s)
p = Path('lk2nd/device/2nd/rules.mk')
p.write_text(p.read_text() + '\nOBJS += lk2nd/device/2nd/motorola-chosen.o\n')
PY
# Bundle the device database as well as appending it: Motorola RAM boot can
# pass its stock DT instead of lk2nd's appended one. The database stays explicit.
extra=()
build=build-lk2nd-msm8952
output=lk2nd-athene.img
if [ "$mode" = recovery ]; then
    build=build-lk2nd-msm8952-recovery
    output=lk2nd-athene-recovery.img
    extra+=(BUILDDIR="$build" LK2ND_FORCE_FASTBOOT=1)
fi
make -j4 TOOLCHAIN_PREFIX=arm-none-eabi- LK2ND_VERSION=moto-g4-fd11905 "${extra[@]}" \
    LK2ND_DTBS=msm8952-mtp.dtb \
    LK2ND_BUNDLE_DTB=msm8952-mtp.dtb lk2nd-msm8952
cp "$build/lk2nd.img" "$project/out/$output"
test "$(stat -c %s "$project/out/$output")" -le 524288
sha256sum "$project/out/$output"
if [ "$mode" = recovery ]; then
    # Recovery has a different partition size from boot on this XT1640.
    : "${MOTO_RECOVERY_BYTES:?Set your verified recovery partition size in bytes}"
    python3 - "$project/out/$output" "$project/out/lk2nd-athene-recovery-full.img" "$MOTO_RECOVERY_BYTES" <<'PY'
from pathlib import Path
import sys
image = Path(sys.argv[1]).read_bytes()
assert len(image) <= 524288
size = int(sys.argv[3])
assert len(image) <= size <= 64*1024*1024
Path(sys.argv[2]).write_bytes(image.ljust(size, b'\0'))
PY
    sha256sum "$project/out/lk2nd-athene-recovery-full.img"
fi
