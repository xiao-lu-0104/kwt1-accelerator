"""707cd7f structural hold review, native incremental FM, fresh E203 system DC."""
from collections import Counter
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

REV = '707cd7f4a0a4d416d11bac71112980079e0a9d34'
ACC_NAME = 'tpusoc_hold_recovery_20261110_707cd7f_Bwf2gR'


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()


def verify_manifest(directory, filename, expected=None):
    manifest = directory / filename
    if expected and sha(manifest) != expected:
        raise ValueError('Frozen manifest changed: ' + str(manifest))
    paths = [manifest]
    for line in manifest.read_text().splitlines():
        digest, name = line.split('  ', 1)
        path = (directory / name).resolve()
        if directory.resolve() not in path.parents or not path.is_file() or sha(path) != digest:
            raise ValueError('Payload changed: ' + name)
        paths.append(path)
    return paths


def check_hashes(ledger):
    for name, digest in ledger.items():
        if not Path(name).is_file() or sha(Path(name)) != digest:
            raise ValueError('Input changed: ' + name)


def inventory(path):
    result = {}
    for line in path.read_text().splitlines():
        name, ref = line.split('\t')
        if not name or not ref or name in result:
            raise ValueError('Invalid/duplicate inventory: ' + str(path))
        result[name] = ref
    if not result:
        raise ValueError('Empty inventory: ' + str(path))
    return result


def changes(before, after):
    return [{'name': n, 'kind': 'added' if n not in before else 'removed' if n not in after else 'ref_changed',
             'region': 'sram' if n.startswith('Tpu/Core/Sram/') else 'outside',
             'before': before.get(n, ''), 'after': after.get(n, '')}
            for n in sorted(set(before) | set(after)) if before.get(n) != after.get(n)]


def validate_changes(rows):
    if not rows:
        raise ValueError('Expected actual hold changes; inspect unexpected empty comparison')
    for r in rows:
        if r['kind'] != 'added' or not re.fullmatch(r'(BUF|DEL)[A-Za-z0-9_]*_12TR40', r['after']):
            raise ValueError('Hold review needs investigation; expected only added buffer/delay leaves: ' + str(r))


def timing_lines(p):
    return sorted(x.strip() for x in p.read_text().splitlines() if x.strip() and not x.lstrip().startswith('#')
                  and not re.match(r'^\s*(set_fix_hold|set_dont_touch)\s', x))


def parse_sources(text):
    result = {}
    for line in text.splitlines():
        m = re.fullmatch(r'set (Sources|Includes) \[list(.*)\]', line)
        if not m or m[1] in result:
            raise ValueError('Unexpected historical Sources.tcl syntax')
        values = re.findall(r'\{([^{}\r\n]*)\}', m[2])
        if re.sub(r'\{[^{}\r\n]*\}', '', m[2]).strip():
            raise ValueError('Unsafe source-list syntax')
        result[m[1]] = values
    if set(result) != {'Sources', 'Includes'} or not result['Sources']:
        raise ValueError('Incomplete historical source list')
    return result


def tcl_list(paths):
    if any(any(c in str(p) for c in '{}\r\n') for p in paths):
        raise ValueError('Unsafe Tcl path')
    return '[list ' + ' '.join('{' + str(p) + '}' for p in paths) + ']'


def checked(path, ledger):
    path = path.resolve()
    check_hashes({str(path): ledger[str(path)]})
    return path


def validate_system(data):
    for k, v in [('TOP', 'e203_cpu_top'), ('SOURCE_ID', REV), ('FROZEN_ACCELERATOR', 'UNCHANGED'),
                 ('PRIVATE_SRAM_COUNT', '56'), ('SHARED_SRAM_COUNT', '64'), ('SHARED_CAPACITY_BYTES', '524288')]:
        if data.get(k) != v:
            raise ValueError('System boundary mismatch: ' + k)
    for key in ('SETUP_WNS_NS', 'HOLD_WNS_NS', 'SYSTEM_LIBRARY_AREA_UM2'):
        value = float(data[key])
        if not math.isfinite(value) or (key.endswith('AREA_UM2') and value <= 0):
            raise ValueError('Invalid native number: ' + key)
    for key, flag in [('SETUP_WNS_NS', 'SETUP_STATUS'), ('HOLD_WNS_NS', 'HOLD_STATUS')]:
        if data[flag] != ('PASS' if float(data[key]) >= 0 else 'FAIL'):
            raise ValueError('Incorrect timing flag: ' + flag)


def main():
    out = Path(sys.argv[1]).resolve()
    tools = out / 'tools'
    config = json.loads((out / 'Config.json').read_text())
    acc = Path.home() / 'soc' / ACC_NAME
    stage = 'accelerator_review'
    tracked = {}
    progress = {'source_commit': REV, 'accelerator': str(acc), 'successful_stages': []}

    def track(paths):
        for p in paths:
            if not p.is_file() or p.stat().st_size == 0:
                raise ValueError('Missing/nonempty input required: ' + str(p))
            tracked[str(p)] = sha(p)

    def done(name):
        progress['successful_stages'].append(name)
        (out / 'FlowProgress.json').write_text(json.dumps(progress, indent=2) + '\n')
        print('PHASE_COMPLETE:', name, flush=True)

    def native(label, limit, cwd, log, command, env):
        code = subprocess.call(['python3', str(tools / 'StageWatch.py'), '--label', label, '--limit', str(limit),
            '--log', str(log), '--cwd', str(cwd), '--'] + command, env=env)
        text = log.read_text(errors='replace')
        check_hashes(tracked)
        if code or re.search(r'^(Error:|SYSTEM_MAPPING_ERROR:)', text, re.M):
            print(text[-7500:], flush=True)
            raise ValueError('Native stage failed: ' + label + ' exit=' + str(code))
        return text

    try:
        paths = verify_manifest(acc, 'PACKAGE.sha256', config['accelerator_recovery_package_sha256'])
        rec = json.loads((acc / 'RecoveryInputs.json').read_text())
        if rec['source_commit'] != REV or Path(rec['original_run']).name != 'tpusoc_frontend_20261110_707cd7f_ZKpdeM':
            raise ValueError('Wrong accelerator source/run')
        check_hashes(rec['original_sha256'])
        check_hashes(rec['new_inputs_sha256'])
        original = Path(rec['original_run'])
        paths += verify_manifest(original, 'MANIFEST.sha256', config['original_manifest_sha256'])
        state = json.loads((acc / 'SourceUnchanged.json').read_text())
        if state != {'original_unchanged': True, 'input_copies_unchanged': True, 'native_exit': 0}:
            raise ValueError('Recovery native exit/integrity not accepted')
        outputs = json.loads((acc / 'RecoveryOutputs.json').read_text())
        check_hashes({str(acc / n): h for n, h in outputs.items()})
        summary = dict(line.split(': ', 1) for line in (acc / 'mapped/summary.txt').read_text().splitlines())
        if summary['SOURCE_ID'] != REV + '_with_platform_icb' or summary['SETUP_STATUS'] != 'PASS' or summary['HOLD_STATUS'] != 'PASS':
            raise ValueError('Accelerator source/timing mismatch')
        baseline = inventory(acc / 'mapped/baseline_leaves.tsv')
        candidate = inventory(acc / 'mapped/candidate_leaves.tsv')
        if Counter(baseline.values())['RAMSP1024X16'] != 56 or Counter(candidate.values())['RAMSP1024X16'] != 56:
            raise ValueError('Private macro inventory mismatch')
        # Independently recompute the outside-SRAM inventories and every full-leaf change.
        for name, leaves in [('outside_before.tsv', baseline), ('outside_after.tsv', candidate)]:
            if inventory(acc / 'mapped' / name) != {n: r for n, r in leaves.items() if not n.startswith('Tpu/Core/Sram/')}:
                raise ValueError('Outside inventory inconsistent with full inventory')
        rows = changes(baseline, candidate)
        with (out / 'HoldChanges.tsv').open('w') as f:
            writer = csv.DictWriter(f, fieldnames=['name', 'kind', 'region', 'before', 'after'], delimiter='\t')
            writer.writeheader()
            writer.writerows(rows)
        counts = Counter((r['region'], r['kind'], r['before'], r['after']) for r in rows)
        review = {'baseline_leaves': len(baseline), 'candidate_leaves': len(candidate), 'change_count': len(rows),
                  'classes': [{'region': k[0], 'kind': k[1], 'before': k[2], 'after': k[3], 'count': v} for k, v in sorted(counts.items())],
                  'scope': 'baseline to hold candidate; no RTL equivalence claim'}
        (out / 'HoldReview.json').write_text(json.dumps(review, indent=2) + '\n')
        print('HOLD_CHANGE_REVIEW:', json.dumps(review), flush=True)
        validate_changes(rows)
        if timing_lines(acc / 'inputs/baseline.sdc') != timing_lines(acc / 'mapped/candidate.sdc'):
            raise ValueError('Accelerator timing requirements changed')
        libraries = []
        for line in (original / 'library_sha256.txt').read_text().splitlines():
            h, n = line.split(None, 1)
            check_hashes({n.strip(): h})
            libraries.append(Path(n.strip()))
        if len(libraries) != 2:
            raise ValueError('Expected standard/private library pair')
        track(paths + [Path(p) for p in rec['original_sha256']] + [Path(p) for p in rec['new_inputs_sha256']])
        track([out / 'Config.json', out / 'PACKAGE.sha256'] + [p for p in tools.iterdir() if p.is_file()])
        track([acc / n for n in ('RecoveryInputs.json', 'SourceUnchanged.json', 'RecoveryOutputs.json')])
        track([acc / n for n in outputs])
        (out / 'Inputs.json').write_text(json.dumps({'sha256': tracked, 'source_commit': REV}, indent=2) + '\n')
        done('hold_structure_review')

        stage = 'hold_equivalence'
        fm = os.environ.get('FM_BIN') or shutil.which('fm_shell')
        known = Path.home() / 'soc/tpusoc_final_preflight_20261108_sCgoD1/BackendPreflight.json'
        if not fm and known.is_file():
            fm = json.loads(known.read_text()).get('tools', {}).get('fm_shell', {}).get('executable')
        if not fm or not os.access(fm, os.X_OK):
            raise ValueError('fm_shell unavailable; set FM_BIN to installed executable')
        fmout = out / 'equiv'
        fmout.mkdir()
        env = dict(os.environ, TPU_STDCELL_DB=str(libraries[0]), TPU_SRAM_DB=str(libraries[1]),
                   TPU_BASELINE_NETLIST=str(acc / 'inputs/baseline.v'), TPU_CANDIDATE_NETLIST=str(acc / 'mapped/candidate.v'))
        native('707cd7f_hold_equivalence', 3600, fmout, fmout / 'fm.log', [fm, '-f', str(tools / 'Equiv.tcl')], env)
        status = {}
        for line in (fmout / 'EquivStatus.tsv').read_text().splitlines():
            k, v = line.split('\t', 1)
            status.setdefault(k, []).append(v)
        if status.get('MATCH_RETURN') != ['1'] or status.get('VERIFY_RETURN') != ['1'] or status.get('REPORT_ERROR'):
            raise ValueError('Native FM match/verify/report collection not complete')
        if status.get('RESULT') != ['HOLD_NETLIST_TOOL_VERIFY_TRUE_BOUNDARY_REVIEW_PENDING']:
            raise ValueError('Unexpected FM result')
        for name in ('black_boxes_r.rpt', 'black_boxes_i.rpt', 'report_unmatched_points.rpt',
                     'report_failing_points.rpt', 'report_aborted_points.rpt', 'report_unverified_points.rpt'):
            track([fmout / name])
        (out / 'EquivSummary.json').write_text(json.dumps({'native_match': True, 'native_verify': True, 'status': status,
            'scope': 'incremental mapped baseline versus candidate; SRAM internals and RTL-to-netlist proof excluded',
            'boundary_review': 'paired technology boundary; full native blackbox reports retained for review',
            'permission': 'engineering system mapping; not full-system functional/signoff acceptance'}, indent=2) + '\n')
        track([out / 'EquivSummary.json', out / 'HoldReview.json', out / 'HoldChanges.tsv', fmout / 'EquivStatus.tsv', fmout / 'fm.log'])
        print('MATCH_RETURN: 1\nVERIFY_RETURN: 1', flush=True)
        for side in ('r', 'i'):
            print('BLACKBOX_REPORT:', side, flush=True)
            print((fmout / ('black_boxes_' + side + '.rpt')).read_text(), flush=True)
        done('hold_native_incremental_equivalence')

        stage = 'system_inputs'
        system = out / 'system'
        system.mkdir()
        # Reuse only historical platform source, validated macro binding and shared DB.
        clock = Path.home() / 'soc/tpusoc_clock_port_review_20261106_TiLrj3'
        clock_record = json.loads((clock / 'Inputs.json').read_text())
        old = Path(clock_record['source']).resolve()
        if old.name != 'tpusoc_system_base_20261106_GamjxW':
            raise ValueError('Historical platform provenance mismatch')
        ledger = clock_record['inputs']
        source_list = checked(old / 'Sources.tcl', ledger)
        source = parse_sources(source_list.read_text())
        if Path(source['Sources'][0]).name != 'frozen_accelerator.v':
            raise ValueError('Unexpected historical accelerator position')
        tcm = checked(Path(source['Sources'][1]), ledger)
        if tcm.name != 'TcmMacro.sv' or sha(tcm) != sha(tools / 'TcmMacro.sv'):
            raise ValueError('TCM binding implementation differs')
        cpu_sources = [checked(Path(n), ledger) for n in source['Sources'][2:]]
        names = [p.name for p in cpu_sources]
        if names.count('e203_cpu_top.v') != 1 or 'e203_subsys_nice_core.v' in names or 'sirv_gnrl_ram.v' in names:
            raise ValueError('CPU/NICE/shared-macro source boundary mismatch')
        shared = checked(old / 'sram_db/RAMSP4096X16_tt_1p10v_1p10v_25c.db', ledger)
        contract = (old / 'contract/run.log').read_text()
        required = ['PASS TCM_PORT_CONTRACT: DW=64 DP=32768 banks=8 macros=32 checks=96;',
                    'PASS TCM_PORT_CONTRACT: DW=32 DP=65536 banks=16 macros=32 checks=128;',
                    'PASS TCM_CONTRACT: 256KiB ITCM + 256KiB DTCM; 64 real RAMSP4096X16 macros;']
        if not all(s in contract for s in required) or (old / 'contract/status.txt').read_text().strip() != 'PASS':
            raise ValueError('Historical same-source/shared-DB port contract incomplete')
        headers = []
        for name in source['Includes']:
            d = Path(name)
            if not d.is_dir():
                raise ValueError('Missing include directory: ' + name)
            headers += [p for p in d.iterdir() if p.is_file() and p.suffix in ('.vh', '.svh', '.h')]
        track(cpu_sources + headers + [shared, source_list, tcm, clock / 'Inputs.json', old / 'contract/run.log', old / 'contract/status.txt'])
        frozen = system / 'frozen_accelerator.v'
        shutil.copy2(acc / 'mapped/candidate.v', frozen)
        if sha(frozen) != sha(acc / 'mapped/candidate.v'):
            raise ValueError('Frozen accelerator copy mismatch')
        with (system / 'ExpectedAccelerator.tsv').open('w') as f:
            f.write('name\tref\tregion\n')
            for n, r in sorted(candidate.items()):
                f.write(n + '\t' + r + '\t' + ('sram' if n.startswith('Tpu/Core/Sram/') else 'outside') + '\n')
        (system / 'Sources.tcl').write_text('set Sources ' + tcl_list([frozen, tools / 'TcmMacro.sv'] + cpu_sources) + '\nset Includes ' + tcl_list(source['Includes']) + '\n')
        track([frozen, system / 'ExpectedAccelerator.tsv', system / 'Sources.tcl'])
        inputs = {'source_commit': REV, 'accelerator_run': str(acc), 'old_system': str(old), 'sha256': tracked,
                  'scope': 'new 707cd7f frozen accelerator + E203/internal ICB + private112KiB/shared512KiB',
                  'tcm_contract': 'reused same source and DB port contract; system functional tasks pending'}
        (system / 'SystemInputs.json').write_text(json.dumps(inputs, indent=2) + '\n')
        done('system_inputs_frozen')

        stage = 'system_dc'
        mapped = system / 'mapped'
        mapped.mkdir()
        dc = os.environ.get('DC_BIN') or shutil.which('dc_shell') or '/eda/synopsys/dc/dc_2022.03-SP5-5/bin/dc_shell'
        if not os.access(dc, os.X_OK):
            raise ValueError('DC executable unavailable: ' + dc)
        env = dict(os.environ, TPU_STDCELL_DB=str(libraries[0]), TPU_SRAM_DB=str(libraries[1]),
                   TPU_SYSTEM_DB=str(shared), TPU_SYSTEM_OUT=str(mapped), TPU_SYSTEM_TOOLS=str(tools))
        print('SOURCE_COMMIT:', REV, flush=True)
        print('SYSTEM_SCOPE: new frozen accelerator + E203/internal ICB + private56/shared64; external peripherals excluded', flush=True)
        print('LIBRARIES: fingerprint-checked std/private/shared DB reuse; no conversion', flush=True)
        text = native('707cd7f_e203_system_dc', 7200, mapped, mapped / 'dc.log', [dc, '-f', str(tools / 'System.tcl')], env)
        if 'SYSTEM_MAPPING_REPORTS_COMPLETE:' not in text:
            raise ValueError('System completion marker absent')
        for name in ('baseline.ddc', 'baseline.v', 'baseline.sdc', 'candidate.ddc', 'candidate.v', 'candidate.sdc',
                     'system_guidance.svf', 'system_name_map.tcl', 'summary.txt', 'area_breakdown.tsv', 'area_totals.txt',
                     'check_design.rpt', 'check_timing.rpt', 'units.rpt', 'setup.rpt', 'hold.rpt'):
            if not (mapped / name).is_file() or not (mapped / name).stat().st_size:
                raise ValueError('Missing system output: ' + name)
        summary = dict(line.split(': ', 1) for line in (mapped / 'summary.txt').read_text().splitlines())
        validate_system(summary)
        (system / 'SystemSummary.json').write_text(json.dumps({'result': 'NEW_707CD7F_SYSTEM_DC_REPORTS_COMPLETE_REVIEW_PENDING',
            'original_inputs_unchanged': True, 'summary': summary, 'native_exit': 0}, indent=2) + '\n')
        (system / 'SystemOutputs.json').write_text(json.dumps({p.name: sha(p) for p in mapped.iterdir() if p.is_file()}, indent=2) + '\n')
        print((mapped / 'summary.txt').read_text(), flush=True)
        print((mapped / 'area_breakdown.tsv').read_text(), flush=True)
        for name in ('check_design.rpt', 'check_timing.rpt'):
            print('REPORT_TAIL:', name, flush=True)
            print('\n'.join((mapped / name).read_text().splitlines()[-25:]), flush=True)
        done('e203_system_dc_reports')
        progress['result'] = 'NEW_707CD7F_SYSTEM_DC_REPORTS_COMPLETE_REVIEW_PENDING'
        print('RESULT:', progress['result'], flush=True)
        print('NEXT: fresh 707cd7f firmware + strict golden system tasks + new SAIF + system DDC power; no old SAIF reuse', flush=True)
    except Exception as error:
        progress['result'] = 'NEW_707CD7F_SYSTEM_FLOW_INCOMPLETE_RETAIN_CHECKPOINTS'
        progress['failed_stage'] = stage
        progress['error'] = str(error)
        print('SYSTEM_FLOW_ERROR:', error, flush=True)
        print('RESULT:', progress['result'], 'stage=' + stage, flush=True)
    finally:
        unchanged = True
        try:
            check_hashes(tracked)
        except Exception as error:
            unchanged = False
            progress['integrity_error'] = str(error)
        progress['inputs_unchanged'] = unchanged
        if not unchanged:
            progress['result'] = 'NEW_707CD7F_SYSTEM_FLOW_INCOMPLETE_RETAIN_CHECKPOINTS'
        (out / 'FlowProgress.json').write_text(json.dumps(progress, indent=2) + '\n')
        (out / 'SourceUnchanged.json').write_text(json.dumps({'unchanged': unchanged}, indent=2) + '\n')
        with tarfile.open(str(out / 'SystemFlowReports.tar.gz'), 'w:gz') as archive:
            for name in ('Config.json', 'PACKAGE.sha256', 'Inputs.json', 'HoldChanges.tsv', 'HoldReview.json',
                         'EquivSummary.json', 'FlowProgress.json', 'SourceUnchanged.json', 'tools', 'equiv', 'system'):
                if (out / name).exists():
                    archive.add(str(out / name), arcname=name)
        print('ORIGINAL_INPUTS_UNCHANGED:', unchanged, flush=True)
        print('WORK_DIR:', out, flush=True)
    if progress.get('result') != 'NEW_707CD7F_SYSTEM_DC_REPORTS_COMPLETE_REVIEW_PENDING':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
