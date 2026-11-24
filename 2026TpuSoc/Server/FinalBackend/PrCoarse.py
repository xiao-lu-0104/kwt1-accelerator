"""Initial coarse placement on isolated copies of a verified ICC2 import."""
import argparse
import csv
import html
import json
import math
from pathlib import Path
import re
import shutil
import signal
import tarfile
import time

from Formal import TOP, NETLIST_SHA, read_status, tcl_list
from Preflight import sha, save_json, command, terminate
from PrStart import SUCCESS as IMPORT_SUCCESS, scalar, stage_result, library_check_evidence

HERE = Path(__file__).resolve().parent
SUCCESS = 'INITIAL_COARSE_PLACEMENT_COMPLETE_REVIEW_PENDING'


def tree_manifest(root):
    """Bounded, symlink-free snapshot; all paths are relative to the library root."""
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError('Expected ordinary library directory: ' + str(root))
    result, total, started = {}, 0, time.monotonic()
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Library contains a symlink: ' + str(path))
        if path.is_file():
            total += path.stat().st_size
            if len(result) >= 50000 or total > 2 * 1024 ** 3 or time.monotonic() - started > 45:
                raise ValueError('Library snapshot exceeds bounded inspection')
            result[path.relative_to(root).as_posix()] = sha(path)
        elif not path.is_dir():
            raise ValueError('Library contains a special file: ' + str(path))
    if not result:
        raise ValueError('Empty library directory: ' + str(root))
    return result


def verify_source(source):
    source = source.resolve()
    inputs = json.loads((source / 'PrInputs.json').read_text(encoding='utf-8'))
    summary = json.loads((source / 'PrSummary.json').read_text(encoding='utf-8'))
    if summary.get('status') != IMPORT_SUCCESS or summary.get('inputs_unchanged') is not True:
        raise ValueError('A successful unchanged ICC2 import is required')
    if sha(Path(inputs['netlist'])) != NETLIST_SHA:
        raise ValueError('Frozen accelerator netlist differs')
    for path, expected in inputs['inputs'].items():
        if sha(Path(path)) != expected:
            raise ValueError('Import input changed: ' + path)
    imported = summary['import']
    expected_lib = source / 'design/accelerator.nlib'
    expected_def = source / 'design/initial_floorplan.def'
    if (Path(imported['design_library']).resolve() != expected_lib or
            Path(imported['floorplan_def']).resolve() != expected_def):
        raise ValueError('Unexpected source library or DEF path')
    if (imported['native_status'].get('PRIVATE_MACROS') != ['56'] or
            imported['native_status'].get('UNBOUND_CELLS') != ['0']):
        raise ValueError('Source import counts not accepted')
    for label, stage in list(summary['libraries'].items()) + [('import', imported)]:
        expected = IMPORT_SUCCESS if label == 'import' else 'REFERENCE_LIBRARY_CREATED_REVIEW_PENDING'
        if (not stage.get('success') or not stage_result(stage['run'], stage['native_status'], expected)['success'] or
                sha(Path(stage['run']['log'])) != stage['run']['log_sha256']):
            raise ValueError('Source native stage changed or failed: ' + label)
        directory = source / ('design' if label == 'import' else 'library_' + label)
        if label != 'import':
            evidence = library_check_evidence(directory, stage['native_status'])
            if not evidence['accepted'] or evidence != stage['workspace_check_evidence']:
                raise ValueError('Source native workspace reports changed: ' + label)
    if set(summary['libraries']) != {'rvt', 'private'} or not expected_def.is_file():
        raise ValueError('Missing source reference libraries or initial DEF')
    # Native library contents were not fingerprinted at creation by the old entry.
    # Capture their current bytes now; do not claim a retrospective creation-time hash.
    libraries = {'design/accelerator.nlib': expected_lib,
                 'library_rvt/rvt.ndm': source / 'library_rvt/rvt.ndm',
                 'library_private/private.ndm': source / 'library_private/private.ndm'}
    return inputs, summary, libraries


def geometry(stage, expected=56):
    text = (stage / 'core_bbox.txt').read_text(encoding='utf-8')
    values = text.replace('{', ' ').replace('}', ' ').split()
    core = [float(value) for value in values]
    if len(core) != 4 or not all(math.isfinite(v) for v in core) or core[2] <= core[0] or core[3] <= core[1]:
        raise ValueError('Invalid rectangular core bounding box')
    rows, names = [], set()
    with (stage / 'macros.tsv').open(encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream, delimiter='\t'):
            name = row['instance']
            box = [float(row[key]) for key in ('x1', 'y1', 'x2', 'y2')]
            if name in names or not all(math.isfinite(v) for v in box):
                raise ValueError('Duplicate macro or invalid coordinates')
            names.add(name)
            if box[2] <= box[0] or box[3] <= box[1]:
                raise ValueError('Macro has empty bbox: ' + name)
            if abs((box[2] - box[0]) * (box[3] - box[1]) - 9148.5247) > 0.05:
                raise ValueError('Macro footprint differs from reviewed SRAM: ' + name)
            if box[0] < core[0] - 1e-5 or box[1] < core[1] - 1e-5 or box[2] > core[2] + 1e-5 or box[3] > core[3] + 1e-5:
                raise ValueError('Macro outside core: ' + name)
            rows.append({'name': name, 'bbox': box})
    if len(rows) != expected:
        raise ValueError('Expected exactly ' + str(expected) + ' macro bounding boxes')
    for index, first in enumerate(rows):
        a = first['bbox']
        for second in rows[index + 1:]:
            b = second['bbox']
            if min(a[2], b[2]) - max(a[0], b[0]) > 1e-5 and min(a[3], b[3]) - max(a[1], b[1]) > 1e-5:
                raise ValueError('Macro overlap: ' + first['name'] + ' / ' + second['name'])
    placement = (stage / 'report_placement.rpt').read_text(encoding='utf-8', errors='replace')
    counts = re.findall(r'(?:Total hard macro to hard macro overlaps|HM to HM overlaps in design[^\n:]*):\s*(\d+)', placement)
    if not counts or any(int(value) != 0 for value in counts) or re.search(r'^\s*(?:Error|Fatal):', placement, re.M | re.I):
        raise ValueError('Native hard-macro zero-overlap report required')
    # Use the native DEF placement states as an independent unplaced-macro check.
    definition = (stage / 'coarse_floorplan.def').read_text(encoding='utf-8', errors='strict')
    section = re.search(r'^\s*COMPONENTS\s+\d+\s*;(.*?)^\s*END COMPONENTS', definition, re.M | re.S)
    if not section:
        raise ValueError('DEF COMPONENTS section missing')
    placed = set()
    for entry in section.group(1).split(';'):
        match = re.match(r'\s*-\s+(\S+)\s+RAMSP1024X16(?=\s)', entry)
        if match:
            name = match.group(1)
            # DEF escaping protects special characters; our hierarchical names have no whitespace.
            name = re.sub(r'\\(.)', r'\1', name)
            if not re.search(r'\+\s+(?:PLACED|FIXED|COVER)\s+\(', entry):
                raise ValueError('Unplaced macro in DEF: ' + name)
            if name in placed:
                raise ValueError('Duplicate macro in DEF')
            placed.add(name)
    if placed != names:
        raise ValueError('Native macro inventory and DEF placement inventory differ')
    return {'status': 'MACRO_GEOMETRY_CHECKED', 'core_bbox_um': core, 'macros': rows,
            'macro_count': len(rows), 'macro_overlaps': 0, 'macros_outside_core': 0,
            'limitations': 'Rectangular core and macro geometry only; no routing accessibility, PG, grid, standard-cell legality or signoff acceptance'}


def write_svg(path, review):
    x1, y1, x2, y2 = review['core_bbox_um']
    width, height = x2 - x1, y2 - y1
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {} {}">'.format(width, height),
             '<rect width="100%" height="100%" fill="#f5f7fa" stroke="#273444"/>']
    for index, macro in enumerate(review['macros']):
        a, b, c, d = macro['bbox']
        parts.append('<rect x="{}" y="{}" width="{}" height="{}" fill="{}" stroke="#18334e" stroke-width="0.5"><title>{}</title></rect>'.format(
            a - x1, y2 - d, c - a, d - b, '#8bc4e8' if index % 2 else '#b5dce8', html.escape(macro['name'])))
    parts.append('</svg>')
    path.write_text('\n'.join(parts), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--source', required=True, type=Path)
    args = parser.parse_args()
    out, source = args.out.resolve(), args.source.resolve()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, terminate)
    snapshots, bound, result, review, error = {}, {}, None, None, None
    try:
        inputs, summary, libraries = verify_source(source)
        paths = [source / name for name in ('PrInputs.json', 'PrSummary.json', 'design/initial_floorplan.def')]
        paths += [p for p in HERE.iterdir() if p.is_file() and p.suffix in ('.py', '.tcl')]
        paths += [Path(p) for p in inputs['inputs']]
        paths += [Path(s['run']['log']) for s in list(summary['libraries'].values()) + [summary['import']]]
        bound = {str(p): sha(p) for p in paths}
        for relative, original in libraries.items():
            snapshot = tree_manifest(original)
            snapshots[str(original)] = snapshot
            destination = out / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(str(original), str(destination))
            if tree_manifest(destination) != snapshot:
                raise ValueError('Library copy differs: ' + relative)
        save_json(out / 'CoarseInputs.json', {'source': str(source), 'files': bound, 'source_libraries': snapshots,
                  'snapshot_scope': 'Current bytes captured before coarse placement; no creation-time library hash claimed',
                  'limits': {'icc2_seconds': 1200}, 'scope': inputs['scope'], 'rc_status': 'NOT_CONFIGURED'})
        stage = out / 'design'
        config = ''.join(scalar(name, value) for name, value in (
            ('PrDesignLib', stage / 'accelerator.nlib'), ('PrTop', TOP),
            ('PrExpectedLeaves', summary['import']['native_status']['LEAF_CELLS'][0]),
            ('PrDef', stage / 'coarse_floorplan.def')))
        config += 'set PrRefLibs ' + tcl_list([out / 'library_rvt/rvt.ndm', out / 'library_private/private.ndm']) + '\n'
        (stage / 'PrCoarseConfig.tcl').write_text(config, encoding='utf-8')
        print('PR_COARSE_SOURCE:', str(source), flush=True)
        print('PR_COARSE_MODE: isolated library copies; initial geometric placement; no RC/CTS/route/signoff', flush=True)
        run = command([inputs['icc2'], inputs['icc2_flag'], str(HERE / 'PrCoarse.tcl')], stage, 'icc2_coarse', 1200)
        status = read_status(stage / 'PrStatus.tsv')
        # Old PrStatus.tsv is not inside the copied .nlib; this stage starts a new status file.
        result = stage_result(run, status, 'COARSE_PLACEMENT_NATIVE_COMPLETE_REVIEW_PENDING', [stage / 'coarse_floorplan.def'])
        if status.get('LOGICAL_LEAF_SIGNATURE') != ['UNCHANGED'] or status.get('PRIVATE_MACROS') != ['56'] or status.get('UNBOUND_CELLS') != ['0']:
            result.update(success=False, status='COARSE_NATIVE_INVENTORY_NOT_ACCEPTED')
        if result['success']:
            review = geometry(stage)
            save_json(out / 'MacroGeometry.json', review)
            write_svg(out / 'MacroPlacement.svg', review)
    except (OSError, ValueError, KeyError) as why:
        error = str(why)
    unchanged = bool(snapshots and bound)
    try:
        for original, snapshot in snapshots.items():
            if tree_manifest(Path(original)) != snapshot:
                raise ValueError('Original library changed: ' + original)
        for path, expected in bound.items():
            if sha(Path(path)) != expected:
                raise ValueError('Original input changed: ' + path)
    except (OSError, ValueError) as why:
        unchanged, error = False, str(why)
    accepted = bool(result and result['success'] and review and unchanged and not error)
    report = {'status': SUCCESS if accepted else 'COARSE_PLACEMENT_INCOMPLETE_REVIEW_LOGS',
              'source': str(source), 'run': result, 'geometry': review, 'source_unchanged': unchanged, 'error': error,
              'limitations': 'Initial coarse placement only. Original FRAM-066 warnings remain; no physical netlist optimization, RC, PG routing, CTS, signal routing, standard-cell legality or timing signoff claimed.'}
    save_json(out / 'CoarseSummary.json', report)
    with tarfile.open(out / 'CoarseReports.partial.tar.gz', 'x:gz') as stream:
        for path in sorted(out.rglob('*')):
            if any(part.endswith(('.ndm', '.nlib')) for part in path.relative_to(out).parts):
                continue
            if path.is_file() and not path.is_symlink() and path.suffix in ('.json', '.tcl', '.py', '.log', '.txt', '.tsv', '.rpt', '.def', '.svg') and path.name not in ('runner.log', 'coarse_runner.log'):
                stream.add(path, arcname='CoarseReports/' + path.relative_to(out).as_posix(), recursive=False)
    (out / 'CoarseReports.sha256').write_text(sha(out / 'CoarseReports.partial.tar.gz') + '  CoarseReports.partial.tar.gz\n')
    print('PR_COARSE_NATIVE:', json.dumps(result, sort_keys=True), flush=True)
    if result and not result['success']:
        print('PR_COARSE_LOG_TAIL:', '\n'.join(Path(result['run']['log']).read_text(errors='replace').splitlines()[-30:]), flush=True)
    if error:
        print('PR_COARSE_ERROR:', error, flush=True)
    print('PR_MACRO_GEOMETRY:', '56 macros; zero overlaps; all inside rectangular core' if accepted else 'NOT_ACCEPTED', flush=True)
    print('PR_SOURCE_UNCHANGED:', unchanged, flush=True)
    if accepted:
        print('PR_COARSE_DESIGN:', str(out / 'design/accelerator.nlib'), flush=True)
        print('PR_MACRO_SVG:', str(out / 'MacroPlacement.svg'), flush=True)
    print('RESULT:', report['status'], flush=True)


if __name__ == '__main__':
    main()
