"""Check first-X selection and read-only cone traversal with saved fixture inputs."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import ReadCone
from TestCone import BUS, FF, INV


class ReadConeTests(unittest.TestCase):
    def test_first_x_is_reported_before_final_failure(self):
        text = '\n'.join(['CONE_POST: edge=8 state=000 word=00',
                          'CONE_FF_PRE: D=x Q=0',
                          'CONE_POST: edge=9 state=010 word=0x',
                          'CONE_POST: edge=10 state=xx0 word=xx'] + ['tail'] * 50)
        context = ReadCone.first_x_context(text)
        self.assertIn('D=x Q=0', context)
        self.assertIn('edge=9', context)
        self.assertNotIn('tail', context)

    def test_saved_models_and_escaped_ff_cone(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = root / 'tools'
            tools.mkdir()
            source = Path(__file__).parent / 'ReadProbe.py'
            shutil.copy2(source, tools / source.name)
            (tools / 'MANIFEST.sha256').write_text(ReadCone.digest(source) + '  ReadProbe.py\n')
            candidate = root / 'candidate.v'
            candidate.write_text(BUS)
            models = root / 'BusModels.json'
            models.write_text(json.dumps({'DQV0_12TR40': FF, 'INV': INV}))
            record = {'inputs': {str(path): ReadCone.digest(path) for path in (candidate, models)}}
            (root / 'ConeInputs.json').write_text(json.dumps(record))
            (root / 'runner.log').write_text('RESULT: GATE_CONE_DIAGNOSTICS_COMPLETE\n')
            for case in ('real', 'functional', 'nba_diagnostic'):
                (root / case).mkdir()
                (root / case / 'run.log').write_text('CONE_POST: edge=9 state=010 word=0x\n')
            result = subprocess.run([sys.executable, str(Path(__file__).parent / 'ReadCone.py'), str(root)],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('SEQUENTIAL_BOUNDARY: \\Word_reg[0]', result.stdout)
            self.assertIn('WORD_MODEL_BEGIN: INV', result.stdout)
            self.assertIn('RESULT: READ_ONLY_CONE_COMPLETE', result.stdout)


if __name__ == '__main__':
    unittest.main()
