#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Regressions for login versus connectivity; never operates a real VPN."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('services', Path(os.environ.get('MOTO_UI_REVIEW_DIR', Path(__file__).resolve().parents[1] / 'native')) / 'moto-services.py')
services = importlib.util.module_from_spec(spec)
spec.loader.exec_module(services)
URL = 'https://login.tailscale.com/a/example-test-only'


class TailscaleUX(unittest.TestCase):
    def test_running_offline_retains_ssh_without_requesting_login(self):
        state = services.tailscale_view({'BackendState': 'Running', 'AuthURL': URL,
            'Self': {'Online': False, 'KeyExpiry': '2027-04-17T19:59:46Z'},
            'TailscaleIPs': ['100.64.0.1'], 'Health': ['Network map response timeout']})
        self.assertEqual(state['kind'], 'degraded')
        self.assertTrue(state['can_ssh'])
        self.assertFalse(state['connected'])
        self.assertEqual(state['url'], '')
        self.assertEqual(len(state['health']), 1)

    def test_running_with_warning_is_not_reported_as_disconnected(self):
        state = services.tailscale_view({'BackendState': 'Running',
            'Self': {'Online': True}, 'Health': ['DNS warning']})
        self.assertTrue(state['connected'])
        self.assertEqual(state['kind'], 'warning')

    def test_only_needs_login_exposes_auth_url(self):
        for backend in ('Running', 'Stopped', 'NeedsMachineAuth', 'Starting'):
            self.assertEqual(services.tailscale_view({'BackendState': backend, 'AuthURL': URL})['url'], '')
        self.assertEqual(services.tailscale_view({'BackendState': 'NeedsLogin', 'AuthURL': URL})['url'], URL)

    def test_bad_auth_urls_never_reach_qr(self):
        for url in ('http://login.tailscale.com/a/x', 'https://login.tailscale.com.evil/a/x',
                    'https://evil@login.tailscale.com/a/x', 'https://login.tailscale.com:22/a/x',
                    URL + '\n', None):
            self.assertEqual(services.tailscale_auth_url(url), '')

    def test_wifi_loss_is_distinct_from_expired_identity(self):
        state = services.tailscale_view({'BackendState': 'Running', 'Self': {'Online': True}}, False)
        self.assertEqual(state['kind'], 'network')
        self.assertFalse(state['connected'])
        state = services.tailscale_view({'BackendState': 'Running', 'Self': {'Expired': True}})
        self.assertEqual(state['kind'], 'expired')
        self.assertFalse(state['can_ssh'])

    def test_valid_json_survives_nonzero_cli_exit(self):
        process = subprocess.CompletedProcess([], 1, json.dumps({'BackendState': 'NeedsLogin', 'AuthURL': URL}), '')
        with patch.object(services.subprocess, 'run', return_value=process) as run:
            self.assertEqual(services.tailscale_state()['kind'], 'login')
        self.assertEqual(run.call_args.args[0], ['tailscale', 'status', '--json'])

    def test_daemon_failure_does_not_claim_expired_credentials(self):
        with patch.object(services.subprocess, 'run', side_effect=OSError('socket unavailable')):
            state = services.tailscale_state()
        self.assertEqual(state['kind'], 'unavailable')
        self.assertEqual(state['url'], '')

    def test_up_timeout_preserves_observed_state(self):
        degraded = services.tailscale_view({'BackendState': 'Running', 'Self': {'Online': False}})
        with patch.object(services, 'command', side_effect=subprocess.TimeoutExpired('tailscale', 12)) as command, \
             patch.object(services, 'tailscale_state', return_value=degraded):
            self.assertEqual(services.tailscale_connect()['kind'], 'degraded')
        self.assertNotIn('--force-reauth', command.call_args.args)
        self.assertNotIn('logout', command.call_args.args)

    def test_first_login_waiting_for_browser_returns_official_qr_url(self):
        login = services.tailscale_view({'BackendState': 'NeedsLogin', 'AuthURL': URL})
        with patch.object(services, 'command', side_effect=RuntimeError('login pending')) as command, \
             patch.object(services, 'tailscale_state', return_value=login):
            self.assertEqual(services.tailscale_connect()['url'], URL)
        self.assertEqual(command.call_args.args[:2], ('tailscale', 'up'))
        self.assertFalse(any(arg.startswith('--auth-key') for arg in command.call_args.args))
        self.assertNotIn('--force-reauth', command.call_args.args)

    def test_reconnect_restarts_only_local_vpn_service(self):
        connected = services.tailscale_view({'BackendState': 'Running', 'Self': {'Online': True}})
        with patch.object(services, 'command') as command, \
             patch.object(services, 'tailscale_state', return_value=connected):
            services.tailscale_reconnect()
        command.assert_called_once_with('rc-service', 'moto-tailscale', 'restart', timeout=18)

    def test_repeated_connect_is_rejected_without_another_cli_call(self):
        services._tailscale_connect_lock.acquire()
        try:
            with patch.object(services, 'command') as command:
                with self.assertRaisesRegex(RuntimeError, 'andamento'):
                    services.tailscale_connect()
                command.assert_not_called()
        finally:
            services._tailscale_connect_lock.release()

    def test_ssh_check_is_detected_separately_from_device_login(self):
        text = '# Tailscale SSH requires an additional check.\n# To authenticate, visit: ' + URL
        self.assertEqual(services.ssh_auth_url_from_pane(text), URL)
        self.assertEqual(services.ssh_auth_url_from_pane(text + '\nWelcome to Ubuntu\nubuntu@host:~$'), '')
        self.assertEqual(services.ssh_auth_url_from_pane('echo ' + URL), '')
        self.assertEqual(services.ssh_auth_url_from_pane(text.replace('login.tailscale.com', 'evil.example')), '')

    def test_non_ssh_pane_is_never_captured(self):
        with patch.object(services, 'command', return_value='%1|sh|sh') as command:
            self.assertEqual(services.ssh_auth_request(), {})
        self.assertEqual(command.call_count, 1)

    def test_ssh_check_is_limited_to_the_app_launched_target(self):
        with patch.object(services, 'command', return_value='%1|ssh|ssh other-server') as command:
            self.assertEqual(services.ssh_auth_request(), {})
        self.assertEqual(command.call_count, 1)

    def test_saved_destination_launcher_is_detected_without_hardcoded_host(self):
        text = '# Tailscale SSH requires an additional check.\n# To authenticate, visit: ' + URL
        ident = 'a'*32
        with patch.object(services, 'command', side_effect=[
                '%3|python3|tailscale|/usr/sbin/moto-ssh-launch '+ident, text]):
            self.assertEqual(services.ssh_auth_request(), {'url': URL, 'pane': '%3'})
        with patch.object(services, 'command', return_value='%3|python3|tailscale|python3 other.py') as command:
            self.assertEqual(services.ssh_auth_request(), {})
            self.assertEqual(command.call_count, 1)


if __name__ == '__main__':
    unittest.main()
