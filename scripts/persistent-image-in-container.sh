#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -euo pipefail
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
tar -xzf /project/.private/moto-boot-root.tar.gz -C "$stage"
cp /project/initramfs/persistent-init "$stage/init"
cp /project/initramfs/rescue "$stage/sbin/moto-rescue"
chmod 0755 "$stage/init" "$stage/sbin/moto-rescue"
cd "$stage"
find . -print0 | LC_ALL=C sort -z | cpio --null -o -H newc --owner=0:0 | gzip -n -9 > /project/out/persistent-initramfs.cpio.gz
cmdline=$(cat /project/out/athene-usb-debug.img-cmdline)
python3 /project/scripts/extract-stock-dt.py /project/.private/stock-boot.img /project/out/stock-dt.img
/work/boot-tools/mkbootimg-2021.08.06/mkbootimg \
    --kernel /project/out/Image.gz --ramdisk /project/out/persistent-initramfs.cpio.gz \
    --dt /project/out/stock-dt.img --base 0x80000000 --kernel_offset 0x00008000 \
    --ramdisk_offset 0x01000000 --second_offset 0x00f00000 \
    --tags_offset 0x00000100 --pagesize 2048 --cmdline "$cmdline" \
    --output /project/out/athene-persistent.img
size=$(stat -c %s /project/out/athene-persistent.img)
[ "$size" -le 16777216 ] || { echo 'Image exceeds boot partition' >&2; exit 1; }
sha256sum /project/out/athene-persistent.img
echo "Boot image fits: $size / 16777216 bytes"
