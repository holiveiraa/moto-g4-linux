#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Saved destination validation/persistence. Never contacts a server."""
import importlib.util
import json
import os
from test_support import EXAMPLE_HOST
from pathlib import Path
import tempfile
import unittest

root = Path(os.environ.get('MOTO_UI_REVIEW_DIR', Path(__file__).resolve().parents[1]/'native'))
spec = importlib.util.spec_from_file_location('hosts', root/'moto-hosts.py')
hosts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hosts)


class Hosts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'private/hosts.json'
        self.store = hosts.HostStore(self.path, initial=[EXAMPLE_HOST])
    def tearDown(self): self.temp.cleanup()
    def profile(self, **kwargs):
        return dict(EXAMPLE_HOST, **kwargs)
    def test_existing_example_server_identity_is_preserved_without_writing(self):
        row = self.store.find('example-server')
        self.assertEqual((row['user'], row['mode']), ('demo', 'tailscale'))
        self.assertFalse(self.path.exists())
        self.assertEqual(hosts.HostStore(self.path).list(), [])

    def test_create_edit_reload_remove_and_private_modes(self):
        row = self.store.save(self.profile(name='Meu servidor', host='host.example', mode='ssh', port=2222))
        self.assertNotEqual(row['id'], 'example-server')
        self.assertEqual(hosts.HostStore(self.path).find(row['id'])['port'], 2222)
        changed = self.store.save(dict(row, name='Outro nome'), row['id'])
        self.assertEqual(changed['id'], row['id'])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o700)
        self.store.remove(row['id'])
        self.assertEqual(len(self.store.list()), 1)
        self.assertFalse(list(self.path.parent.glob('.hosts-*')))
    def test_removing_default_does_not_resurrect_it(self):
        self.store.remove('example-server')
        self.assertEqual(hosts.HostStore(self.path).list(), [])
    def test_corrupt_file_is_not_overwritten(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text('broken')
        with self.assertRaises(RuntimeError): self.store.save(self.profile())
        self.assertEqual(self.path.read_text(), 'broken')
    def test_secrets_and_extra_fields_are_not_stored(self):
        self.store.save(self.profile(password='fixture-secret', private_key='fixture-secret'))
        self.assertNotIn('fixture-secret', self.path.read_text())
    def test_optional_password_is_separate_private_bound_and_explicitly_removed(self):
        row = self.store.save(self.profile(mode='ssh'), password='fixture-secret')
        ident = row['id']
        self.assertEqual(self.store.password(ident), 'fixture-secret')
        self.assertNotIn('fixture-secret', self.path.read_text())
        self.assertEqual(self.store.secret_path(ident).stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.store.secret_dir.stat().st_mode & 0o777, 0o700)
        self.store.save(dict(row, name='Renamed'), ident)
        self.assertEqual(self.store.password(ident), 'fixture-secret')
        self.store.save(dict(row, host='another.example'), ident)
        self.assertIsNone(self.store.password(ident))
        self.store.save(row, ident, password='new-fixture')
        self.store.remove_password(ident)
        self.assertIsNone(self.store.password(ident))
        self.assertEqual(self.store.find(ident)['host'], row['host'])

    def test_password_removal_follows_favorite_and_tailscale_never_uses_it(self):
        row = self.store.save(self.profile(mode='ssh'), password='fixture')
        self.store.remove(row['id'])
        self.assertFalse(self.store.secret_path(row['id']).exists())
        row = self.store.save(self.profile(mode='ssh'), password='fixture')
        self.store.save(dict(row, mode='tailscale'), row['id'])
        self.assertIsNone(self.store.password(row['id']))
        with self.assertRaises(ValueError): self.store.save(self.profile(), password='fixture')

    def test_password_rollback_and_invalid_secret_never_leak(self):
        from unittest.mock import patch
        row = self.store.save(self.profile(mode='ssh'), password='old-fixture')
        with patch.object(self.store, 'write', side_effect=OSError('fixture write failure')):
            with self.assertRaises(OSError): self.store.save(row, row['id'], password='new-fixture')
        self.assertEqual(self.store.password(row['id']), 'old-fixture')
        for value in ('bad\npassword', 'a'*513, '\x00'):
            with self.assertRaises(ValueError): self.store.save(row, row['id'], password=value)
        self.assertEqual(self.store.password(row['id']), 'old-fixture')
        self.store.secret_path(row['id']).write_text('invalid')
        with self.assertRaises(RuntimeError): self.store.password(row['id'])
    def test_no_shell_or_option_injection(self):
        for field, values in {'host': ['-oProxyCommand=bad', 'host;id', 'host\n', 'x y', 'x$(id)', 'x\x00'],
                              'user': ['-oX', 'root;id', 'a b', 'x\n'],
                              'port': ['0', '65536', '-p22', '22;id'],
                              'name': ['x\n', '\x1b[31m']}.items():
            for value in values:
                with self.subTest(field=field, value=repr(value)):
                    with self.assertRaises(ValueError): hosts.validate(self.profile(**{field: value}))
    def test_argv_preserves_host_verification_and_distinguishes_modes(self):
        self.assertEqual(hosts.command_argv(EXAMPLE_HOST), ['tailscale', 'ssh', 'demo@server.example'])
        argv = hosts.command_argv(self.profile(mode='ssh', host='::1', port=2222))
        self.assertIn('StrictHostKeyChecking=ask', argv)
        self.assertEqual(argv[-1], '::1')
        self.assertEqual(argv[argv.index('-p')+1], '2222')
        with self.assertRaises(ValueError): hosts.command_argv(self.profile(port=2222))
    def test_stale_ids_do_not_change_another_destination(self):
        self.store.remove('example-server')
        with self.assertRaises(RuntimeError): self.store.save(self.profile(), 'example-server')
        self.assertEqual(self.store.list(), [])
    def test_last_used_does_not_change_identity(self):
        self.store.used('example-server')
        row = self.store.find('example-server')
        self.assertGreater(row['last_used'], 0)
        self.assertEqual(row['user'], 'demo')


if __name__ == '__main__': unittest.main()
