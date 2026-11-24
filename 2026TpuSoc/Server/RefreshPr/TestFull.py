"""Full-flow RC selection, error classification and real Tcl protocol tests."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from FullRun import layer_map,select_rc,sha,operational_errors,routed_nets
HERE=Path(__file__).resolve().parent


def mapping():
    a=['conducting_layers','GT npoly']+['M%d metal%d'%(i,i) for i in range(1,8)]+['TM2 metal8','ALPA alpa','via_layers','CT npolyCont']
    return '\n'.join(a+['V%d via%d'%(i,i) for i in range(1,7)]+['TV2 via7','PA viapa','marker_layers','remove_layers'])+'\n'


class Tests(unittest.TestCase):
    def test_unique_matching_rc_pair_and_actual_mapping(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);r=root/'StarRC_40LL_1P8M_1TM_TYP.tluplus';r.write_text('foundry fixture')
            m=root/'StarRC_40LL_1P8M_1TM_cell.map';m.write_text(mapping())
            value={'rc_candidates':[{'path':str(r),'sha256':sha(r)}],
                'map_inventory':{'truncated':False,'candidates':[{'path':str(m),'sha256':sha(m)}]}}
            self.assertEqual(select_rc(value)['mapping']['conducting_layers']['TM2'],'metal8')
            m.write_text(mapping().replace('TM2 metal8','M8 metal8'));value['map_inventory']['candidates'][0]['sha256']=sha(m)
            with self.assertRaises(ValueError):select_rc(value)
            value['map_inventory']['truncated']=True
            with self.assertRaises(ValueError):select_rc(value)

    def test_operational_errors_are_not_hidden_by_check_reporting(self):
        self.assertEqual(operational_errors('FULL_PR_CHECK_BEGIN: pg\nError: floating\nFULL_PR_CHECK_END: pg'),[])
        self.assertEqual(len(operational_errors('Error: route operation failed')),1)
        self.assertEqual(len(operational_errors('FULL_PR_CHECK_BEGIN: pg\nFatal: crashed')),1)

    def test_signal_route_evidence_excludes_pg_special_nets(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'r.def';p.write_text('SPECIALNETS 1 ;\n- VDD + ROUTED M7 ( 0 0 ) ;\nEND SPECIALNETS\nNETS 2 ;\n- signal + ROUTED M3 ( 0 0 ) ;\nEND NETS\n')
            self.assertEqual(routed_nets(p),1)

    @unittest.skipUnless(shutil.which('tclsh'),'Tcl runtime required')
    def test_actual_tcl_all_phases_and_failed_route(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for phase in ('01_rc','02_pg','03_place','04_cts','05_route','06_route_opt','07_export'):
                result=subprocess.run(['tclsh',str(HERE/'TestFullStage.tcl'),str(root/phase),phase],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
                self.assertEqual(result.returncode,0,result.stdout.decode())
                self.assertTrue((root/phase/'checkpoint.def').exists())
            failed=subprocess.run(['tclsh',str(HERE/'TestFullStage.tcl'),str(root/'bad'),'05_route','fail'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            self.assertEqual(failed.returncode,2)
            self.assertFalse((root/'bad/checkpoint.def').exists())


if __name__=='__main__':unittest.main()
