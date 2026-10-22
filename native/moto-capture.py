# SPDX-License-Identifier: MIT
"""Shared ALSA capture lease; inherited by the child until it exits."""
import fcntl
import os
from pathlib import Path
import stat

LOCK = Path('/run/moto-capture.lock')


class CaptureLease:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else LOCK
        self.fd = None

    def acquire(self):
        if self.fd is not None:
            return
        fd = None
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise OSError('unsafe capture lease')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.fd = fd
        except OSError:
            if fd is not None:
                os.close(fd)
            raise RuntimeError('Microfone em uso ou indisponível. Termine a outra gravação.') from None

    def fileno(self):
        if self.fd is None:
            raise RuntimeError('Microfone sem reserva.')
        return self.fd

    def release(self):
        if self.fd is not None:
            # Closing, rather than explicit LOCK_UN, preserves a lease inherited
            # by a still-running capture child when its parent unexpectedly exits.
            os.close(self.fd)
            self.fd = None
