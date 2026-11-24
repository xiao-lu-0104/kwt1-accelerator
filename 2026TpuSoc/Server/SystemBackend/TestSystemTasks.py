"""Physical init and unchanged benchmark transformation tests; local macros are fixtures."""
import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from SystemTasks import physical_bench,shared_guard,validate,verify_review_manifest,prepare,saif_time,TASKS
from ResumeSystemTasks import prepare as resume_prepare,finish as resume_finish
from Prepare import sha

HERE=Path(__file__).resolve().parent


def write_fixture(out):
    out.mkdir(parents=True,exist_ok=True)
    firmware=out/'Firmware.hex'
    firmware.write_text(''.join(f'{(i<<32)|(i^0x12345678):016x}\n' for i in range(32768)))
    (out/'SharedTcmGuard.sv').write_text(shared_guard())
    (out/'Fixture.sv').write_text('''`timescale 1ns/1ps
module LocalInitTop;
SharedTest SharedTest(); TcmInitializer TcmInitializer();
TaskActivity TaskActivity(); SharedTcmGuard SharedTcmGuard();
endmodule
module TaskActivity; bit Started=0,Stopped=0; endmodule
module SharedTest;
logic Clock=0,ResetN=0;
FixtureCpu Cpu();
initial forever begin #3.333 Clock=1; #3.334 Clock=0; end
initial begin
wait(TcmInitializer.Done); #0.001;
if (!TcmInitializer.Released) $fatal(1,"INIT_DRIVE_NOT_RELEASED");
@(negedge Clock); ResetN=1;
TaskActivity.Started=1;
Cpu.u_e203_srams.u_e203_dtcm_ram.HostCs=1;
Cpu.u_e203_srams.u_e203_dtcm_ram.HostWe=1;
Cpu.u_e203_srams.u_e203_dtcm_ram.HostAddress=16'd12345;
Cpu.u_e203_srams.u_e203_dtcm_ram.HostData=32'h1234abcd;
@(posedge Clock); @(negedge Clock);
Cpu.u_e203_srams.u_e203_dtcm_ram.HostWe=0;
@(posedge Clock); #0.001;
if (Cpu.u_e203_srams.u_e203_dtcm_ram.u_e203_dtcm_gnrl_ram.dout!==32'h1234abcd) $fatal(1,"INIT_FORCE_RETAINED_OR_NORMAL_PORT_WRITE_FAILED");
@(negedge Clock); Cpu.u_e203_srams.u_e203_dtcm_ram.HostCs=0;
TaskActivity.Stopped=1;
wait(SharedTcmGuard.Complete); #0.001;
$display("PASS LOCAL_PHYSICAL_INIT: full capacity real-port writes/readback; init drives released"); $finish;
end
endmodule
module FixtureCpu; FixtureSrams u_e203_srams(); endmodule
module FixtureSrams;
FixtureItcm u_e203_itcm_ram(); FixtureDtcm u_e203_dtcm_ram();
endmodule
module FixtureItcm;
sirv_gnrl_ram #(.DP(32768),.DW(64),.MW(8),.AW(15)) u_e203_itcm_gnrl_ram
(.clk(SharedTest.Clock),.rst_n(SharedTest.ResetN),.cs(1'b0),.we(1'b0),.addr(15'b0),.wem(8'b0),.din(64'b0),.dout(),.sd(1'b0),.ds(1'b0),.ls(1'b0));
endmodule
module FixtureDtcm;
logic HostCs=0,HostWe=0; logic [15:0] HostAddress=0; logic [31:0] HostData=0;
sirv_gnrl_ram #(.DP(65536),.DW(32),.MW(4),.AW(16)) u_e203_dtcm_gnrl_ram
(.clk(SharedTest.Clock),.rst_n(SharedTest.ResetN),.cs(HostCs),.we(HostWe),.addr(HostAddress),.wem(4'hf),.din(HostData),.dout(),.sd(1'b0),.ds(1'b0),.ls(1'b0));
endmodule
''')


class SystemTaskTests(unittest.TestCase):
    def test_saif_number_formats_and_invalid_headers(self):
        for header in ('(TIMESCALE 1 ps) (DURATION 2215764116)',
                       '(TIMESCALE 1.0e-12 s) (DURATION 2.215764116e+09)',
                       '(TIMESCALE 1 PS) (DURATION 2215764116.0)',
                       '(TIMESCALE 1000 fs)\n(DURATION 2.215764116E9)'):
            with self.subTest(header=header): self.assertAlmostEqual(saif_time(header)['seconds'],0.002215764116,places=15)
        for header in ('(TIMESCALE 1 ns) (DURATION 0)','(TIMESCALE -1 ps) (DURATION 1)',
                       '(TIMESCALE nan ps) (DURATION 1)','(TIMESCALE 1 ps) (DURATION inf)',
                       '(TIMESCALE 1 ps) (DURATION 1) (DURATION 2)','(DURATION 1)'):
            with self.subTest(header=header),self.assertRaises(ValueError): saif_time(header)

    def test_resume_preserves_binary_ff1_and_only_accepts_complete_encoder(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); old=root/'old'; out=root/'resume'; tools=root/'tools'
            for p in (old/'ff1',old/'encoder',out,tools): p.mkdir(parents=True,exist_ok=True)
            (old/'Inputs.json').write_text(json.dumps({'inputs':{}}))
            (old/'runner.log').write_text('STAGE_FINISHED: compile exit=0 elapsed_seconds=57\nSTAGE_FINISHED: simulate_ff1 exit=0 elapsed_seconds=582\n')
            for name in ('simv','compile.log','Bundle.txt','Firmware.txt'): (old/name).write_text('ORIGINAL '+name)
            (tools/'resume.py').write_text('FIXTURE HELPER')
            def evidence(name):
                kind,values,cycles,reads,writes,loaded=TASKS[name]
                (old/name/'run.log').write_text(f'''PASS SHARED: kind={kind} layers=1 values={values} cycles={cycles} DMA_read_bytes={reads} DMA_write_bytes={writes} loaded_bytes={loaded}
PASS PHYSICAL_TCM_INIT: ITCM_writes=32768 DTCM_writes=65536 ITCM_readback=32768 DTCM_readback=65536; details
PHYSICAL_TCM_INIT_FINAL: done=1 released=1
INIT_FINAL: all=1 pattern=2 released=1 checked=1 new_control_QX=0
ICB_MIRROR_FINAL: divergence_observed=0
TASK_ACTIVITY_FINAL: started=1 stopped=1
EFFECTIVE_GUARD_FINAL: complete=1
SHARED_TCM_GUARD_FINAL: complete=1
TASK_ACTIVITY_END: cycles={cycles} duration_ns={cycles*6.667:.3f}
''')
                # Native reports may use scientific notation for the long ps count.
                (old/name/'task.saif').write_text(f'(TIMESCALE 1e-12 s) (DURATION {cycles*6667:.12e}) (INSTANCE u_e203_cpu (TC 1) (TX 0)) (INSTANCE u_e203_srams)')
            evidence('ff1')
            original={str(p):p.read_bytes() for p in (old/'ff1/run.log',old/'ff1/task.saif',old/'simv',old/'runner.log')}
            resume_prepare(old,out,tools)
            self.assertFalse((old/'encoder/run.log').exists())
            self.assertTrue((old/'ff1/Activity.json').exists())
            with self.assertRaises(FileNotFoundError): resume_finish(out)
            evidence('encoder'); resume_finish(out)
            result=json.loads((out/'SystemActivitySummary.json').read_text())
            self.assertTrue(result['FF1_preserved'])
            self.assertEqual(result['tasks']['encoder']['cycles'],1485712)
            for name,data in original.items(): self.assertEqual(Path(name).read_bytes(),data)

    def test_preparation_replaces_only_ram_and_init_and_freezes_static_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            review=root/'review'; base=root/'base'; source=root/'power'; qualification=root/'qualification'
            tools=root/'tools'; out=root/'new'; functional=root/'functional'
            for p in (review,base,source,qualification,tools,out,functional/'project',base/'tools'): p.mkdir(parents=True,exist_ok=True)
            (review/'Inputs.json').write_text(json.dumps({'inputs':{},'source':str(base)}))
            (review/'ClockPortSummary.json').write_text(json.dumps({'SETUP_STATUS':'PASS','HOLD_STATUS':'PASS'}))
            (review/'clock_ports_corrected.sdc').write_text('VERIFIED SDC')
            (review/'MANIFEST.sha256').write_text(sha(review/'ClockPortSummary.json')+'  ClockPortSummary.json\n')
            (base/'SystemBaseRecoveryInputs.json').write_text(json.dumps({'source':str(source),'qualification':str(qualification),'inputs':{}}))
            (source/'TaskPowerInputs.json').write_text(json.dumps({'inputs':{}}))
            (source/'Functional.txt').write_text(str(functional))
            (source/'Bundle.txt').write_text(str(root/'bundle'))
            (functional/'project/Firmware.hex').write_text('0000000000000000\n'*32768)
            text=(HERE.parents[1]/'Sim/SharedTest.sv').read_text()
            text=text.replace('Measured = 1; StartCycle = Cycles + 1;',
                'Measured = 1; StartCycle = Cycles + 1; TaskActivity.StartWindow();').replace(
                'LastWriteCycle = Cycles; LastWritePending = 0;',
                'LastWriteCycle = Cycles; LastWritePending = 0; TaskActivity.EndRequested = 1;')
            (source/'TaskSharedTest.sv').write_text(text+'\n// UNKNOWN_LOADER_COMMAND_READY UNKNOWN_LOADER_RESPONSE_VALID UNKNOWN_LOADER_READ_DATA\n')
            (source/'Task.f').write_text('\n'.join(str(source/n) for n in ('TaskSharedTest.sv','candidate.v','sirv_gnrl_ram.v'))+'\n')
            (base/'frozen_accelerator.v').write_text('FROZEN CANDIDATE FIXTURE')
            (base/'tools/TcmMacro.sv').write_bytes((HERE/'TcmMacro.sv').read_bytes())
            macro=root/'raw_macro.v'; macro.write_text('RAW MACRO FIXTURE')
            (base/'SharedModel.txt').write_text(str(macro))
            for name in ('GateResetInventory.sv','IcbMirror.sv'): (source/name).write_text('ORIGINAL '+name)
            (qualification/'EffectiveDataGuard.sv').write_text('ORIGINAL EFFECTIVE GUARD')
            (tools/'TaskActivity.sv').write_bytes((HERE.parent/'SharedAsic/TaskActivity.sv').read_bytes())
            (out/'prepare.log').write_text('OPEN RUNTIME LOG')
            real_sha=sha
            def fixture_sha(path):
                return 'b366417d57d6251f13a827933288886637b61071472d391b121a7341fa2ea75e' if path.name=='candidate.v' else real_sha(path)
            with patch('SystemTasks.sha',side_effect=fixture_sha): prepare(out,tools,review)
            record=json.loads((out/'Inputs.json').read_text())
            self.assertNotIn(str(out/'prepare.log'),record['inputs'])
            self.assertIn(str(base/'tools/TcmMacro.sv'),(out/'Task.f').read_text())
            self.assertNotIn('sirv_gnrl_ram.v',(out/'Task.f').read_text())
            self.assertIn('$set_toggle_region(SharedTest.Cpu);',(out/'SystemActivity.sv').read_text())
            self.assertIn('no full-system gate/SDF claim',record['scope'])

    def test_closed_runtime_journal_requires_original_prefix_and_complete_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory); log=out/'summary_recovery_v1_ABC123.log'
            log.write_bytes(b'RECOVERY: original input proof\n')
            digest=sha(log)
            (out/'MANIFEST.sha256').write_text(digest+'  '+log.name+'\n')
            log.write_bytes(log.read_bytes()+b'CLOCK_PORT_REVIEW: NETLIST UNCHANGED\nRECOVERY_RAW_REPORTS_UNCHANGED: PASS\n')
            self.assertEqual(len(verify_review_manifest(out)),1)
            log.write_bytes(b'altered\n'+log.read_bytes())
            with self.assertRaisesRegex(ValueError,'prefix changed'): verify_review_manifest(out)
    def test_bench_changes_only_init_and_diagnostic_backdoors(self):
        original=(HERE.parents[1]/'Sim/SharedTest.sv').read_text()
        text=original.replace('Measured = 1; StartCycle = Cycles + 1;',
            'Measured = 1; StartCycle = Cycles + 1; TaskActivity.StartWindow();').replace(
            'LastWriteCycle = Cycles; LastWritePending = 0;',
            'LastWriteCycle = Cycles; LastWritePending = 0; TaskActivity.EndRequested = 1;')
        text+='\n// UNKNOWN_LOADER_COMMAND_READY UNKNOWN_LOADER_RESPONSE_VALID UNKNOWN_LOADER_READ_DATA\n'
        result=physical_bench(text)
        self.assertIn('wait (TcmInitializer.Done && TcmInitializer.Released);',result)
        self.assertNotIn('u_sirv_sim_ram.mem_r',result)
        self.assertIn('Result !== ExpectedHost[WordIndex]',result)
        self.assertIn('DmaReads != ExpectedReads || DmaWrites != ExpectedWrites',result)
        self.assertIn('CPU failed/trapped',result)
        with self.assertRaises(ValueError): physical_bench(text.replace('UNKNOWN_LOADER_READ_DATA','removed'))

    def test_shared_guard_has_all_macros_and_no_dut_drive(self):
        text=shared_guard()
        self.assertEqual(text.count('SHARED_MACRO_CEN_X'),64)
        self.assertEqual(text.count('SHARED_MACRO_READ_Q_X'),64)
        self.assertNotIn('force ',text)
        self.assertNotIn('release ',text)

    def test_validation_requires_all_function_init_activity_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory); case=out/'ff1'; case.mkdir()
            (out/'Inputs.json').write_text(json.dumps({'inputs':{}}))
            text='''PASS SHARED: kind=1 layers=1 values=25344 cycles=332348 DMA_read_bytes=45952 DMA_write_bytes=50688 loaded_bytes=45960
PASS PHYSICAL_TCM_INIT: ITCM_writes=32768 DTCM_writes=65536 ITCM_readback=32768 DTCM_readback=65536; details
PHYSICAL_TCM_INIT_FINAL: done=1 released=1
INIT_FINAL: all=1 pattern=2 released=1 checked=1 new_control_QX=0
ICB_MIRROR_FINAL: divergence_observed=0
TASK_ACTIVITY_FINAL: started=1 stopped=1
EFFECTIVE_GUARD_FINAL: complete=1
SHARED_TCM_GUARD_FINAL: complete=1
TASK_ACTIVITY_END: cycles=332348 duration_ns=2215764.116
'''
            (case/'run.log').write_text(text)
            (case/'task.saif').write_text('(TIMESCALE 1 ps) (DURATION 2215764116) (INSTANCE u_e203_cpu (TC 1)) (INSTANCE u_e203_srams)')
            validate(out,'ff1')
            for bad in (text.replace('released=1','released=0'),text.replace('cycles=332348','cycles=332349'),text+'Fatal: failure\n'):
                (case/'run.log').write_text(bad)
                with self.assertRaises(ValueError): validate(out,'ff1')


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--fixtures',type=Path); args,remaining=parser.parse_known_args()
    if args.fixtures: write_fixture(args.fixtures)
    else: unittest.main(argv=[__file__]+remaining)
