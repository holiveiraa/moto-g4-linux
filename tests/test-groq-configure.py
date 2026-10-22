#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise the local credential form with a fake SSH sink, never a real key."""
import importlib.util
import json
import subprocess
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from pathlib import Path

spec = importlib.util.spec_from_file_location('configure', Path(__file__).resolve().parents[1]/'scripts/configure-groq.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class FormTests(unittest.TestCase):
    def setUp(self):
        self.server = c.HTTPServer(('127.0.0.1', 0), c.Form)
        self.server.host_header = '127.0.0.1:%d' % self.server.server_port
        self.server.saved = False
        self.url = 'http://' + self.server.host_header + '/' + c.NONCE
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_get_is_private_and_has_no_external_scripts(self):
        with urlopen(self.url, timeout=2) as result:
            body = result.read().decode()
            self.assertEqual(result.headers['Cache-Control'], 'no-store')
            self.assertIn('frame-ancestors', result.headers['Content-Security-Policy'])
        self.assertIn('type="password"', body)
        self.assertNotIn('<script', body)

    def test_origin_and_nonce_are_required_before_ssh(self):
        for origin, nonce in (('https://elsewhere.example', c.NONCE), ('http://'+self.server.host_header, 'wrong'), ('null', 'wrong')):
            with patch.object(c.subprocess, 'run') as ssh:
                request = Request(self.url, data=urlencode({'nonce': nonce, 'api_key': 'test_'+'a'*40}).encode(), headers={'Origin': origin})
                with self.assertRaises(HTTPError):
                    urlopen(request, timeout=2)
                ssh.assert_not_called()

    def test_webview_opaque_origin_still_requires_valid_nonce(self):
        with patch.object(c.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'', b'')) as ssh, patch('builtins.print'):
            req = Request(self.url, data=urlencode({'nonce': c.NONCE, 'api_key': 'test_'+'a'*40}).encode(), headers={'Origin': 'null'})
            with urlopen(req, timeout=2) as response:
                self.assertEqual(response.status, 200)
            self.assertEqual(ssh.call_count, 1)

    def test_secret_uses_stdin_and_response_does_not_echo_it(self):
        key = 'test_'+'a'*40
        with patch.object(c.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'', b'')) as ssh, patch('builtins.print'):
            with urlopen(Request(self.url, data=urlencode({'nonce': c.NONCE, 'api_key': key}).encode()), timeout=2) as response:
                self.assertNotIn(key.encode(), response.read())
            self.assertTrue(self.server.saved)
            self.assertNotIn(key, ' '.join(ssh.call_args.args[0]))
            self.assertEqual(json.loads(ssh.call_args.kwargs['input'])['api_key'], key)


if __name__ == '__main__':
    unittest.main(verbosity=2)
