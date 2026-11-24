"""Check new eight-pipeline guard and actual locally compiled firmware provenance."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.append(str(ROOT / 'Server/SharedAsic'))
import PowerGuards


def fixture(dots=8):
    def m(name, body):
        return 'module ' + name + ';\n' + body + '\nendmodule\n'
    text = m('e203_subsys_nice_core', 'wire nice_rst_n;\nTpuNice Tpu();')
    text += m('TpuNice', 'TpuCore Core();')
    text += m('TpuCore', 'TpuMatmul Matrix();\nTpuDma Dma();\nTpuSram Sram();')
    text += m('TpuMatmul', 'BiasBuffer BiasBuffer();\n' + '\n'.join('TpuDot \\RowPipelines[%d].Dot  ();' % i for i in range(dots)))
    text += m('TpuDot', 'wire InputValid; wire [127:0] InputOperandA,InputOperandB;')
    text += m('BiasBuffer', 'wire WriteValid; wire [127:0] WriteData;')
    text += m('TpuDma', 'wire WriteDataValid,ReadDataValid,ReadDataReady,ReadDataLast,ReadDataError,SramReadValid,SramReadReady;\nwire [127:0] WriteData,ReadData,SramReadData;')
    text += m('TpuSram', '\n'.join('RAMSP1024X16 Macro%d ();' % i for i in range(56)))
    return text


class Prep(unittest.TestCase):
    def test_eight_pipeline_guard_and_all_macros(self):
        guard = PowerGuards.effective_guard(fixture())
        for i in range(8):
            self.assertIn('EFFECTIVE_DATA_X DOT_' + str(i), guard)
        self.assertEqual(guard.count('MACRO_ENABLE_X '), 56)
        self.assertNotIn('force ', guard)

    def test_old_four_pipeline_input_rejected(self):
        with self.assertRaises(ValueError):
            PowerGuards.effective_guard(fixture(4))

    def test_actual_compiled_firmware_hashes_and_boot(self):
        out = ROOT / 'workspace/Checks/PowerFirmware_20261110_707cd7f_v1'
        proof = json.loads((out / 'BuildEvidence/FirmwareEvidence.json').read_text())
        self.assertEqual(proof['frontend_revision'], '707cd7f4a0a4d416d11bac71112980079e0a9d34')
        self.assertEqual(proof['FF1_blocks'], [32, 32, 28, 7])
        for name, h in proof['sha256'].items():
            self.assertEqual(hashlib.sha256((out / name).read_bytes()).hexdigest(), h)
        binary = (out / 'BuildEvidence/Shared.bin').read_bytes()
        self.assertTrue(binary.startswith(b''.join(((r << 7) | 0x13).to_bytes(4, 'little') for r in range(1, 32))))


if __name__ == '__main__':
    unittest.main()
