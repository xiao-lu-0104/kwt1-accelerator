"""Guard the link from server functional evidence to a fresh synthesis source set."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('shared_asic_verify', Path(__file__).with_name('Verify.py'))
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bundle = self.root / 'bundle'
        self.run = self.root / 'run'
        project = self.run / 'project'
        config = project / 'e203_hbirdv2/rtl/e203/core/config.v'
        config.parent.mkdir(parents=True)
        config.write_text('`define E203_CFG_ITCM_ADDR_WIDTH 18\n')
        scope = {'scope': 'COMPETITION_CPU_TCM_FUNCTIONAL', 'configuration_modified': False,
                 'cpu_datapath_modified': False,
                 'copied_platform_sha256': {'core/config.v': VERIFY.digest(config)}}
        (project / 'Scope.json').write_text(json.dumps(scope))
        files = [self.bundle / 'Rtl' / (name + '.sv') for name in VERIFY.RTL]
        files += [self.bundle / 'Backend/e203_subsys_nice_core.sv',
                  self.bundle / 'Server/Backend/SpFoundry.sv']
        for path in files:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('// fixture ' + path.name + '\n')
        (project / 'Files.f').write_text('\n'.join(str(path) for path in files[:-1]) + '\n')
        manifest = ''.join(VERIFY.digest(path) + '  ' + path.relative_to(self.bundle).as_posix()
                           + '\n' for path in files)
        (self.bundle / 'MANIFEST.sha256').write_text(manifest)
        self.sha = VERIFY.digest(self.bundle / 'MANIFEST.sha256')
        (self.run / 'runner.log').write_text('RESULT: PASS SHARED_FUNCTIONAL (17 tasks; fixture)\n')
        for name in ['normal', 'zero', 'extreme'] + [f'Layer{index}' for index in range(12)]:
            (self.run / ('ff1_' + name + '.log')).write_text(
                'PASS SHARED: kind=1 layers=1 values=25344 cycles=332348 '
                'DMA_read_bytes=45952 DMA_write_bytes=50688 loaded_bytes=45960\n')
        for name, layers in [('one', 1), ('twelve', 12)]:
            (self.run / ('encoder_' + name + '.log')).write_text(
                f'PASS SHARED: kind=0 layers={layers} values=6336 cycles=17501035 '
                f'DMA_read_bytes={12672 + 99584 * layers} DMA_write_bytes=12672 '
                f'loaded_bytes={12672 + 99592 * layers}\n')

    def test_success_uses_exact_functional_source_set(self):
        bundle, sources, scope = VERIFY.verify(self.run, self.sha)
        self.assertEqual(bundle, self.bundle)
        self.assertEqual(len(sources), 15)
        self.assertEqual(sources[-1].name, 'e203_subsys_nice_core.sv')
        self.assertFalse(scope['configuration_modified'])

    def test_refuses_changed_source_or_changed_manifest(self):
        source = self.bundle / 'Rtl/TpuIcb.sv'
        source.write_text('// changed after testing\n')
        with self.assertRaisesRegex(ValueError, 'Bundle changed'):
            VERIFY.verify(self.run, self.sha)
        manifest = self.bundle / 'MANIFEST.sha256'
        manifest.write_text(manifest.read_text().replace(VERIFY.RTL[0], 'Different'))
        with self.assertRaisesRegex(ValueError, 'reviewed shared_v1'):
            VERIFY.verify(self.run, self.sha)

    def test_refuses_changed_copied_platform(self):
        config = self.run / 'project/e203_hbirdv2/rtl/e203/core/config.v'
        config.write_text('`define E203_CFG_ITCM_ADDR_WIDTH 16\n')
        with self.assertRaisesRegex(ValueError, 'Copied platform changed'):
            VERIFY.verify(self.run, self.sha)

    def test_refuses_local_width_comparison(self):
        path = self.run / 'project/Scope.json'
        scope = json.loads(path.read_text())
        scope['scope'] = 'LOCAL_UPSTREAM_WIDTH_COMPARISON'
        scope['configuration_modified'] = True
        path.write_text(json.dumps(scope))
        with self.assertRaisesRegex(ValueError, 'competition-platform'):
            VERIFY.verify(self.run, self.sha)

    def test_refuses_missing_case_and_partial_ff1_writeback(self):
        log = self.run / 'ff1_Layer11.log'
        original = log.read_text()
        log.write_text(original.replace('50688', '512'))
        with self.assertRaisesRegex(ValueError, 'Unexpected counts'):
            VERIFY.verify(self.run, self.sha)
        log.write_text('simulation interrupted\n')
        with self.assertRaisesRegex(ValueError, 'Missing/ambiguous'):
            VERIFY.verify(self.run, self.sha)


if __name__ == '__main__':
    unittest.main()
