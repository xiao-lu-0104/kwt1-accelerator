"""Verify saved reports, inspect all changes, and select actual foundry cell models."""
import argparse
import gzip
import json
import os
from pathlib import Path
import re
import shutil
from RecoverReport import prepare, recheck, table, differences, sha


def model_text(path):
    data = gzip.decompress(path.read_bytes()) if path.suffix == '.gz' else path.read_bytes()
    return data.decode('utf-8', errors='replace')


def definitions(text):
    text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
    return set(re.findall(r'\b(?:module|primitive)\s+(?:automatic\s+)?([A-Za-z_]\w*)', text))


def choose_models(required, paths):
    candidates = {path: definitions(model_text(path)) for path in paths}
    missing, selected = set(required), []
    while missing:
        useful = [path for path in candidates if candidates[path] & missing]
        if not useful:
            break
        best = sorted(useful, key=lambda path: (-len(candidates[path] & missing), len(str(path)), str(path)))[0]
        selected.append(best)
        missing -= candidates[best]
        del candidates[best]
    covered = set().union(*(definitions(model_text(path)) for path in selected)) if selected else set()
    # Include separate UDP support files only when they add definitions. VCS
    # library loading resolves references; no substitute cell models are made.
    for path in sorted(candidates):
        text = model_text(path)
        if re.search(r'\bprimitive\s+\w+', text) and candidates[path] - covered:
            selected.append(path)
            covered |= candidates[path]
    return selected, missing


def check_manifest(directory, expected):
    manifest = directory / 'MANIFEST.sha256'
    if sha(manifest) != expected:
        raise ValueError('Unexpected recovery tool manifest')
    for line in manifest.read_text().splitlines():
        digest, name = line.split('  ', 1)
        path = (directory / name).resolve()
        if directory.resolve() not in path.parents or sha(path) != digest:
            raise ValueError('Recovery tool changed: ' + name)


def select_report(selected, expected):
    choices = [selected.resolve()] if selected else sorted(
        (Path.home() / 'soc').glob('tpusoc_shared_report_20261105_*'),
        key=lambda path: path.stat().st_mtime, reverse=True)
    for report in choices:
        try:
            if 'RESULT: SHARED_SAVED_REPORTS_COMPLETE' not in (report / 'runner.log').read_text():
                raise ValueError('Report not complete')
            check_manifest(report / 'tools', expected)
            recheck(report)
            return report
        except (OSError, ValueError, KeyError):
            if selected:
                raise
    raise ValueError('No unchanged completed shared report found')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--report-tools-sha', required=True)
    parser.add_argument('--asic-tools-sha', required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    report = select_report(args.report, args.report_tools_sha)
    previous = Path(json.loads((report / 'ReportInputs.json').read_text())['previous'])
    prepare(previous, out, args.asic_tools_sha)
    before, after = [table(report / mode / 'cells.tsv') for mode in ('baseline', 'candidate')]
    delta = differences(before, after)
    outside = [row for row in delta if row[0] == 'OUTSIDE']
    valid_additions = all(row[1] == 'REAL_CELL' and row[2] == 'ADDED' for row in outside)
    summary = ['VERIFIED_REPORT: ' + str(report), 'OUTSIDE_CHANGES_TOTAL: ' + str(len(outside)),
               'OUTSIDE_CHANGES_ALL_ADDITIONS: ' + str(valid_additions)]
    refs = sorted({row[5] for row in outside if row[2] != 'REMOVED'})
    if any(not re.fullmatch(r'[A-Za-z_]\w*', ref) for ref in refs):
        raise ValueError('Unsupported library identifier in change list')
    (out / 'ChangedRefs.tcl').write_text('set ChangedRefs {' + ' '.join(refs) + '}\n')
    (out / 'outside_changes.tsv').write_text(''.join('\t'.join(row) + '\n' for row in outside))
    for ref in refs:
        summary.append('OUTSIDE_REFERENCE_COUNT: ' + ref + ' ' + str(sum(row[5] == ref for row in outside)))
    source_evidence = json.loads((previous / 'source/Evidence.json').read_text())
    functional = Path(source_evidence['functional_run'])
    bundle = Path(source_evidence['bundle'])
    std_db = Path((out / 'StdDb.txt').read_text().strip())
    override = os.environ.get('TPU_STDCELL_VERILOG')
    roots = [Path(value).expanduser() for value in override.split(os.pathsep)] if override else [std_db.parents[2]]
    paths = []
    for root in roots:
        if root.is_file():
            paths.append(root)
        elif root.is_dir():
            for pattern in ('*.v', '*.v.gz', '*.sv', '*.sv.gz'):
                paths += list(root.rglob(pattern))
    required = set(after.values()) - {'RAMSP1024X16', '**logic_0**', '**logic_1**'}
    models, missing = choose_models(required, sorted(set(paths)))
    summary += ['STDCELL_MODEL_SEARCH: ' + ' | '.join(str(path) for path in roots),
                'STDCELL_REQUIRED_REFERENCES: ' + str(len(required)),
                'STDCELL_MODEL_FILES_SCANNED: ' + str(len(paths)),
                'STDCELL_MODEL_STATUS: ' + ('MISSING' if missing else 'COVERED_REQUIRES_VCS_COMPILE')]
    if missing:
        summary.append('MISSING_MODEL_REFERENCES: ' + ','.join(sorted(missing)))
    model_dir = out / 'models'
    model_dir.mkdir()
    library_lines, model_inputs = [], {}
    for index, model in enumerate(models):
        target = model_dir / (str(index) + '_' + re.sub(r'\.gz$', '', model.name))
        target.write_bytes(gzip.decompress(model.read_bytes()) if model.suffix == '.gz' else model.read_bytes())
        library_lines.append('-v ' + str(target))
        library_lines += ['+incdir+' + str(model.parent)]
        model_inputs[str(model)] = sha(model)
    candidate = out / 'candidate.v'
    shutil.copy2(previous / 'mapped/candidate.v', candidate)
    original = (functional / 'project/Files.f').read_text().splitlines()
    lines = [line for line in original if line.startswith('+')]
    lines += library_lines + [str(candidate)]
    for line in original:
        if not line or line.startswith('+'):
            continue
        path = Path(line)
        if path.parent == bundle / 'Rtl' or path == bundle / 'Backend/e203_subsys_nice_core.sv':
            continue
        lines.append(line)
    vendor_file = None
    for line in (functional / 'compile.log').read_text(errors='replace').splitlines():
        if 'RAMSP1024X16.v' in line:
            found = re.search(r"['\"]([^'\"]*/RAMSP1024X16\.v)['\"]", line)
            if found and Path(found[1]).is_file():
                vendor_file = Path(found[1])
                break
    if vendor_file is None:
        vendor_file = Path(os.environ.get('SRAM_LIBRARY_ROOT', '/storage1/admin_public_dir/SRAM_Lib_2025')) / 'RAMSP1024X16/verilog/RAMSP1024X16.v'
    if sha(vendor_file) != '81b55d87d5e6821d44037d6f0290ec89c9edb9582eb1932957f181aefc300d51':
        raise ValueError('Different vendor SRAM model')
    lines.append(str(vendor_file))
    (out / 'Gate.f').write_text('\n'.join(lines) + '\n')
    (out / 'Bundle.txt').write_text(str(bundle) + '\n')
    (out / 'Functional.txt').write_text(str(functional) + '\n')
    (out / 'ModelsReady.txt').write_text('0\n' if missing else '1\n')
    (out / 'OutsideAdditionsOnly.txt').write_text('1\n' if valid_additions else '0\n')
    record = {'report': str(report), 'original': str(previous), 'model_inputs_sha256': model_inputs,
              'candidate_sha256': sha(candidate), 'vendor_model': str(vendor_file),
              'vendor_sha256': sha(vendor_file), 'outside_changes': outside,
              'copied_model_sha256': {str(path): sha(path) for path in model_dir.iterdir()},
              'missing_models': sorted(missing), 'power_activity': 'not captured in this run'}
    (out / 'GateInputs.json').write_text(json.dumps(record, indent=2) + '\n')
    (out / 'preparation.txt').write_text('\n'.join(summary) + '\n')
    print('\n'.join(summary))


def recheck_gate(out):
    recheck(out)
    record = json.loads((out / 'GateInputs.json').read_text())
    paths = dict(record['model_inputs_sha256'], **record['copied_model_sha256'])
    paths[str(out / 'candidate.v')] = record['candidate_sha256']
    paths[record['vendor_model']] = record['vendor_sha256']
    for name, expected in paths.items():
        if sha(Path(name)) != expected:
            raise ValueError('Gate input changed: ' + name)


if __name__ == '__main__':
    main()
