#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Controlled maintenance reboot into recovery on this ARM64 native port."""
import ctypes
import os
from pathlib import Path
import platform

assert platform.machine() == 'aarch64'
assert os.geteuid() == 0 and Path('/etc/moto-persistent').is_file()
os.sync()
libc = ctypes.CDLL(None, use_errno=True)
# ARM64 __NR_reboot, same RESTART2 path as the existing reboot-bootloader helper.
libc.syscall.restype = ctypes.c_long
result = libc.syscall(ctypes.c_long(142), ctypes.c_long(0xfee1dead),
                      ctypes.c_long(672274793), ctypes.c_long(0xa1b2c3d4),
                      ctypes.c_char_p(b'recovery'))
if result < 0:
    raise OSError(ctypes.get_errno(), 'reboot to recovery failed')
