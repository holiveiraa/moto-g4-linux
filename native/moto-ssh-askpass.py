#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""OpenSSH askpass: one saved password, other prompts remain interactive."""
import importlib.util
import os
from pathlib import Path
import sys
import termios


def tty_answer(prompt, echo=False, notification=False):
    fd = os.open('/dev/tty', os.O_RDWR)
    previous = termios.tcgetattr(fd)
    try:
        current = termios.tcgetattr(fd)
        if not echo:
            current[3] &= ~termios.ECHO
        termios.tcsetattr(fd, termios.TCSADRAIN, current)
        # All UI goes to the controlling terminal. stdout belongs to OpenSSH.
        os.write(fd, prompt.encode('utf-8', errors='replace'))
        if notification:
            os.write(fd, b'\r\n')
            return None
        answer = bytearray()
        while len(answer) <= 2048:
            char = os.read(fd, 1)
            if not char or char == b'\x04':
                raise RuntimeError('Entrada cancelada.')
            if char in (b'\r', b'\n'):
                return answer.decode('utf-8')
            answer.extend(char)
        raise RuntimeError('Resposta muito longa.')
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)
        if not echo:
            os.write(fd, b'\r\n')
        os.close(fd)


def answer(prompt, store, ident, hint='', interactive=tty_answer, endpoint=None):
    profile = store.find(ident)
    expected = profile['user']+'@'+profile['host']+"'s password:"
    # Password autofill is enabled only with keyboard-interactive disabled by
    # the launcher. Never send it to host-key, key-passphrase or OTP prompts.
    if endpoint and not hint and prompt.strip() == expected:
        password = store.password(ident, endpoint)
        if password is not None:
            return password
    confirm = hint == 'confirm' or prompt.startswith('Are you sure you want to continue connecting')
    return interactive(prompt, echo=confirm, notification=hint == 'none')


def main():
    try:
        if len(sys.argv) != 2:
            return 1
        spec = importlib.util.spec_from_file_location('moto_hosts', Path(__file__).with_name('moto-hosts.py'))
        hosts = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hosts)
        result = answer(sys.argv[1], hosts.HostStore(), os.environ.get('MOTO_SSH_DESTINATION', ''),
                        os.environ.get('SSH_ASKPASS_PROMPT', ''), endpoint=os.environ.get('MOTO_SSH_ENDPOINT'))
        if result is not None:
            sys.stdout.write(result+'\n')
            sys.stdout.flush()
        return 0
    except (OSError, RuntimeError, ValueError, KeyboardInterrupt):
        sys.stderr.write('Não foi possível responder à autenticação. Use Abrir com entrada manual.\n')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
