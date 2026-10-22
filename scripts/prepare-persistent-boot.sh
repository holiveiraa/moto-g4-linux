#!/bin/sh
# SPDX-License-Identifier: MIT
# Run on the native phone. Build a minimal rescue-capable ramdisk staging tree.
# No partition writes. The PC separately packs this into a size-checked image.
set -eu
target=/tmp/moto-boot-root
[ ! -e "$target" ] || { echo 'Boot staging directory already exists' >&2; exit 1; }
mkdir -p "$target/bin" "$target/sbin" "$target/lib" "$target/usr/sbin" \
    "$target/etc/dropbear" "$target/root/.ssh" "$target/dev" "$target/proc" \
    "$target/sys" "$target/run" "$target/tmp" "$target/newroot"
for binary in /bin/busybox /sbin/e2fsck /usr/sbin/dropbear /usr/sbin/dnsmasq; do
    cp -L "$binary" "$target$binary"
    ldd "$binary" | awk '{for (i=1;i<=NF;i++) if ($i ~ /^\//) print $i}' | while read -r library; do
        mkdir -p "$target${library%/*}"
        cp -L "$library" "$target$library"
    done
done
for name in sh mount umount mkdir grep sleep cat ip blkid switch_root date sync; do
    ln -s busybox "$target/bin/$name"
done
cp /etc/dropbear/dropbear_ed25519_host_key "$target/etc/dropbear/"
cp /root/.ssh/authorized_keys "$target/root/.ssh/"
chmod 700 "$target/root/.ssh"
chmod 600 "$target/root/.ssh/authorized_keys" "$target/etc/dropbear/dropbear_ed25519_host_key"
printf 'root:x:0:0:root:/root:/bin/sh\n' > "$target/etc/passwd"
printf 'root::19000:0:99999:7:::\n' > "$target/etc/shadow"
printf 'root:x:0:\n' > "$target/etc/group"
cp /tmp/moto-persistent-init "$target/init"
cp /tmp/moto-rescue "$target/sbin/moto-rescue"
chmod 755 "$target/init" "$target/sbin/moto-rescue"
# SSH bootloader recovery helper retains an escape from the rescue root.
cp /usr/sbin/reboot-bootloader "$target/usr/sbin/"
tar -czf /tmp/moto-boot-root.tar.gz -C "$target" .
sha256sum /tmp/moto-boot-root.tar.gz
