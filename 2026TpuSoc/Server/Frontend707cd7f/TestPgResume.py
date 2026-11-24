import csv
import json
from pathlib import Path
import shutil
import unittest
from BuildPgResume import build_files
from MacroDiag import summarize
from TestPg import Pg


def prepare(test,source,out,soc,mode):
    sha=test.module.sha
    failed=soc/'tpusoc_pg_20261110_707cd7f_failed';failed.mkdir()
    (failed/'legalize').mkdir();(failed/'legalize/legalize.log').write_text('Legalization succeeded\nMACRO_REF_BBOX changed: M0')
    (failed/'tool.txt').write_text('OLD_PG_TOOL');(failed/'PACKAGE.sha256').write_text(sha(failed/'tool.txt')+'  tool.txt\n')
    (failed/'PgInputs.json').write_text(json.dumps({'source_commit':test.module.REV,'source_run':str(source),
        'source_design_snapshot':test.module.tree(source/'design/system_707cd7f.nlib'),
        'original_files':{str(source/'inputs/candidate.v'):sha(source/'inputs/candidate.v')}}))
    diag=soc/'tpusoc_macro_diag_20261110_707cd7f_good';diag.mkdir()
    shutil.copytree(source/'design/system_707cd7f.nlib',diag/'diagnostic.nlib')
    (diag/'diagnostic.nlib/design.dat').write_text('ORIGINAL_GROUPED_IO_DESIGN_LEGALIZED')
    (diag/'diagnostic_only.def').write_text('SAVED_LEGALIZED_DIAGNOSTIC')
    (diag/'native.log').write_text('MACRO_DIAGNOSTIC_NATIVE_COMPLETE_NO_PG')
    macros=list(csv.DictReader((source/'design/macros.tsv').read_text().splitlines(),delimiter='\t'))
    for tag in ('opened','fixed','keepout','legalized'):
        rows=[]
        for m in macros:
            x1,y1,x2,y2=[float(m[k]) for k in ('x1','y1','x2','y2')]
            halo=1.12 if tag in ('keepout','legalized') else 0
            rows.append({'instance':m['instance'],'ref':m['ref'],'x1':x1-halo,'y1':y1-halo,'x2':x2+halo,'y2':y2+halo,
                'bbox_raw':str((x1-halo,y1-halo,x2+halo,y2+halo)), 'origin':str(x1)+' '+str(y1),'orientation':'R0',
                'is_fixed':'false' if tag=='opened' else 'true','physical_status':'placed' if tag=='opened' else 'fixed',
                'pg_pin_count':'3','pg_pin_signature':'VDDCE VDDPE VSSE'})
        if mode=='diag_motion' and tag=='legalized':rows[0]['origin']='99 99'
        with (diag/('macro_'+tag+'.tsv')).open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]),delimiter='\t');w.writeheader();w.writerows(rows)
    (diag/'MacroDiagSummary.json').write_text(json.dumps(summarize(diag)))
    if mode=='bad_diag':
        p=diag/'macro_legalized.tsv';p.write_text(p.read_text().replace('VDDCE VDDPE VSSE','CHANGED_PIN_SHAPE',1))
    (diag/'Config.json').write_text(json.dumps({'pg_manifest_sha256':sha(failed/'PACKAGE.sha256')}))
    (diag/'tool.txt').write_text('DIAGNOSTIC_TOOL')
    (diag/'PACKAGE.sha256').write_text(''.join(sha(diag/n)+'  '+n+'\n' for n in ('tool.txt','Config.json')))
    cfg=json.loads((out/'Config.json').read_text());cfg.update(failed_pg_manifest_sha256=sha(failed/'PACKAGE.sha256'),diagnostic_manifest_sha256=sha(diag/'PACKAGE.sha256'))
    (out/'Config.json').write_text(json.dumps(cfg))
    if mode=='prior':
        p=soc/'tpusoc_pg_resume_20261110_707cd7f_existing';p.mkdir();(p/'PgInputs.json').write_text(json.dumps({'recovered_diagnostic':str(diag)}))


def fake_transform(text):
    text=text.replace("lib=p/'system_707cd7f.nlib';(lib/'design.dat').write_text('NEW_COPY_'+phase)",
        "lib=p/'system_707cd7f.nlib'\n"
        "if phase=='legalize':raise RuntimeError('Unexpected legalization rerun')\n"
        "if phase=='pg_core':assert (lib/'design.dat').read_text()=='ORIGINAL_GROUPED_IO_DESIGN_LEGALIZED','Did not use saved diagnostic'\n"
        "(lib/'design.dat').write_text('NEW_COPY_'+phase)")
    text=text.replace("if phase in ('legalize','pg_core'):","if phase in ('audit_baseline','pg_core'):")
    text=text.replace("'legalized.def' if phase=='legalize' else 'pg_complete.def'","'baseline_audited.def' if phase=='audit_baseline' else 'pg_complete.def'")
    text=text.replace("    data=json.loads((p/'PinPlan.json').read_text());rows=", "    if phase=='audit_baseline':\n        for n in ('BaselineLeaves.tsv','BaselineMacros.tsv','SourceMacroBoxes.tsv'):(p/n).write_text('MOCK_INDEPENDENT_AUDIT')\n    data=json.loads((p/'PinPlan.json').read_text());rows=")
    return text


class Resume(Pg):
    def case(self,mode='ok'):
        return super().case(mode,files_builder=build_files,prepare_hook=prepare,fake_transform=fake_transform)

    def test_prior_attempt_requires_checkpoint_review(self):
        code,log=self.case('prior');self.assertNotEqual(code,0,log);self.assertIn('A recovery attempt already exists',log)

    def test_changed_diagnostic_evidence_cannot_be_promoted(self):
        code,log=self.case('bad_diag');self.assertNotEqual(code,0,log);self.assertIn('Diagnostic summary differs',log)

    def test_real_diagnostic_macro_motion_cannot_be_promoted(self):
        code,log=self.case('diag_motion');self.assertNotEqual(code,0,log);self.assertIn('real macro identity change',log)


if __name__=='__main__':unittest.main(defaultTest='Resume')
