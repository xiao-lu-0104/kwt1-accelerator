import json
from pathlib import Path
import tempfile
import unittest
from EncoderWriteDiagnostic import prepare,finish
from Prepare import sha


class EncoderTraceTests(unittest.TestCase):
    def test_passive_trace_preserves_old_evidence_and_requires_complete_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); old=root/'old'; out=root/'new'; tools=root/'tools'
            for p in (old/'ff1',old/'encoder',out,tools): p.mkdir(parents=True,exist_ok=True)
            (old/'Inputs.json').write_text(json.dumps({'inputs':{}}))
            for name in ('Task.f','Bundle.txt','Firmware.txt','ff1/run.log'): (old/name).write_text('ORIGINAL '+name)
            (old/'ff1/task.saif').write_bytes(b'PASSED FF1 ACTIVITY')
            (old/'ff1/Activity.json').write_text(json.dumps({'saif_sha256':sha(old/'ff1/task.saif')}))
            (old/'encoder/run.log').write_text('Fatal: SHARED_MACRO_WRITE_X 62\nTASK_ACTIVITY_FINAL: started=1 stopped=0\n')
            (tools/'trace.sv').write_text('PASSIVE TRACE FIXTURE')
            before={str(p):p.read_bytes() for p in old.rglob('*') if p.is_file()}
            prepare(old,out,tools)
            (out/'run.log').write_text('CPU_WRITE_TRACE: incomplete\n')
            with self.assertRaisesRegex(ValueError,'all required'): finish(out)
            (out/'run.log').write_text('''Fatal: SHARED_MACRO_WRITE_X 62
CPU_WRITE_TRACE: fetch_pc=80000100 cycles=112136
CPU_DTCM_WRITE: cs=1 we=1 word_address=fffe byte_address=9003fff8 wem=f din=xxxxxxxx
MACRO62_WRITE: CEN=0 GWEN=0 A=ffe byte_address=9003fff8 WEN=0000 D=xxxx Q=0000
CPU_GPRS: sp=9003ffa0 s0=xxxxxxxx
CPU_RECENT_FETCH_PC: 800000fa
''')
            finish(out)
            self.assertTrue((out/'WriteTrace.txt').exists())
            for name,data in before.items(): self.assertEqual(Path(name).read_bytes(),data)
            (old/'ff1/task.saif').write_bytes(b'CHANGED')
            with self.assertRaisesRegex(ValueError,'Frozen input changed'): finish(out)


if __name__=='__main__': unittest.main()
