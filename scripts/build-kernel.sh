#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Rebuild the existing postmarketOS downstream kernel. Never touches the phone.
set -euo pipefail

project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
work=${MOTO_WORK_ROOT:-"$HOME/src/moto-g4-linux"}
jobs=${MOTO_BUILD_JOBS:-8}
pm_revision=767b10462fb3f0cb591e2e04c20dd2ed4d6e2568
kernel_revision=4f6c8d2e1507595b5ef404d076128874176f1219
kernel_sha512=74d13e6787337454dc09c643efcf95cd46a2f02deecbe687c7a451f53bc2a5978aca394cf76f828cced88a6cffb310deb430c2c8c989471b368733f1aad728c2
kernel_dir="$work/android_kernel_motorola_msm8952-$kernel_revision"
archive="$work/kernel-$kernel_revision.tar.gz"

mkdir -p "$work" "$project/out"
if [[ ! -d "$work/pmaports/.git" ]]; then
    git clone --depth=1 --filter=blob:none --sparse --no-checkout \
        https://gitlab.postmarketos.org/postmarketOS/pmaports.git "$work/pmaports"
    git -C "$work/pmaports" fetch --depth=1 origin "$pm_revision"
    git -C "$work/pmaports" checkout --detach "$pm_revision"
fi
if [[ $(git -C "$work/pmaports" rev-parse HEAD) != "$pm_revision" ]]; then
    echo "pmaports revision differs from the recorded reference; inspect before building." >&2
    exit 1
fi
git -C "$work/pmaports" sparse-checkout set \
    device/archived/device-motorola-athene \
    device/archived/linux-motorola-athene device/.shared-patches/linux \
    main/devicepkg-dev main/dtbtool main/mkbootimg-osm0sis

if [[ ! -f "$archive" ]]; then
    curl --fail --location --retry 3 \
        "https://codeload.github.com/fengjiongmax/android_kernel_motorola_msm8952/tar.gz/$kernel_revision" \
        -o "$archive.part"
    printf '%s  %s\n' "$kernel_sha512" "$archive.part" | sha512sum --check -
    mv -- "$archive.part" "$archive"
fi
printf '%s  %s\n' "$kernel_sha512" "$archive" | sha512sum --check -

if [[ ! -d "$kernel_dir" ]]; then
    tar -xzf "$archive" -C "$work"
fi

docker build -f "$project/docker/kernel.Dockerfile" -t moto-g4-kernel:gcc6 "$project/docker"
docker run --rm --user "$(id -u):$(id -g)" \
    -v "$work:/work" -v "$project:/project:ro" \
    -e KERNEL_REVISION="$kernel_revision" -e BUILD_JOBS="$jobs" \
    -e AUDIO_DIAGNOSTICS="${MOTO_AUDIO_DIAGNOSTICS:-0}" \
    moto-g4-kernel:gcc6 bash /project/scripts/kernel-in-container.sh

cp -- "$kernel_dir/arch/arm64/boot/Image.gz" "$project/out/Image.gz"
find "$kernel_dir/arch/arm64/boot" -name '*.dtb' -type f -print > "$project/out/dtb-paths.txt"
sha256sum "$project/out/Image.gz" > "$project/out/kernel.sha256"
echo "Kernel compiled. This is not yet a boot image or a verified device boot."
