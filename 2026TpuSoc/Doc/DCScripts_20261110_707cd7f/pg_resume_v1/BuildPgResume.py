"""Recover actual PG from the diagnosed legalized checkpoint, without re-legalizing."""
import base64
import io
import json
import tarfile
from BuildPr import HERE,ROOT,sha


def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Expected one frozen insertion: '+old[:100])
    return text.replace(old,new,1)


def build_files():
    frozen=ROOT/'Doc/DCScripts_20261110_707cd7f/pg_v1'
    files={}
    for line in (frozen/'PACKAGE.sha256').read_text().splitlines():
        digest,name=line.split('  ',1);data=(frozen/name).read_bytes()
        if sha(data)!=digest:raise ValueError('Original frozen PG tool changed: '+name)
        files[name]=data
    stage=files['tools/PgStage.tcl'].decode()
    begin=stage.index('proc PgMacroSignature {} {');end=stage.index('proc PgLeafSignature {} {')
    stage=stage[:begin]+(HERE/'PgPhysical.tcl').read_text()+ '\n'+stage[end:]
    stage=stage.replace('MACRO_REF_BBOX','MACRO_PHYSICAL_IDENTITY')
    stage=once(stage,'        if {![dict exists $After $N] || [dict get $After $N] ne $V} {error "$Kind changed: $N"}',
        '''        if {![dict exists $After $N] || [dict get $After $N] ne $V} {
            PrRecord IDENTITY_DIFF_BEFORE "$Kind $N $V"
            if {[dict exists $After $N]} {PrRecord IDENTITY_DIFF_AFTER "$Kind $N [dict get $After $N]"}
            error "$Kind changed: $N"
        }''')
    point='    PrStep fix_macros [list set_fixed_objects $Macros]'
    stage=once(stage,point,'''    if {$Phase eq "pg_core"} {
        PgSame [PgReadSignature $BaselineLeaves] $BeforeLeaves SOURCE_LOGICAL_MAP
        PgSame [PgReadSignature $BaselineMacros] $BeforeMacros SOURCE_MACRO_PHYSICAL_IDENTITY
        set SourcePhysicalBoxes [PgReadBoxes $BaselineBoxes]
        PgCheckSourceIo $BaselineIo
        PrRecord RECOVERY_BASELINE_MATCH LOGICAL_LEAVES_AND_MACRO_PHYSICAL_IDENTITY
    }
'''+point+'\n    PgRequireFixed $Macros')
    a=stage.index('        legalize {');b=stage.index('        pg_core {',a)
    stage=stage[:a]+'''        audit_baseline {
            PgWriteSignature BaselineLeaves.tsv $BeforeLeaves
            PgWriteSignature BaselineMacros.tsv $BeforeMacros
            set F [open SourceMacroBoxes.tsv w]
            puts $F "instance\\tx1\\ty1\\tx2\\ty2"
            foreach_in_collection C $Macros {puts $F "[get_object_name $C]\\t[join [IoBox $C] \\t]"}
            close $F
            PgSave baseline_audited
        }
'''+stage[b:]
    stage=once(stage,'                lassign [IoBox $C] X1 Y1 X2 Y2',
        '                # Original no-keepout bbox: do not add the same halo twice.\n'
        '                lassign [dict get $SourcePhysicalBoxes [get_object_name $C]] X1 Y1 X2 Y2')
    stage=once(stage,'    PgExportIo','    PgRequireFixed $Macros\n    PgExportIo')
    files['tools/PgStage.tcl']=stage.encode()
    flow=files['tools/PgFlow.py'].decode()
    flow=once(flow,'from SystemFlow import REV, verify_manifest','from SystemFlow import REV, verify_manifest\nfrom PgResumeInputs import select_recovered')
    flow=once(flow,"    source,summary=choose_source(Path.home()/'soc',cfg['initial_package_sha256'])",
        "    source,summary=choose_source(Path.home()/'soc',cfg['initial_package_sha256'])\n"
        "    recovery=select_recovered(Path.home()/'soc',source,cfg)\n"
        "    print('RECOVERED_LEGALIZED_DIAGNOSTIC:',recovery['diagnostic'],flush=True)")
    a=flow.index('    for prior in ');b=flow.index('    inputs=json.loads',a)
    flow=flow[:a]+'''    for prior in (Path.home()/'soc').glob('tpusoc_pg_resume_20261110_707cd7f_*/PgInputs.json'):
        if prior.parent.resolve()!=out.resolve() and json.loads(prior.read_text()).get('recovered_diagnostic')==recovery['diagnostic']:
            raise ValueError('A recovery attempt already exists; review its checkpoint: '+str(prior.parent))
'''+flow[b:]
    flow=once(flow,"    originals=dict(inputs['inputs'])","    originals=dict(inputs['inputs'])\n    originals.update(recovery['files'])")
    flow=once(flow,"            'input_netlist_sha256':summary['design_netlist_sha256']}",
        "            'input_netlist_sha256':summary['design_netlist_sha256'],\n"
        "            'recovered_diagnostic':recovery['diagnostic'],'recovered_library_snapshot':recovery['snapshot'],\n"
        "            'resume_scope':'audit original library, then recovered PG; no legalize rerun'}")
    flow=once(flow,"        (directory/'PgConfig.tcl').write_text(text)",'''        if kind=='pg_core':
            audit=out/'audit_baseline'
            text+=''.join(scalar(k,v) for k,v in [('BaselineLeaves',audit/'BaselineLeaves.tsv'),
                ('BaselineMacros',audit/'BaselineMacros.tsv'),('BaselineBoxes',audit/'SourceMacroBoxes.tsv'),
                ('BaselineIo',audit/'PortTerminalGeometry.tsv')])
        (directory/'PgConfig.tcl').write_text(text)''')
    flow=once(flow,"if kind in ('legalize','pg_core'):","if kind in ('audit_baseline','pg_core'):")
    flow=once(flow,"for kind,tag in [('legalize','legalized'),('pg_core','pg_complete')]:",
        "for kind,tag in [('audit_baseline','baseline_audited'),('pg_core','pg_complete')]:")
    flow=once(flow,"        directory,lib,log=stage(kind,previous,'PgStage.tcl',3600)",
        "        input_lib=Path(recovery['library']) if kind=='pg_core' else previous\n"
        "        directory,lib,log=stage(kind,input_lib,'PgStage.tcl',1200 if kind=='audit_baseline' else 3600)")
    flow=once(flow,'        io=validate_io(directory)',"""        io=validate_io(directory)
        if kind=='audit_baseline':
            for n in ('BaselineLeaves.tsv','BaselineMacros.tsv','SourceMacroBoxes.tsv'):
                p=directory/n
                if not p.is_file() or p.stat().st_size==0:raise ValueError('Missing independent source audit: '+n)
                originals[str(p)]=sha(p)
            save(out/'BaselineAuditOutputs.json',{n:sha(directory/n) for n in ('BaselineLeaves.tsv','BaselineMacros.tsv','SourceMacroBoxes.tsv')})""")
    flow=once(flow,"    if tree(original_lib)!=original_snapshot:raise ValueError('Original new placement library changed')",
        "    if tree(original_lib)!=original_snapshot:raise ValueError('Original new placement library changed')\n"
        "    if tree(Path(recovery['library']))!=recovery['snapshot']:raise ValueError('Saved diagnostic library changed')")
    files['tools/PgFlow.py']=flow.encode()
    files['tools/PgResumeInputs.py']=(HERE/'PgResumeInputs.py').read_bytes().replace(b'\r\n',b'\n')
    files['tools/MacroDiag.py']=(ROOT/'Doc/DCScripts_20261110_707cd7f/macro_diag_v1/tools/MacroDiag.py').read_bytes()
    cfg=json.loads(files['Config.json'].decode())
    cfg.update(failed_pg_manifest_sha256=sha((frozen/'PACKAGE.sha256').read_bytes()),
        diagnostic_manifest_sha256=sha((ROOT/'Doc/DCScripts_20261110_707cd7f/macro_diag_v1/PACKAGE.sha256').read_bytes()),
        scope='independent initial-library audit and saved legalize diagnostic qualification, then actual PG/checks; no legalization rerun')
    files['Config.json']=(json.dumps(cfg,indent=2)+'\n').encode()
    return files


def main():
    files=build_files();files['PACKAGE.sha256']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(files.items())).encode();buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode='w:gz') as z:
        for n,b in sorted(files.items()):
            t=tarfile.TarInfo(n);t.size=len(b);t.mode=0o644;t.mtime=1704067200;z.addfile(t,io.BytesIO(b))
    data=buf.getvalue()
    entry='''#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$HOME/soc"
work=$(mktemp -d "$HOME/soc/tpusoc_pg_resume_20261110_707cd7f_XXXXXX")
echo "WORK_DIR: $work"
base64 -d > "$work/payload.tar.gz" <<'PG_RESUME_707CD7F'
'''+base64.encodebytes(data).decode()+'''PG_RESUME_707CD7F
echo "'''+sha(data)+'''  $work/payload.tar.gz" | sha256sum -c -
tar -xzf "$work/payload.tar.gz" -C "$work"
cd "$work"
sha256sum --quiet -c PACKAGE.sha256
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; echo "PG_RESUME_EXIT: $rc"; echo "WORK_DIR: $work"' EXIT
export PYTHONDONTWRITEBYTECODE=1
python3 -u tools/PgFlow.py "$work"
sha256sum --quiet -c PACKAGE.sha256
'''
    name='tpusoc_pg_resume_20261110_707cd7f_v1.sh';p=ROOT/'workspace/Server'/name
    with p.open('xb') as f:f.write(entry.encode())
    digest=sha(p.read_bytes())
    command=(HERE/'NormalizePgCommand.txt').read_text().replace('tpusoc_pg_20261110_707cd7f_v1.sh',name)
    command=command.replace('tpusoc_pg_20261110_707cd7f_verified.sh','tpusoc_pg_resume_20261110_707cd7f_verified.sh').replace('d15bbe174d9563451a68b3d16a4ea668de29452e8cb4b353935fb15cb142dceb',digest)
    (HERE/'NormalizePgResumeCommand.txt').write_text(command)
    helper=(HERE/'CopyPgToClipboard.ps1').read_text().replace('tpusoc_pg_20261110_707cd7f_v1.sh',name)
    helper=helper.replace('d15bbe174d9563451a68b3d16a4ea668de29452e8cb4b353935fb15cb142dceb',digest).replace('NormalizePgCommand.txt','NormalizePgResumeCommand.txt')
    (HERE/'CopyPgResumeToClipboard.ps1').write_text(helper)
    print(name,len(entry.encode()),digest)


if __name__=='__main__':main()
