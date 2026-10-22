#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Launch one saved SSH destination using argv, then leave a local shell."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys


def connection_options(profile, store, manual=False, environ=None):
    env = dict(os.environ if environ is None else environ)
    for key in ('SSH_ASKPASS', 'SSH_ASKPASS_REQUIRE', 'SSH_ASKPASS_PROMPT', 'MOTO_SSH_DESTINATION', 'MOTO_SSH_ENDPOINT'):
        env.pop(key, None)
    endpoint = store.endpoint_token(profile) if profile['mode'] == 'ssh' else None
    if manual or profile['mode'] != 'ssh' or store.password(profile['id'], endpoint) is None:
        return [], env
    env.update(SSH_ASKPASS=str(Path(__file__).with_name('moto-ssh-askpass')),
               SSH_ASKPASS_REQUIRE='force', MOTO_SSH_DESTINATION=profile['id'], MOTO_SSH_ENDPOINT=endpoint)
    return ['-o', 'KbdInteractiveAuthentication=no', '-o', 'PasswordAuthentication=yes',
            '-o', 'PreferredAuthentications=publickey,password', '-o', 'NumberOfPasswordPrompts=1'], env


def main():
    spec = importlib.util.spec_from_file_location('moto_hosts', Path(__file__).with_name('moto-hosts.py'))
    hosts = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hosts)
    try:
        if len(sys.argv) not in (2, 3) or (len(sys.argv) == 3 and sys.argv[2] != '--manual'):
            raise ValueError('Selecione um favorito no menu SSH.')
        store = hosts.HostStore()
        profile = store.find(sys.argv[1])
        argv = hosts.command_argv(profile)
        options, env = connection_options(profile, store, manual=len(sys.argv) == 3)
        argv = argv[:1]+options+argv[1:]
        try:
            store.used(profile['id'])
        except (OSError, RuntimeError):
            print('Não foi possível registrar o último uso do favorito.', flush=True)
        print('Conectando a '+profile['user']+'@'+profile['host']+':'+str(profile['port'])+'…', flush=True)
        result = subprocess.run(argv, check=False, env=env)
        if result.returncode and options:
            print('Se a senha mudou ou o servidor pede código adicional, use Abrir com entrada manual ou edite o favorito.', flush=True)
        print('\nSessão SSH encerrada. Terminal local disponível.', flush=True)
    except (OSError, RuntimeError, ValueError) as exc:
        print(str(exc), flush=True)
    except KeyboardInterrupt:
        print('\nConexão cancelada. Terminal local disponível.', flush=True)
    os.execv('/bin/ash', ['/bin/ash', '-l'])


if __name__ == '__main__': main()
