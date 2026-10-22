#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Wi-Fi transaction regressions; all control commands use an in-memory daemon."""
import copy
import fcntl
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

root = Path(os.environ.get('MOTO_UI_REVIEW_DIR', Path(__file__).resolve().parents[1]/'native'))
spec = importlib.util.spec_from_file_location('wifi', root/'moto-wifi.py')
wifi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wifi)


class Daemon:
    def __init__(self):
        self.rows = {'0': {'ssid': '"Home"', 'key_mgmt': 'WPA-PSK', 'enabled': True},
                     '1': {'ssid': '"Other"', 'key_mgmt': 'WPA-PSK', 'enabled': True},
                     '2': {'ssid': '"Home"', 'key_mgmt': 'NONE', 'enabled': False}}
        self.original = copy.deepcopy(self.rows)
        self.current, self.failed, self.save_failed = '0', set(), False
        self.calls = []
        self.saves, self.fail_save_on = 0, set()
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def status(self):
        return {'id': self.current, 'wpa_state': 'DISCONNECTED' if self.current in self.failed else 'COMPLETED'}
    def ask(self, value, ok=False):
        self.calls.append(value)
        parts = value.split(' ', 3)
        cmd = parts[0]
        if cmd == 'LIST_NETWORKS':
            return 'network id / ssid / bssid / flags\n' + '\n'.join(
                f'{ident}\t{name["ssid"]}\tany\t'+('[CURRENT]' if ident == self.current else '')+('' if name['enabled'] else '[DISABLED]')
                for ident, name in self.rows.items())
        if cmd == 'GET_NETWORK':
            assert parts[2] != 'psk', 'Credentials must not be read'
            return str(self.rows[parts[1]].get(parts[2], {'priority': '0', 'scan_ssid': '0', 'bssid': 'any'}.get(parts[2], '')))
        if cmd == 'ADD_NETWORK':
            ident = str(max(map(int, self.rows))+1)
            self.rows[ident] = {'enabled': False}
            return ident
        if cmd == 'SET_NETWORK':
            self.rows[parts[1]][parts[2]] = parts[3]
        elif cmd == 'SELECT_NETWORK':
            self.current = parts[1]
            for ident, row in self.rows.items(): row['enabled'] = ident == self.current
        elif cmd in ('ENABLE_NETWORK', 'DISABLE_NETWORK'):
            self.rows[parts[1]]['enabled'] = cmd == 'ENABLE_NETWORK'
        elif cmd == 'REMOVE_NETWORK':
            del self.rows[parts[1]]
        elif cmd == 'SAVE_CONFIG':
            self.saves += 1
            if self.save_failed or self.saves in self.fail_save_on:
                raise RuntimeError('fixture save failed')
            self.original = copy.deepcopy(self.rows)
        elif cmd == 'RECONFIGURE':
            self.rows = copy.deepcopy(self.original)
        return 'OK'


class Profiles(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        folder = Path(self.temp.name)
        self.config = folder/'wifi.conf'
        self.config.write_text('private fixture config')
        self.daemon, self.renewals = Daemon(), []
        self.manager = wifi.WifiProfiles(lambda: self.daemon, self.config, folder/'lock', lambda: self.renewals.append(True))
    def tearDown(self): self.temp.cleanup()
    def test_metadata_never_reads_credentials_and_distinguishes_security(self):
        rows = self.manager.profiles()
        self.assertEqual(len(rows), 3)
        self.assertNotEqual(wifi.fingerprint(rows[0]), wifi.fingerprint(rows[2]))
        self.assertFalse(any('psk' in row for row in rows))
    def test_current_saved_reconnect_has_no_new_profile_or_disruption(self):
        result = self.manager.connect_saved(self.manager.profiles()[0])
        self.assertTrue(result['saved'])
        self.assertFalse(self.renewals)
        self.assertFalse(any(call.startswith(('ADD_NETWORK', 'SELECT_NETWORK')) for call in self.daemon.calls))
        self.assertFalse(self.daemon.rows['2']['enabled'])
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
    def test_saved_switch_reuses_secret_and_preserves_disabled_profiles(self):
        target = next(row for row in self.manager.profiles() if row['id'] == '1')
        self.assertTrue(self.manager.connect_saved(target)['saved'])
        self.assertEqual(self.daemon.current, '1')
        self.assertFalse(any(call == 'ADD_NETWORK' for call in self.daemon.calls))
        self.assertTrue(self.daemon.rows['0']['enabled'])
        self.assertFalse(self.daemon.rows['2']['enabled'])
        self.assertEqual(len(self.renewals), 1)
    def test_stale_id_does_not_connect_to_a_different_network(self):
        row = self.manager.profiles()[0]
        self.daemon.rows['0']['ssid'] = '"Changed"'
        with self.assertRaises(RuntimeError): self.manager.connect_saved(row)
        self.assertFalse(any(call.startswith('SELECT_NETWORK') for call in self.daemon.calls))
    def test_failed_candidate_restores_selection_and_never_saves_bad_profile(self):
        self.daemon.failed.add('3')
        clock = iter(range(0, 1000, 10))
        with patch.object(wifi.time, 'sleep'), patch.object(wifi.time, 'monotonic', side_effect=lambda: next(clock)):
            with self.assertRaises(RuntimeError): self.manager.connect_new('Bad', 'not-a-real-password')
        self.assertEqual(self.daemon.current, '0')
        self.assertEqual(set(self.daemon.rows), {'0', '1', '2'})
        self.assertFalse(self.daemon.rows['2']['enabled'])
        self.assertFalse(any(call == 'SAVE_CONFIG' for call in self.daemon.calls))
    def test_associated_but_save_failed_is_kept_and_reported_separately(self):
        self.daemon.save_failed = True
        result = self.manager.connect_new('New', 'fixture-password')
        self.assertTrue(result['connected'])
        self.assertFalse(result['saved'])
        self.assertEqual(self.daemon.current, '3')
        self.assertIn('0', self.daemon.rows)
        self.assertIn('3', self.daemon.rows)
    def test_same_name_profiles_are_not_automatically_deleted(self):
        self.manager.connect_new('Home', 'fixture-password')
        self.assertEqual(len(self.daemon.rows), 4)
        self.assertFalse(any(call.startswith('REMOVE_NETWORK') for call in self.daemon.calls))
    def test_forget_failure_restores_private_file_and_previous_profile(self):
        self.daemon.save_failed = True
        row = self.manager.profiles()[0]
        original = self.config.read_bytes()
        with self.assertRaises(RuntimeError): self.manager.forget(row)
        self.assertEqual(self.config.read_bytes(), original)
        self.assertEqual(self.daemon.current, '0')
        self.assertIn('0', self.daemon.rows)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
    def test_forget_only_removes_explicit_profile(self):
        row = next(row for row in self.manager.profiles() if row['id'] == '1')
        self.manager.forget(row)
        self.assertEqual(set(self.daemon.rows), {'0', '2'})
    def test_forget_refuses_to_discard_a_connected_unsaved_candidate(self):
        self.daemon.save_failed = True
        self.manager.connect_new('New', 'fixture-password')
        target = next(row for row in self.manager.profiles() if row['id'] == '1')
        with self.assertRaises(RuntimeError): self.manager.forget(target)
        self.assertIn('3', self.daemon.rows)
        self.assertEqual(self.daemon.current, '3')
        self.assertFalse(any(call.startswith('REMOVE_NETWORK') for call in self.daemon.calls))
    def test_forget_late_save_failure_uses_stable_tag_not_old_numeric_id(self):
        self.daemon.fail_save_on = {2}
        target = self.manager.profiles()[0]
        with self.assertRaises(RuntimeError): self.manager.forget(target)
        self.assertIn('0', self.daemon.rows)
        self.assertEqual(self.daemon.current, '0')
        self.assertTrue(self.daemon.rows['0']['id_str'].startswith('"moto-'))
        self.assertTrue(self.daemon.rows['1']['enabled'])
        self.assertFalse(self.daemon.rows['2']['enabled'])
    def test_forget_rollback_preserves_explicit_disconnection(self):
        self.daemon.fail_save_on = {2}
        target = self.manager.profiles()[1]
        with patch.object(self.daemon, 'status', return_value={'wpa_state': 'DISCONNECTED'}):
            with self.assertRaises(RuntimeError): self.manager.forget(target)
        self.assertIn('DISCONNECT', self.daemon.calls)
    def test_lock_rejects_a_second_operation(self):
        row = self.manager.profiles()[0]
        with self.manager.lock.open('a') as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(RuntimeError): self.manager.connect_saved(row)
    def test_ssid_encoding_and_limits(self):
        self.assertEqual(wifi.ssid_bytes('"Cafe\\x20WiFi"'), b'Cafe WiFi')
        self.assertEqual(wifi.ssid_bytes('43616665'), b'Cafe')
        for value in ('', 'a'*33, 'a\n'):
            with self.assertRaises(ValueError): self.manager.connect_new(value, 'fixture-password')


if __name__ == '__main__': unittest.main()
