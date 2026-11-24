"""Installed option semantics and explicit fresh-session automatic strategy."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'SharedAsic'))
from AutoMappedPower import manual_sections,prepare,finish_power
from TestNativeMappedPower import NativePowerTests
from Prepare import sha


class AutoPowerTests(unittest.TestCase):
    def test_manual_definition_sections_are_not_confused_with_option_synopsis(self):
        text='SYNTAX\n [-map_names]\n [-auto_map_names]\nARGUMENTS\n    -map_names\n        Read the saved mapping.\n    -auto_map_names\n        Automatically match changed names.\n    -verbose\n        Verbose output.\n'
        sections=manual_sections(text)
        self.assertEqual(len(sections),2)
        self.assertIn('Read the saved mapping.',sections[0]['text'])
        self.assertIn('Automatically match changed names.',sections[1]['text'])
        self.assertNotIn('-verbose',sections[1]['text'])

    def test_automatic_preparation_retains_old_files_and_sets_distinct_strategy(self):
        with tempfile.TemporaryDirectory() as directory,contextlib.redirect_stdout(io.StringIO()):
            source,out,tools,base,sdc=NativePowerTests().fixture(Path(directory))
            before={p:p.read_bytes() for p in source.rglob('*') if p.is_file()}
            prepare(source,out,tools)
            record=json.loads((out/'Inputs.json').read_text())
            self.assertIn('explicitly NOT loaded',record['mapping'])
            self.assertTrue(record['require_active_mapping'])
            self.assertEqual(record['inputs'][str(out/'InstalledAnnotationSemantics.json')],sha(out/'InstalledAnnotationSemantics.json'))
            for path,data in before.items(): self.assertEqual(path.read_bytes(),data)
            (out/'ff1/tool_status.txt').write_text('MAPPING_MODE: INSTALLED_READ_SAIF_AUTO_MAP_NAMES\nEXTERNAL_NAME_MAP: RETAINED_NOT_SOURCED_IN_FIRST_ESTIMATE\n')
            with self.assertRaisesRegex(ValueError,'Mapping lifecycle completion evidence missing'):
                finish_power(out,expected_mode='INSTALLED_READ_SAIF_AUTO_MAP_NAMES',
                    expected_external='RETAINED_NOT_SOURCED_IN_FIRST_ESTIMATE')


if __name__=='__main__': unittest.main()
