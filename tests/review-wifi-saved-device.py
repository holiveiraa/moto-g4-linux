#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Reuse the currently associated profile; never switch AP or read credentials."""
import importlib.util
import os
from pathlib import Path

root = Path(os.environ.get('MOTO_UI_REVIEW_DIR', '/usr/sbin'))
spec = importlib.util.spec_from_file_location('services_review', root/'moto-services.py')
services = importlib.util.module_from_spec(spec)
spec.loader.exec_module(services)
commands = []


class TrackedWPA(services.WPA):
    def ask(self, command, *args, **kwargs):
        assert not command.startswith('GET_NETWORK ') or not command.endswith(' psk')
        assert not command.startswith(('ADD_NETWORK', 'SELECT_NETWORK', 'REMOVE_NETWORK'))
        commands.append(command.split()[0])
        return super().ask(command, *args, **kwargs)


def no_renew():
    raise AssertionError('Current connection must not restart DHCP')


manager = services._wifi_module().WifiProfiles(TrackedWPA, renew=no_renew)
before = manager.profiles()
current = next(row for row in before if row['current'])
with TrackedWPA() as wpa:
    assert wpa.status().get('wpa_state') == 'COMPLETED'
result = manager.connect_saved(current)
after = manager.profiles()
assert result['connected'] and result['saved']
assert len(after) == len(before)
assert next(row['id'] for row in after if row['current']) == current['id']
assert manager.config.stat().st_mode & 0o777 == 0o600
assert 'SAVE_CONFIG' in commands
print('PASS: current saved Wi-Fi reused and persisted; same profile count/ID; no password read, ADD, SELECT or DHCP restart; config 0600')
