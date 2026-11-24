import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from ClockPortReview import budget_diff,finish,area_breakdown,generated_clock
from Prepare import sha

HERE=Path(__file__).resolve().parent
BEFORE='''create_clock -name CoreClock -period 6.666667 [get_ports clk]
set_clock_uncertainty -setup 0.2 [get_clocks CoreClock]
set_output_delay -clock CoreClock -max 1 [get_ports inspect_core_clk]
set_output_delay -clock CoreClock -min -0.1 [get_ports inspect_core_clk]
set_output_delay -clock CoreClock -max 1 [get_ports core_csr_clk]
set_output_delay -clock CoreClock -min -0.1 [get_ports core_csr_clk]
set_output_delay -clock CoreClock -min -0.1 [get_ports data]
set_load 0.035 [get_ports inspect_core_clk]
set_load 0.035 [get_ports core_csr_clk]
'''
AFTER='\n'.join(line for line in BEFORE.splitlines() if not (line.startswith('set_output_delay ') and ('inspect_core_clk' in line or 'core_csr_clk' in line)))+'\n'+'''create_generated_clock -name InspectCoreClock -source [get_ports clk] -divide_by 1 -combinational [get_ports inspect_core_clk]
create_generated_clock -name CoreCsrClock -source [get_ports clk] -divide_by 1 -combinational [get_ports core_csr_clk]
set_clock_uncertainty -hold 0.1 [get_clocks InspectCoreClock]
set_clock_uncertainty -hold 0.1 [get_clocks CoreCsrClock]
'''

def area_fixture(out):
    values=(('ACCELERATOR_LOGIC_AND_INTERFACES',100,190955.016),('ACCELERATOR_PRIVATE_SRAM',56,512317.367184),
        ('REUSED_CPU_AND_INTERNAL_ICB_LOGIC',100,192542.427586),('SHARED_ITCM_MACROS',32,800000),
        ('SHARED_DTCM_MACROS',32,800000),('SHARED_TCM_BINDING_LOGIC',10,0),('OTHER_SYSTEM_LOGIC',1,0))
    (out/'area_breakdown.tsv').write_text('component\tleaf_count\tarea_um2\tarea_mm2\tin_accelerator_budget\n'+
        ''.join(f'{k}\t{n}\t{a:.9f}\t{a/1e6:.12f}\t{int(k.startswith("ACCELERATOR_"))}\n' for k,n,a in values))


def native_after():
    text=AFTER
    for name,port in (('InspectCoreClock','inspect_core_clk'),('CoreCsrClock','core_csr_clk')):
        text=text.replace(f'create_generated_clock -name {name} -source [get_ports clk] -divide_by 1 -combinational [get_ports {port}]',
            f'create_generated_clock [get_ports {port}] -name {name} -source [get_ports clk] -combinational')
    return text


class ClockPortTests(unittest.TestCase):
    def test_native_dc_serialization_and_bad_clock_semantics(self):
        self.assertEqual(budget_diff(BEFORE,native_after())['removed_clock_output_data_delays'],
                         budget_diff(BEFORE,AFTER)['removed_clock_output_data_delays'])
        self.assertTrue(budget_diff(BEFORE,native_after().replace('-source [get_ports clk]','-source [get_ports {clk}]')))
        for bad in (native_after().replace('-combinational','-combinational -divide_by 2'),
                    native_after().replace('-combinational','-combinational -invert'),
                    native_after().replace('-source [get_ports clk]','-source [get_ports data]'),
                    native_after().replace('[get_ports inspect_core_clk]','[get_ports data]'),
                    native_after().replace('-hold 0.1','-hold 0.05'),
                    native_after().replace('-hold 0.1','-hold nan')):
            with self.subTest(bad=bad),self.assertRaises(ValueError): budget_diff(BEFORE,bad)

    def test_area_totals_and_inventory_cannot_be_silently_changed(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory); area_fixture(out)
            expected={'SYSTEM_LIBRARY_AREA_UM2':'2495814.81077'}
            data=area_breakdown(out,expected)
            self.assertAlmostEqual(data['accelerator_budget_area_um2'],703272.383184,places=6)
            saved=(out/'area_breakdown.tsv').read_text()
            for bad in (saved.replace('SHARED_ITCM_MACROS\t32','SHARED_ITCM_MACROS\t31'),
                        saved.replace('800000.000000000','800001.000000000'),
                        saved.replace('ACCELERATOR_PRIVATE_SRAM\t56','ACCELERATOR_PRIVATE_SRAM\t55')):
                (out/'area_breakdown.tsv').write_text(bad)
                with self.assertRaises(ValueError): area_breakdown(out,expected)

    def test_tcl_area_counts_each_leaf_once(self):
        import tkinter
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory); t=tkinter.Tcl()
            t.call('source',str(HERE/'AreaBreakdown.tcl'))
            t.eval(r'''
set Cells {}; array set Refs {}
foreach {Prefix Ref N} {
u_e203_cpu/u_e203_nice_core/Private RAMSP1024X16 56
u_e203_srams/u_e203_itcm_ram/M RAMSP4096X16 32
u_e203_srams/u_e203_dtcm_ram/M RAMSP4096X16 32
u_e203_cpu/u_e203_nice_core/Logic DQV0 2
u_e203_cpu/Logic DQV0 3
u_e203_srams/Binding DQV0 4
TopReset DQV0 1
} {
for {set i 0} {$i<$N} {incr i} {set Name $Prefix$i; lappend Cells $Name; set Refs($Name) $Ref}
}
proc get_cells args {return $::Cells}
proc foreach_in_collection {var objects body} {foreach obj $objects {uplevel 1 [list set $var $obj]; uplevel 1 $body}}
proc get_object_name obj {return $obj}
proc sizeof_collection objects {llength $objects}
proc get_lib_cells args {return [lindex $args end]}
proc get_attribute {obj attr} {
if {$attr eq "ref_name"} {return $::Refs($obj)}
if {$attr eq "area"} {
if {$obj eq "*/RAMSP1024X16"} {return 100.0}
if {$obj eq "*/RAMSP4096X16"} {return 400.0}
return 1.0
}
error "Unexpected attribute $attr"
}
''')
            t.call('WriteAreaBreakdown',str(out))
            rows=(out/'area_breakdown.tsv').read_text().splitlines()
            self.assertEqual(len(rows),8)
            self.assertIn('ACCELERATOR_LOGIC_AND_INTERFACES\t2\t2.000000000',rows[1])
            self.assertIn('REUSED_CPU_AND_INTERNAL_ICB_LOGIC\t3\t3.000000000',rows[3])
            self.assertIn('SYSTEM_AREA_UM2: 31210.0',(out/'area_totals.txt').read_text())
            with self.assertRaises(tkinter.TclError):
                t.call('AreaClass','u_e203_cpu/WrongPlace','RAMSP4096X16')

    def test_only_clock_port_roles_may_change(self):
        self.assertEqual(len(budget_diff(BEFORE,AFTER)['removed_clock_output_data_delays']),4)
        for bad in (AFTER.replace('set_load 0.035','set_load 0.001'),
                    AFTER.replace('-min -0.1 [get_ports data]','-min 0.1 [get_ports data]'),
                    AFTER.replace('-setup 0.2','-setup 0.1'),
                    AFTER+'set_false_path -from [all_inputs]\n',
                    AFTER.replace('-divide_by 1','-divide_by 2')):
            with self.subTest(bad=bad),self.assertRaises(ValueError): budget_diff(BEFORE,bad)

    def test_finish_preserves_fail_and_hashes_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); out=root/'review'; out.mkdir(); source=root/'source'; source.mkdir()
            original=source/'candidate.ddc'; original.write_bytes(b'ORIGINAL DDC')
            (source/'SystemBaseSummary.json').write_text(json.dumps({'mapped':{'SETUP_WNS_NS':'0.00191832','HOLD_WNS_NS':'-0.2','SYSTEM_LIBRARY_AREA_UM2':'2495814.81077'}}))
            area_fixture(out)
            (out/'Inputs.json').write_text(json.dumps({'source':str(source),'inputs':{str(original):sha(original)}}))
            (out/'dc.log').write_text('CLOCK_PORT_REPORT_COMPLETE: fixture\n')
            (out/'loaded.sdc').write_text(BEFORE); (out/'clock_ports_corrected.sdc').write_text(AFTER)
            (out/'summary.txt').write_text('''NETLIST: UNCHANGED
ORIGINAL_SETUP_WNS_NS: 0.00191832
ORIGINAL_HOLD_WNS_NS: -0.2
SETUP_WNS_NS: -0.01
HOLD_WNS_NS: 0.000083
SETUP_STATUS: FAIL
HOLD_STATUS: PASS
''')
            finish(out)
            data=json.loads((out/'ClockPortSummary.json').read_text())
            self.assertEqual(data['SETUP_STATUS'],'FAIL')
            self.assertTrue((out/'ClockPortReports.partial.tar.gz').exists())
            original.write_bytes(b'CHANGED')
            with self.assertRaisesRegex(ValueError,'Frozen input changed'): finish(out)

    def test_recovery_finishes_native_sdc_without_eda_or_raw_file_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); out=root/'review'; out.mkdir(); source=root/'source'; source.mkdir()
            original=source/'candidate.ddc'; original.write_bytes(b'ORIGINAL DDC')
            (source/'SystemBaseSummary.json').write_text(json.dumps({'mapped':{'SETUP_WNS_NS':'0.00191832','HOLD_WNS_NS':'-0.2','SYSTEM_LIBRARY_AREA_UM2':'2495814.81077'}}))
            (out/'Inputs.json').write_text(json.dumps({'source':str(source),'inputs':{str(original):sha(original)}}))
            area_fixture(out)
            (out/'dc.log').write_text('CLOCK_PORT_REPORT_COMPLETE: fixture\n')
            (out/'loaded.sdc').write_text(BEFORE); (out/'clock_ports_corrected.sdc').write_text(native_after())
            (out/'summary.txt').write_text('''NETLIST: UNCHANGED
ORIGINAL_SETUP_WNS_NS: 0.00191832
ORIGINAL_HOLD_WNS_NS: -0.2
SETUP_WNS_NS: 0.00191832
HOLD_WNS_NS: 0.000083
SETUP_STATUS: PASS
HOLD_STATUS: PASS
''')
            for name in ('area_totals.txt','clock_port_sources.txt','setup.rpt','hold.rpt'): (out/name).write_text('ORIGINAL '+name)
            before={str(p):p.read_bytes() for p in out.iterdir() if p.is_file()}
            result=subprocess.run([sys.executable,'-B',str(HERE/'RecoverClockReview.py'),str(out)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            for name,data in before.items(): self.assertEqual(Path(name).read_bytes(),data)
            self.assertIn('RECOVERY_RAW_REPORTS_UNCHANGED: PASS',result.stdout)
            self.assertTrue((out/'ClockReviewRecoveryInputs.json').exists())
            self.assertTrue((out/'ClockPortReports.partial.tar.gz').exists())

    def test_tcl_reports_only_and_rejects_non_clock_fanin(self):
        import tkinter
        for bad_fanin,expected in ((False,0),(True,1)):
            with self.subTest(bad_fanin=bad_fanin),tempfile.TemporaryDirectory() as directory:
                out=Path(directory); t=tkinter.Tcl()
                (out/'AsicCommon.tcl').write_bytes((HERE.parent/'Backend/AsicCommon.tcl').read_bytes())
                (out/'AreaBreakdown.tcl').write_text('proc WriteAreaBreakdown Out {}\n')
                for key,value in {'TPU_CLOCK_OUT':str(out),'TPU_CLOCK_TOOLS':str(out),
                    'TPU_CLOCK_DDC':'original.ddc','TPU_STDCELL_DB':'std.db','TPU_SRAM_DB':'sp.db','TPU_SYSTEM_DB':'shared.db'}.items():
                    t.setvar('env('+key+')',value)
                t.setvar('BadFanin',int(bad_fanin))
                t.eval(r'''
set Clocks {CoreClock}; set Removed {}; set Leaf {one two}; set Corrected 0
proc exit code {set ::TestExit $code; error TEST_EXIT}
proc foreach_in_collection {var objects body} {foreach obj $objects {uplevel 1 [list set $var $obj]; uplevel 1 $body}}
proc sizeof_collection objects {llength $objects}
proc get_object_name obj {return $obj}
proc read_ddc args {return {e203_cpu_top e203_cpu_MASTER1 e203_srams}}
proc get_designs args {return e203_cpu_top}
proc current_design args {}
proc link {} {return 1}
proc all_clocks {} {return $::Clocks}
proc get_clocks args {return [lindex $args end]}
proc get_ports args {return [lindex $args end]}
proc get_cells args {
set f [lindex $args end]
if {$f eq "ref_name == RAMSP1024X16"} {return [lrepeat 56 M]}
if {$f eq "ref_name == RAMSP4096X16"} {return [lrepeat 64 M]}
return $::Leaf
}
proc get_attribute {obj attr} {
if {$attr eq "period"} {return 6.666667}
if {$attr eq "ref_name"} {return DQV0}
if {$attr eq "slack"} {
if {$obj eq "min" && !$::Corrected} {return -0.2}
if {$obj eq "min"} {return 0.000083}
return 0.00191832
}
error "Unexpected attribute $attr"
}
proc all_fanin args {if {$::BadFanin} {return data}; return clk}
proc remove_output_delay obj {lappend ::Removed $obj}
proc create_generated_clock args {lappend ::Clocks [lindex $args 1]; set ::Corrected 1}
proc get_timing_paths args {return [lindex $args 1]}
foreach name {set_clock_uncertainty set_clock_transition write_sdc report_timing report_clock report_port check_timing check_design report_constraint} {proc $name args {}}
proc compile args {error "No compilation authorized in report-only entry"}
proc compile_ultra args {error "No compilation authorized in report-only entry"}
proc set_false_path args {error "No timing cut authorized"}
''')
                import os
                old=Path.cwd()
                try:
                    with self.assertRaises(tkinter.TclError): t.call('source',str(HERE/'ClockPortReview.tcl'))
                    self.assertEqual(int(t.getvar('TestExit')),expected)
                    if expected==0:
                        self.assertEqual(t.eval('join $Removed'),'inspect_core_clk core_csr_clk')
                        self.assertIn('HOLD_STATUS: PASS',(out/'summary.txt').read_text())
                finally: os.chdir(old)


if __name__=='__main__': unittest.main()
