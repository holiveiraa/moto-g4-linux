#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Replace only the kernel of a known boot payload; emit RAM-test image, no flash."""
import argparse
import hashlib
from pathlib import Path
import struct


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = args.source.read_bytes()
    if source[524288:524296] == b'ANDROID!':
        source = source[524288:]
    assert source[:8] == b'ANDROID!'
    page = struct.unpack_from('<I', source, 36)[0]
    assert page == 2048
    header = bytearray(source[:page])
    sizes = [struct.unpack_from('<I', source, i)[0] for i in (8, 16, 24, 40)]
    assert sizes[1] and sizes[3]
    align = lambda size: (size+page-1)//page*page
    parts, offset = [], page
    for size in sizes:
        assert offset + size <= len(source)
        parts.append(source[offset:offset+size])
        offset += align(size)
    kernel = args.kernel.read_bytes()
    assert kernel[:2] == b'\x1f\x8b'
    parts[0] = kernel
    struct.pack_into('<I', header, 8, len(kernel))
    digest = hashlib.sha1()
    for part in parts:
        digest.update(part)
        digest.update(struct.pack('<I', len(part)))
    header[576:608] = digest.digest() + bytes(12)
    result = bytes(header) + b''.join(part + bytes(align(len(part))-len(part)) for part in parts)
    assert len(result) <= 16777216
    args.output.write_bytes(result)
    print('RAM-test image:', args.output, len(result), hashlib.sha256(result).hexdigest())
    print('Original ramdisk and device tree preserved; installed boot untouched.')


if __name__ == '__main__':
    main()
