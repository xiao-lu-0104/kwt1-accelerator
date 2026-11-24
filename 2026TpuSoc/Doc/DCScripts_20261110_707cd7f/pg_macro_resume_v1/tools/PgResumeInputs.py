"""Qualify the saved diagnostic library using independently recomputed evidence."""
import csv
import json
import math
from pathlib import Path
from MacroDiag import summarize
from PrHelpers import sha,tree,verify
from SystemFlow import REV,verify_manifest


def select_recovered(soc,source,cfg):
    failed=[]
    for f in soc.glob('tpusoc_pg_20261110_707cd7f_*/PgInputs.json'):
        d=json.loads(f.read_text());log=f.parent/'legalize/legalize.log'
        if d.get('source_commit')==REV and d.get('source_run')==str(source) and log.is_file() and 'MACRO_REF_BBOX changed:' in log.read_text():
            failed.append((f.parent,d))
    if len(failed)!=1:raise ValueError('Expected one original macro-bbox failed PG attempt')
    failure,record=failed[0];verify_manifest(failure,'PACKAGE.sha256',cfg['failed_pg_manifest_sha256'])
    verify(record['original_files'])
    if tree(source/'design/system_707cd7f.nlib')!=record['source_design_snapshot']:
        raise ValueError('Original successful placement library changed')
    choices=[]
    for f in soc.glob('tpusoc_macro_diag_20261110_707cd7f_*/MacroDiagSummary.json'):
        p=f.parent
        if not (p/'diagnostic.nlib').is_dir() or not (p/'diagnostic_only.def').is_file():continue
        verify_manifest(p,'PACKAGE.sha256',cfg['diagnostic_manifest_sha256'])
        if json.loads((p/'Config.json').read_text())['pg_manifest_sha256']!=cfg['failed_pg_manifest_sha256']:
            raise ValueError('Diagnostic targeted a different frozen PG flow')
        if 'MACRO_DIAGNOSTIC_NATIVE_COMPLETE_NO_PG' not in (p/'native.log').read_text():continue
        # Native JSON serializes state tuples as lists; compare the same canonical JSON representation.
        data=json.loads(json.dumps(summarize(p)))
        if data!=json.loads(f.read_text()):raise ValueError('Diagnostic summary differs from native TSV evidence')
        for tag in ('fixed','keepout','legalized'):
            state=data[tag]
            if any(state['counts'][k]!=0 for k in ('ref','origin_numeric','orientation','pg_pin_signature')):
                raise ValueError('Diagnostic indicates real macro identity change: '+tag)
            if any(state['unavailable'].values()) or state['incomplete_pg_pin_capture']:
                raise ValueError('Diagnostic physical identity is incomplete')
            if state['fixed_states']!=[['true','fixed']]:raise ValueError('Not all recovered macros are fixed')
        for name in ('macro_opened.tsv','macro_fixed.tsv','macro_keepout.tsv','macro_legalized.tsv'):
            for r in csv.DictReader((p/name).read_text().splitlines(),delimiter='\t'):
                values=[float(r[k]) for k in ('x1','y1','x2','y2')]+[float(v) for v in r['origin'].replace('{',' ').replace('}',' ').split()]
                if not all(math.isfinite(v) for v in values):raise ValueError('Invalid diagnostic coordinates')
        choices.append((p,data))
    if len(choices)!=1:raise ValueError('Expected exactly one qualified saved diagnostic')
    p,data=choices[0]
    files={str(p/n):sha(p/n) for n in ('PACKAGE.sha256','Config.json','MacroDiagSummary.json','native.log','diagnostic_only.def',
          'macro_opened.tsv','macro_fixed.tsv','macro_keepout.tsv','macro_legalized.tsv')}
    files[str(failure/'PgInputs.json')]=sha(failure/'PgInputs.json')
    files[str(failure/'PACKAGE.sha256')]=sha(failure/'PACKAGE.sha256')
    return {'diagnostic':str(p),'library':str(p/'diagnostic.nlib'),'snapshot':tree(p/'diagnostic.nlib'),
            'files':files,'summary':data,'failed_run':str(failure),
            'qualification':'physical identity stable; full logical map and IO must still match independent initial-library audit'}
