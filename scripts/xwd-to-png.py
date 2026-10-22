#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Convert an Xorg screen capture for local visual inspection (Pillow)."""
from pathlib import Path
import struct
import sys
from PIL import Image

source, target = map(Path, sys.argv[1:])
data = source.read_bytes()
header = struct.unpack('!25I', data[:100])
assert header[1] == 7 and header[11] == 32 and header[7] == 0, 'Expected little-endian 32-bit XWD'
mode = {(255, 65280, 16711680): 'RGBX', (16711680, 65280, 255): 'BGRX'}[tuple(header[14:17])]
pixels = data[header[0] + header[19] * 12:]
Image.frombytes('RGB', (header[4], header[5]), pixels, 'raw', mode, header[12], 1).save(target)
