"""Ensure committing the tooling does not invalidate the pinned RTL exporter."""
from pathlib import Path
import unittest
from unittest.mock import patch
import MakePackage as package


class PackageTest(unittest.TestCase):
    def test_tool_commit_can_follow_hardware_baseline(self):
        calls = []

        def fake_git(repo, *args):
            calls.append((Path(repo), args))
            if args == ('rev-parse', 'HEAD'):
                return b'9f3e34f337f5d0a1236a285871ffa2032491617a\n'
            return b''

        with patch.object(package, 'git', side_effect=fake_git):
            package.verify_baseline()
        self.assertIn((package.ROOT, ('diff', package.COMMIT, '--name-only', '--',
                                     'Rtl', 'Backend', 'Sim', 'e203_hbirdv2')), calls)

    def test_changed_hardware_is_rejected(self):
        with patch.object(package, 'git', return_value=b'Rtl/TpuSram.sv\n'):
            with self.assertRaisesRegex(ValueError, 'source differs'):
                package.verify_baseline()

    def test_bundle_tag_cannot_escape_output_directory(self):
        for tag in ('../other', '/tmp/other', 'C:\\other', '.', '..', 'two words'):
            with self.assertRaises(ValueError):
                package.validate_tag(tag)
        self.assertEqual(package.validate_tag('tpusoc-review_v1'), 'tpusoc-review_v1')


if __name__ == '__main__':
    unittest.main()
