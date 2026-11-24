"""Read-only inventory for Formality and physical implementation of the frozen candidate.

An available executable, LEF or RC file is not a completed equivalence proof or
physical implementation. No synthesis, match/verify, placement or routing runs here.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import time

SOURCE_SHA256 = '63104eac90eb30e02dd1f8df504fea4360fbdb8a73fb8945ebb222ee1186bbda'
RESUME_SCRIPT_SHA256 = 'c7e4863b4cd919d9bb1a92e393b1dea1e92e2ec63c2f78b18866c8d22cdb19b6'
KEYWORDS = set('module endmodule input output inout wire reg assign always initial if else for generate '
               'endgenerate parameter localparam supply0 supply1 tran buf not and or xor nand nor xnor'.split())
CHILDREN = []


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def stop(child):
    if child.poll() is not None:
        return
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        child.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            child.wait(timeout=1)
        except subprocess.TimeoutExpired:
            # A process blocked in kernel I/O may not reap immediately after
            # SIGKILL. Keep the supervisor bounded and disclose its PID.
            pass


def terminate(signum, frame):
    for child in CHILDREN:
        stop(child)
    raise SystemExit(128 + signum)


def command(argv, out, label, limit=30):
    log = out / (label + '.log')
    print('PREFLIGHT_TOOL:', label, 'limit_seconds=' + str(limit), flush=True)
    with log.open('x', encoding='utf-8') as stream:
        try:
            child = subprocess.Popen(argv, cwd=out, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as error:
            stream.write('TOOL_START_ERROR: ' + str(error) + '\n')
            stream.flush()
            return {'argv': argv, 'exit_code': 127, 'status': 'START_ERROR', 'log': str(log), 'log_sha256': sha(log)}
        CHILDREN.append(child)
        try:
            try:
                code = child.wait(timeout=limit)
                status = 'EXIT_' + str(code)
            except subprocess.TimeoutExpired:
                stop(child)
                code, status = 124, 'TIMEOUT'
        finally:
            stop(child)
            CHILDREN.remove(child)
    return {'argv': argv, 'exit_code': code, 'status': status, 'log': str(log), 'log_sha256': sha(log),
            'pid': child.pid, 'cleanup_pending': child.poll() is None}


def structural_references(text):
    """Inventory structural reference names; actual PR import must still validate linkage."""
    text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
    modules = set(re.findall(r'\bmodule\s+(\\\S+|[A-Za-z_$][\w$]*)', text))
    references = Counter()
    pattern = r'(?m)^\s*(\\\S+|[A-Za-z_$][\w$]*)\s+(\\\S+|[A-Za-z_$][\w$]*)\s*\('
    for ref, instance in re.findall(pattern, text):
        if ref not in KEYWORDS and ref not in modules:
            references[ref] += 1
    return dict(references)


def lef_info(text):
    # One pass: nested geometry LAYER records must not trigger a whole-file
    # backtracking search for matching END statements in large cell LEFs.
    macros, routing, sites = {}, [], []
    macro = pin = layer = None
    for line in text.splitlines():
        words = line.split('#', 1)[0].split()
        if not words:
            continue
        key = words[0]
        if key == 'MACRO' and len(words) > 1:
            macro, pin = words[1], None
            macros[macro] = {'size_um': None, 'site': [], 'pins': {}}
        elif macro is not None:
            details = macros[macro]
            if key == 'PIN' and len(words) > 1:
                pin = words[1]
                details['pins'][pin] = {'use': None, 'direction': None}
            elif key == 'END' and len(words) > 1:
                if words[1] == pin:
                    pin = None
                elif words[1] == macro:
                    macro = pin = None
            elif pin is not None and key in ('USE', 'DIRECTION') and len(words) > 1:
                details['pins'][pin]['use' if key == 'USE' else 'direction'] = words[1].rstrip(';')
            elif pin is None and key == 'SIZE' and len(words) >= 4 and words[2] == 'BY':
                details['size_um'] = [float(words[1]), float(words[3].rstrip(';'))]
            elif pin is None and key == 'SITE' and len(words) > 1:
                details['site'].append(words[1].rstrip(';'))
        elif key == 'LAYER' and len(words) == 2:
            layer = words[1]
        elif layer is not None:
            if key == 'TYPE' and len(words) > 1 and words[1] == 'ROUTING':
                routing.append(layer)
            elif key == 'END' and len(words) > 1 and words[1] == layer:
                layer = None
        elif key == 'SITE' and len(words) == 2:
            sites.append(words[1])
    return {'macros': macros, 'routing_layers': routing, 'sites': sites}


def save_json(path, value):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    os.replace(str(temporary), str(path))


def scan_assets(roots, limit_seconds=90, max_files=16000, checkpoint=None):
    found, errors, walked = [], [], 0
    deadline = time.monotonic() + limit_seconds
    truncated = False
    for root in roots:
        print('SCAN_ROOT:', str(root), flush=True)
        try:
            available = root.is_dir()
        except OSError as error:
            errors.append({'root': str(root), 'reason': str(error), 'errno': error.errno})
            continue
        if not available:
            errors.append({'root': str(root), 'reason': 'DIRECTORY_UNAVAILABLE'})
            continue
        for parent, directories, filenames in os.walk(root, onerror=lambda error: errors.append({'reason': str(error)})):
            print('SCAN_DIRECTORY:', parent, flush=True)
            if checkpoint:
                save_json(checkpoint, {'assets': found, 'scan': {'files_seen': walked, 'truncated': True,
                          'errors': errors, 'last_directory': parent, 'worker_complete': False}})
            if time.monotonic() >= deadline or walked >= max_files:
                truncated = True
                break
            directories[:] = sorted(d for d in directories if d not in ('.git', '__pycache__', '.cache'))
            for name in list(directories):
                if name.lower().endswith(('.ndm', '.nlib', '.mw')):
                    found.append({'path': str(Path(parent) / name), 'kind': 'PHYSICAL_DB_DIRECTORY_CANDIDATE'})
                    directories.remove(name)
            for filename in sorted(filenames):
                walked += 1
                if walked > max_files or time.monotonic() >= deadline:
                    truncated = True
                    break
                lower = filename.lower()
                path = Path(parent) / filename
                if path.is_symlink():
                    # Do not follow unbounded links to other installations.
                    continue
                if lower.endswith(('.lef', '.lef.gz', '.tlef', '.tlef.gz')):
                    found.append({'path': str(path), 'kind': 'LEF'})
                elif lower.endswith(('.tf', '.tluplus', '.tlu_plus', '.itf', '.ict', '.captable', '.tch', '.nxtgrd')) or 'qrctech' in lower:
                    found.append({'path': str(path), 'kind': 'TECH_OR_RC_CANDIDATE'})
                elif lower.endswith(('.ndm', '.nlib')):
                    found.append({'path': str(path), 'kind': 'PHYSICAL_DB_FILE_CANDIDATE'})
                elif lower.endswith(('.zip', '.tar.gz', '.tgz')):
                    found.append({'path': str(path), 'kind': 'PACKAGED_PDK_CANDIDATE_NOT_INSPECTED'})
            if truncated:
                break
        if truncated:
            break
    status = {'roots': [str(p) for p in roots], 'files_seen': walked, 'truncated': truncated,
              'errors': errors, 'worker_complete': True}
    if checkpoint:
        save_json(checkpoint, {'assets': found, 'scan': status})
    return found, status


def json_worker(out, label, arguments, limit):
    target = out / (label + '.json')
    details = command([sys.executable, '-B', str(Path(__file__).resolve())] + arguments +
                      ['--worker-output', str(target)], out, label, limit)
    value = json.loads(target.read_text(encoding='utf-8')) if target.is_file() else None
    return value, details


def physical_inventory(out, roots, references, scan_limit=35, file_limit=12, inspect_limit=90):
    assets, runs, errors, walked, truncated = [], [], [], 0, False
    for index, root in enumerate(roots):
        value, run = json_worker(out, 'pdk_scan_' + str(index), ['--worker-scan-root', str(root)], scan_limit)
        runs.append(run)
        if value:
            assets.extend(value['assets'])
            walked += value['scan']['files_seen']
            errors.extend(value['scan']['errors'])
        if not value or run['exit_code'] != 0 or value['scan']['truncated']:
            truncated = True
            errors.append({'root': str(root), 'status': run['status'], 'log': run['log']})
    # Isolate each read/decompression/parser; one slow LEF cannot stop the summary.
    lef_results, inspections = [], []
    deadline = time.monotonic() + inspect_limit
    lef_assets = [item for item in assets if item['kind'] == 'LEF']
    for index, item in enumerate(lef_assets):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        value, run = json_worker(out, 'lef_' + str(index), ['--worker-inspect-lef', item['path']],
                                 min(file_limit, remaining))
        inspections.append(run)
        if value and run['exit_code'] == 0:
            lef_results.append(value)
        else:
            lef_results.append({'path': item['path'], 'error': run['status'], 'log': run['log']})
    definitions, tech, sites, macros, evidence, inspection_errors = {}, [], [], {}, [], []
    for record in lef_results:
        if record.get('error'):
            inspection_errors.append(record)
            continue
        path, info = record['path'], record['info']
        evidence.append({'path': path, 'sha256': record['sha256'], 'macro_count': len(info['macros']),
                         'routing_layers': info['routing_layers'], 'sites': info['sites']})
        if info['routing_layers']:
            tech.append(path)
        if info['sites']:
            sites.append(path)
        for name, details in info['macros'].items():
            if name in references:
                definitions.setdefault(name, []).append(path)
            if name in ('RAMSP1024X16', 'RAMSP4096X16'):
                macros.setdefault(name, []).append(dict(details, path=path))
    physical = {'lef_definitions': definitions, 'missing_reference_lef': sorted(set(references) - set(definitions)),
                'technology_lef_candidates': tech, 'site_lef_candidates': sites, 'sram_lef_details': macros,
                'tech_or_rc_candidates': [item['path'] for item in assets if item['kind'] == 'TECH_OR_RC_CANDIDATE'],
                'lef_evidence': evidence, 'errors': inspection_errors,
                'inspection_truncated': len(inspections) < len(lef_assets) or bool(inspection_errors),
                'worker_runs': inspections, 'acceptance': 'FILE_INVENTORY_ONLY; actual tool import not verified'}
    scan = {'roots': [str(root) for root in roots], 'files_seen': walked,
            'truncated': truncated, 'errors': errors, 'worker_runs': runs}
    return assets, scan, physical


def worker_scan(root, target):
    save_json(target, {'assets': [], 'scan': {'files_seen': 0, 'truncated': True,
              'errors': [], 'worker_complete': False}})
    scan_assets([root], limit_seconds=25, max_files=16000, checkpoint=target)


def worker_inspect(path, target):
    print('INSPECT_LEF:', str(path), flush=True)
    try:
        if path.stat().st_size > 100 * 1024 * 1024:
            raise ValueError('LEF exceeds inspection size')
        raw = path.read_bytes()
        if path.name.lower().endswith('.gz'):
            with gzip.open(path, 'rb') as stream:
                data = stream.read(150 * 1024 * 1024 + 1)
        else:
            data = raw
        if len(data) > 150 * 1024 * 1024:
            raise ValueError('Expanded LEF exceeds inspection size')
        record = {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
                  'info': lef_info(data.decode('utf-8', errors='replace'))}
    except (OSError, ValueError, EOFError) as error:
        record = {'path': str(path), 'error': str(error)}
    save_json(target, record)


def inspect_assets(assets, references):
    definitions, tech, sites, macro_details, evidence, errors = {}, [], [], {}, [], []
    deadline, total_bytes, truncated = time.monotonic() + 120, 0, False
    for item in assets:
        if time.monotonic() >= deadline or total_bytes >= 700 * 1024 * 1024:
            truncated = True
            break
        if item['kind'] != 'LEF':
            continue
        path = Path(item['path'])
        try:
            if path.stat().st_size > 100 * 1024 * 1024:
                raise ValueError('LEF exceeds bounded inspection size')
            raw = path.read_bytes()
            if path.name.lower().endswith('.gz'):
                with gzip.open(path, 'rb') as stream:
                    data = stream.read(150 * 1024 * 1024 + 1)
            else:
                data = raw
            if len(data) > 150 * 1024 * 1024:
                raise ValueError('Expanded LEF exceeds inspection size')
            total_bytes += len(data)
            info = lef_info(data.decode('utf-8', errors='replace'))
            evidence.append({'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
                             'macro_count': len(info['macros']), 'routing_layers': info['routing_layers'], 'sites': info['sites']})
            if info['routing_layers']:
                tech.append(str(path))
            if info['sites']:
                sites.append(str(path))
            for name, details in info['macros'].items():
                if name in references:
                    definitions.setdefault(name, []).append(str(path))
                if name in ('RAMSP1024X16', 'RAMSP4096X16'):
                    macro_details.setdefault(name, []).append(dict(details, path=str(path)))
        except (OSError, ValueError, EOFError) as error:
            errors.append({'path': str(path), 'reason': str(error)})
    missing = sorted(set(references) - set(definitions))
    rc = [item['path'] for item in assets if item['kind'] == 'TECH_OR_RC_CANDIDATE']
    return {'lef_definitions': definitions, 'missing_reference_lef': missing,
            'technology_lef_candidates': tech, 'site_lef_candidates': sites,
            'sram_lef_details': macro_details, 'tech_or_rc_candidates': rc,
            'lef_evidence': evidence, 'errors': errors, 'inspection_truncated': truncated,
            'acceptance': 'FILE_INVENTORY_ONLY; layer stack/RC/library consistency and actual tool import remain unverified'}


def load_candidate(source, out, expected_sha=SOURCE_SHA256):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from InitialMaterials import verify
    archive = source / 'InitialMaterials.candidate.tar.gz'
    if sha(archive) != expected_sha:
        raise ValueError('Source archive differs from the successful numerical candidate')
    root = source / 'InitialMaterials'
    with tarfile.open(archive, 'r:gz') as stream:
        proof = stream.extractfile('InitialMaterials/MANIFEST.sha256')
        if proof is None or proof.read() != (root / 'MANIFEST.sha256').read_bytes():
            raise ValueError('Source manifest differs from the archived candidate')
    originals = verify(root)
    record = json.loads((root / 'ReviewStatus.json').read_text(encoding='utf-8'))
    if record['numerical_replay'] != 'PASS_FIXED_POINT_HEX_REPLAY' or len(record['float_parameter_sha256']) != 37:
        raise ValueError('Completed replay and full numerical material required')
    backend = record['backend_results']
    power = Path(backend['power_source'])
    power_record = json.loads((power / 'Inputs.json').read_text(encoding='utf-8'))
    paths = {key: Path(value) for key, value in power_record['paths'].items()}
    for key in ('ddc', 'sdc', 'std_db', 'private_db', 'shared_db'):
        path = paths[key]
        if power_record['inputs'].get(str(path)) != sha(path):
            raise ValueError('Frozen tool input changed: ' + str(path))
    task = Path(backend['task_source'])
    task_record = json.loads((task / 'Inputs.json').read_text(encoding='utf-8'))
    base = Path(task_record['source'])
    netlist = base / 'mapped/candidate.v'
    with tarfile.open(root / 'Backend/BackendRawMaterials.partial.tar.gz', 'r:gz') as stream:
        archived_netlist = stream.extractfile('BackendRawMaterials/Netlist/candidate.v').read()
    if hashlib.sha256(archived_netlist).hexdigest() != sha(netlist):
        raise ValueError('Archived system netlist and live frozen checkpoint differ')
    references = structural_references(archived_netlist.decode('utf-8', errors='replace'))
    if not references or not {'RAMSP1024X16', 'RAMSP4096X16'}.issubset(references):
        raise ValueError('Could not inventory structural standard-cell and SRAM references')
    bundle = root / 'Project'
    formal_sources = sorted(str(path) for path in (bundle / 'Rtl').glob('*.sv'))
    formal_sources += [str(bundle / 'Backend/e203_subsys_nice_core.sv'), str(bundle / 'Server/Backend/SpFoundry.sv')]
    available = {name: Path(name).is_file() for name in formal_sources}
    svf = sorted({str(path) for parent in (base, base / 'mapped', paths['ddc'].parent)
                  for path in parent.glob('*.svf') if path.is_file()})
    result = {'source': str(source), 'source_sha256': expected_sha, 'top': 'e203_cpu_top',
              'paths': {key: str(value) for key, value in paths.items()},
              'base': str(base), 'task_source': str(task), 'netlist': str(netlist),
              'netlist_sha256': sha(netlist), 'reference_declarations': references,
              'reference_inventory_scope': 'unique structural references in module definitions, not flattened physical instance counts',
              'synthesis_sources_tcl': str(base / 'Sources.tcl'),
              'system_synthesis_defines': ['SYNTHESIS', 'FPGA', 'FPGA_SOURCE'],
              'accelerator_synthesis_defines': ['SYNTHESIS', 'TPU_SRAM_MODEL'],
              'accelerator_source_candidates': available, 'svf_candidates': svf,
              'svf_status': 'CANDIDATE_GUIDANCE_NOT_VALIDATED' if svf else 'NOT_FOUND_IN_BOUNDED_CHECKPOINT_DIRECTORIES',
              'formal_partition_plan': ['Frozen accelerator RTL to accelerator mapped netlist',
                  'CPU/internal ICB/TCM wrapper plus the proven accelerator partition to the system netlist'],
              'memory_model_requirement': 'Identical macro interfaces/semantics in both designs; no unrestricted black-box waiver.'}
    (out / 'FrozenInputs.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return root, originals, result


def recovered_log(previous, out, label):
    source = previous / (label + '.log')
    if not source.is_file() or source.stat().st_size > 32 * 1024 * 1024:
        return None
    digest = sha(source)
    target = out / (label + '.log')
    shutil.copyfile(str(source), str(target))
    if sha(target) != digest or sha(source) != digest:
        raise ValueError('Tool documentation log changed while recovering')
    print('RECOVERED_TOOL_LOG:', label, flush=True)
    return {'status': 'RECOVERED_LOG_EXIT_STATUS_UNKNOWN', 'exit_code': None,
            'log': str(target), 'log_sha256': digest, 'original_log': str(source)}


def validate_resume(previous, frozen):
    if sha(previous / 'tools/Preflight.py') != RESUME_SCRIPT_SHA256:
        raise ValueError('Recovery requires the unchanged known v3 inspection script')
    original = json.loads((previous / 'FrozenInputs.json').read_text(encoding='utf-8'))
    if original != frozen:
        raise ValueError('Recovery frozen inputs differ from the verified current candidate')


def tools_inventory(out, installation_root=Path('/eda'), resume=None):
    found = {}
    for name in ('fm_shell', 'innovus', 'icc2_shell', 'pt_shell', 'dc_shell'):
        errors = []
        try:
            executable = shutil.which(name)
        except OSError as error:
            executable = None
            errors.append({'path': 'PATH', 'reason': str(error), 'errno': error.errno})
        if not executable:
            # Bounded known installation patterns; never scan the entire /eda tree.
            vendor = 'cadence' if name == 'innovus' else 'synopsys'
            prefix = {'fm_shell': 'fm', 'innovus': 'innovus', 'icc2_shell': 'icc2',
                      'pt_shell': 'pt', 'dc_shell': 'dc'}[name]
            root = installation_root / vendor / prefix
            try:
                # Python 3.6 pathlib can raise EACCES while iterating a glob.
                # Record inaccessible installations; never change permissions.
                candidates = sorted(root.glob('*/bin/' + name))
            except OSError as error:
                candidates = []
                errors.append({'path': str(root), 'reason': str(error), 'errno': error.errno})
            executable = next((str(path) for path in candidates if os.access(str(path), os.X_OK)), None)
        if executable:
            details = recovered_log(resume, out, name + '_help') if resume else None
            if details is None:
                details = command([executable, '-help'], out, name + '_help', 25)
            found[name] = dict(details, executable=executable, availability='EXECUTABLE_FOUND; license/session not implied')
        else:
            found[name] = {'availability': ('DISCOVERY_INCOMPLETE_ACCESS_ERROR' if errors else
                          'EXECUTABLE_NOT_FOUND_IN_PATH_OR_KNOWN_INSTALLATIONS')}
        found[name]['discovery_errors'] = errors
        for error in errors:
            print('TOOL_DISCOVERY_SKIPPED:', name, error['path'], 'errno=' + str(error['errno']), flush=True)
    fm = found.get('fm_shell', {})
    if fm.get('executable'):
        recovered = recovered_log(resume, out, 'fm_commands') if resume else None
        if recovered:
            marker = resume / 'FormalitySession.txt'
            recovered['session_marker'] = marker.is_file() and 'NO_EQUIVALENCE_RUN' in marker.read_text(encoding='utf-8')
            recovered['session_scope'] = 'PREVIOUS_DOCUMENTATION_SESSION_ONLY; no new session or equivalence run'
            found['formality_documentation_session'] = recovered
            save_json(out / 'ToolsInventory.json', found)
            return found
        help_text = Path(fm['log']).read_text(encoding='utf-8', errors='replace')
        script_flag = next((flag for flag in ('-f', '-file')
            if re.search(r'(?:^|[\s\[])' + re.escape(flag) + r'(?=[\s,\]])', help_text)), None)
        if script_flag:
            probe = out / 'FormalityHelpProbe.tcl'
            probe.write_text('''# Documentation/session probe only: no design loading, match or verify.
foreach command {read_verilog read_sverilog read_db set_svf set_top match verify report_failing_points report_unmatched_points} {
    puts "FORMAL_COMMAND_HELP: $command"
    if {[catch {help $command} reason]} {puts "FORMAL_HELP_UNAVAILABLE: $command $reason"}
}
foreach command {read_verilog read_db set_svf set_top} {
    puts "FORMAL_COMMAND_MANUAL: $command"
    if {[catch {man $command} reason]} {puts "FORMAL_MANUAL_UNAVAILABLE: $command $reason"}
}
set f [open FormalitySession.txt w]
puts $f "SESSION_STARTED; DOCUMENTATION_ONLY; NO_EQUIVALENCE_RUN"
close $f
exit
''', encoding='utf-8')
            found['formality_documentation_session'] = command([fm['executable'], script_flag, str(probe)], out, 'fm_commands', 75)
            found['formality_documentation_session']['session_marker'] = (out / 'FormalitySession.txt').is_file()
        else:
            found['formality_documentation_session'] = {'status': 'SKIPPED_UNCONFIRMED_SCRIPT_FLAG'}
    save_json(out / 'ToolsInventory.json', found)
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path, nargs='?')
    parser.add_argument('--source', type=Path)
    parser.add_argument('--resume', type=Path)
    parser.add_argument('--worker-scan-root', type=Path)
    parser.add_argument('--worker-inspect-lef', type=Path)
    parser.add_argument('--worker-output', type=Path)
    parser.add_argument('--pdk-root', type=Path, action='append')
    args = parser.parse_args()
    if args.worker_scan_root or args.worker_inspect_lef:
        if not args.worker_output:
            parser.error('Worker output required')
        if args.worker_scan_root:
            worker_scan(args.worker_scan_root, args.worker_output)
        else:
            worker_inspect(args.worker_inspect_lef, args.worker_output)
        return
    if not args.source or not args.out:
        parser.error('Frozen source and output directory required')
    out = args.out.resolve()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, terminate)
    root, originals, frozen = load_candidate(args.source.resolve(), out)
    if args.resume:
        validate_resume(args.resume, frozen)
    tools = tools_inventory(out, resume=args.resume)
    roots = args.pdk_root or [Path.home() / 'lib/S40', Path('/storage1/admin_public_dir/SRAM_Lib_2025')]
    roots = list(dict.fromkeys(roots))
    print('PREFLIGHT_PDK: bounded technology/LEF/RC inventory', flush=True)
    assets, scan, physical = physical_inventory(out, roots, frozen['reference_declarations'])
    save_json(out / 'PhysicalInventory.json', {'assets': assets, 'scan': scan, 'physical': physical})
    result = {'status': 'FINAL_BACKEND_PREFLIGHT_COLLECTED', 'source': frozen,
              'tools': tools, 'scan': scan, 'assets': assets, 'physical': physical,
              'license_environment_configured': {name: bool(os.environ.get(name))
                  for name in ('SNPSLMD_LICENSE_FILE', 'LM_LICENSE_FILE', 'CDS_LIC_FILE')},
              'actual_formal_verification': 'NOT_RUN', 'actual_placement_routing': 'NOT_RUN',
              'deadline': 'MID_NOVEMBER_WINDOW; exact official deadline not confirmed',
              'limitations': ['File presence and a started documentation session do not prove tool import or equivalence.',
                  'Truncated scans cannot prove that a missing technology asset is absent from the server.',
                  'RC/process/corner compatibility, physical power connectivity and PG pin mapping require explicit review.',
                  'A physical route is an additional requested deliverable; the published problem scope does not require P&R.',
                  'Existing power-default/X/peripheral-boundary and official numerical-accuracy reviews remain open.']}
    from InitialMaterials import verify
    if verify(root) != originals:
        raise ValueError('Frozen candidate changed during inventory')
    (out / 'BackendPreflight.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('FROZEN_CANDIDATE_UNCHANGED: PASS', flush=True)
    print('FORMAL_TOOL:', tools['fm_shell']['availability'], flush=True)
    print('FORMAL_DOCUMENTATION_SESSION:', tools.get('formality_documentation_session', {}).get('session_marker', False), flush=True)
    for name in ('innovus', 'icc2_shell'):
        print('PR_TOOL:', name, tools[name]['availability'], flush=True)
    print('PR_TECH_LEF_CANDIDATES:', len(physical['technology_lef_candidates']), flush=True)
    print('PR_SRAM_LEF:', ' '.join(name + '=' + str(len(physical['sram_lef_details'].get(name, [])))
                               for name in ('RAMSP1024X16', 'RAMSP4096X16')), flush=True)
    print('PR_MISSING_REFERENCE_LEF:', len(physical['missing_reference_lef']),
          ' '.join(physical['missing_reference_lef'][:12]), flush=True)
    print('PR_TECH_OR_RC_CANDIDATES:', len(physical['tech_or_rc_candidates']), 'scan_truncated=' + str(scan['truncated']),
          'inspection_truncated=' + str(physical['inspection_truncated']), flush=True)
    print('FORMAL_SVF_CANDIDATES:', len(frozen['svf_candidates']), flush=True)
    print('PDK_SCAN_ERRORS:', len(scan['errors']), 'LEF_INSPECTION_ERRORS:', len(physical['errors']), flush=True)
    print('TOOLS_EVIDENCE:', 'RECOVERED_LOGS_EXIT_STATUS_UNKNOWN' if args.resume else 'CURRENT_PROBES', flush=True)
    print('RESULT: FINAL_BACKEND_PREFLIGHT_COLLECTED; formal_verification=NOT_RUN placement_routing=NOT_RUN', flush=True)


if __name__ == '__main__':
    main()
