"""Read-only qualification of the saved rails checkpoint after native PGR-002."""
import json
from pathlib import Path
from PrHelpers import sha,tree,verify
from SystemFlow import REV,verify_manifest
from PgResumeInputs import select_recovered


def select_rails(soc,source,cfg):
    diagnostic=select_recovered(soc,source,cfg)
    choices=[]
    for f in soc.glob('tpusoc_pg_resume_20261110_707cd7f_*/PgInputs.json'):
        p=f.parent;record=json.loads(f.read_text());log=p/'pg_core/pg_core.log'
        if record.get('source_run')!=str(source) or record.get('source_commit')!=REV:continue
        if not log.is_file():continue
        text=log.read_text()
        if 'CHECKPOINT_SAVED rails' not in text or 'PGR-002' not in text or 'Fail to create macro connection pattern MACRO707_M5' not in text:continue
        verify_manifest(p,'PACKAGE.sha256',cfg['rails_manifest_sha256'])
        verify(record['original_files'])
        if record.get('recovered_diagnostic')!=diagnostic['diagnostic']:raise ValueError('Rails diagnostic source differs')
        if tree(source/'design/system_707cd7f.nlib')!=record['source_design_snapshot']:raise ValueError('Initial library changed')
        if tree(Path(diagnostic['library']))!=record['recovered_library_snapshot']:raise ValueError('Diagnostic library changed')
        for name,h in record['source_reference_snapshots'].items():
            if tree(Path(name))!=h:raise ValueError('Source reference changed')
        progress=json.loads((p/'PgProgress.json').read_text())['stages']
        if len(progress)!=1 or progress[0]['phase']!='audit_baseline' or progress[0]['complete'] is not True:raise ValueError('Unexpected saved audit progress')
        audit=json.loads((p/'BaselineAuditOutputs.json').read_text())
        if set(audit)!={'BaselineLeaves.tsv','BaselineMacros.tsv','SourceMacroBoxes.tsv'}:raise ValueError('Incomplete independent audit')
        verify({str(p/'audit_baseline'/n):h for n,h in audit.items()})
        for n in ('ring.def','mesh42.def','rails.def'):
            q=p/'pg_core'/n
            if not q.is_file() or q.stat().st_size==0:raise ValueError('Missing saved checkpoint '+n)
        if (p/'pg_core/pg_complete.def').exists():raise ValueError('Unexpected completed macro checkpoint')
        lib=p/'pg_core/system_707cd7f.nlib';snapshot=tree(lib)
        files=dict(diagnostic['files']);files.update(record['original_files'])
        for n in ('PgInputs.json','PgProgress.json','BaselineAuditOutputs.json','PACKAGE.sha256','pg_core/pg_core.log',
                  'pg_core/ring.def','pg_core/mesh42.def','pg_core/rails.def','audit_baseline/PortTerminalGeometry.tsv',
                  'audit_baseline/BaselineLeaves.tsv','audit_baseline/BaselineMacros.tsv','audit_baseline/SourceMacroBoxes.tsv'):
            files[str(p/n)]=sha(p/n)
        choices.append({'diagnostic':diagnostic['diagnostic'],'library':str(lib),'snapshot':snapshot,
                        'rails_run':str(p),'audit':str(p/'audit_baseline'),'files':files})
    if len(choices)!=1:raise ValueError('Expected exactly one qualified saved rails checkpoint')
    return choices[0]
