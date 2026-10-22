#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Protect the shared-pool ordering and single-attempt startup contract."""
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = spec_from_file_location('startup', Path(__file__).resolve().parents[1] / 'native/moto-audio-start.py')
startup = module_from_spec(spec)
spec.loader.exec_module(startup)


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.files = {
            '/proc/device-tree/model': 'Athene_16MP\0',
            '/proc/asound/cards': '0 msm8952-cs35l34-snd-card',
            '/sys/bus/msm_subsys/devices/subsys1/name': 'adsp',
            '/sys/bus/msm_subsys/devices/subsys1/state': 'OFFLINING',
            '/sys/bus/msm_subsys/devices/subsys2/name': 'wcnss',
            '/sys/bus/msm_subsys/devices/subsys2/state': 'OFFLINING',
            '/firmware/image/adsp.mdt': 'fixture',
            '/etc/moto-audio.json': json.dumps({'model': 'athene-cs35l34', 'validated': True, 'route': []}),
        }
        for name, content in self.files.items():
            self.write(name, content)
        (self.root / 'run').mkdir()
        self.patches = [
            patch.object(startup, 'Path', self.path),
            patch.object(startup, 'PROFILE', self.path('/etc/moto-audio.json')),
            patch.object(startup, 'VOLUME_STATE', self.path('/var/lib/moto-audio-volume.json')),
            patch.object(startup.os, 'geteuid', return_value=0),
            patch.object(startup.platform, 'machine', return_value='aarch64'),
            patch.object(startup.os, 'open', return_value=55),
            patch.object(startup.os, 'write', side_effect=self.activate),
            patch.object(startup.os, 'close'),
            patch.object(startup, 'run', return_value=''),
        ]
        self.mocks = [p.start() for p in self.patches]

    def path(self, value):
        return self.root / str(value).lstrip('/')

    def write(self, name, content):
        p = self.path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)

    def activate(self, fd, data):
        self.write('/sys/bus/msm_subsys/devices/subsys1/state', 'ONLINE')
        return len(data)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.folder.cleanup()

    def test_audio_activates_before_wifi_and_creates_ready_marker(self):
        startup.initialize()
        startup.os.write.assert_called_once_with(55, b'1\n')
        self.assertTrue(self.path('/run/moto-audio-ready').exists())
        startup.run.assert_any_call('amixer', '-c', '0', 'cset', 'name=Moto Playback Volume', '70')

    def test_wifi_first_refuses_activation(self):
        self.write('/sys/bus/msm_subsys/devices/subsys2/state', 'ONLINE')
        with self.assertRaisesRegex(RuntimeError, 'Wi-Fi started before audio'):
            startup.initialize()
        startup.os.write.assert_not_called()

    def test_failed_activation_is_not_retried_in_same_boot(self):
        startup.os.write.side_effect = OSError('fixture failure')
        with self.assertRaises(OSError):
            startup.initialize()
        with self.assertRaises(FileExistsError):
            startup.initialize()
        self.assertEqual(startup.os.write.call_count, 1)

    def test_already_online_does_not_reload_firmware(self):
        self.write('/sys/bus/msm_subsys/devices/subsys1/state', 'ONLINE')
        startup.initialize()
        startup.os.write.assert_not_called()

    def test_ready_restart_does_not_touch_active_pcm(self):
        self.write('/sys/bus/msm_subsys/devices/subsys1/state', 'ONLINE')
        self.write('/run/moto-audio-ready', 'ready')
        startup.initialize()
        startup.os.write.assert_not_called()
        startup.run.assert_not_called()

    def test_failed_initialization_clears_stale_ready_marker(self):
        self.write('/run/moto-audio-ready', 'stale')
        startup.os.write.side_effect = OSError('fixture failure')
        with self.assertRaises(OSError):
            startup.initialize()
        self.assertFalse(self.path('/run/moto-audio-ready').exists())

    def test_saved_mute_survives_initialization(self):
        self.write('/var/lib/moto-audio-volume.json', '{"percent":0}')
        startup.initialize()
        startup.run.assert_any_call('amixer', '-c', '0', 'cset', 'name=Moto Playback Volume', '0')

    def test_wrong_hardware_refuses_before_activation(self):
        self.write('/proc/device-tree/model', 'Other phone')
        with self.assertRaisesRegex(RuntimeError, 'Unsupported hardware'):
            startup.initialize()
        startup.os.write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
