"""Recover a completed v1 run whose live preparation log was incorrectly frozen."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from Prepare import check,sha


def recovery_record(out,tools):
    original=out/'SystemBaseInputs.json'
    record=json.loads(original.read_text())
    inputs=dict(record['inputs'])
    log=out/'prepare.log'
    expected=inputs.pop(str(log))
    content=log.read_bytes()
    # The only allowed difference is the final progress line printed AFTER hashing.
    marker=b'SYSTEM_PREP_COMPLETE: '
    boundary=content.rfind(marker)
    if boundary<0 or hashlib.sha256(content[:boundary]).hexdigest()!=expected:
        raise ValueError('Preparation log is not the original frozen prefix plus final progress line')
    suffix=content[boundary:]
    if not re.fullmatch(rb'SYSTEM_PREP_COMPLETE: sources=[1-9][0-9]* elapsed_seconds=[0-9]+\.[0-9]{3}\n',suffix):
        raise ValueError('Unexpected appended preparation log content')
    check({'inputs':inputs})
    if (out/'mapped/status.txt').read_text().strip()!='COMPLETE':
        raise ValueError('Mapping status is not COMPLETE; inspect mapped/dc.log')
    dc_log=(out/'mapped/dc.log').read_text(errors='replace')
    if 'SYSTEM_MAPPING_REPORTS_COMPLETE:' not in dc_log or re.search(r'^(Error:|SYSTEM_MAPPING_ERROR:)',dc_log,re.M):
        raise ValueError('Mapping completion evidence missing or contains errors')
    inputs[str(original)]=sha(original)
    inputs[str(log)]=sha(log)  # It is now closed; retain its full hash rather than waive it.
    for path in tools.iterdir():
        if path.is_file(): inputs[str(path)]=sha(path)
    record['inputs']=inputs
    record['recovery']={'reason':'v1 incorrectly froze still-open prepare.log',
        'original_record':str(original),'original_record_sha256':sha(original),
        'frozen_prepare_log_prefix_sha256':expected,'prefix_bytes':boundary,
        'verified_appended_line':suffix.decode().strip(),
        'policy':'All other original input hashes checked unchanged; no EDA or simulation rerun; original files retained'}
    return record


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('out',type=Path)
    args=parser.parse_args(); out=args.out.resolve(); tools=Path(__file__).resolve().parent
    target=out/'SystemBaseRecoveryInputs.json'
    if target.exists() or (out/'SystemBaseSummary.json').exists() or (out/'SystemMappingReports.partial.tar.gz').exists():
        raise ValueError('Recovery output already exists; refusing overwrite')
    record=recovery_record(out,tools)
    target.write_text(json.dumps(record,indent=2)+'\n')
    print('RECOVERY_INPUTS_VERIFIED: original log prefix and all other frozen inputs unchanged',flush=True)
    env=dict(os.environ); env['PYTHONPATH']=str(tools)
    subprocess.run([sys.executable,'-B','-u',str(tools/'Summarize.py'),str(out),'--inputs',str(target)],env=env,check=True)
    print('RESULT: SYSTEM_BASE_SUMMARY_RECOVERED (inspect timing statuses; system power/function pending)',flush=True)


if __name__=='__main__': main()
