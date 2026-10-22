# SPDX-License-Identifier: MIT
"""Declarative built-in appearance and keyboard layouts; no background work."""
import json
import os
from pathlib import Path
import tempfile


THEMES = {
    'moto': {'name': 'Jade', 'detail': 'Verde suave · a identidade do Moto',
        'BG': '#0B1118', 'PANEL': '#141E2A', 'KEY': '#1E2C3B', 'FG': '#F1F5FA',
        'MUTED': '#A8B8CA', 'ACCENT': '#68E3BC', 'ERROR': '#FFADB6',
        'SELECTED': '#205745', 'BORDER': '#34465A', 'DANGER': '#593040', 'PRESS': '#365979'},
    'midnight': {'name': 'Meia-noite', 'detail': 'Azul profundo · detalhes em lavanda',
        'BG': '#161824', 'PANEL': '#202335', 'KEY': '#2B3048', 'FG': '#E2E6FF',
        'MUTED': '#B0B9D8', 'ACCENT': '#B3ABFF', 'ERROR': '#FFADB6',
        'SELECTED': '#3D4168', 'BORDER': '#48516F', 'DANGER': '#633347', 'PRESS': '#484F76'},
    'paper': {'name': 'Papel', 'detail': 'Claro · texto escuro e contraste alto',
        'BG': '#F4F1E9', 'PANEL': '#E8E4D9', 'KEY': '#DCD8CD', 'FG': '#202C29',
        'MUTED': '#505D57', 'ACCENT': '#166B4D', 'ERROR': '#9F243E',
        'SELECTED': '#C3DCCB', 'BORDER': '#8B968D', 'DANGER': '#E8C6CE', 'PRESS': '#B5CEC2'},
}
COLOR_KEYS = tuple(key for key in THEMES['moto'] if key.isupper())
KEYBOARDS = {'terminal': 'Terminal', 'code': 'Código', 'text': 'Português'}


def config_path():
    return Path(os.environ.get('MOTO_UX_CONFIG', '/root/.config/moto-linux/ux.json'))


def preferences(path=None):
    try:
        path = Path(path) if path is not None else config_path()
        if path.stat().st_size > 65536:
            return {}
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def save_preferences(changes, path=None):
    """Merge explicit edits, preserving brightness and other installed settings."""
    path = Path(path) if path is not None else config_path()
    value = preferences(path)
    value.update(changes)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.ux-', delete=False) as output:
            name = output.name
            os.fchmod(output.fileno(), 0o600)
            json.dump(value, output, ensure_ascii=False)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
    finally:
        if name is not None:
            Path(name).unlink(missing_ok=True)


def theme_name(name):
    return name if isinstance(name, str) and name in THEMES else 'moto'


def palette(name):
    return {key: THEMES[theme_name(name)][key] for key in COLOR_KEYS}


def font_size(value):
    try:
        return max(10, min(30, int(value)))
    except (ValueError, TypeError, OverflowError):
        return 18


def keyboard_name(value):
    return value if isinstance(value, str) and value in KEYBOARDS else 'terminal'


def keyboard_rows(page, symbols=False):
    page = keyboard_name(page)
    rows = [[('Esc', 'Escape'), ('Tab', 'Tab'), ('Ctrl', 'mod:Ctrl'), ('Alt', 'mod:Alt'),
             ('←', 'Left'), ('↑', 'Up'), ('↓', 'Down'), ('→', 'Right')]]
    if symbols:
        rows += [[(s, s) for s in ('1234567890' if page != 'terminal' else '!@#$%&*()=')],
                 [(s, s) for s in '[]{}<>_+|~'], [(s, s) for s in '\\:;\'"`?,.'],
                 [('Home', 'Home'), ('End', 'End'), ('Pg↑', 'Prior'), ('Pg↓', 'Next'),
                  ('Del', 'Delete'), ('⌫', 'BackSpace')]]
    else:
        first = {'terminal': '1234567890', 'code': '[]{}()=<>', 'text': 'áàâãéêíóôõ'}[page]
        rows += [[(s, s) for s in first], [(s, s) for s in 'qwertyuiop'],
                 [(s, s) for s in ('asdfghjklç' if page == 'text' else 'asdfghjkl')],
                 [('⇧', 'mod:Shift')] + [(s, s) for s in ('zxcvbnmú' if page == 'text' else 'zxcvbnm')]
                 + [('⌫', 'BackSpace')]]
    return rows


def terminal_colors(name):
    p = palette(name)
    base = ['#202632', '#C54D61', '#29805B', '#A37424', '#447CCF', '#975BC2', '#258080', '#CFD5DF',
            '#606C7D', '#FF8496', '#68CF9B', '#E8C078', '#8EBAFF', '#C6ACFF', '#83D5D0', '#F1F5FA']
    if theme_name(name) == 'paper':
        base = ['#202C29', '#A52D42', '#176B48', '#805C16', '#285B9F', '#75449F', '#176970', '#DCD8CD',
                '#505D57', '#A52D42', '#176B48', '#805C16', '#285B9F', '#75449F', '#176970', '#F4F1E9']
    return p, base


def color_sequence(name):
    """Only trusted built-in color values, never text from a form or a theme file."""
    p, colors = terminal_colors(name)
    entries = [('10', p['FG']), ('11', p['BG']), ('12', p['ACCENT'])]
    return (''.join('\x1b]'+key+';'+value+'\x07' for key, value in entries)
            + ''.join('\x1b]4;'+str(i)+';'+color+'\x07' for i, color in enumerate(colors))).encode('ascii')


def terminal_argv(prefs=None):
    prefs = preferences() if prefs is None else prefs
    p, colors = terminal_colors(prefs.get('theme'))
    args = ['xterm', '-u8', '-fa', 'DejaVu Sans Mono', '-fs', str(font_size(prefs.get('font_size', 18))),
            '-bg', p['BG'], '-fg', p['FG'], '-cr', p['ACCENT'], '-b', '12', '-sb', '-rightbar',
            '-sl', '10000', '-title', 'Moto G4 - Linux nativo', '-geometry', '44x28+0+104']
    resources = ['metaSendsEscape: true', 'altSendsEscape: true', 'backarrowKey: false',
                 'cursorBlink: false', 'allowColorOps: true',
                 'VT100.Translations: #override Shift <Key>KP_Add: larger-vt-font()\\nShift <Key>KP_Subtract: smaller-vt-font()']
    resources += ['color'+str(i)+': '+color for i, color in enumerate(colors)]
    for resource in resources:
        args += ['-xrm', 'XTerm*'+resource]
    return args + ['-e', '/usr/sbin/moto-terminal-session']


if __name__ == '__main__':
    import sys
    if sys.argv[1:] != ['terminal']:
        raise SystemExit('Use terminal')
    arguments = terminal_argv()
    os.execvp(arguments[0], arguments)
