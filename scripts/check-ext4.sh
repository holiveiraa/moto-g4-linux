#!/bin/sh
# SPDX-License-Identifier: MIT
set -eu
image=/tmp/moto-ext4-check.img
target=/tmp/moto-ext4-check
[ ! -e "$image" ] || exit 1
truncate -s 64M "$image"
mkfs.ext4 -F -b 4096 -i 65536 -m 0 \
    -O none,has_journal,ext_attr,resize_inode,dir_index,filetype,extent,flex_bg,sparse_super,large_file,huge_file,dir_nlink,extra_isize,uninit_bg \
    -E lazy_itable_init=0,lazy_journal_init=0 "$image"
mkdir "$target"
mount -t ext4 -o loop "$image" "$target"
echo 'Native kernel ext4 compatibility verified' > "$target/check"
sync
cat "$target/check"
umount "$target"
e2fsck -fn "$image"
rm "$image"
rmdir "$target"
