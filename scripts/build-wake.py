#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compatibility entry point: builds speech detection only, never local ASR."""
from pathlib import Path
import runpy

if __name__ == '__main__':
    runpy.run_path(str(Path(__file__).with_name('build-hearing.py')), run_name='__main__')
