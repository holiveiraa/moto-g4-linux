#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fresh staging has no owner state; never writes a block device or runs binaries."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('assembly',Path(__file__).resolve().parents[1]/'scripts/assemble-userspace.py')
assembly=importlib.util.module_from_spec(spec);spec.loader.exec_module(assembly)


class CleanUserspace(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.root=self.base/'root';(self.root/'etc').mkdir(parents=True)
        (self.root/'etc/alpine-release').write_text('fixture')
        self.key=self.base/'maintenance.pub';self.key.write_text('ssh-ed25519 AAAATEST fixture')
        self.host=self.base/'host-key';self.host.write_bytes(b'fixture-not-a-real-key')
        self.tools=self.base/'tools';self.tools.mkdir()
        self.ts=self.base/'tailscale';self.ts.mkdir()
        for path in (self.tools/'msm-fb-refresher',self.tools/'reboot-bootloader',self.ts/'tailscale',self.ts/'tailscaled'):
            path.write_bytes(b'fixture-not-executable')
    def tearDown(self):self.temp.cleanup()
    def run_assembly(self):assembly.assemble(self.root,self.key,self.host,self.tools,self.ts,1234567890)
    def test_new_install_contains_services_and_empty_personal_configuration(self):
        self.run_assembly()
        self.assertNotIn('network=',(self.root/'etc/wpa_supplicant.conf').read_text())
        self.assertFalse((self.root/'var/lib/tailscale/tailscaled.state').exists())
        self.assertFalse((self.root/'root/.config/moto-linux').exists())
        self.assertTrue((self.root/'usr/sbin/moto-ssh-askpass').exists())
        self.assertEqual((self.root/'etc/runlevels/default/moto-audio').readlink(),Path('/etc/init.d/moto-audio'))
        self.assertEqual((self.root/'etc/wpa_supplicant.conf').stat().st_mode & 0o777,0o600)
        self.assertEqual((self.root/'root/.ssh/authorized_keys').stat().st_mode & 0o777,0o600)
    def test_personal_state_is_refused_and_preserved(self):
        path=self.root/'var/lib/tailscale';path.mkdir(parents=True)
        (path/'tailscaled.state').write_text('fixture-private')
        with self.assertRaises(ValueError):self.run_assembly()
        self.assertEqual((path/'tailscaled.state').read_text(),'fixture-private')
        self.assertFalse((self.root/'usr/sbin/moto-shell').exists())
    def test_existing_wifi_is_refused(self):
        (self.root/'etc/wpa_supplicant.conf').write_text('network={\nssid="fixture"\n}')
        with self.assertRaises(ValueError):self.run_assembly()
    def test_missing_input_is_refused_before_staging(self):
        (self.ts/'tailscaled').unlink()
        with self.assertRaises(ValueError):self.run_assembly()
        self.assertFalse((self.root/'usr/sbin/moto-shell').exists())
    def test_wifi_with_tabs_is_refused_before_staging(self):
        (self.root/'etc/wpa_supplicant.conf').write_text('network\t=\t{\nssid="fixture"\n}')
        with self.assertRaises(ValueError):self.run_assembly()
        self.assertFalse((self.root/'usr').exists())
    def test_parent_symlink_cannot_escape_staging(self):
        outside=self.base/'outside';outside.mkdir()
        (self.root/'usr').symlink_to(outside,target_is_directory=True)
        with self.assertRaises(ValueError):self.run_assembly()
        self.assertEqual(list(outside.iterdir()),[])
        self.assertFalse((self.root/'root').exists())
    def test_file_symlink_cannot_overwrite_an_external_file(self):
        outside=self.base/'outside.txt';outside.write_text('preserve')
        (self.root/'etc/hostname').symlink_to(outside)
        with self.assertRaises(ValueError):self.run_assembly()
        self.assertEqual(outside.read_text(),'preserve')
        self.assertFalse((self.root/'usr').exists())


if __name__=='__main__':unittest.main()
