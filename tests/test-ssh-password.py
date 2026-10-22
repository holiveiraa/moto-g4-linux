#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Authentication selection and prompt routing; synthetic secrets only."""
import importlib.util
import os
from test_support import EXAMPLE_HOST
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

root = Path(os.environ.get('MOTO_UI_REVIEW_DIR', Path(__file__).resolve().parents[1]/'native'))
def load(name):
    spec = importlib.util.spec_from_file_location(name, root/(name+'.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module
hosts, ask, launch = (load(name) for name in ('moto-hosts','moto-ssh-askpass','moto-ssh-launch'))


class Password(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = hosts.HostStore(Path(self.temp.name)/'hosts.json')
        self.row = self.store.save(dict(EXAMPLE_HOST, mode='ssh'), password='fixture-$-secret')
    def tearDown(self): self.temp.cleanup()

    def test_no_password_and_manual_keep_standard_auth(self):
        for manual in (True, False):
            if not manual: self.store.remove_password(self.row['id'])
            options, env = launch.connection_options(self.row, self.store, manual, {'SSH_ASKPASS_REQUIRE':'force'})
            self.assertEqual(options, [])
            self.assertNotIn('SSH_ASKPASS_REQUIRE', env)
    def test_password_is_not_in_argv_or_environment(self):
        options, env = launch.connection_options(self.row, self.store, environ={})
        self.assertIn('KbdInteractiveAuthentication=no', options)
        self.assertEqual(env['MOTO_SSH_DESTINATION'], self.row['id'])
        self.assertNotIn('fixture-$-secret', repr((options, env)))
    def test_tailscale_does_not_read_password(self):
        store = Mock()
        options, env = launch.connection_options(EXAMPLE_HOST, store, environ={})
        self.assertEqual(options, [])
        store.password.assert_not_called()
    def test_only_standard_password_prompt_is_automatic(self):
        interactive = Mock(side_effect=AssertionError('Unexpected terminal interaction'))
        value = ask.answer("demo@server.example's password: ", self.store, self.row['id'], interactive=interactive,
                           endpoint=self.store.endpoint_token(self.row))
        self.assertEqual(value, 'fixture-$-secret')
    def test_host_key_otp_private_key_and_notification_never_get_saved_secret(self):
        for prompt, hint in [('Are you sure you want to continue connecting (yes/no/[fingerprint])? ', ''),
                              ('Verification code: ', ''), ('Enter passphrase for key: ', ''),
                              ("demo@server.example's password: ", 'confirm'), ('Notice', 'none')]:
            interactive = Mock(return_value='manual-response')
            self.assertEqual(ask.answer(prompt,self.store,self.row['id'],hint,interactive), 'manual-response')
            interactive.assert_called_once()

    def test_editing_port_and_password_while_connecting_never_sends_new_secret_to_old_endpoint(self):
        endpoint = self.store.endpoint_token(self.row)
        self.store.save(dict(self.row,port=2222), self.row['id'], password='new-endpoint-secret')
        interactive = Mock(return_value='manual-response')
        value = ask.answer("demo@server.example's password: ", self.store, self.row['id'], interactive=interactive, endpoint=endpoint)
        self.assertEqual(value, 'manual-response')
        interactive.assert_called_once()
        options,env = launch.connection_options(self.row,self.store,environ={})
        self.assertEqual(options, [])


if __name__ == '__main__': unittest.main()
