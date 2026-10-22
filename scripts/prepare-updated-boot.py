#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Wrap a RAM-tested kernel payload in the existing lk2nd boot container.

No device writes. Refuse changes to the loader, ramdisk, second stage or DT.
"""
import argparse
import hashlib
from pathlib import Path
import struct


def parts(payload):
    assert payload[:8] == b'ANDROID!'
    page = struct.unpack_from('<I', payload, 36)[0]
    assert page == 2048
    sizes = [struct.unpack_from('<I', payload, p)[0] for p in (8, 16, 24, 40)]
    result, offset = [], page
    for size in sizes:
        assert offset + size <= len(payload)
        result.append(payload[offset:offset + size])
        offset += (size + page - 1) // page * page
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    original, payload = args.source.read_bytes(), args.payload.read_bytes()
    assert hashlib.sha256(original).hexdigest() == args.source_sha256
    assert len(original) == 16777216 and original[:8] == b'ANDROID!'
    assert original[-4096:] == bytes(4096)
    assert parts(original[524288:])[1:] == parts(payload)[1:]
    assert len(payload) + 524288 <= len(original) - 4096
    result = (original[:524288] + payload).ljust(len(original), b'\0')
    assert result[:524288] == original[:524288]
    assert result[-4096:] == bytes(4096)
    args.output.write_bytes(result)
    print('Full boot:', args.output, len(result), hashlib.sha256(result).hexdigest())
    print('Existing lk2nd, ramdisk and device tree preserved byte for byte.')


if __name__ == '__main__':
    main()
