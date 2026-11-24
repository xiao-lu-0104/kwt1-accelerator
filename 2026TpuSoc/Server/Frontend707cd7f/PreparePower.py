"""Bind fresh 707cd7f tasks to the successful new system, never an old SAIF."""
import gzip
import json
from pathlib import Path
import shutil
from SystemFlow import REV, sha, verify_manifest, check_hashes, parse_sources, validate_system
from PrepareInventory import designs, inventory, monitor
from SystemTasks import shared_guard
from Guards import effective_guard


def select_system(soc, expected_package):
    choices = []
    for flow in soc.glob('tpusoc_system_dc_20261110_707cd7f_*'):
        progress = flow / 'FlowProgress.json'
        if not progress.is_file():
            continue
        data = json.loads(progress.read_text())
        if data.get('result') == 'NEW_707CD7F_SYSTEM_DC_REPORTS_COMPLETE_REVIEW_PENDING' and data.get('inputs_unchanged') is True:
            choices.append(flow)
    if len(choices) != 1:
        raise ValueError('Expected exactly one successful new 707cd7f system flow, found ' + str(len(choices)))
    flow = choices[0]
    verify_manifest(flow, 'PACKAGE.sha256', expected_package)
    progress = json.loads((flow / 'FlowProgress.json').read_text())
    if progress.get('source_commit') != REV or progress.get('successful_stages') != [
            'hold_structure_review', 'hold_native_incremental_equivalence', 'system_inputs_frozen', 'e203_system_dc_reports']:
        raise ValueError('New system source/stage chain mismatch')
    if json.loads((flow / 'SourceUnchanged.json').read_text()).get('unchanged') is not True:
        raise ValueError('System flow input integrity incomplete')
    system = flow / 'system'
    inputs = json.loads((system / 'SystemInputs.json').read_text())
    check_hashes(inputs['sha256'])
    if inputs.get('source_commit') != REV or Path(inputs['accelerator_run']).name != 'tpusoc_hold_recovery_20261110_707cd7f_Bwf2gR':
        raise ValueError('System accelerator provenance mismatch')
    outputs = json.loads((system / 'SystemOutputs.json').read_text())
    check_hashes({str(system / 'mapped' / name): h for name, h in outputs.items()})
    result = json.loads((system / 'SystemSummary.json').read_text())
    if result.get('result') != 'NEW_707CD7F_SYSTEM_DC_REPORTS_COMPLETE_REVIEW_PENDING' or result.get('original_inputs_unchanged') is not True:
        raise ValueError('System result incomplete')
    validate_system(result['summary'])
    print('CURRENT_SYSTEM_SUMMARY:', json.dumps(result['summary'], sort_keys=True), flush=True)
    print('CURRENT_SYSTEM_AREAS:\n' + (system / 'mapped/area_breakdown.tsv').read_text(), flush=True)
    if result['summary']['SETUP_STATUS'] != 'PASS' or result['summary']['HOLD_STATUS'] != 'PASS':
        raise ValueError('Current system timing is not PASS; review system reports before task power')
    return flow, system, inputs, outputs


def prepare_current(out):
    # Import the generated Tasks module only after its definitions have loaded.
    from Tasks import current_bench, check_record
    config = json.loads((out / 'PowerConfig.json').read_text())
    soc = Path.home() / 'soc'
    flow, system, system_inputs, system_outputs = select_system(soc, config['system_package_sha256'])
    acc = Path(system_inputs['accelerator_run'])
    rec = json.loads((acc / 'RecoveryInputs.json').read_text())
    original = Path(rec['original_run'])
    check_hashes(rec['original_sha256'])
    old = soc / 'tpusoc_system_tasks_20261106_ZBysEH'
    old_record = check_record(old / 'Inputs.json')
    tools = out / 'tools'
    proof = json.loads((out / 'firmware/BuildEvidence/FirmwareEvidence.json').read_text())
    if proof.get('frontend_revision') != REV or proof.get('FF1_blocks') != [32, 32, 28, 7]:
        raise ValueError('New firmware source/block mismatch')
    for name, digest in proof['sha256'].items():
        if sha(out / 'firmware' / name) != digest:
            raise ValueError('New firmware evidence changed: ' + name)
    binary = (out / 'firmware/BuildEvidence/Shared.bin').read_bytes()
    expected = b''.join(((reg << 7) | 0x13).to_bytes(4, 'little') for reg in range(1, 32))
    if not binary.startswith(expected):
        raise ValueError('Boot GPR initialization missing')
    firmware = out / 'firmware/BuildEvidence/Firmware.hex'
    words = firmware.read_text().split()
    if len(words) != 32768 or b''.join(int(w, 16).to_bytes(8, 'little') for w in words) != binary + bytes(262144 - len(binary)):
        raise ValueError('Full ITCM image differs from executable')
    candidate = out / 'candidate.v'
    shutil.copy2(system / 'frozen_accelerator.v', candidate)
    if sha(candidate) != sha(acc / 'mapped/candidate.v'):
        raise ValueError('System and standalone accelerator copies differ')
    bench = out / 'PhysicalSharedTest.sv'
    bench.write_text(current_bench((old / 'PhysicalSharedTest.sv').read_text()))
    lines = (old / 'Task.f').read_text().splitlines()
    updated, replacements = [], [0, 0]
    for line in lines:
        if line == str(old / 'candidate.v'):
            line = str(candidate)
            replacements[0] += 1
        if line == str(old / 'PhysicalSharedTest.sv'):
            line = str(bench)
            replacements[1] += 1
        updated.append(line)
    if replacements != [1, 1]:
        raise ValueError('Historical task file-list boundary mismatch')
    hdl = [Path(line) for line in updated if line and not line.startswith(('+', '-'))]
    # Match the actual CPU/controller source contents and TCM binder to this system DC.
    system_sources = parse_sources((system / 'Sources.tcl').read_text())
    by_name = {}
    for path in hdl:
        by_name.setdefault(path.name, []).append(path)
    for name in system_sources['Sources'][1:]:
        path = Path(name)
        if not any(sha(p) == sha(path) for p in by_name.get(path.name, [])):
            raise ValueError('Simulation CPU/TCM source differs from current system: ' + str(path))
    # Compare every system include file with a file in an actual Task.f include directory.
    task_include_dirs = [Path(part) for line in updated if line.startswith('+incdir+') for part in line[len('+incdir+'):].split('+') if part]
    for name in system_sources['Includes']:
        for p in Path(name).iterdir():
            if p.is_file() and p.suffix in ('.vh', '.svh', '.h'):
                matches = [d / p.name for d in task_include_dirs if (d / p.name).is_file()]
                if not matches or not any(sha(q) == sha(p) for q in matches):
                    raise ValueError('Simulation include differs from system DC: ' + str(p))
    (out / 'Task.f').write_text('\n'.join(updated) + '\n')
    models = {}
    model_paths = [Path(line[3:]) for line in lines if line.startswith('-v ')]
    if not model_paths:
        raise ValueError('No real foundry simulation models')
    for path in model_paths:
        data = gzip.decompress(path.read_bytes()) if path.suffix == '.gz' else path.read_bytes()
        models.update(designs(data.decode(errors='replace')))
    rows, opaque = inventory(designs(candidate.read_text()), models)
    (out / 'Registers.json').write_text(json.dumps({'registers': rows, 'opaque': dict(opaque)}, indent=2))
    reset, controls = monitor(rows)
    (out / 'GateResetInventory.sv').write_text(reset)
    (out / 'EffectiveDataGuard.sv').write_text(effective_guard(candidate.read_text()))
    (out / 'SharedTcmGuard.sv').write_text(shared_guard())
    shutil.copy2(old / 'IcbMirror.sv', out / 'IcbMirror.sv')
    activity = (tools / 'TaskActivity.sv').read_text()
    scope = 'SharedTest.Cpu.u_e203_cpu.u_e203_nice_core'
    if activity.count(scope) != 2:
        raise ValueError('Unexpected activity scope template')
    activity = activity.replace(scope, 'SharedTest.Cpu').replace('if (Started || Stopped)',
        'if (!TcmInitializer.Done || !TcmInitializer.Released) $fatal(1,"SYSTEM_SAIF_STARTED_DURING_INIT");\n        if (Started || Stopped)')
    (out / 'SystemActivity.sv').write_text(activity)
    bundle = Path((old / 'Bundle.txt').read_text().strip())
    vectors = []
    for directory in (bundle / 'Vectors', bundle / 'Vectors/Ff1_normal'):
        for name in ('Input.hex', 'Fractions.hex', 'Layer0.hex', 'Expected0.hex'):
            p = directory / name
            if not p.is_file():
                raise ValueError('Missing golden vector: ' + str(p))
            vectors.append(p)
    libraries = []
    for line in (original / 'library_sha256.txt').read_text().splitlines():
        digest, name = line.split(None, 1)
        check_hashes({name.strip(): digest})
        libraries.append(Path(name.strip()))
    shared = Path(system_inputs['old_system']) / 'sram_db/RAMSP4096X16_tt_1p10v_1p10v_25c.db'
    if len(libraries) != 2 or str(shared) not in system_inputs['sha256']:
        raise ValueError('Current three-library provenance incomplete')
    check_hashes({str(shared): system_inputs['sha256'][str(shared)]})
    paths = dict(system_inputs['sha256'])
    paths.update(old_record['inputs'])
    selected = [flow / name for name in ('PACKAGE.sha256', 'Config.json', 'FlowProgress.json', 'SourceUnchanged.json', 'EquivSummary.json')]
    selected += [system / name for name in ('SystemSummary.json', 'SystemInputs.json', 'SystemOutputs.json', 'Sources.tcl')]
    selected += [system / 'mapped' / name for name in system_outputs]
    selected += vectors + [old / 'Inputs.json', old / 'Task.f', old / 'PhysicalSharedTest.sv', old / 'IcbMirror.sv', old / 'Bundle.txt']
    for line in updated:
        p = Path(line[3:]) if line.startswith('-v ') else Path(line) if line and not line.startswith(('+', '-')) else None
        if p:
            selected.append(p)
    for directory in (out / 'firmware', tools):
        selected += [p for p in directory.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    selected += [p for p in out.iterdir() if p.is_file() and p.name not in ('runner.log', 'prepare.log', 'payload.tar.gz')]
    for p in selected:
        paths[str(p)] = sha(p)
    record = {'source_commit': REV, 'inputs': paths, 'system_flow': str(flow), 'system': str(system), 'accelerator': str(acc),
        'bundle': str(bundle), 'firmware': str(firmware), 'libraries': [str(p) for p in libraries + [shared]],
        'simulation': 'current system CPU RTL + frozen 707cd7f mapped accelerator + real 120 SRAM models; zero delay; no SDF',
        'initial_state': '31 executable boot GPR clears; pattern2 accelerator FF seed for one reset clock then release; physical TCM full initialization/readback; no task-time forces',
        'scope': 'SharedTest/Cpu system task; initialization excluded', 'ff1_expected_commands': {'loads': 2, 'executes': 4, 'stores': 4},
        'ff1_blocks': [32, 32, 28, 7]}
    (out / 'Inputs.json').write_text(json.dumps(record, indent=2) + '\n')
    print('NEW_707CD7F_TASKS_PREPARED: current system fingerprinted; eight DOT guards; FFs=%d controls=%d' % (len(rows), len(controls)), flush=True)
    print('SYSTEM_SOURCE:', system, flush=True)
