#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail

cd "/work/android_kernel_motorola_msm8952-$KERNEL_REVISION"
reference=/work/pmaports/device/archived/linux-motorola-athene
if [[ ! -f .moto-no-wireguard-fetch ]]; then
    patch -p1 --forward < /project/patches/0004-disable-build-time-wireguard-fetch.patch
    touch .moto-no-wireguard-fetch
fi
# Reproduce downstreamkernel_prepare from the same pmaports revision.
cmp -s /work/pmaports/main/devicepkg-dev/compiler-gcc.h include/linux/compiler-gcc.h || \
    cp /work/pmaports/main/devicepkg-dev/compiler-gcc.h include/linux/compiler-gcc.h
if [[ ! -f .moto-no-werror ]]; then
    find . -type f \( -name Makefile -o -name Makefile.common -o -name Kbuild \) \
        -exec sed -i -e 's/-Werror-/-W/g' -e 's/-Werror=/-W/g' -e 's/-Werror//g' {} +
    touch .moto-no-werror
fi
if [[ ! -f .moto-reference-patched ]]; then
    for name in 01_fix_gcc6_errors.patch scripts-dtc-yylloc.patch \
        disable-wireguard-Kconfig.patch optimize_compile_options.patch \
        linux3.7to4.5-ARM64-remove-Sun-Solaris-style-flag-on-section.patch; do
        patch -p1 --forward < "$reference/$name"
    done
    touch .moto-reference-patched
fi
# Restore the archived framebuffer driver if an earlier local experiment was
# applied. The vendor driver allocates screen_base on userspace mmap; generic
# fbcon drawing callbacks are unsafe before that allocation.
if [[ -f .moto-console-ops-patched ]]; then
    patch -R -p1 < /project/patches/0001-mdss-fb-console-ops.patch
    rm .moto-console-ops-patched
fi
# The parent experiment breaks the downstream runtime PM hierarchy. Restore
# the virtual framebuffer, then expose the driver's existing hardware link.
if [[ -f .moto-fb-parent-patched ]]; then
    patch -R -p1 < /project/patches/0002-mdss-fb-register-parent.patch
    rm .moto-fb-parent-patched
fi
if [[ ! -f .moto-fb-device-link-patched ]]; then
    patch -p1 --forward < /project/patches/0003-mdss-fb-standard-device-link.patch
    touch .moto-fb-device-link-patched
fi
if [[ ! -f .moto-native-playback-unity ]]; then
    patch -p1 --forward < /project/patches/0007-q6-native-playback-unity.patch
    touch .moto-native-playback-unity
fi
# Explicit opt-in: diagnostics read back ADSP segment checksums without changing
# firmware, authentication, SMC ABI or the subsystem restart policy.
if [[ ${AUDIO_DIAGNOSTICS:-0} == 1 ]]; then
    if [[ ! -f .moto-adsp-readback-diagnostic ]]; then
        patch -p1 --forward < /project/patches/0006-adsp-segment-readback-diagnostic.patch
        touch .moto-adsp-readback-diagnostic
    fi
elif [[ -f .moto-adsp-readback-diagnostic ]]; then
    patch -R -p1 < /project/patches/0006-adsp-segment-readback-diagnostic.patch
    rm .moto-adsp-readback-diagnostic
fi
if [[ ${AUDIO_DIAGNOSTICS:-0} == memory ]]; then
    cp /project/native/moto-audio-memory.c drivers/misc/moto-audio-memory.c
    if [[ ! -f .moto-audio-memory-diagnostic ]]; then
        printf '\nobj-y += moto-audio-memory.o\n' >> drivers/misc/Makefile
        touch .moto-audio-memory-diagnostic
    fi
elif [[ -f .moto-audio-memory-diagnostic ]]; then
    sed -i '/^obj-y += moto-audio-memory.o$/d' drivers/misc/Makefile
    rm .moto-audio-memory-diagnostic
fi
if [[ ! -f .config ]]; then
    cp "$reference/config-motorola-athene.aarch64" .config
fi
# Match the original port: display drawing is done by a userspace framebuffer
# client, not by adding console callbacks to the vendor driver.
scripts/config --disable FRAMEBUFFER_CONSOLE --disable FRAMEBUFFER_CONSOLE_ROTATION
# This vendor Makefile omits msm_rng.o whenever FIPS_ENABLE=y, despite
# HW_RANDOM_MSM=y. The archived config inherits that Android option. Native
# Dropbear then blocks in getrandom, with no /dev/hwrng or platform RNG driver.
# Use the normal kernel hardware RNG path; keep cryptographic primitives and
# the RNG driver's own self-tests enabled.
scripts/config --disable FIPS_ENABLE --disable FIPS_RECOMPILE
export ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- CC=aarch64-linux-gnu-gcc HOSTCC=gcc
export KBUILD_BUILD_USER=moto-g4-linux KBUILD_BUILD_HOST=builder
export KBUILD_BUILD_TIMESTAMP='2026-10-19 00:00:00 UTC'
make CC="$CC" HOSTCC="$HOSTCC" olddefconfig
make CC="$CC" HOSTCC="$HOSTCC" -j "$BUILD_JOBS" Image.gz dtbs
