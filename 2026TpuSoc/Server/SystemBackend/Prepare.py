"""Archive passed raw evidence and prepare current-platform CPU/TCM mapping."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import time

BUNDLE_MANIFEST='baeeca78a1b60d921fd7de97397946457b39f63cde73d126880ca763a2b1ec83'


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''): digest.update(block)
    return digest.hexdigest()


def check(record):
    for filename,digest in record['inputs'].items():
        if sha(Path(filename))!=digest: raise ValueError('Frozen input changed: '+filename)


def freeze_prepared_outputs(out,inputs):
    # StageWatch keeps prepare.log open until this process has exited.
    for name in ('Sources.tcl','frozen_accelerator.v','OriginalRam.txt','SharedModel.txt',
                 'SharedLib.txt','StdDb.txt','SpDb.txt','ExistingMaterials.partial.tar.gz',
                 'ExistingMaterials.sha256'):
        path=out/name
        inputs[str(path)]=sha(path)


def choose():
    choices=sorted((Path.home()/'soc').glob('tpusoc_activity_qualification_20261106_*'),
                   key=lambda p:p.stat().st_mtime,reverse=True)
    for path in choices:
        if not (path/'QualificationSummary.json').exists(): continue
        if 'RESULT: ACTIVITY_QUALIFICATION_COLLECTION_COMPLETE' not in (path/'runner.log').read_text(): continue
        result=json.loads((path/'QualificationSummary.json').read_text())
        if result['shared_macro_smoke']!='PASS': continue
        if any(result[t] != {'effective_data_guard':'PASS','clock_query':'PASS'} for t in ('ff1','encoder')): continue
        record=json.loads((path/'QualificationInputs.json').read_text())
        check(record)
        return path,record
    raise ValueError('An unchanged completed PASS qualification run is required')


def tcl_list(values):
    values=[str(value) for value in values]
    if any(any(c in value for c in '{}\n\r') for value in values): raise ValueError('Unsafe Tcl path')
    return '[list '+' '.join('{'+v+'}' for v in values)+']'


def platform_files(source,audit,tools,out):
    context=json.loads((audit/'SystemPowerPreparation.json').read_text())
    platform=Path(context['platform_source'])
    scope=json.loads((platform.parents[2]/'Scope.json').read_text())
    if scope['configuration_modified'] or scope['cpu_datapath_modified']: raise ValueError('Modified platform CPU/configuration')
    for name,digest in scope['copied_platform_sha256'].items():
        if sha(platform/name)!=digest: raise ValueError('Platform snapshot changed: '+name)
    lines=(source/'Task.f').read_text().splitlines()
    includes=[p for line in lines if line.startswith('+incdir+') for p in line[len('+incdir+'):].split('+')]
    originals=[Path(line) for line in lines if line and not line.startswith(('+','-')) and platform in Path(line).parents]
    if not originals or len(set(originals))!=len(originals): raise ValueError('Missing/duplicate platform source list')
    replacement=[p for p in originals if p.name=='sirv_gnrl_ram.v']
    sim=[p for p in originals if p.name=='sirv_sim_ram.v']
    cpu=[p for p in originals if p.name=='e203_cpu_top.v']
    if len(replacement)!=1 or len(sim)!=1 or len(cpu)!=1: raise ValueError('Expected one CPU top and two original RAM definitions')
    if any(p.name=='e203_subsys_nice_core.v' for p in originals): raise ValueError('Original NICE conflicts with frozen accelerator')
    candidate=source/'candidate.v'
    if sha(candidate)!='b366417d57d6251f13a827933288886637b61071472d391b121a7341fa2ea75e':
        raise ValueError('Unexpected frozen accelerator')
    frozen=out/'frozen_accelerator.v'; shutil.copy2(candidate,frozen)
    sources=[frozen,tools/'TcmMacro.sv']+[p for p in originals if p!=replacement[0]]
    (out/'Sources.tcl').write_text('set Sources '+tcl_list(sources)+'\nset Includes '+tcl_list(includes)+'\n')
    (out/'OriginalRam.txt').write_text(str(sim[0])+'\n')
    return platform,originals


def archive(out,qualification,record,source,power,platform):
    root=out/'ExistingMaterials'; root.mkdir()
    copies={}
    def copy(path,relative):
        if not path.is_file() or path.is_symlink(): raise ValueError('Expected regular material file: '+str(path))
        target=root/relative; target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists(): raise ValueError('Duplicate archive destination: '+str(relative))
        shutil.copy2(path,target)
        digest=sha(path)
        if sha(target)!=digest: raise ValueError('Archive copy changed: '+str(path))
        copies[target.relative_to(root).as_posix()]={'source':str(path),'sha256':digest}
    def tree(directory,label,recursive=False,suffixes=None):
        for path in sorted(directory.rglob('*') if recursive else directory.iterdir()):
            if '__pycache__' in path.parts or path.suffix=='.pyc': continue
            if path.is_file() and (suffixes is None or path.suffix in suffixes):
                copy(path,Path(label)/path.relative_to(directory))
    bundle=Path((source/'Bundle.txt').read_text().strip())
    # The known deployment bundle contains team RTL/firmware/vectors, no foundry libs.
    if sha(bundle/'MANIFEST.sha256')!=BUNDLE_MANIFEST: raise ValueError('Original bundle manifest changed')
    for line in (bundle/'MANIFEST.sha256').read_text().splitlines():
        digest,name=line.split('  ',1); path=(bundle/name).resolve()
        if bundle.resolve() not in path.parents or sha(path)!=digest: raise ValueError('Original bundle changed: '+name)
    if sum(p.stat().st_size for p in bundle.rglob('*') if p.is_file())>256*1024*1024:
        raise ValueError('Unexpectedly large original deployment bundle')
    tree(bundle,'SourceBundle',True)
    tree(platform,'CompetitionPlatform/rtl/e203',True)
    functional=Path((source/'Functional.txt').read_text().strip())
    tree(functional,'FunctionalLogs',suffixes={'.log','.json','.txt'})
    for name in ('Scope.json','Files.f','Firmware.hex','SharedLayout.svh','SharedLayout.h','Shared.ld'):
        path=functional/'project'/name
        if path.exists(): copy(path,Path('FunctionalProject')/name)
    original=Path(power['paths']['original']); report=Path(power['paths']['report'])
    for name in ('candidate.ddc','candidate.v','candidate.sdc'):
        copy(original/'mapped'/name,Path('AcceleratorMapping')/name)
    for directory,label in ((original/'mapped','AcceleratorOriginalReports'),(report,'AcceleratorReviewedReports'),
        (source,'TaskPower'),(qualification,'Qualification')):
        tree(directory,label,suffixes={'.rpt','.tsv','.txt','.json','.log','.sv'})
    for mode in ('baseline','candidate'):
        if (report/mode).is_dir(): tree(report/mode,'AcceleratorReviewedReports/'+mode,suffixes={'.rpt','.tsv','.txt','.json'})
    for task in ('ff1','encoder'):
        tree(source/task,'TaskPower/'+task,suffixes={'.saif','.rpt','.log','.json','.txt'})
        tree(qualification/task,'Qualification/'+task,suffixes={'.rpt','.log','.json','.txt'})
    inventory=Path(power['inventory'])
    tree(inventory,'GateInventory',suffixes={'.log','.json','.txt','.sv','.f','.tsv'})
    libraries={}
    for key in ('std_db','sram_db'):
        path=Path(power['paths'][key]); libraries[key]={'path':str(path),'sha256':sha(path)}
    (root/'ExternalLibraries.json').write_text(json.dumps(libraries,indent=2)+'\n')
    (root/'ArchiveSources.json').write_text(json.dumps(copies,indent=2)+'\n')
    (root/'STATUS.txt').write_text('PARTIAL INITIAL-SUBMISSION RAW EVIDENCE ARCHIVE\n'
        'Current task1-3 sources, original functional/gate evidence, accelerator PPA and task SAIF are preserved.\n'
        'Qualified consumer X guards and isolated raw shared macro PASS are included.\n'
        'CPU/shared-TCM mapped reports, complete system activity/power, idle-X power review, numerical-model packaging and clean portable reproduction remain pending.\n'
        'Existing candidate includes explicit binary one-reset-clock mapped-FF initial conditions.\n'
        'No foundry libraries/models are copied. Paths and hashes identify required external tools/libraries.\n')
    manifest=''.join(sha(p)+'  '+p.relative_to(root).as_posix()+'\n' for p in sorted(root.rglob('*')) if p.is_file())
    (root/'MANIFEST.sha256').write_text(manifest)
    package=out/'ExistingMaterials.partial.tar.gz'
    with tarfile.open(package,'x:gz') as stream:
        for path in sorted(root.rglob('*')):
            if path.is_file(): stream.add(path,arcname='ExistingMaterials/'+path.relative_to(root).as_posix(),recursive=False)
    (out/'ExistingMaterials.sha256').write_text(sha(package)+'  '+package.name+'\n')
    print('EXISTING_MATERIALS_ARCHIVED:',package,'files='+str(len(copies)),'bytes='+str(package.stat().st_size),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('out',type=Path)
    args=parser.parse_args(); out=args.out.resolve(); tools=Path(__file__).resolve().parent
    started=time.monotonic(); print('SYSTEM_PREP: verifying completed qualification and frozen inputs',flush=True)
    qualification,record=choose(); source=Path(record['source']); audit=Path(record['audit'])
    power=json.loads((source/'TaskPowerInputs.json').read_text()); check(power)
    platform,originals=platform_files(source,audit,tools,out)
    evidence=json.loads((audit/'SharedSramMacroEvidence.json').read_text())
    for key in ('model','liberty'):
        if sha(Path(evidence[key]))!=evidence[key+'_sha256']: raise ValueError('Shared macro input changed: '+key)
    (out/'SharedModel.txt').write_text(evidence['model']+'\n')
    (out/'SharedLib.txt').write_text(evidence['liberty']+'\n')
    for name in ('StdDb.txt','SpDb.txt'): shutil.copy2(source/name,out/name)
    print('SYSTEM_PREP: archiving existing raw source/report/activity evidence',flush=True)
    archive(out,qualification,record,source,power,platform)
    inputs=dict(record['inputs'])
    for path in originals+[qualification/'runner.log',qualification/'QualificationSummary.json',
        qualification/'QualificationInputs.json',Path(evidence['model']),Path(evidence['liberty'])]: inputs[str(path)]=sha(path)
    for path in tools.iterdir():
        if path.is_file(): inputs[str(path)]=sha(path)
    freeze_prepared_outputs(out,inputs)
    (out/'SystemBaseInputs.json').write_text(json.dumps({'qualification':str(qualification),'source':str(source),
        'platform':str(platform),'inputs':inputs,'scope':'CPU/internal ICB/frozen accelerator/shared TCM mapping; no system power acceptance'},indent=2)+'\n')
    print('SYSTEM_PREP_COMPLETE: sources='+str(len(originals))+' elapsed_seconds='+format(time.monotonic()-started,'.3f'),flush=True)


if __name__=='__main__': main()
