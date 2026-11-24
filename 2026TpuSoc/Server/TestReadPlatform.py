"""Check platform audit safety and detection of misleading source evidence."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from ReadPlatform import audit


class PlatformReadTests(unittest.TestCase):
    def test_comments_install_divergence_and_source_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / 'platform'
            config = root / 'rtl/e203/core/config.v'
            config.parent.mkdir(parents=True)
            config.write_bytes(b'//`define E203_CFG_ITCM_ADDR_WIDTH 16\r\n'
                               b'/* `define E203_CFG_DTCM_ADDR_WIDTH 20 */\r\n'
                               b'`define E203_CFG_ITCM_ADDR_WIDTH 18\r\n'
                               b'`define E203_CFG_DTCM_ADDR_WIDTH 18\r\n')
            installed = root / 'vsim/install/rtl/core/config.v'
            installed.parent.mkdir(parents=True)
            installed.write_bytes(config.read_bytes().replace(b'\r\n', b'\n'))
            before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in root.rglob('*') if p.is_file()}
            summary, output = audit(str(root), str(base / 'first'))
            self.assertIn('ITCM: RAW_WIDTH=18 CAPACITY=256_KiB', summary)
            self.assertIn('DTCM: RAW_WIDTH=18 CAPACITY=256_KiB', summary)
            self.assertIn('INSTALL_ITCM_RAW_WIDTH: 18', summary)
            evidence = json.loads((Path(output) / 'evidence.json').read_text())
            self.assertEqual(evidence['files'][0]['installed_state'], 'LINE_ENDINGS_ONLY')
            after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in root.rglob('*') if p.is_file()}
            self.assertEqual(before, after)
            installed.write_bytes(b'`define E203_CFG_ITCM_ADDR_WIDTH 16\n')
            second, _ = audit(str(root), str(base / 'second'))
            self.assertTrue(any('CONTENT_DIFFERS=1' in line for line in second))
            self.assertIn('INSTALL_ITCM_RAW_WIDTH: 16', second)
            with self.assertRaisesRegex(ValueError, 'already exists'):
                audit(str(root), str(base / 'second'))
            with self.assertRaisesRegex(ValueError, 'outside'):
                audit(str(root), str(root / 'report'))
            self.assertFalse((root / 'report').exists())

    def test_missing_platform_rejected_without_creating_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / 'report'
            with self.assertRaisesRegex(ValueError, 'config.v not found'):
                audit(str(Path(temporary) / 'missing'), str(out))
            self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
