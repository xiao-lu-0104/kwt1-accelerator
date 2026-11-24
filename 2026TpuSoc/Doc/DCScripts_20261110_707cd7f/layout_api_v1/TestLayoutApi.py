"""Protocol tests only; do not claim native ICC2 layout results."""
import ast
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


class ProbeTests(unittest.TestCase):
    def probe(self, missing=False, man_error=False):
        with tempfile.TemporaryDirectory() as task_dir:
            d = Path(task_dir)
            source = (HERE / 'LayoutApiProbe.tcl').read_text()
            commands = source.split('set Commands {', 1)[1].split('}', 1)[0].split()
            stubs = []
            for command in commands:
                if missing and command == 'create_pin_constraint':
                    continue
                stubs.append('proc ' + command + ' {args} {error "MUTATION CALLED"}')
            stubs += ['proc man {name} {return "SYNTAX\\n$name -ports -sides\\nARGUMENTS\\nbody"}',
                      'proc redirect {file command} {set f [open $file w];puts $f [uplevel 1 $command];close $f}']
            if man_error:
                stubs.append('proc man {name} {error "mock manual unavailable"}')
            (d / 'Test.tcl').write_text('\n'.join(stubs) + '\nsource {' + str(HERE / 'LayoutApiProbe.tcl') + '}\n')
            result = subprocess.run(['tclsh', str(d / 'Test.tcl')], cwd=str(d), capture_output=True, text=True)
            return result, (d / 'PinApiSummary.txt').read_text()

    def test_available_documentation_only(self):
        result, text = self.probe()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('DOCUMENTATION_COLLECTED_NOT_LAYOUT_OR_PG_ACCEPTANCE', text)
        self.assertNotIn('MUTATION CALLED', result.stdout + result.stderr)

    def test_missing_required_is_not_success(self):
        result, text = self.probe(missing=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('MISSING_REQUIRED: create_pin_constraint', text)

    def test_manual_error_retained(self):
        result, text = self.probe(man_error=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('MANUAL_ERROR: mock manual unavailable', text)

    def test_normalization_hash_and_shell(self):
        entry = ROOT / 'workspace/Server/tpusoc_layout_api_20261110_707cd7f_v1.sh'
        original = entry.read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(), 'ae13d79a5d003010ab8b40c7ef312be0fff95ad877c170ce7d869c389e666d5e')
        subprocess.run(['bash', '-n', str(entry)], check=True)
        command = (HERE / 'NormalizeLayoutApiCommand.txt').read_text()
        ast.parse(command.split("'", 2)[1])
        for raw in (original, b'\xef\xbb\xbf' + original.replace(b'\n', b'\r\n'), b'\n' + original + b'\n'):
            restored = (raw.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n').strip('\n') + '\n').encode()
            self.assertEqual(restored, original)
        self.assertNotEqual(hashlib.sha256(original[:-20]).digest(), hashlib.sha256(original).digest())


if __name__ == '__main__':
    unittest.main()
