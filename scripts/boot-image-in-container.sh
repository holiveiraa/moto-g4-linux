#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
cd /work/boot-tools
boot_kernel=${BOOT_KERNEL_FILE:-Image.gz}
rootfs=${ROOTFS_NAME:-firstlight-rootfs}
case "$boot_kernel" in */*) echo 'Kernel filename must be a basename' >&2; exit 1 ;; esac
case "$rootfs" in ''|.|..|*/*) echo 'Rootfs name must be a basename' >&2; exit 1 ;; esac
test -f "/project/out/$boot_kernel"
if [[ ! -d mkbootimg-2021.08.06 ]]; then
    tar -xzf mkbootimg-2021.08.06.tar.gz
fi
make -C mkbootimg-2021.08.06 -j1
if [[ ! -f dtbTool.patched ]]; then
    cp dtbTool.original dtbTool
    for patchfile in /work/pmaports/main/dtbtool/*.patch; do
        patch --forward dtbTool < "$patchfile"
    done
    touch dtbTool.patched
fi
kernel=/work/android_kernel_motorola_msm8952-4f6c8d2e1507595b5ef404d076128874176f1219
python3 dtbTool -s 2048 -p "$kernel/scripts/dtc/" -o /project/out/dt.img "$kernel/arch/arm64/boot/"

mkdir -p "$rootfs"
test -f "$rootfs/.moto-packages-prepared"
if [[ ! -d msm-fb-refresher-0.2 ]]; then
    tar -xzf msm-fb-refresher-0.2.tar.gz
fi
aarch64-linux-gnu-gcc -static -Os msm-fb-refresher-0.2/refresher.c \
    -o "$rootfs/usr/sbin/msm-fb-refresher"
aarch64-linux-gnu-gcc -static -Os /project/native/reboot-bootloader.c \
    -o "$rootfs/usr/sbin/reboot-bootloader"
aarch64-linux-gnu-gcc -static -Os -Wall -Wextra -Werror /project/native/framebuffer-status.c \
    -o "$rootfs/usr/sbin/framebuffer-status"
cp /project/initramfs/init "$rootfs/init"
for service in debug-console wifi-init wifi-connect network-start wait-network install-tailscale install-gui desktop-start terminal-session power hardware-start; do
    cp "/project/initramfs/$service" "$rootfs/usr/sbin/moto-$service"
    chmod 0755 "$rootfs/usr/sbin/moto-$service"
done
for module in moto-panel moto-widgets moto-services moto-wifi moto-wifi-panel moto-hosts moto-ssh-panel moto-terminals moto-voice moto-quick-voice moto-voice-panel moto-audio; do
    cp "/project/native/$module.py" "$rootfs/usr/sbin/$module.py"
    chmod 0644 "$rootfs/usr/sbin/$module.py"
done
cp /project/native/moto-audio-start.py "$rootfs/usr/sbin/moto-audio-start"
chmod 0755 "$rootfs/usr/sbin/moto-audio-start"
cp /project/config/moto-audio.json "$rootfs/etc/moto-audio.json"
cp /project/config/moto-asound.conf "$rootfs/etc/asound.conf"
for app in moto-inputd moto-shell moto-ui-control moto-fingerprint-control moto-ssh-launch moto-ssh-askpass; do
    cp "/project/native/$app.py" "$rootfs/usr/sbin/$app"
    chmod 0755 "$rootfs/usr/sbin/$app"
done
mkdir -p "$rootfs/usr/share/licenses/moto-g4-linux" "$rootfs/usr/share/licenses/msm-fb-refresher"
cp /project/LICENSE /project/NOTICE.md /project/sources.lock.json "$rootfs/usr/share/licenses/moto-g4-linux/"
cp msm-fb-refresher-0.2/LICENSE "$rootfs/usr/share/licenses/msm-fb-refresher/"
printf 'ctrl_interface=/run/wpa_supplicant\nupdate_config=1\n' > "$rootfs/etc/wpa_supplicant.conf"
chmod 0600 "$rootfs/etc/wpa_supplicant.conf"
if [[ -f /project/config/xorg-athene.conf ]]; then
    mkdir -p "$rootfs/etc/X11"
    cp /project/config/xorg-athene.conf "$rootfs/etc/X11/xorg-athene.conf"
    cp /project/config/openbox-moto.xml "$rootfs/etc/X11/openbox-moto.xml"
    cp /project/config/tmux-moto.conf "$rootfs/etc/X11/tmux-moto.conf"
    cp /project/config/moto-help.txt "$rootfs/etc/moto-help.txt"
fi
date +%s > "$rootfs/etc/moto-build-epoch"
chmod 0755 "$rootfs/init"
(
    cd "$rootfs"
    find . -print0 | LC_ALL=C sort -z | cpio --null -o -H newc --owner=0:0 | gzip -n -9
) > /project/out/initramfs.cpio.gz

cmdline=$(tr '\n' ' ' < /work/pmaports/device/archived/device-motorola-athene/kernel-cmdline.conf)
cmdline="$cmdline console=tty0 boot_cpus=0-7 rdinit=/init"
mkbootimg-2021.08.06/mkbootimg \
    --kernel "/project/out/$boot_kernel" --ramdisk /project/out/initramfs.cpio.gz \
    --dt /project/out/dt.img --base 0x80000000 --kernel_offset 0x00008000 \
    --ramdisk_offset 0x01000000 --second_offset 0x00f00000 \
    --tags_offset 0x00000100 --pagesize 2048 --cmdline "$cmdline" \
    --output /project/out/athene-usb-debug.img

mkbootimg-2021.08.06/unpackbootimg -i /project/out/athene-usb-debug.img \
    -o /project/out > /project/out/boot-header.txt
cd /project/out
sha256sum "$boot_kernel" initramfs.cpio.gz dt.img athene-usb-debug.img > image.sha256
cp /work/boot-tools/debug-packages.txt .
stat -c 'Boot image bytes: %s' athene-usb-debug.img
echo 'Image assembled. Build success does not validate this exact image on hardware.'
