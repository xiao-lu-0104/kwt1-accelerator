"""Compare the standard-library fixed-point translation with frozen NumPy primitives."""
import importlib.util
import math
from pathlib import Path
import shutil
import tempfile
import unittest
import numpy as np
import CheckSharedHexScalar as scalar

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('frozen_reference_for_scalar_tests',
    ROOT / 'workspace/Checks/InitialNumerics_20261106_hrz58ess/NumericalMaterial/Model/Reference.py')
reference = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reference)


class ScalarTests(unittest.TestCase):
    def test_changed_golden_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = ROOT / 'workspace/Server/tpusoc_shared_20261105_v1/Vectors/Ff1_normal'
            target = Path(directory) / 'Ff1_normal'
            shutil.copytree(source, target)
            expected = target / 'Expected0.hex'
            lines = expected.read_text(encoding='utf-8').splitlines()
            lines[0] = format(int(lines[0], 16) ^ 1, '08x')
            expected.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            model = ROOT / 'workspace/Checks/InitialNumerics_20261106_hrz58ess/NumericalMaterial/Model'
            with self.assertRaisesRegex(ValueError, 'Numerical mismatch'):
                scalar.replay(Path(directory), model)

    def test_changed_canonical_model_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory)
            original = ROOT / 'workspace/Checks/InitialNumerics_20261106_hrz58ess/NumericalMaterial/Model/Reference.py'
            (model / 'Reference.py').write_bytes(original.read_bytes() + b'\n')
            with self.assertRaisesRegex(ValueError, 'unchanged frozen Reference.py'):
                scalar.replay(model, model)

    def test_rounding_ties_and_every_int16_gelu_value_match_reference(self):
        for power in range(80):
            for offset in (-1, 0, 1):
                value = max(0, (1 << power) + offset)
                self.assertEqual(scalar.integer_root(value), math.isqrt(value))
        for bits in range(1, 16):
            edge = 1 << (bits - 1)
            values = [-2**40, -edge - 1, -edge, -edge + 1, -1, 0, 1, edge - 1, edge, edge + 1, 2**40]
            self.assertEqual([scalar.shift(value, bits) for value in values], reference.RoundShift(values, bits).tolist())
        values = list(range(-32768, 32768))
        self.assertEqual(scalar.gelu([values])[0], reference.Gelu(np.asarray(values)).tolist())

    def test_softmax_and_layernorm_extremes_match_reference(self):
        rng = np.random.default_rng(20261107)
        rows = rng.integers(-32768, 32768, size=(5, 64), dtype=np.int64)
        rows[0] = 32767
        rows[1] = -32768
        rows[2, ::2] = -32768
        rows[2, 1::2] = 32767
        residual = rng.integers(-32768, 32768, size=(5, 64), dtype=np.int64)
        gamma = rng.integers(-32768, 32768, size=64, dtype=np.int64)
        beta = rng.integers(-32768, 32768, size=64, dtype=np.int64)
        self.assertEqual(scalar.softmax(rows.tolist()), reference.Softmax(rows).tolist())
        for fraction in (1, 7, 15):
            self.assertEqual(scalar.norm(rows.tolist(), residual.tolist(), gamma.tolist(), beta.tolist(), fraction),
                             reference.LayerNorm(rows, residual, gamma, beta, fraction).tolist())

    def test_every_encoder_stage_matches_canonical_reference(self):
        rng = np.random.default_rng(7)
        params, translated, fractions, translated_fractions = {}, {}, {}, {}
        for name, inputs, outputs, bias in (('Query',64,64,False),('Key',64,64,False),('Value',64,64,False),
              ('Output',64,64,True),('Norm1',0,64,True),('Ff1',64,256,True),('Ff2',256,64,True),('Norm2',0,64,True)):
            fraction = int(rng.integers(9, 16))
            translated_fractions[name] = fraction
            if inputs:
                weight = rng.integers(-3000, 3001, size=(inputs, outputs), dtype=np.int64)
                params[name + 'Weight'] = weight
                fractions[name + 'Weight'] = fraction
                translated[name + 'Columns'] = weight.T.tolist()
                if bias:
                    value = rng.integers(-3000, 3001, size=outputs, dtype=np.int64)
                    params[name + 'Bias'] = value
                    translated[name + 'Bias'] = value.tolist()
            else:
                fractions[name + 'Gamma'] = fraction
                for suffix in ('Gamma', 'Beta'):
                    value = rng.integers(-3000, 3001, size=outputs, dtype=np.int64)
                    params[name + suffix] = value
                    translated[name + suffix] = value.tolist()
        rows = rng.integers(-32768, 32768, size=(6, 64), dtype=np.int64)
        expected = reference.Encoder(rows, params, Fixed=True, Fractions=fractions)
        actual = scalar.encoder(rows.tolist(), translated, translated_fractions)
        self.assertEqual(set(actual), set(expected))
        for name in expected:
            self.assertEqual(actual[name], expected[name].tolist(), name)


if __name__ == '__main__':
    unittest.main()
