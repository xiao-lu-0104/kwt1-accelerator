"""Fresh CPU mapping around the current accelerator, reusing verified old platform and shared DB."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
from Review import sha, verify_manifest


def parse_sources(text):
    result = {}
    for line in text.splitlines():
        match = re.fullmatch(r'set (Sources|Includes) \[list(.*)\]', line)
        if not match or match[1] in result:
            raise ValueError('Unexpected old Sources.tcl syntax')
        values = re.findall(r'\{([^{}\r\n]*)\}', match[2])
        if re.sub(r'\{[^{}\r\n]*\}', '', match[2]).strip():
            raise ValueError('Unsafe old source list')
        result[match[1]] = values
    if set(result) != {'Sources', 'Includes'} or not result['Sources']:
        raise ValueError('Incomplete old source lists')
    return result


def tcl_list(values):
    if any(any(c in str(value) for c in '{}\r\n') for value in values):
        raise ValueError('Unsafe Tcl path')
    return '[list ' + ' '.join('{' + str(value) + '}' for value in values) + ']'


def checked(path, ledger):
    path = path.resolve()
    if str(path) not in ledger or not path.is_file() or sha(path) != ledger[str(path)]:
        raise ValueError('Historical input changed or absent from ledger: ' + str(path))
    return path


def validate_summary(data):
    for key, value in [('TOP','e203_cpu_top'),('FROZEN_ACCELERATOR','UNCHANGED'),
        ('PRIVATE_SRAM_COUNT','56'),('SHARED_SRAM_COUNT','64'),('SHARED_CAPACITY_BYTES','524288')]:
        if data.get(key) != value:
            raise ValueError('System result boundary mismatch: ' + key)
    for key in ('SETUP_WNS_NS','HOLD_WNS_NS','SYSTEM_LIBRARY_AREA_UM2'):
        value = float(data[key])
        if not (-1e20 < value < 1e20) or (key.endswith('AREA_UM2') and value <= 0):
            raise ValueError('Invalid system result number: ' + key)
    for key, flag in [('SETUP_WNS_NS','SETUP_STATUS'),('HOLD_WNS_NS','HOLD_STATUS')]:
        if data.get(flag) != ('PASS' if float(data[key]) >= 0 else 'FAIL'):
            raise ValueError('Timing result flag mismatch: ' + flag)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--manifest-sha', required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    choices = []
    for path in (Path.home() / 'soc').glob('tpusoc_hold_equiv_20261109_*'):
        summary = path / 'EquivSummary.json'
        if summary.is_file():
            data = json.loads(summary.read_text())
            if data.get('result') == 'HOLD_NETLIST_TOOL_VERIFY_TRUE_BOUNDARY_REVIEW_PENDING' and data.get('input_unchanged') is True:
                choices.append((path, data))
    if len(choices) != 1:
        raise ValueError('Expected exactly one successful current hold-equivalence run')
    equiv, proof = choices[0]
    run = Path(proof['original_run']).resolve()
    review = Path(proof['review']).resolve()
    verify_manifest(run, args.manifest_sha)
    equiv_inputs = json.loads((equiv / 'EquivInputs.json').read_text())
    for name, digest in equiv_inputs['sha256'].items():
        if sha(Path(name)) != digest:
            raise ValueError('Equivalence input changed: ' + name)
    status = proof.get('status', {})
    if status.get('MATCH_RETURN') != ['1'] or status.get('VERIFY_RETURN') != ['1']:
        raise ValueError('Native match/verify evidence missing')
    unchanged = json.loads((equiv / 'SourceUnchanged.json').read_text())
    if unchanged.get('unchanged') is not True or proof.get('native_exit') != 0:
        raise ValueError('Equivalence run exit or input integrity failed')

    # Bind the historical shared DB to its recorded fingerprint; do not rebuild it.
    clock = Path.home() / 'soc/tpusoc_clock_port_review_20261106_TiLrj3'
    clock_record = json.loads((clock / 'Inputs.json').read_text())
    old = Path(clock_record['source']).resolve()
    if old.name != 'tpusoc_system_base_20261106_GamjxW':
        raise ValueError('Unexpected historical system source')
    ledger = clock_record['inputs']
    sources_file = checked(old / 'Sources.tcl', ledger)
    sources = parse_sources(sources_file.read_text())
    if len(sources['Sources']) < 3 or Path(sources['Sources'][0]).resolve() != old / 'frozen_accelerator.v':
        raise ValueError('Unexpected old frozen-accelerator source position')
    tcm = checked(Path(sources['Sources'][1]), ledger)
    if tcm.name != 'TcmMacro.sv' or sha(tcm) != sha(out / 'tools/TcmMacro.sv'):
        raise ValueError('TCM binding differs from the previously used implementation')
    originals = [checked(Path(name), ledger) for name in sources['Sources'][2:]]
    names = [path.name for path in originals]
    if names.count('e203_cpu_top.v') != 1 or 'e203_subsys_nice_core.v' in names or 'sirv_gnrl_ram.v' in names:
        raise ValueError('CPU/NICE/TCM source boundary mismatch')
    shared = checked(old / 'sram_db/RAMSP4096X16_tt_1p10v_1p10v_25c.db', ledger)
    contract = (old / 'contract/run.log').read_text(errors='replace')
    required = ['PASS TCM_PORT_CONTRACT: DW=64 DP=32768 banks=8 macros=32 checks=96;',
                'PASS TCM_PORT_CONTRACT: DW=32 DP=65536 banks=16 macros=32 checks=128;',
                'PASS TCM_CONTRACT: 256KiB ITCM + 256KiB DTCM; 64 real RAMSP4096X16 macros;']
    if not all(line in contract for line in required) or (old / 'contract/status.txt').read_text().strip() != 'PASS':
        raise ValueError('Historical TCM port-contract evidence incomplete')
    libraries = []
    for line in (run / 'library_sha256.txt').read_text().splitlines():
        digest, name = line.split(None, 1)
        path = Path(name.strip())
        if sha(path) != digest:
            raise ValueError('Current accelerator technology library changed')
        libraries.append(path)
    if len(libraries) != 2:
        raise ValueError('Expected accelerator standard-cell/SRAM DB pair')
    included = []
    for name in sources['Includes']:
        directory = Path(name)
        if not directory.is_dir():
            raise ValueError('Missing include directory: ' + name)
        included += [p for p in directory.iterdir() if p.is_file() and p.suffix in ('.vh', '.svh', '.h')]
    tracked = originals + included + libraries + [shared, sources_file, tcm,
        old / 'contract/run.log', old / 'contract/status.txt', clock / 'Inputs.json',
        equiv / 'EquivSummary.json', equiv / 'EquivInputs.json', equiv / 'SourceUnchanged.json',
        equiv / 'EquivStatus.tsv', equiv / 'fm.log', equiv / 'black_boxes_r.rpt', equiv / 'black_boxes_i.rpt',
        run / 'mapped/candidate.v', review / 'candidate/leaves.tsv']
    tracked += [Path(name) for name in equiv_inputs['sha256']]
    initial = {str(p): sha(p) for p in tracked}
    frozen = out / 'frozen_accelerator.v'
    shutil.copy2(run / 'mapped/candidate.v', frozen)
    if sha(frozen) != initial[str(run / 'mapped/candidate.v')]:
        raise ValueError('Candidate copy mismatch')
    shutil.copy2(review / 'candidate/leaves.tsv', out / 'ExpectedAccelerator.tsv')
    new_sources = [frozen, out / 'tools/TcmMacro.sv'] + originals
    (out / 'Sources.tcl').write_text('set Sources ' + tcl_list(new_sources) + '\nset Includes ' + tcl_list(sources['Includes']) + '\n')
    for path in [frozen, out / 'ExpectedAccelerator.tsv', out / 'Sources.tcl'] + list((out / 'tools').iterdir()):
        if path.is_file():
            initial[str(path)] = sha(path)
    (out / 'SystemInputs.json').write_text(json.dumps({'accelerator_run': str(run), 'equiv': str(equiv),
        'old_system': str(old), 'sha256': initial,
        'boundary_review': 'incremental FM tool verify true; black-box scope review remains separate',
        'tcm_contract': 'reused historical same-source/same-DB evidence; not rerun system function'}, indent=2))
    dc = os.environ.get('DC_BIN') or shutil.which('dc_shell')
    if not dc:
        raise ValueError('dc_shell not on PATH; set DC_BIN')
    mapped = out / 'mapped'
    mapped.mkdir()
    env = dict(os.environ, TPU_STDCELL_DB=str(libraries[0]), TPU_SRAM_DB=str(libraries[1]),
        TPU_SYSTEM_DB=str(shared), TPU_SYSTEM_OUT=str(mapped), TPU_SYSTEM_TOOLS=str(out / 'tools'))
    print('ACCELERATOR_RUN:', run, flush=True)
    print('HISTORICAL_PLATFORM:', old, flush=True)
    print('LIBRARIES: reusing fingerprint-checked standard/private/shared DB; no library conversion', flush=True)
    print('SCOPE: e203_cpu_top + new frozen accelerator + private56/shared64 macros; external peripherals excluded', flush=True)
    code = subprocess.call(['python3', str(out / 'tools/StageWatch.py'), '--label', 'new_e203_system_dc',
        '--limit', '2400', '--log', str(mapped / 'dc.log'), '--cwd', str(mapped), '--', dc, '-f', str(out / 'tools/System.tcl')], env=env)
    intact = all(Path(name).is_file() and sha(Path(name)) == digest for name, digest in initial.items())
    (out / 'SourceUnchanged.json').write_text(json.dumps({'unchanged': intact}))
    log = (mapped / 'dc.log').read_text(errors='replace')
    success = code == 0 and intact and 'SYSTEM_MAPPING_REPORTS_COMPLETE:' in log and not re.search(r'^(Error:|SYSTEM_MAPPING_ERROR:)', log, re.M)
    summary = None
    if success:
        for name in ('candidate.ddc', 'candidate.v', 'candidate.sdc', 'summary.txt', 'area_breakdown.tsv', 'system_guidance.svf'):
            if not (mapped / name).is_file() or (mapped / name).stat().st_size == 0:
                print('SYSTEM_OUTPUT_ERROR: missing ' + name)
                success = False
    if success:
        summary = dict(line.split(': ', 1) for line in (mapped / 'summary.txt').read_text().splitlines() if ': ' in line)
        try:
            validate_summary(summary)
        except (ValueError, KeyError) as error:
            print('SYSTEM_SUMMARY_ERROR:', error)
            success = False
    result = {'native_exit': code, 'original_inputs_unchanged': intact,
        'result': 'NEW_SYSTEM_DC_REPORTS_COMPLETE_REVIEW_PENDING' if success else 'NEW_SYSTEM_DC_INCOMPLETE_REVIEW_CHECKPOINTS'}
    if success:
        print((mapped / 'summary.txt').read_text())
        print((mapped / 'area_totals.txt').read_text())
        result['summary'] = summary
    else:
        print(log[-7500:])
    (out / 'SystemSummary.json').write_text(json.dumps(result, indent=2))
    with tarfile.open(str(out / 'SystemDcReports.tar.gz'), 'w:gz') as archive:
        for path in sorted(out.rglob('*')):
            if path.is_file() and path.name != 'SystemDcReports.tar.gz' and '__pycache__' not in path.parts:
                archive.add(str(path), arcname=str(path.relative_to(out)), recursive=False)
    print('ORIGINAL_INPUTS_UNCHANGED:', intact)
    print('RESULT:', result['result'])
    if not success:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
