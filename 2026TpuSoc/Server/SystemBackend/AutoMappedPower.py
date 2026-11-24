"""Use installed automatic name matching after the native-map-only attempt failed."""
import argparse
import json
from pathlib import Path
import re
from Prepare import sha
from NativeMappedPower import prepare as prepare_original,finish as finish_power


def manual_sections(text):
    lines=text.splitlines(); sections=[]
    for index,line in enumerate(lines):
        if re.fullmatch(r'\s*-(?:map_names|auto_map_names|instance_name)(?:\s+\w+)?\s*',line):
            end=index+1
            while end<len(lines) and end-index<48:
                if re.match(r'^\s{0,8}-[A-Za-z_]\w*(?:\s|$)',lines[end]) or re.match(r'^\s*(?:EXAMPLES|SEE ALSO)\s*$',lines[end]): break
                end+=1
            sections.append({'line':index+1,'text':'\n'.join(lines[index:end])})
    return sections


def prepare(source,out,tools):
    prepare_original(source,out,tools)
    record=json.loads((out/'Inputs.json').read_text())
    manual=source/'ff1/read_saif_manual.txt'
    if '-auto_map_names' not in manual.read_text(): raise ValueError('Installed manual must support -auto_map_names')
    sections=manual_sections(manual.read_text())
    path=out/'InstalledAnnotationSemantics.json'
    path.write_text(json.dumps({'manual':str(manual),'sections':sections},indent=2)+'\n')
    record['inputs'][str(path)]=sha(path)
    record['mapping']='saif_map -start before read_ddc, then read_saif -auto_map_names; native synthesis map explicitly NOT loaded in this fresh DC session'
    record['require_active_mapping']=True
    (out/'Inputs.json').write_text(json.dumps(record,indent=2)+'\n')
    print('AUTO_MATCH_PREPARED: activate mapping before checkpoint import, then automatic matching; original failed attempts and all original results preserved',flush=True)
    for section in sections:
        print('INSTALLED_ANNOTATION_SEMANTICS: line='+str(section['line']),flush=True)
        for line in section['text'].splitlines()[:14]: print(line,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('mode',choices=('prepare','finish'))
    parser.add_argument('out',type=Path); parser.add_argument('--source',type=Path); args=parser.parse_args()
    if args.mode=='prepare': prepare(args.source.resolve(),args.out.resolve(),Path(__file__).resolve().parent)
    else: finish_power(args.out.resolve(),expected_mode='INSTALLED_READ_SAIF_AUTO_MAP_NAMES',
        expected_external='RETAINED_NOT_SOURCED_IN_FIRST_ESTIMATE',result_name='AUTO_NAME_MATCHED_SYSTEM_POWER_COMPLETE')
