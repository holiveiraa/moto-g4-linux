#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Offline preference, declarative theme and input-layout contracts."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('experience_test', Path(__file__).resolve().parents[1]/'native/moto-experience.py')
ux = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ux)


class ExperienceTests(unittest.TestCase):
    def test_preferences_merge_and_private_atomic_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'settings/ux.json'
            ux.save_preferences({'brightness': 88, 'theme': 'paper', 'unknown': 'preserve'}, path)
            ux.save_preferences({'keyboard': 'code'}, path)
            ux.save_preferences({'brightness': 120}, path)
            self.assertEqual(ux.preferences(path), {'brightness': 120, 'theme': 'paper', 'unknown': 'preserve', 'keyboard': 'code'})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(path.parent.glob('.ux-*')), [])

    def test_corrupt_or_oversized_preferences_fall_back(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'ux.json'
            for value in ('[1,2]', '{broken', 'x'*65537):
                path.write_text(value)
                self.assertEqual(ux.preferences(path), {})

    def test_untrusted_theme_never_becomes_terminal_code(self):
        evil = '\x1b]52;c;payload\x07;touch /tmp/unwanted'
        self.assertEqual(ux.color_sequence(evil), ux.color_sequence('moto'))
        self.assertNotIn(b'52;', ux.color_sequence(evil))
        self.assertNotIn('payload', ' '.join(ux.terminal_argv({'theme': evil, 'font_size': evil})))

    def test_all_theme_colors_are_fixed_hex_and_readable(self):
        def luminance(color):
            channels = [int(color[n:n+2], 16)/255 for n in (1, 3, 5)]
            linear = [c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4 for c in channels]
            return sum(c*w for c, w in zip(linear, (.2126, .7152, .0722)))
        def contrast(a, b):
            x, y = sorted((luminance(a), luminance(b)))
            return (y+.05)/(x+.05)
        for name in ux.THEMES:
            p = ux.palette(name)
            for color in p.values():
                self.assertRegex(color, r'^#[0-9A-Fa-f]{6}$')
            for foreground in ('FG', 'MUTED', 'ACCENT', 'ERROR'):
                self.assertGreaterEqual(contrast(p[foreground], p['BG']), 4.5, (name, foreground))
            self.assertGreaterEqual(contrast(p['FG'], p['KEY']), 4.5)
            self.assertGreaterEqual(contrast(p['BG'], p['ACCENT']), 4.5)

    def test_keyboard_has_portuguese_and_keeps_terminal_navigation(self):
        actions = lambda page, symbols=False: {action for row in ux.keyboard_rows(page, symbols) for _, action in row}
        self.assertTrue(set('áàâãéêíóôõúç') <= actions('text'))
        self.assertTrue(set('[]{}()=<>') <= actions('code'))
        for page in ux.KEYBOARDS:
            self.assertTrue({'Escape', 'Tab', 'mod:Ctrl', 'mod:Alt', 'Left', 'Right', 'BackSpace'} <= actions(page))
        self.assertTrue(set('1234567890') <= actions('text', True))

    def test_safe_defaults(self):
        for value in (None, [], {}, 'bad'):
            self.assertEqual(ux.font_size(value), 18)
            self.assertEqual(ux.keyboard_name(value), 'terminal')
            self.assertEqual(ux.theme_name(value), 'moto')
        self.assertEqual(ux.font_size(999), 30)
        self.assertEqual(ux.font_size(-999), 10)

    def test_launcher_uses_argv_and_preserves_terminal_contracts(self):
        argv = ux.terminal_argv({'theme': 'paper', 'font_size': 22})
        self.assertEqual(argv[0], 'xterm')
        self.assertEqual(argv[argv.index('-fs')+1], '22')
        self.assertIn('XTerm*cursorBlink: false', argv)
        self.assertEqual(argv[-2:], ['-e', '/usr/sbin/moto-terminal-session'])
        self.assertNotIn('sh', argv)


if __name__ == '__main__':
    unittest.main()
