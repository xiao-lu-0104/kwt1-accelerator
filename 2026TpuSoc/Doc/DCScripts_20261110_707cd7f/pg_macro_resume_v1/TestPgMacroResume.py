"""Macro-only recovery orchestration with fake tools, never native PG proof."""
import json
from pathlib import Path
import shutil
import unittest
from BuildPgMacroResume import build_files
from TestPg import Pg
from TestPgResume import prepare as diagnostic_fixture


def prepare(test,source,out,soc,mode):
    diagnostic_fixture(test,source,out,soc,'ok')
    sha=test.module.sha;tree=test.module.tree
    diag=soc/'tpusoc_macro_diag_20261110_707cd7f_good'
    prior=soc/'tpusoc_pg_resume_20261110_707cd7f_saved';prior.mkdir()
    (prior/'tool').write_text('FROZEN_RAILS_PACKAGE')
    (prior/'PACKAGE.sha256').write_text(sha(prior/'tool')+'  tool\n')
    core=prior/'pg_core';core.mkdir();shutil.copytree(diag/'diagnostic.nlib',core/'system_707cd7f.nlib')
    (core/'system_707cd7f.nlib/design.dat').write_text('SAVED_RING_MESH_RAILS')
    for n in ('ring.def','mesh42.def','rails.def'):(core/n).write_text('SAVED_DEF '+n)
    (core/'pg_core.log').write_text('CHECKPOINT_SAVED rails\nPGR-002\nFail to create macro connection pattern MACRO707_M5')
    audit=prior/'audit_baseline';audit.mkdir()
    for n in ('BaselineLeaves.tsv','BaselineMacros.tsv','SourceMacroBoxes.tsv'):(audit/n).write_text('NATIVE_AUDIT_FIXTURE')
    shutil.copy2(source/'design/PortTerminalGeometry.tsv',audit/'PortTerminalGeometry.tsv')
    (prior/'BaselineAuditOutputs.json').write_text(json.dumps({n:sha(audit/n) for n in ('BaselineLeaves.tsv','BaselineMacros.tsv','SourceMacroBoxes.tsv')}))
    (prior/'PgProgress.json').write_text(json.dumps({'stages':[{'phase':'audit_baseline','complete':True}]}))
    refs={str(source/('library_'+label)/(label+'.ndm')):tree(source/('library_'+label)/(label+'.ndm')) for label in ('rvt','private','shared')}
    (prior/'PgInputs.json').write_text(json.dumps({'source_run':str(source),'source_commit':test.module.REV,
        'recovered_diagnostic':str(diag),'source_design_snapshot':tree(source/'design/system_707cd7f.nlib'),
        'recovered_library_snapshot':tree(diag/'diagnostic.nlib'),'source_reference_snapshots':refs,'original_files':{}}))
    cfg=json.loads((out/'Config.json').read_text());cfg['rails_manifest_sha256']=sha(prior/'PACKAGE.sha256');(out/'Config.json').write_text(json.dumps(cfg))
    if mode=='bad_audit':(audit/'BaselineLeaves.tsv').write_text('CHANGED')
    if mode=='missing_rails':(core/'rails.def').unlink()
    if mode=='bad_manifest':(prior/'tool').write_text('CHANGED')
    if mode=='prior':
        p=soc/'tpusoc_pg_macro_resume_20261110_707cd7f_existing';p.mkdir()
        (p/'PgInputs.json').write_text(json.dumps({'recovered_rails_run':str(prior)}))


def fake_transform(text):
    text=text.replace("lib=p/'system_707cd7f.nlib';(lib/'design.dat').write_text('NEW_COPY_'+phase)",
        "lib=p/'system_707cd7f.nlib'\n"
        "assert phase in ('pg_core','connectivity','drc'),'Completed stage rerun'\n"
        "if phase=='pg_core':assert (lib/'design.dat').read_text()=='SAVED_RING_MESH_RAILS','Wrong recovery checkpoint'\n"
        "(lib/'design.dat').write_text('NEW_COPY_'+phase)")
    return text


class MacroResume(Pg):
    def case(self,mode='ok'):
        # The generic old bad_io fixture expects no pg_core directory. Here IO is checked
        # within the sole pg_core copy, so test that guard with the actual Tcl suite.
        return super().case(mode,files_builder=build_files,prepare_hook=prepare,fake_transform=fake_transform)

    test_bad_io_stops_before_pg=None  # Covered by actual generated Tcl mock.
    def test_prior_attempt_requires_checkpoint_review(self):
        c,s=self.case('prior');self.assertNotEqual(c,0,s);self.assertIn('A recovery attempt already exists',s)
    def test_audit_tamper_rejected(self):
        c,s=self.case('bad_audit');self.assertNotEqual(c,0,s);self.assertIn('Input changed',s)
    def test_missing_saved_rails_rejected(self):
        c,s=self.case('missing_rails');self.assertNotEqual(c,0,s);self.assertIn('Missing saved checkpoint rails.def',s)
    def test_frozen_tool_tamper_rejected(self):
        c,s=self.case('bad_manifest');self.assertNotEqual(c,0,s);self.assertIn('changed',s.lower())


if __name__=='__main__':unittest.main(defaultTest='MacroResume')
