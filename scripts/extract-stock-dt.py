#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Extract the handset's original Motorola QCDT, without copying Android code.

The archived ARM64 DTS set only describes P0/P1 hardware. This XT1640 is P2A.
Its bootloader also expects Motorola's QCDT extension (0x103, not generic v2).
Keep the matched hardware description already proven by tethered boots until
the P2A DTS is ported. This file is device-specific build input, not public data.
"""
from pathlib import Path
import struct
import sys


def extract(source, target):
    data = Path(source).read_bytes()
    if data[:8] != b'ANDROID!':
        raise ValueError('Expected a legacy Android boot header')
    kernel, _, ramdisk, _, second, _, _, page, size, _ = struct.unpack_from('<10I', data, 8)
    if page < 2048 or page > 16384 or page & (page - 1):
        raise ValueError('Invalid boot page size')
    offset = page + sum((length + page-1) // page * page for length in (kernel, ramdisk, second))
    if size < 12 or offset + size > len(data):
        raise ValueError('DT section is outside the boot image')
    dt = data[offset:offset + size]
    magic, version, count = struct.unpack_from('<4sII', dt)
    if magic != b'QCDT' or version != 0x103 or not 1 <= count <= 128:
        raise ValueError('Expected this handset\'s Motorola QCDT 0x103 table')
    Path(target).write_bytes(dt)
    print('Original Motorola QCDT: version 0x{:x}, {} entries, {} bytes'.format(version, count, size))


if __name__ == '__main__':
    extract(*sys.argv[1:])
