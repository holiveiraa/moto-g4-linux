#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# A small ramdisk loads the real rootfs from userdata. No flashing commands.
set -euo pipefail
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
work=${MOTO_WORK_ROOT:-"$HOME/src/moto-g4-linux"}
docker run --rm -v "$work:/work" -v "$project:/project" moto-g4-kernel:gcc6 \
    bash /project/scripts/persistent-image-in-container.sh
