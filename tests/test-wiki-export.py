#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('wiki',Path(__file__).resolve().parents[1]/'scripts/export-wiki.py')
wiki=importlib.util.module_from_spec(spec);spec.loader.exec_module(wiki)


class Wiki(unittest.TestCase):
    def test_all_real_pages_export_with_rewritten_links_and_no_network(self):
        with tempfile.TemporaryDirectory() as temp:
            count=wiki.export('https://github.com/example/moto-g4-linux',temp)
            self.assertGreater(count,10)
            home=(Path(temp)/'Home.md').read_text()
            self.assertIn('https://github.com/example/moto-g4-linux/wiki/Agent-Installation',home)
            self.assertTrue((Path(temp)/'_Sidebar.md').exists())
    def test_noncanonical_repository_is_rejected_without_output(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'no-output'
            with self.assertRaises(ValueError):wiki.export('https://example.com/private?token=x',output)
            self.assertFalse(output.exists())


if __name__=='__main__':unittest.main()
