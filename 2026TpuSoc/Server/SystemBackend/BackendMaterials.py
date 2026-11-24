"""Package verified backend raw materials and explicit power-estimation limitations."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import shutil
import tarfile
from Prepare import check,sha


def coverage_status(group):
    total=group['total']; user=group['user']['count']; propagated=group['propagated']['count']; default=group['default']['count']
    if total<0 or min(user,propagated,default)<0 or user+propagated+default!=total:
        raise ValueError('Invalid activity accounting')
    return {'total':total,'user_annotated':user,'propagated':propagated,'default':default,
        'user_plus_propagated_percent':100*(user+propagated)/total if total else None,
        'default_percent':100*default/total if total else None}


def verified_manifest(source):
    result={}
    for line in (source/'MANIFEST.sha256').read_text().splitlines():
        digest,name=line.split('  ',1); path=(source/name).resolve()
        if source not in path.parents or sha(path)!=digest: raise ValueError('Original power report changed: '+name)
        result[str(path)]=digest
    return result


def pack(source,out,tools):
    record=json.loads((source/'Inputs.json').read_text()); check(record)
    report=json.loads((source/'SystemPowerSummary.json').read_text())
    if not record.get('require_active_mapping'): raise ValueError('Completed active-mapping estimate required')
    originals=dict(record['inputs']); originals.update(verified_manifest(source))
    for name in ('Inputs.json','SystemPowerSummary.json','MANIFEST.sha256','SystemPowerReports.partial.tar.gz'):
        originals[str(source/name)]=sha(source/name)
    task_run=Path(record['task_run']); task_record=json.loads((task_run/'Inputs.json').read_text())
    task_summary=json.loads((task_run/'SystemActivitySummary.json').read_text())
    check(task_record); check({'inputs':task_summary['evidence_sha256']})
    if not task_summary.get('both_tasks_use_same_repaired_firmware'): raise ValueError('Two tasks must share the repaired firmware')
    base=Path(task_record['source']); clock=Path(task_record['review'])
    area=json.loads((clock/'AreaBreakdown.json').read_text())
    timing=json.loads((clock/'ClockPortSummary.json').read_text())
    if timing['SETUP_STATUS']!='PASS' or timing['HOLD_STATUS']!='PASS': raise ValueError('Verified timing view required')
    root=out/'BackendRawMaterials'; root.mkdir()
    copied={}
    def copy(path,relative,replace=False):
        path=Path(path); relative=Path(relative)
        if relative.is_absolute() or '..' in relative.parts: raise ValueError('Unsafe package destination')
        if not path.is_file() or path.is_symlink(): raise ValueError('Regular source material required: '+str(path))
        destination=root/relative
        if destination.exists() and not replace: raise ValueError('Duplicate package material: '+str(relative))
        destination.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(path,destination)
        digest=sha(path)
        if sha(destination)!=digest: raise ValueError('Material copy differs from original')
        copied[relative.as_posix()]={'source':str(path),'sha256':digest}
        originals[str(path)]=digest
    def tree(directory,label,replace=False):
        for path in sorted(directory.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix!='.pyc':
                if path.suffix.lower() in ('.db','.lib'): raise ValueError('Foundry library must remain external: '+str(path))
                if path.relative_to(directory).as_posix()=='MANIFEST.sha256': continue
                copy(path,Path(label)/path.relative_to(directory),replace=replace)
    bundle=Path((task_run/'Bundle.txt').read_text().strip()).resolve()
    originals.update(verified_manifest(bundle))
    # Current source tree explicitly supersedes only the startup/firmware bytes;
    # earlier frozen evidence remains separately labeled as legacy provenance.
    tree(bundle,'Sources/Team')
    copy(bundle/'MANIFEST.sha256','Provenance/OriginalBundleManifest.sha256')
    revised=task_run/'firmware'
    tree(revised/'Sw','Sources/Team/Sw',replace=True)
    tree(revised/'BuildEvidence','Sources/Team/BuildEvidence',replace=True)
    for name in ('Firmware.hex','Shared.bin'):
        target='Firmware.bin' if name=='Shared.bin' else name
        copy(revised/'BuildEvidence'/name,'Sources/Team/'+target,replace=True)
    fix=json.loads((revised/'BuildEvidence/BootFix.json').read_text())
    if sha(root/'Sources/Team/Firmware.hex')!=fix['fixed_hex_sha256']:
        raise ValueError('Packaged firmware differs from the two validated task runs')
    copy(base/'tools/TcmMacro.sv','Sources/SystemImplementation/TcmMacro.sv')
    simulation=Path(task_record['original_task_run'])
    for name in ('PhysicalSharedTest.sv','SharedTcmGuard.sv','SystemActivity.sv','EffectiveDataGuard.sv',
                 'GateResetInventory.sv','IcbMirror.sv','Task.f'):
        copy(simulation/name,'Simulation/'+name)
    copy(task_run/'SystemActivitySummary.json','Simulation/SystemActivitySummary.json')
    copy(simulation/'tools/TcmInitializer.sv','Simulation/TcmInitializer.sv')
    for name in ('candidate.ddc','candidate.v'):
        copy(base/'mapped'/name,'Netlist/'+name)
    copy(clock/'clock_ports_corrected.sdc','Netlist/candidate_clock_ports_corrected.sdc')
    copy(clock/'AreaBreakdown.json','Reports/AreaBreakdown.json')
    copy(clock/'ClockPortSummary.json','Reports/ClockPortSummary.json')
    for path,label in ((base/'ExistingMaterials.partial.tar.gz','LegacyEvidence/ExistingMaterials.partial.tar.gz'),
                       (base/'SystemMappingReports.partial.tar.gz','Reports/SystemMappingReports.partial.tar.gz'),
                       (clock/'ClockPortReports.partial.tar.gz','Reports/ClockPortReports.partial.tar.gz'),
                       (source/'SystemPowerReports.partial.tar.gz','Reports/SystemPowerReports.partial.tar.gz')):
        copy(path,label)
    copy(source/'SystemPowerSummary.json','Reports/SystemPowerSummary.json')
    tasks={}
    missing={}
    for name in ('ff1','encoder'):
        status=(source/name/'tool_status.txt').read_text()
        if 'NAME_MAPPING_LIFECYCLE: STARTED_BEFORE_DDC' not in status:
            raise ValueError('Actual enabled mapping lifecycle proof required: '+name)
        for filename in ('run.log','task.saif','Activity.json'):
            copy(task_run/name/filename,Path('TaskActivity')/name/filename)
        row=report['tasks'][name]
        combined={kind:coverage_status(value) for kind,value in row['coverage'].items()}
        regions={region:{kind:coverage_status(value) for kind,value in cov.items()}
            for region,cov in row.get('regional_coverage',{}).items()}
        tasks[name]={'power':row,'global_activity':combined,'regions':regions}
        raw=json.loads((source/name/'RawUnknowns.json').read_text())
        blocks=Counter('/'.join(item['scope'].split('/')[2:5]) or '<top>' for item in raw['unknown'])
        # Preserve the missing-object report and a small readable excerpt. A
        # missing/default entry is never automatically classified as harmless.
        text=(source/name/'saif_missing.rpt').read_text(errors='replace')
        match=re.search(r'List of Non-annotated',text,re.I)
        excerpt=text[match.start():].splitlines()[:45] if match else text.splitlines()[-25:]
        missing[name]={'TX_nonzero_entries':row['TX_nonzero_entries'],'unknown_blocks':dict(blocks),
            'missing_report_excerpt':excerpt,'waiver':False}
        copy(source/name/'saif_missing.rpt',Path('ActivityLimitations')/name/'saif_missing.rpt')
        for filename in ('saif_hierarchy.rpt','saif_cpu_core.rpt','saif_accelerator.rpt','saif_shared_tcm.rpt','root_clock_activity.txt','activity.rpt'):
            if (source/name/filename).exists(): copy(source/name/filename,Path('ActivityLimitations')/name/filename)
        print('PACKAGED_TASK:',name,'cycles='+str(row['cycles']),'power_mW='+format(row['total_w']*1000,'.9g'),
              'energy_uJ='+format(row['task_energy_j']*1e6,'.9g'),flush=True)
        print('ACTIVITY_ACCOUNTING:',name,json.dumps(combined,sort_keys=True),flush=True)
        for region,cov in regions.items():
            print('REGION_ACTIVITY_ACCOUNTING:',name,region,
                'nets_annotated_or_propagated_percent='+format(cov['nets']['user_plus_propagated_percent'],'.4f'),
                'pins_annotated_or_propagated_percent='+format(cov['pins']['user_plus_propagated_percent'],'.4f'),
                'default_nets='+str(cov['nets']['default']),'default_pins='+str(cov['pins']['default']),flush=True)
        print('REMAINING_X:',name,'records='+str(row['TX_nonzero_entries'])+'; no blanket waiver',flush=True)
    external={key:{'path':value,'sha256':sha(Path(value))} for key,value in record['paths'].items()
              if key in ('std_db','private_db','shared_db')}
    result={'power_source':str(source),'task_source':str(task_run),'area':area,'timing':timing,'tasks':tasks,
        'scope':report['scope'],'method':report['method'],
        'status':'BACKEND_RAW_MATERIALS_COLLECTED_WITH_EXPLICIT_ESTIMATION_LIMITATIONS',
        'limitations':['Default and unknown activity effects have not received a blanket waiver.',
            'e203_cpu_top excludes external fixed peripherals; contest total-power boundary requires review.',
            'TT ideal-clock pre-layout estimate; no CTS/routing/parasitic/SDF signoff.',
            'Only the listed FF1 and single-layer encoder tasks use this repaired firmware in the physical-TCM evidence.',
            'Official numerical accuracy/sample evaluation and a final portable submission are not established by this package.']}
    (root/'BackendMaterialsSummary.json').write_text(json.dumps(result,indent=2)+'\n')
    (root/'ActivityLimitations.json').write_text(json.dumps(missing,indent=2)+'\n')
    (root/'ExternalLibraries.json').write_text(json.dumps(external,indent=2)+'\n')
    lines=['# Backend raw materials / 后端原始材料','',
        'Current power estimates and coverage below are measured tool reports, with limitations retained.',
        'Sources/Team contains the revised boot firmware used by BOTH listed physical-TCM tasks.',
        'LegacyEvidence contains older snapshots for provenance; their startup firmware is superseded.',
        'Netlist/candidate_clock_ports_corrected.sdc pairs with Netlist/candidate.ddc; candidate.v is the same system checkpoint.',
        'Foundry libraries/models remain external. Task.f retains original source/library locations; this archive is not a clean portable reproduction claim.','',
        '| Task | Cycles | Dynamic/mW | Leakage/mW | Total/mW | Energy/uJ |',
        '|---|---:|---:|---:|---:|---:|']
    for name,value in tasks.items():
        row=value['power']
        lines.append(f'| {name} | {row["cycles"]} | {row["dynamic_w"]*1000:.9g} | {row["leakage_w"]*1000:.9g} | {row["total_w"]*1000:.9g} | {row["task_energy_j"]*1e6:.9g} |')
    lines += ['',f'Accelerator area budget used: {area["accelerator_budget_area_um2"]/1e6:.12f} mm2 of 2.25 mm2.',
        f'System library area: {area["system_area_um2"]/1e6:.12f} mm2; shared capacity {area["shared_capacity_bytes"]} bytes.',
        f'TT ideal-clock setup WNS: {timing["SETUP_WNS_NS"]} ns; hold WNS: {timing["HOLD_WNS_NS"]} ns.','',
        'ActivityLimitations.json and ActivityLimitations/ retain default activity and unknown activity evidence.',
        'User-annotated and propagated activity are listed separately; defaults are not counted as observed activity.','']
    lines += ['- '+item for item in result['limitations']]
    (root/'README.md').write_text('\n'.join(lines)+'\n')
    for name in ('功耗原始报告_20261107.md','面积分配_20261106.md'):
        if (tools/name).exists(): copy(tools/name,'Reports/'+name)
    (root/'MaterialSources.json').write_text(json.dumps(copied,indent=2)+'\n')
    check({'inputs':originals})
    (out/'Inputs.json').write_text(json.dumps({'inputs':originals,'source':str(source)},indent=2)+'\n')
    files=sorted(path for path in root.rglob('*') if path.is_file())
    (root/'MANIFEST.sha256').write_text(''.join(sha(path)+'  '+path.relative_to(root).as_posix()+'\n' for path in files))
    archive=out/'BackendRawMaterials.partial.tar.gz'
    with tarfile.open(archive,'x:gz') as stream:
        for path in files+[root/'MANIFEST.sha256']:
            stream.add(path,arcname='BackendRawMaterials/'+path.relative_to(root).as_posix(),recursive=False)
    digest=sha(archive); (out/'BackendRawMaterials.sha256').write_text(digest+'  '+archive.name+'\n')
    print('BACKEND_MATERIAL_ARCHIVE:',archive,'bytes='+str(archive.stat().st_size),'sha256='+digest,flush=True)
    print('RESULT: BACKEND_RAW_MATERIALS_PACKAGED (sources/netlist/SDC/area/timing/activity/power collected; limitations disclosed; not final submission acceptance)',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('out',type=Path)
    parser.add_argument('--source',type=Path,required=True); args=parser.parse_args()
    pack(args.source.resolve(),args.out.resolve(),Path(__file__).resolve().parent)
