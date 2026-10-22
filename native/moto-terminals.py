# SPDX-License-Identifier: MIT
"""Small tmux tab controller. All mutations target immutable window IDs."""
import re


class TerminalTabs:
    LIMIT = 4
    FORMAT = '#{window_id}|#{window_index}|#{window_active}|#{window_name}'

    def __init__(self, command, session='moto'):
        self.command = command
        self.session = session
        self.launcher = '/usr/sbin/moto-ssh-launch'

    def run(self, *args):
        result = self.command(*args)
        if result.returncode:
            raise RuntimeError('Não foi possível atualizar os terminais. Tente novamente.')
        return result.stdout.strip()

    def list(self):
        rows = []
        for line in self.run('list-windows', '-t', self.session, '-F', self.FORMAT).splitlines():
            fields = line.split('|', 3)
            if len(fields) != 4 or not re.fullmatch(r'@\d+', fields[0]) or not fields[1].isdigit():
                continue
            ident, index, active, name = fields
            name = ''.join(c for c in name if c.isprintable()) or 'terminal'
            rows.append({'id': ident, 'index': index, 'active': active == '1',
                         'name': 'local' if name in ('ash', 'sh', 'bash', 'zsh') else name})
        return rows

    def get(self, ident):
        if not re.fullmatch(r'@\d+', ident):
            raise ValueError('Identificador de aba inválido')
        return next((row for row in self.list() if row['id'] == ident), None)

    def select(self, ident):
        if self.get(ident) is None:
            return False
        self.run('select-window', '-t', ident)
        return True

    def new(self, ssh=False, profile=None, manual=False):
        if len(self.list()) >= self.LIMIT:
            raise RuntimeError('Quatro abas abertas. Feche uma para abrir outra.')
        if ssh:
            if profile is None:
                raise ValueError('Escolha um destino salvo no menu SSH.')
            if not re.fullmatch(r'(?:[a-f0-9]{32}|[a-z][a-z0-9_-]{0,31})', str(profile.get('id', ''))) or profile.get('mode') not in ('ssh', 'tailscale'):
                raise ValueError('Favorito SSH inválido.')
        name = profile['name'] if ssh else 'local'
        args = ['new-window', '-P', '-F', '#{window_id}', '-t', self.session, '-n', name]
        # Multiple command arguments use tmux direct execution. Editable fields
        # never enter a shell command; only a validated immutable ID is passed.
        args += [self.launcher, profile['id']] if ssh else ['/bin/ash', '-l']
        if ssh and manual:
            args.append('--manual')
        ident = self.run(*args)
        if not re.fullmatch(r'@\d+', ident) or self.get(ident) is None:
            raise RuntimeError('A nova aba não ficou disponível; as abas anteriores foram preservadas.')
        self.run('set-window-option', '-t', ident, 'automatic-rename', 'off' if ssh else 'on')
        if ssh:
            self.run('set-window-option', '-t', ident, '@moto_ssh_mode', profile['mode'])
        return ident

    def close(self, ident):
        if not re.fullmatch(r'@\d+', ident):
            raise ValueError('Identificador de aba inválido')
        rows = self.list()
        target = next((row for row in rows if row['id'] == ident), None)
        if target is None:
            return False
        active = next((row['id'] for row in rows if row['active']), None)
        if len(rows) == 1:
            # Never destroy the last session/client before a replacement exists.
            focus = self.new()
        elif active != ident:
            focus = active
        else:
            position = next(i for i, row in enumerate(rows) if row['id'] == ident)
            focus = rows[position + 1 if position + 1 < len(rows) else position - 1]['id']
        self.run('kill-window', '-t', ident)
        if focus and self.get(focus):
            self.run('select-window', '-t', focus)
        return True
