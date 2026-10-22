# SPDX-License-Identifier: MIT
"""Repackage our tested kernel/root loader with a standard QCDT for lk2nd.

The vendor's table uses Motorola IDs and an extended 0x103 entry format.
lk2nd uses Qualcomm v1/v2/v3 tables. Keep the actual stock Athene 16MP DTB
unchanged and select it with the IDs of lk2nd's explicit MSM8952 MTP database.
No partition writes; private stock DT remains a device-specific build input.
"""
from pathlib import Path
import hashlib
import struct

ROOT = Path(__file__).resolve().parents[1]
PAGE = 2048


def aligned(size):
    return (size + PAGE - 1) // PAGE * PAGE


def pad(data):
    return data + bytes(aligned(len(data)) - len(data))


def main():
    stock = (ROOT / 'out/stock-dt.img').read_bytes()
    assert struct.unpack_from('<4sII', stock) == (b'QCDT', 0x103, 9)
    matches = []
    for index in range(9):
        start = 12 + index * 72
        fields = struct.unpack_from('<10I', stock, start)
        name = stock[start + 40:start + 72].split(b'\0')[0]
        if name == b'Athene_16MP' and fields[2] == 0x81a0:
            offset, size = fields[8:10]
            dtb = stock[offset:offset + size]
            assert dtb[:4] == b'\xd0\x0d\xfe\xed'
            actual = struct.unpack_from('>I', dtb, 4)[0]
            assert 40 <= actual <= size and offset + size <= len(stock)
            matches.append(dtb[:actual])
    assert len(matches) == 1, 'Expected exactly one original Athene_16MP DTB'
    dtb = matches[0]
    table_header = struct.pack('<4sII6I', b'QCDT', 2, 1,
                               264, 8, 0, 0, PAGE, len(dtb))
    table = pad(table_header) + pad(dtb)
    (ROOT / 'out/athene-stock-16mp.dtb').write_bytes(dtb)
    (ROOT / 'out/athene-lk2nd-dt.img').write_bytes(table)

    original = (ROOT / 'out/athene-persistent.img').read_bytes()
    assert original[:8] == b'ANDROID!'
    header = bytearray(original[:PAGE])
    # Stock Motorola used to rewrite the console flags for us. With lk2nd,
    # make that choice explicit and leave room for the firmware's own cmdline.
    cmdline = (b'console=null androidboot.hardware=qcom msm_rtb.filter=0x237 '
               b'ehci-hcd.park=3 androidboot.bootdevice=7824900.sdhci '
               b'lpm_levels.sleep_disabled=1 buildvariant=userdebug '
               b'boot_cpus=0-7 rdinit=/init')
    assert len(cmdline) < 512
    header[64:576] = cmdline + bytes(512 - len(cmdline))
    assert struct.unpack_from('<I', header, 36)[0] == PAGE
    sizes = [struct.unpack_from('<I', header, offset)[0] for offset in (8, 16, 24)]
    offset = PAGE
    parts = []
    for size in sizes:
        parts.append(original[offset:offset + size])
        offset += aligned(size)
    assert parts[0][:2] == b'\x1f\x8b'
    struct.pack_into('<I', header, 40, len(table))
    digest = hashlib.sha1()
    for part in parts + [table]:
        digest.update(part)
        digest.update(struct.pack('<I', len(part)))
    header[576:608] = digest.digest() + bytes(12)
    result = bytes(header) + b''.join(pad(p) for p in parts) + pad(table)
    assert len(result) + 524288 <= 16777216
    target = ROOT / 'out/athene-lk2nd-linux.img'
    target.write_bytes(result)
    print(target.name, len(result), hashlib.sha256(result).hexdigest())
    print('Kernel and initramfs unchanged; original 16MP DTB SHA256:',
          hashlib.sha256(dtb).hexdigest())
    loader = (ROOT / 'out/lk2nd-athene.img').read_bytes()
    assert loader[:8] == b'ANDROID!' and len(loader) <= 524288
    combined = loader + bytes(524288 - len(loader)) + result
    assert len(combined) <= 16777216
    combined += bytes(16777216 - len(combined))
    (ROOT / 'out/athene-lk2nd-full.img').write_bytes(combined)
    print('Full boot, lk2nd + native Linux at 512 KiB:',
          hashlib.sha256(combined).hexdigest())


if __name__ == '__main__':
    main()
