#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run only offline regressions: no phone, cloud API or live user session."""
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
TESTS=('test-mobile-input.py','test-wifi-profiles.py','test-audio-start.py',
       'test-voice.py','test-quick-voice.py','test-ssh-hosts.py','test-ssh-password.py',
       'test-tailscale-ux.py','test-groq-configure.py','test-clean-userspace.py','test-wiki-export.py',
       'test-experience.py')


def main():
    if sys.platform=='win32':
        print('Run this suite on Linux/WSL: it tests POSIX locks, termios and symlinks.',file=sys.stderr)
        return 2
    for name in TESTS:
        print('\n'+name,flush=True)
        result=subprocess.run([sys.executable,str(ROOT/'tests'/name)],cwd=ROOT)
        if result.returncode:return result.returncode
    print('\nAll offline regressions passed. No handset installation was performed.')
    return 0


if __name__=='__main__':raise SystemExit(main())
