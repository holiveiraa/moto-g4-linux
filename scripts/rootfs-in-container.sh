#!/bin/sh
# SPDX-License-Identifier: MIT
set -eu
rootfs=/work/boot-tools/firstlight-rootfs
mkdir -p "$rootfs"
if [ -e "$rootfs/root/.config/moto-linux" ] || [ -e "$rootfs/var/lib/tailscale/tailscaled.state" ] || \
   { [ -f "$rootfs/etc/wpa_supplicant.conf" ] && grep -q 'network[[:space:]]*=' "$rootfs/etc/wpa_supplicant.conf"; }; then
    echo 'Personal state exists in the build root. Use a fresh MOTO_WORK_ROOT.' >&2
    exit 1
fi
tar -xzf /work/boot-tools/alpine-minirootfs-3.24.2-aarch64.tar.gz -C "$rootfs"
# Cross-architecture installation only extracts packages; foreign scripts must
# not run on the x86_64 build machine. Signatures remain enabled.
apk --root "$rootfs" --arch aarch64 --no-scripts --no-cache add \
    dropbear dnsmasq wpa_supplicant iw busybox-extras rng-tools
# Generate the debug host identity once with the build machine's RNG. Preserve
# it across RAM boots, instead of waiting for on-device RSA generation.
if [ ! -f /secrets/dropbear_ed25519_host_key ]; then
    apk --no-cache add dropbear
    dropbearkey -t ed25519 -f /secrets/dropbear_ed25519_host_key \
        > /secrets/dropbear-host-public.txt
    chmod 0600 /secrets/dropbear_ed25519_host_key
fi
mkdir -p "$rootfs/root/.ssh" "$rootfs/lib/firmware"
cp /project/.private/device-debug-ed25519.pub "$rootfs/root/.ssh/authorized_keys"
chmod 0700 "$rootfs/root/.ssh"
chmod 0600 "$rootfs/root/.ssh/authorized_keys"
mkdir -p "$rootfs/etc/dropbear"
# The host container has a seeded RNG. Keep this token out of source and logs.
if [ ! -s /secrets/debug-console-token.txt ]; then
    od -An -N32 -tx1 /dev/urandom | tr -d ' \n' > /secrets/debug-console-token.txt
    chmod 0600 /secrets/debug-console-token.txt
fi
cp /secrets/debug-console-token.txt "$rootfs/etc/moto-debug-token"
chmod 0600 "$rootfs/etc/moto-debug-token"
cp /secrets/dropbear_ed25519_host_key "$rootfs/etc/dropbear/dropbear_ed25519_host_key"
chmod 0600 "$rootfs/etc/dropbear/dropbear_ed25519_host_key"
firmware=/project/.private/firmware-stock/system-etc-firmware
if [ -d "$firmware" ]; then
    cp -a "$firmware/." "$rootfs/lib/firmware/"
fi
apk --root "$rootfs" --arch aarch64 info -v > /work/boot-tools/debug-packages.txt
touch "$rootfs/.moto-packages-prepared"
chown -R "$LOCAL_UID:$LOCAL_GID" "$rootfs" /work/boot-tools/debug-packages.txt
