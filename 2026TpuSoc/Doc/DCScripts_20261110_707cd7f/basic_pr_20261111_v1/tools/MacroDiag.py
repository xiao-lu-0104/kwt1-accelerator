"""Diagnose macro identity changes on a fresh copy; never starts PG generation."""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent

PROCS=r'''
proc MdAttr {C A} {
    if {[catch {get_attribute $C $A} V]} {return UNAVAILABLE}
    return [string map [list "\t" " " "\n" " "] $V]
}
proc MdDump {Tag} {
    set F [open "macro_${Tag}.tsv" w]
    puts $F "instance\tref\tx1\ty1\tx2\ty2\tbbox_raw\torigin\torientation\tis_fixed\tphysical_status\tpg_pin_count\tpg_pin_signature"
    foreach_in_collection C $::Macros {
        set Sig {}
        foreach_in_collection P [get_pins -physical_context -of_objects $C] {
            set Name [lindex [split [get_object_name $P] /] end]
            if {$Name ni {VDDCE VDDPE VSSE}} {continue}
            set Values {}
            foreach V [IoBox $P] {lappend Values [format %.9f $V]}
            lappend Sig [list $Name $Values]
        }
        puts $F "[get_object_name $C]\t[get_attribute $C ref_name]\t[join [IoBox $C] \t]\t[MdAttr $C bbox]\t[MdAttr $C origin]\t[MdAttr $C orientation]\t[MdAttr $C is_fixed]\t[MdAttr $C physical_status]\t[llength $Sig]\t[lsort $Sig]"
    }
    close $F
    puts "MACRO_DIAG_CAPTURED: $Tag"
    flush stdout
}
'''


def native_script(old):
    boundary='    switch $Phase {'
    if old.count(boundary)!=1:raise ValueError('Unexpected frozen native stage')
    prefix=old.split(boundary,1)[0]
    point='    PrStep fix_macros [list set_fixed_objects $Macros]'
    if prefix.count(point)!=1:raise ValueError('Missing fixed-macro boundary')
    prefix=prefix.replace(point,'    MdDump opened\n'+point+'\n    MdDump fixed')
    return PROCS+'\n'+prefix+r'''
    PrNeed create_keepout_margin {-type -outer}
    PrNeed legalize_placement {}
    PrStep diagnostic_keepout [list create_keepout_margin -type hard -outer {1.12 1.12 1.12 1.12} $Macros]
    MdDump keepout
    PrStep diagnostic_legalize [list legalize_placement]
    MdDump legalized
    # Quarantined evidence only; never selected as an accepted PG source.
    PgSave diagnostic_only
    puts "MACRO_DIAGNOSTIC_NATIVE_COMPLETE_NO_PG"
} Why]} {
    puts stderr $::errorInfo
    exit 2
}
exit 0
'''


def summarize(directory):
    directory=Path(directory);states={}
    for tag in ('opened','fixed','keepout','legalized'):
        rows=list(csv.DictReader((directory/('macro_'+tag+'.tsv')).read_text().splitlines(),delimiter='\t'))
        states[tag]={r['instance']:r for r in rows}
    baseline=states['opened'];result={}
    for tag,rows in states.items():
        if set(rows)!=set(baseline) or len(rows)!=120:raise ValueError('Incomplete diagnostic macro coverage')
        fields={'bbox_numeric':[],'bbox_raw':[],'ref':[],'origin':[],'origin_numeric':[],'orientation':[],'pg_pin_signature':[]}
        for name,b in baseline.items():
            a=rows[name]
            if any(abs(float(a[k])-float(b[k]))>1e-7 for k in ('x1','y1','x2','y2')):fields['bbox_numeric'].append(name)
            for key in ('bbox_raw','ref','origin','orientation','pg_pin_signature'):
                if a[key]!=b[key]:fields[key].append(name)
            if 'UNAVAILABLE' not in (a['origin'],b['origin']):
                av=[float(v) for v in a['origin'].replace('{',' ').replace('}',' ').split()]
                bv=[float(v) for v in b['origin'].replace('{',' ').replace('}',' ').split()]
                if len(av)!=2 or len(bv)!=2 or any(abs(x-y)>1e-7 for x,y in zip(av,bv)):
                    fields['origin_numeric'].append(name)
        names=fields['bbox_numeric'] or fields['bbox_raw']
        samples=[{'instance':n,'before':baseline[n],'after':rows[n]} for n in names[:2]]
        result[tag]={'counts':{k:len(v) for k,v in fields.items()},
                     'unavailable':{k:sum(r[k]=='UNAVAILABLE' for r in rows.values()) for k in ('origin','orientation','is_fixed','physical_status')},
                     'incomplete_pg_pin_capture':sum(r.get('pg_pin_count')!='3' for r in rows.values()),
                     'fixed_states':sorted(set((r['is_fixed'],r['physical_status']) for r in rows.values())),
                     'samples':samples}
    return result


def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main(out):
    cfg=json.loads((out/'Config.json').read_text());soc=Path.home()/'soc';candidates=[]
    for p in soc.glob('tpusoc_pg_20261110_707cd7f_*/PgInputs.json'):
        log=p.parent/'legalize/legalize.log'
        if log.is_file() and 'MACRO_REF_BBOX changed:' in log.read_text() and 'Legalization succeeded' in log.read_text():candidates.append(p.parent)
    if len(candidates)!=1:raise ValueError('Expected one failed PG legalization to diagnose')
    failed=candidates[0];manifest=failed/'PACKAGE.sha256'
    if digest(manifest)!=cfg['pg_manifest_sha256']:raise ValueError('Failed package manifest changed')
    for line in manifest.read_text().splitlines():
        h,n=line.split('  ',1);p=(failed/n).resolve()
        if failed.resolve() not in p.parents or digest(p)!=h:raise ValueError('Frozen failed tool changed: '+n)
    sys.path.insert(0,str(failed/'tools'))
    from PrHelpers import tree,scalar,tlist,verify
    record=json.loads((failed/'PgInputs.json').read_text());source=Path(record['source_run'])
    if record['source_commit']!='707cd7f4a0a4d416d11bac71112980079e0a9d34':raise ValueError('Wrong design')
    verify(record['original_files'])
    lib_source=source/'design/system_707cd7f.nlib'
    if tree(lib_source)!=record['source_design_snapshot']:raise ValueError('Successful source library changed')
    lib=out/'diagnostic.nlib';shutil.copytree(lib_source,lib)
    if tree(lib)!=record['source_design_snapshot']:raise ValueError('Diagnostic copy differs')
    refs=[]
    for label in ('rvt','private','shared'):
        old=source/('library_'+label)/(label+'.ndm');expected=record['source_reference_snapshots'][str(old)]
        if tree(old)!=expected:raise ValueError('Source references changed')
        dest=out/('reference_'+label)/(label+'.ndm');dest.parent.mkdir();shutil.copytree(old,dest)
        if tree(dest)!=expected:raise ValueError('Reference copy differs')
        refs.append(dest)
    for n in ('PrCommon.tcl','IoGeometry.tcl','StageWatch.py'):shutil.copy2(failed/'tools'/n,HERE/n)
    native=(failed/'tools/PgStage.tcl').read_text();(HERE/'Diagnose.tcl').write_text(native_script(native))
    oldinputs=json.loads((source/'NewPrInputs.json').read_text())
    config=''.join(scalar(k,v) for k,v in [('Phase','legalize'),('DesignLib',lib),('ExpectedPeriod',oldinputs['expected_serialized_period_ns'])])+tlist('RefLibs',refs)
    (out/'PgConfig.tcl').write_text(config)
    tools=json.loads((soc/'tpusoc_icc2_start_20261108_mTq1LE/PrInputs.json').read_text())
    command=['python3',str(HERE/'StageWatch.py'),'--label','macro_diagnostic','--limit','600','--log',str(out/'native.log'),'--cwd',str(out),'--',tools['icc2'],tools['icc2_flag'],str(HERE/'Diagnose.tcl')]
    code=subprocess.call(command)
    if code:raise ValueError('Native diagnostic failed; inspect native.log')
    result=summarize(out)
    (out/'MacroDiagSummary.json').write_text(json.dumps(result,indent=2)+'\n')
    for tag,data in result.items():
        print('MACRO_DIAG:',tag,json.dumps(data,sort_keys=True),flush=True)
    verify(record['original_files'])
    if tree(lib_source)!=record['source_design_snapshot']:raise ValueError('Original library changed')
    print('ORIGINAL_INPUTS_UNCHANGED: True',flush=True)
    print('RESULT: MACRO_DIAGNOSTIC_COMPLETE_NO_PG_NO_ACCEPTANCE',flush=True)


if __name__=='__main__':
    out=Path(sys.argv[1]).resolve()
    try:main(out)
    except Exception as e:
        import traceback
        print('MACRO_DIAG_ERROR:',e,flush=True);traceback.print_exc();raise SystemExit(2)
    finally:
        with tarfile.open(str(out/'MacroDiagReports.tar.gz'),'w:gz') as z:
            for p in sorted(out.rglob('*')):
                rel=p.relative_to(out)
                if any(t.endswith(('.nlib','.ndm')) for t in rel.parts) or rel.parts[0].startswith('reference_') or p.name in ('payload.tar.gz','MacroDiagReports.tar.gz','runner.log'):continue
                if p.is_file():z.add(str(p),arcname=rel.as_posix())
