#!/bin/sh
# SPDX-License-Identifier: MIT
# Run on the phone. Secrets are included: keep this archive private.
set -eu
set -o pipefail
archive=/tmp/native-rootfs-snapshot.tar.gz
tar -cf - -C / \
    --exclude='./proc' --exclude='./sys' --exclude='./dev' \
    --exclude='./run' --exclude='./tmp' --exclude='./firmware' \
    --exclude='./mnt' . | gzip -1 > "$archive"
sha256sum "$archive"
