"""Verify isolation, installed-source selection and refusal of stale configurations."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('Prepare.py')


class PrepareTests(unittest.TestCase):
    def invoke(self, platform, output, *extra):
        return subprocess.run([sys.executable, str(SCRIPT), '--platform', str(platform),
                               '--out', str(output), *extra], capture_output=True, text=True)

    def test_local_copy_changes_only_widths_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            platform = base / 'platform'
            config = platform / 'rtl/e203/core/config.v'
            config.parent.mkdir(parents=True)
            original = b'// reference\n`define E203_CFG_ITCM_ADDR_WIDTH 16\n`define E203_CFG_DTCM_ADDR_WIDTH 16\n'
            config.write_bytes(original)
            output = base / 'run'
            result = self.invoke(platform, output, '--local-widths')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(config.read_bytes(), original)
            copied = output / 'e203_hbirdv2/rtl/e203/core/config.v'
            self.assertEqual(copied.read_text(), original.decode().replace('WIDTH 16', 'WIDTH 18'))
            scope = json.loads((output / 'Scope.json').read_text())
            self.assertEqual(scope['scope'], 'LOCAL_UPSTREAM_WIDTH_COMPARISON')
            again = self.invoke(platform, output, '--local-widths')
            self.assertNotEqual(again.returncode, 0)
            self.assertEqual(config.read_bytes(), original)
            self.assertNotEqual(self.invoke(platform, platform / 'report').returncode, 0)
            self.assertFalse((platform / 'report').exists())

    def test_server_requires_256k_and_selects_actual_installed_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            platform = base / 'platform'
            config = platform / 'rtl/e203/core/config.v'
            config.parent.mkdir(parents=True)
            config.write_text('`define E203_CFG_ITCM_ADDR_WIDTH 16\n`define E203_CFG_DTCM_ADDR_WIDTH 16\n')
            self.assertNotEqual(self.invoke(platform, base / 'bad').returncode, 0)
            installed = platform / 'vsim/install/rtl/core/config.v'
            installed.parent.mkdir(parents=True)
            installed.write_text(config.read_text().replace('WIDTH 16', 'WIDTH 18'))
            result = self.invoke(platform, base / 'good')
            self.assertEqual(result.returncode, 0, result.stderr)
            scope = json.loads((base / 'good/Scope.json').read_text())
            self.assertEqual(scope['compiled_source'], str(installed.parents[1]))
            self.assertFalse(scope['configuration_modified'])


if __name__ == '__main__':
    unittest.main()
