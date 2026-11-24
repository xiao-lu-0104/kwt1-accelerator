"""Verify literal object requests and real Tcl audit flow with mocked DC collections."""
import csv
import hashlib
import json
import os
from pathlib import Path
import tempfile
import tkinter
import unittest
from PrepareObjectAudit import queries,system_sources


class ObjectAuditTests(unittest.TestCase):
    def test_system_source_snapshot_and_raw_macro_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory); source=base/'task'; source.mkdir()
            functional=base/'functional'; project=functional/'project'
            platform=project/'e203_hbirdv2/rtl/e203'; core=platform/'core'; core.mkdir(parents=True)
            config=core/'config.v'
            config.write_text('`define E203_CFG_ITCM_ADDR_WIDTH 18\n`define E203_CFG_DTCM_ADDR_WIDTH 18\n')
            scope={'configuration_modified':False,'cpu_datapath_modified':False,
                'copied_platform_sha256':{'core/config.v':hashlib.sha256(config.read_bytes()).hexdigest()}}
            (project/'Scope.json').write_text(json.dumps(scope))
            (source/'Functional.txt').write_text(str(functional))
            (source/'Task.f').write_text(str(config)+'\n')
            macro=base/'RAMSP4096X16'; (macro/'verilog').mkdir(parents=True); (macro/'lib').mkdir()
            (macro/'verilog/RAMSP4096X16.v').write_text('/* output not_a_port; */\nmodule RAMSP4096X16(Q,CLK,WEN);\noutput [15:0] Q;\ninput CLK;\ninput [15:0] WEN;\nendmodule\n')
            (macro/'lib/RAMSP4096X16_tt_1p10v_1p10v_25c.lib').write_text('library(test) {}')
            (source/'SystemPowerContext.json').write_text(json.dumps({'memory_catalog':{
                'available_sram_packages':[{'directory':str(macro)}]}}))
            out=base/'out'; out.mkdir(); inputs={}
            system_sources(source,out,inputs)
            evidence=json.loads((out/'SharedSramMacroEvidence.json').read_text())
            self.assertFalse(any('not_a_port' in x for x in evidence['raw_declarations']))
            self.assertIn(str(config),inputs)
            self.assertEqual(json.loads((out/'SystemPowerPreparation.json').read_text())['candidate_macro_count_for_capacity'],64)
            config.write_text('changed')
            with self.assertRaisesRegex(ValueError,'Platform source changed'): system_sources(source,out,{})

    def test_literal_bit_names_and_annotation_warning_inventory(self):
        review={'tasks':{'ff1':{'unknown':[{'scope':'SharedTest/Cpu/u_e203_cpu/u_e203_nice_core/Bus',
             'kind':'NET','signal':'Word[0]'}]}}}
        rows,unmatched=queries(review,'ff1',"Warning: Line 1, Can't find object 'Bus/Word[0]'. (SAIF-16)\n")
        self.assertIn(('NET','Bus/Word[0]','TX_NONZERO'),[row[1:] for row in rows])
        self.assertEqual(unmatched['Bus/Word[0]'],1)
        review['tasks']['ff1']['unknown'][0]['scope']='OtherCpu/Bus'
        with self.assertRaisesRegex(ValueError,'outside'): queries(review,'ff1','')

    def test_tcl_connectivity_preserves_top_output_and_critical_guards(self):
        for mode,expected in (('pass',0),('bad_saif',1),('bad_macros',1)):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                (root/'objects.tsv').write_text('id\tkind\tname\treason\n0\tNET\tsignal[0]\tTX_NONZERO\n'
                    '1\tNET\tfloating\tTX_NONZERO\n2\tNET\ttop_result\tTX_NONZERO\n3\tAUTO\tremoved\tSAIF_OBJECT_NOT_FOUND\n')
                t=tkinter.Tcl(); t.setvar('Mode',mode)
                t.setvar('env(TPU_OBJECT_CASE)',directory)
                for key in ('TPU_STDCELL_DB','TPU_SRAM_DB','TPU_POWER_DDC','TPU_OBJECT_SAIF'):
                    t.setvar('env('+key+')',key)
                t.eval(r'''
proc exit {code} {set ::TestExit $code; error TEST_EXIT}
proc read_ddc {args} {}
proc current_design {args} {}
proc link {} {return 1}
proc all_clocks {} {return CoreClock}
proc get_object_name {object} {return $object}
proc sizeof_collection {items} {return [llength $items]}
proc foreach_in_collection {var items body} {
    upvar 1 $var item
    foreach item $items {uplevel 1 $body}
}
proc get_cells {args} {
    if {[lsearch -exact $args -filter]>=0} {
        if {$::Mode eq "bad_macros"} {return [lrepeat 55 RAM]}
        return [lrepeat 56 RAM]
    }
    set index [lsearch -exact $args -of_objects]
    if {$index>=0} {return [lindex [split [lindex $args [expr {$index+1}]] /] 0]}
    return {FF GATE}
}
proc get_nets {args} {
    set index [lsearch -exact $args -of_objects]
    if {$index>=0} {return top_result}
    return {{signal[0]} floating top_result}
}
proc get_ports {args} {return {result_port}}
proc get_pins {args} {
    set index [lsearch -exact $args -of_objects]
    if {$index>=0} {
        switch -- [lindex $args [expr {$index+1}]] {
            {signal[0]} {return {FF/Q GATE/A}}
            floating {return FF/Q}
            top_result {return FF/Q}
        }
    }
    return {FF/Q GATE/A}
}
proc get_attribute {args} {
    set object [lindex $args end-1]; set attribute [lindex $args end]
    switch -- $attribute {
        period {return 6.666667}
        direction {
            if {$object eq "GATE/A"} {return in}
            return out
        }
        ref_name {
            if {$object eq "FF"} {return DQV0_12TR40}
            return AND2V0_12TR40
        }
        is_hierarchical {return false}
        constant_value {return {}}
        switching_activity {return {0.1 0.5 read_saif}}
    }
    error "Unexpected attribute $attribute"
}
proc reset_switching_activity {args} {set ::Cleared 1}
proc read_saif {args} {
    if {![info exists ::Cleared]} {error "Old activity retained"}
    if {$::Mode eq "bad_saif"} {return 0}
    return 1
}
proc report_saif {args} {return COVERAGE}
proc report_activity {args} {error "Optional detail unavailable"}
proc list_attributes {args} {return ATTRIBUTES}
proc redirect {path body} {
    set value [uplevel 1 $body]
    set file [open $path w]; puts $file $value; close $file
}
''')
                original=Path.cwd()
                try:
                    with self.assertRaises(tkinter.TclError):
                        t.call('source',str(Path(__file__).with_name('AuditActivityObjects.tcl').resolve()))
                    self.assertEqual(int(t.getvar('TestExit')),expected)
                    if mode=='pass':
                        with (root/'object_connections.tsv').open() as handle:
                            rows=list(csv.DictReader(handle,delimiter='\t'))
                        self.assertEqual(rows[0]['input_pins'],'1')
                        self.assertEqual(rows[1]['top_ports'],'0')
                        self.assertEqual(rows[2]['top_ports'],'1')
                        self.assertEqual(rows[3]['status'],'ABSENT_FROM_DDC_INDEX')
                        self.assertTrue((root/'activity_detail.rpt.error.txt').exists())
                    else: self.assertFalse((root/'object_connections.tsv').exists())
                finally: os.chdir(original)


if __name__=='__main__': unittest.main()
