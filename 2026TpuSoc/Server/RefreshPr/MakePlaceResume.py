"""Freeze recovery from saved PG after native PLACE-042 (no scan DEF)."""
import base64
import hashlib
import io
from pathlib import Path
import tarfile
from MakeFullResume import patched_stage

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def replace_once(text,old,new):
    if text.count(old)!=1: raise ValueError('Recovery source protocol changed: '+old[:70])
    return text.replace(old,new)


def runner():
    text=(HERE/'ResumeFull.py').read_text()
    helper='''
def saved_pg(soc, original_source):
    good=[]
    for p in soc.glob('tpusoc_full_pr_recovery_20261109_*'):
        if not (p/'RecoveryFailure.json').is_file(): continue
        failure=json.loads((p/'RecoveryFailure.json').read_text())
        if failure.get('failed_phase')!='03_place': continue
        progress=json.loads((p/'RecoveryProgress.json').read_text())
        pg=p/'stages/02_pg/system_1109.nlib'
        if Path(failure['last_successful_library'])!=pg: continue
        if not any(s['phase']=='02_pg' and s['complete'] for s in progress['stages']): continue
        place_log=(p/'stages/03_place/icc2.log').read_text(errors='replace')
        if 'PLACE-042' not in place_log or 'No valid scan def found' not in place_log: continue
        inputs=json.loads((p/'RecoveryInputs.json').read_text())
        if Path(inputs['source'])!=original_source: continue
        verify(inputs['original_files']); verify(inputs['tools'])
        for name,fp in inputs['library_snapshots'].items():
            if tree(Path(name))!=fp: raise ValueError('Original PG recovery library changed: '+name)
        good.append((p,pg))
    if len(good)!=1: raise ValueError('Expected one saved PG checkpoint after confirmed PLACE-042')
    return good[0]

'''
    text=replace_once(text,'def main(out):',helper+'def main(out):')
    text=replace_once(text,"PHASES = [('02_pg',2400),('03_place',3600),('04_cts',3600),", "PHASES = [('03_place',3600),('04_cts',3600),")
    text=replace_once(text,"    first = source/'stages/01_rc/system_1109.nlib'\n    if Path(failure['last_successful_library']) != first:\n        raise ValueError('Unexpected original last successful checkpoint')", "    pg_source, first = saved_pg(Path.home()/'soc',source)")
    text=replace_once(text,"if 'FULL_PR_PHASE_COMPLETE: 01_rc' not in rc_log:","if 'FULL_PR_PHASE_COMPLETE: 02_pg' not in rc_log:")
    text=replace_once(text,"raise ValueError('Missing native RC completion evidence')","raise ValueError('Missing native saved PG completion evidence')")
    text=replace_once(text,"    snapshots = {str(first):tree(first)}", "    for n in ('RecoveryInputs.json','RecoveryProgress.json','RecoveryFailure.json','stages/02_pg/icc2.log','stages/03_place/icc2.log'):\n        original[str(pg_source/n)] = sha(pg_source/n)\n    snapshots = {str(first):tree(first)}")
    text=replace_once(text,"'changes':['check_std_cell_pins all','save core checkpoint before reports',", "'pg_source':str(pg_source),'changes':['installed no-scan placement option','check_std_cell_pins all','save core checkpoint before reports',")
    text=replace_once(text,"print('REUSE_RC_CHECKPOINT:',first,flush=True)","print('REUSE_PG_CHECKPOINT:',first,flush=True)")
    text=replace_once(text,"print('NO_DC_OR_POWER_RERUN; PG rebuilt from saved RC; original failed PG remains untouched',flush=True)", "print('NO_DC_POWER_RC_OR_PG_RERUN; saved PG copied; original runs untouched',flush=True)")
    return text.encode()


def stage():
    text=patched_stage().decode()
    old='''        03_place {
            PrNeed place_opt {};PrNeed legalize_placement {}'''
    new='''        03_place {
            # Functional implementation, without inventing a scan chain or scan DEF.
            # Require the installed option; never silently ignore an unsupported setting.
            PrNeed get_app_options {}
            PrNeed set_app_options {-name -value}
            set ScanOption place.coarse.continue_on_missing_scandef
            set Available [get_app_options $ScanOption]
            if {[lsearch -exact $Available $ScanOption]<0} {
                error "Installed no-scan placement option unavailable: $ScanOption"
            }
            PrStep functional_no_scan [list set_app_options -name $ScanOption -value true]
            PrRecord SCAN_SCOPE FUNCTIONAL_IMPLEMENTATION_NO_SCAN_DEF_NO_DFT_CLAIM
            PrNeed place_opt {};PrNeed legalize_placement {}'''
    return replace_once(text,old,new).encode()


def main():
    files={'tools/PlaceResume.py':runner(),'tools/ResumeStage.tcl':stage()}
    for n in ('FullRun.py','PgCheck.tcl'):files['tools/'+n]=(HERE/n).read_bytes()
    files['tools/PrCommon.tcl']=(ROOT/'Server/FinalBackend/PrCommon.tcl').read_bytes()
    files['tools/StageWatch.py']=(ROOT/'Server/SystemBackend/StageWatch.py').read_bytes()
    files['PACKAGE.sha256']=''.join(hashlib.sha256(b).hexdigest()+'  '+n+'\n' for n,b in sorted(files.items())).encode()
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w:gz') as tar:
        for n,b in sorted(files.items()):
            m=tarfile.TarInfo(n);m.size=len(b);m.mtime=1704067200;tar.addfile(m,io.BytesIO(b))
    data=buffer.getvalue()
    shell='''#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$HOME/soc"
work=$(mktemp -d "$HOME/soc/tpusoc_place_resume_20261109_XXXXXX")
echo "WORK_DIR: $work"
base64 -d > "$work/payload.tar.gz" <<'PLACE_PAYLOAD'
'''+base64.encodebytes(data).decode()+'''PLACE_PAYLOAD
echo "'''+hashlib.sha256(data).hexdigest()+'''  $work/payload.tar.gz" | sha256sum -c -
tar -xzf "$work/payload.tar.gz" -C "$work"
cd "$work"
sha256sum --quiet -c PACKAGE.sha256
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; echo "PLACE_RESUME_EXIT: $rc"; echo "WORK_DIR: $work"' EXIT
export PYTHONDONTWRITEBYTECODE=1
python3 -u "$work/tools/PlaceResume.py" "$work"
'''
    path=ROOT/'workspace/Server/tpusoc_place_resume_20261109_v1.sh'
    if path.exists(): raise ValueError('Refusing to overwrite frozen placement recovery')
    path.write_bytes(shell.encode())
    print(path.name,path.stat().st_size,hashlib.sha256(path.read_bytes()).hexdigest())


if __name__=='__main__':main()
