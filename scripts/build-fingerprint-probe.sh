#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
docker build -f "$project/docker/fingerprint.Dockerfile" -t moto-g4-fingerprint:gcc6 "$project/docker"
# Libraries are private copies read from this owner's phone. Never download
# replacements from another handset or redistribute the resulting vendor bundle.
for app in fingerprint-probe fingerprint-button; do
docker run --rm -v "$project:/project" moto-g4-fingerprint:gcc6 \
    arm-linux-gnueabihf-gcc -mfloat-abi=softfp -march=armv7-a -mfpu=neon \
    -fPIC -pie -nostdlib -fno-stack-protector -Wl,-e,_start \
    -Wl,--dynamic-linker,/opt/moto/vendor32/linker -Wl,--allow-shlib-undefined \
    "/project/native/$app.c" \
    /project/.private/fingerprint-abi/libc.so /project/.private/fingerprint-abi/libdl.so \
    -o "/project/out/$app"
done
