#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Real tmux/Tk tests on :9 and a private server; never close user terminals."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import subprocess
import tkinter as tk


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def main():
    os.environ['DISPLAY'] = ':9'
    server = 'moto-tabs-review-' + str(os.getpid())

    def command(*args):
        return subprocess.run(['tmux', '-L', server, *args], capture_output=True, text=True, timeout=2)

    shell = None
    module = load('tabs', str(Path(os.environ.get('MOTO_UI_REVIEW_DIR', '/usr/sbin')) / 'moto-terminals.py'))
    tabs = module.TerminalTabs(command)
    try:
        assert command('-f', '/dev/null', 'new-session', '-d', '-s', 'moto', '-n', 'local', '/bin/ash', '-l').returncode == 0
        tabs.run('set-option', '-g', 'renumber-windows', 'on')
        tabs.run('set-option', '-g', 'base-index', '1')
        first = tabs.list()[0]['id']
        a, b, c = tabs.new(), tabs.new(), tabs.new()
        try:
            tabs.new()
            raise AssertionError('Fifth tab must be refused')
        except RuntimeError:
            pass
        assert len(tabs.list()) == 4
        assert tabs.close(first)
        assert next(row['id'] for row in tabs.list() if row['active']) == c
        before_index = int(tabs.get(c)['index'])
        assert tabs.close(a) and not tabs.close(a)
        assert int(tabs.get(c)['index']) == before_index - 1
        assert tabs.get(b) and tabs.get(c)
        print('PASS: four-tab limit, stable targets after renumbering, inactive close preserves focus, stale close is harmless')

        tabs.close(b)
        replacement = tabs.close(c)
        assert replacement and len(tabs.list()) == 1 and command('has-session', '-t', 'moto').returncode == 0
        last = tabs.list()[0]['id']
        assert last != c
        original = tabs.command

        def fail_new(*args):
            if args[0] == 'new-window':
                return subprocess.CompletedProcess(args, 1, '', 'fixture: cannot allocate terminal')
            return original(*args)

        tabs.command = fail_new
        try:
            tabs.close(last)
            raise AssertionError('Replacement failure must refuse last close')
        except RuntimeError:
            pass
        finally:
            tabs.command = original
        assert tabs.get(last)
        tabs.run('rename-window', '-t', last, 'nome | com espacos')
        assert tabs.get(last)['name'] == 'nome | com espacos'
        print('PASS: closing last tab preserves session; replacement failure preserves the old terminal')

        while len(tabs.list()) < 4:
            tabs.new()
        ui = load('ui', str(Path(os.environ.get('MOTO_UI_REVIEW_DIR', '/usr/sbin')) / 'moto-shell'))
        ui.SOCKET = '/run/' + server + '.sock'
        ui.Shell.tmux = lambda self, *args: command(*args)
        ui.Shell.write_geometry = lambda self: None
        ui.Shell.vpn_worker = lambda self: None
        shell = ui.Shell()
        shell.device = ui.panel_module.services.snapshot()
        shell.device['ssh_auth'] = {}
        shell.refresh_tmux_once()
        shell.status(False)
        sent = []
        shell.keys.send = lambda *args: sent.append(args)

        def tap(action):
            box = next(box for box in shell.header_boxes if box[4] == action)
            x, y = int((box[0]+box[2])/2), int((box[1]+box[3])/2)
            shell.top.event_generate('<ButtonPress-1>', x=x, y=y)
            shell.top.event_generate('<ButtonRelease-1>', x=x, y=y)
            shell.root.update()

        def widgets(parent):
            for widget in parent.winfo_children():
                yield widget
                yield from widgets(widget)

        def button(text):
            return next(w for w in widgets(shell.panel.body) if isinstance(w, tk.Button) and w.cget('text') == text)

        shell.root.update()
        boxes = shell.header_boxes
        for i, box in enumerate(boxes):
            assert box[2]-box[0] >= 75 and box[3]-box[1] >= 76
            for other in boxes[i+1:]:
                assert min(box[2], other[2]) <= max(box[0], other[0]) or min(box[3], other[3]) <= max(box[1], other[1])
        select_box = next(box for box in boxes if box[4][0] == 'select')
        close_box = next(box for box in boxes if box[4] == ('close', select_box[4][1]))
        shell.top.event_generate('<ButtonPress-1>', x=int(select_box[0]+10), y=150)
        shell.top.event_generate('<ButtonRelease-1>', x=int(close_box[0]+10), y=150)
        shell.root.update()
        assert shell.menu is None and len(tabs.list()) == 4
        subprocess.run(['xwd', '-root', '-silent', '-out', '/tmp/moto-tabs-four.xwd'], check=True)
        inactive = next(row['id'] for row in tabs.list() if not row['active'])
        tap(('close', inactive))
        assert shell.panel.page == 'close-terminal' and tabs.get(inactive)
        frozen_active = next(row['id'] for row in tabs.list() if row['active'])
        button('Cancelar · voltar ao terminal').invoke()
        assert shell.menu is None and len(tabs.list()) == 4
        assert next(row['id'] for row in tabs.list() if row['active']) == frozen_active
        print('PASS: real header hitboxes do not overlap; close/cancel never kills or selects an inactive tab')

        tap(('close', inactive))
        subprocess.run(['xwd', '-root', '-silent', '-out', '/tmp/moto-tabs-confirm.xwd'], check=True)
        tabs.close(inactive)  # It disappears externally while confirmation remains open.
        expected = {row['id'] for row in tabs.list()}
        button('Fechar esta aba').invoke()
        assert {row['id'] for row in tabs.list()} == expected
        tap(('new',))
        assert len(tabs.list()) == 4 and shell.menu is None
        tap(('new',))
        assert len(tabs.list()) == 4 and shell.panel.page == 'terminals'
        subprocess.run(['xwd', '-root', '-silent', '-out', '/tmp/moto-tabs-manager.xwd'], check=True)
        tap(('panel',))
        assert shell.menu is None
        closing = next(row['id'] for row in tabs.list() if row['active'])
        expected = {row['id'] for row in tabs.list()} - {closing}
        tap(('close', closing))
        button('Fechar esta aba').invoke()
        assert {row['id'] for row in tabs.list()} == expected and shell.menu is None
        chosen = tabs.list()[0]['id']
        shell.panel.home()
        shell.root.update()
        for w in widgets(shell.panel.body):
            if w.winfo_ismapped():
                assert w.winfo_rooty()+w.winfo_height() <= shell.h, ('home clipped', str(w))
        tap(('select', chosen))
        assert shell.menu is None and tabs.get(chosen)['active']
        shell.panel.terminals()
        shell.emit('Escape')
        assert shell.menu is None and not sent
        print('PASS: stale confirmation preserves other IDs; + opens/limits tabs; selecting a tab, Voltar and Esc dismiss panels')
    finally:
        if shell:
            shell.sock.close()
            shell.root.destroy()
            Path('/run/' + server + '.sock').unlink(missing_ok=True)
        command('kill-server')


if __name__ == '__main__':
    main()
