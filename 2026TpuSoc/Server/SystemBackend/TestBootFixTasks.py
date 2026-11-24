"""Check boot repair provenance and preservation of existing failed/successful runs."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from BootFirmware import validate_code
from BootFixTasks import prepare
from Prepare import sha,check

ROOT=Path(__file__).resolve().parents[2]
FIXED=ROOT/'workspace/Checks/BootGprFix_20261107_v1/fixed'
BUNDLE=ROOT/'workspace/Server/tpusoc_shared_20261105_v1'


class BootFixTests(unittest.TestCase):
    def test_actual_executable_clears_every_gpr_and_rejects_missing_clear(self):
        code=(FIXED/'BuildEvidence/Shared.bin').read_bytes()
        validate_code(code)
        with self.assertRaises(ValueError): validate_code(code[4:])
        broken=bytearray(code); broken[7*4:8*4]=b'\x13\x00\x00\x00'
        with self.assertRaises(ValueError): validate_code(broken)

    def fixture(self,root):
        old=root/'old'; out=root/'out'; tools=out/'tools'
        for p in (old/'ff1',old/'encoder',tools): p.mkdir(parents=True,exist_ok=True)
        shutil.copytree(FIXED,out/'firmware')
        (old/'Inputs.json').write_text(json.dumps({'inputs':{},'source':'ORIGINAL_SYSTEM'}))
        (old/'Firmware.txt').write_text(str(BUNDLE/'Firmware.hex'))
        (old/'Bundle.txt').write_text(str(BUNDLE))
        (old/'ff1/run.log').write_text('ORIGINAL PASSED FF1 EVIDENCE')
        (old/'ff1/task.saif').write_text('ORIGINAL SAIF FIXTURE')
        (old/'ff1/Activity.json').write_text(json.dumps({'saif_sha256':sha(old/'ff1/task.saif')}))
        (old/'encoder/run.log').write_text('Fatal: SHARED_MACRO_WRITE_X 62\nTASK_ACTIVITY_FINAL: started=1 stopped=0\n')
        (old/'simv').write_text('ORIGINAL EXECUTABLE FIXTURE')
        (old/'Task.f').write_text('ORIGINAL IMMUTABLE HDL LIST')
        (tools/'Helper.py').write_text('FIXTURE HELPER')
        return old,out,tools

    def test_preparation_preserves_all_old_files_and_freezes_new_firmware(self):
        with tempfile.TemporaryDirectory() as directory:
            old,out,tools=self.fixture(Path(directory))
            before={p:p.read_bytes() for p in old.rglob('*') if p.is_file()}
            prepare(old,out,tools)
            self.assertEqual(before,{p:p.read_bytes() for p in old.rglob('*') if p.is_file()})
            record=json.loads((out/'Inputs.json').read_text()); check(record)
            self.assertEqual(Path((out/'Firmware.txt').read_text().strip()),out/'firmware/BuildEvidence/Firmware.hex')
            self.assertIn(str(old/'simv'),record['inputs'])
            self.assertIn(str(old/'encoder/run.log'),record['inputs'])
            self.assertNotIn(str(out/'prepare.log'),record['inputs'])
            path=out/'firmware/Sw/SharedStart.S'; path.write_text('changed')
            with self.assertRaises(ValueError): check(record)

    def test_different_original_firmware_cannot_be_repaired_silently(self):
        with tempfile.TemporaryDirectory() as directory:
            old,out,tools=self.fixture(Path(directory))
            alien=Path(directory)/'alien.hex'; alien.write_text('0000000000000000\n')
            (old/'Firmware.txt').write_text(str(alien))
            with self.assertRaisesRegex(ValueError,'Remote firmware differs'): prepare(old,out,tools)


if __name__=='__main__': unittest.main()
