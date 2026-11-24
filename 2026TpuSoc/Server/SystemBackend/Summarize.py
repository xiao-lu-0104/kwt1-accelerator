"""Report current-system mapping and raw archive status without claiming power acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
from Prepare import check,sha


def contract_pass(text):
    return all(line in text for line in (
        'PASS TCM_PORT_CONTRACT: DW=64 DP=32768 banks=8 macros=32 checks=96;',
        'PASS TCM_PORT_CONTRACT: DW=32 DP=65536 banks=16 macros=32 checks=128;',
        'PASS TCM_CONTRACT: 256KiB ITCM + 256KiB DTCM; 64 real RAMSP4096X16 macros;')) \
        and not any(word in text for word in ('Fatal:','FATAL:','Error-['))


def mapped_summary(text):
    data=dict(line.split(': ',1) for line in text.splitlines() if ': ' in line)
    if data.get('TOP')!='e203_cpu_top' or data.get('FROZEN_ACCELERATOR')!='UNCHANGED':
        raise ValueError('System mapping boundary/frozen candidate not verified')
    for key,expected in (('PRIVATE_SRAM_COUNT','56'),('SHARED_SRAM_COUNT','64'),('SHARED_CAPACITY_BYTES','524288')):
        if data.get(key)!=expected: raise ValueError('Invalid system memory accounting: '+key)
    for key in ('SETUP_WNS_NS','HOLD_WNS_NS','SYSTEM_LIBRARY_AREA_UM2'):
        value=float(data[key])
        if not (-1e20<value<1e20): raise ValueError('Invalid mapped number')
    if float(data['SYSTEM_LIBRARY_AREA_UM2'])<=0: raise ValueError('No positive system area')
    for slack,status in (('SETUP_WNS_NS','SETUP_STATUS'),('HOLD_WNS_NS','HOLD_STATUS')):
        if data[status]!=('PASS' if float(data[slack])>=0 else 'FAIL'): raise ValueError('Timing status/slack mismatch')
    return data


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('out',type=Path)
    parser.add_argument('--inputs',type=Path,help='Separate verified recovery input record; original record stays intact')
    args=parser.parse_args(); out=args.out.resolve()
    input_record=args.inputs.resolve() if args.inputs else out/'SystemBaseInputs.json'
    check(json.loads(input_record.read_text()))
    contract=(out/'contract/status.txt').read_text().strip()
    if contract=='PASS' and not contract_pass((out/'contract/run.log').read_text(errors='replace')):
        raise ValueError('Contract PASS evidence missing')
    mapping=(out/'mapped/status.txt').read_text().strip()
    result={'tcm_contract':contract,'mapping_tool':mapping,'system_power':'PENDING_SYSTEM_ACTIVITY_AND_X_REVIEW',
        'full_cpu_macro_tcm_function':'PENDING_FULL_SYSTEM_REGRESSION',
        'raw_archive':'ExistingMaterials.partial.tar.gz; existing evidence only, not final submission'}
    print('SYSTEM_BASE_CONTRACT:',contract)
    print('SYSTEM_BASE_MAPPING:',mapping)
    if mapping=='COMPLETE':
        data=mapped_summary((out/'mapped/summary.txt').read_text()); result['mapped']=data
        for key in ('TOP','FROZEN_ACCELERATOR','PRIVATE_SRAM_COUNT','SHARED_SRAM_COUNT',
                    'SETUP_WNS_NS','HOLD_WNS_NS','SETUP_STATUS','HOLD_STATUS','SYSTEM_LIBRARY_AREA_UM2'):
            print('SYSTEM_MAPPED:',key,data[key])
        files=[p for p in sorted((out/'mapped').iterdir()) if p.is_file() and p.suffix in ('.v','.ddc','.sdc','.rpt','.txt','.tcl')]
        files += [out/'Sources.tcl',out/'frozen_accelerator.v',out/'SystemBaseInputs.json']
        if input_record!=out/'SystemBaseInputs.json': files.append(input_record)
        manifest={str(p.relative_to(out)):sha(p) for p in files}
        (out/'SystemMappingManifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        with tarfile.open(out/'SystemMappingReports.partial.tar.gz','x:gz') as stream:
            for path in files+[out/'SystemMappingManifest.json']:
                stream.add(path,arcname='SystemBase/'+path.relative_to(out).as_posix(),recursive=False)
        print('SYSTEM_REPORT_ARCHIVE:',out/'SystemMappingReports.partial.tar.gz')
    print('RAW_MATERIAL_ARCHIVE:',out/'ExistingMaterials.partial.tar.gz')
    print('SYSTEM_POWER_STATUS:',result['system_power'])
    print('SYSTEM_FUNCTION_STATUS:',result['full_cpu_macro_tcm_function'])
    (out/'SystemBaseSummary.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__': main()
