#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Assemble a RAM-only native Linux boot image. Never invokes adb or fastboot.
set -euo pipefail
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
work=${MOTO_WORK_ROOT:-"$HOME/src/moto-g4-linux"}
mkdir -p "$work/boot-tools" "$project/out"

fetch() {
    local url=$1 destination=$2 checksum=$3 algorithm=$4
    if [[ ! -f "$destination" ]]; then
        curl --fail --location --retry 3 "$url" -o "$destination.part"
        printf '%s  %s\n' "$checksum" "$destination.part" | "${algorithm}sum" --check -
        mv -- "$destination.part" "$destination"
    fi
    printf '%s  %s\n' "$checksum" "$destination" | "${algorithm}sum" --check -
}

fetch 'https://raw.githubusercontent.com/loicpoulain/skales/c2bfa15aa5bfc4e3f1b32de28e327b80b37db1cf/dtbTool' \
    "$work/boot-tools/dtbTool.original" \
    77ad411ff482896919d971c5ef15817a5bee837d5a8827fd4a0449e7a99b8759e3ca2fe3f233b4a3a92c8e386e0457191d8d18755dba842224f5cc64ddb89024 sha512
fetch 'https://codeload.github.com/osm0sis/mkbootimg/tar.gz/refs/tags/2021.08.06' \
    "$work/boot-tools/mkbootimg-2021.08.06.tar.gz" \
    53f1a22e05983a425508a594df63fb37e8f8f510d352c89f2b92b6a9312573e574eecac81c632db47d22b20c64b7caacbaaa98dc679de919fc4d87eedef4ac27 sha512
fetch 'https://dl-cdn.alpinelinux.org/alpine/v3.24/releases/aarch64/alpine-minirootfs-3.24.2-aarch64.tar.gz' \
    "$work/boot-tools/alpine-minirootfs-3.24.2-aarch64.tar.gz" \
    9bf70a7f18ea44094cbb5f70c58f9af129c8214745743db0e68e5502cc2ce773 sha256
fetch 'https://codeload.github.com/AsteroidOS/msm-fb-refresher/tar.gz/refs/tags/v0.2' \
    "$work/boot-tools/msm-fb-refresher-0.2.tar.gz" \
    5e2920cf86f2e373e2411a89cf3ac6745af042ff7d91ae581f26b72772bc9ab621ea4154bc33ef57dce0c04ba3f88ee3b9f98c2a17b2579df368b0929cf0bfa7 sha512

docker build -f "$project/docker/kernel.Dockerfile" -t moto-g4-kernel:gcc6 "$project/docker"
test -f "$project/.private/device-debug-ed25519.pub"
docker run --rm -v "$work:/work" -v "$project:/project:ro" -v "$project/.private:/secrets" \
    -e LOCAL_UID="$(id -u)" -e LOCAL_GID="$(id -g)" \
    alpine@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6 \
    sh /project/scripts/rootfs-in-container.sh
docker run --rm --user "$(id -u):$(id -g)" \
    -v "$work:/work" -v "$project:/project" \
    -e BOOT_KERNEL_FILE="${MOTO_BOOT_KERNEL:-Image.gz}" \
    moto-g4-kernel:gcc6 bash /project/scripts/boot-image-in-container.sh
