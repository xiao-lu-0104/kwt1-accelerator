"""Verify current design selection and bounded read-only RC mapping inventory."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'FinalBackend'))
from PrepareBackend import choose,map_inventory


class Tests(unittest.TestCase):
    def test_only_successful_current_system_selected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);old=root/'tpusoc_icc2_coarse_20261108_old';old.mkdir()
            good=root/'tpusoc_system_pr_resume_20261109_current';good.mkdir()
            value={'result':'NEW_1109_SYSTEM_INITIAL_PLACEMENT_COMPLETE_REVIEW_PENDING','original_inputs_unchanged':True}
            for p in (old,good):(p/'NewPrSummary.json').write_text(json.dumps(value))
            self.assertEqual(choose(root)[0],good)
            value['original_inputs_unchanged']=False;(good/'NewPrSummary.json').write_text(json.dumps(value))
            with self.assertRaises(ValueError):choose(root)

    def test_ambiguous_current_success_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in ('one','two'):
                p=root/('tpusoc_system_pr_resume_20261109_'+name);p.mkdir()
                (p/'NewPrSummary.json').write_text(json.dumps({'result':'NEW_1109_SYSTEM_INITIAL_PLACEMENT_COMPLETE_REVIEW_PENDING','original_inputs_unchanged':True}))
            with self.assertRaises(ValueError):choose(root)

    def test_mapping_scan_preserves_source_and_excludes_ndm(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);mapping=root/'tech2itf.map';data=b'# actual mapping\nM1 metal1\n';mapping.write_bytes(data)
            (root/'library.ndm').mkdir();(root/'library.ndm/ignore.map').write_text('not a PDK map')
            result=map_inventory(root)
            self.assertFalse(result['truncated']);self.assertEqual(len(result['candidates']),1)
            self.assertEqual(result['candidates'][0]['preview'],data.decode());self.assertEqual(mapping.read_bytes(),data)
            self.assertTrue(map_inventory(root,max_files=0)['truncated'])


if __name__=='__main__':unittest.main()
