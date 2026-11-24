"""Freeze a successful mapped run and inspect power/physical library metadata."""
import argparse
import gzip
import json
from pathlib import Path
import re
from ReadProbe import sha

CASES = {'ff1_all_pattern0': (1,25344,332348), 'ff1_all_pattern1': (1,25344,332348),
         'ff1_all_pattern2': (1,25344,332348), 'encoder_all_pattern2': (0,6336,1485712)}


def fingerprints(record):
    for name, expected in record['inputs'].items():
        if sha(Path(name)) != expected:
            raise ValueError('Frozen input changed: ' + name)


def select(previous):
    choices = [previous.resolve()] if previous else sorted(
        (Path.home() / 'soc').glob('tpusoc_gate_inventory_20261105_*'),
        key=lambda path: path.stat().st_mtime, reverse=True)
    for run in choices:
        try:
            record = json.loads((run / 'InventoryInputs.json').read_text())
            if 'RESULT: GATE_INVENTORY_COMPLETE' not in (run / 'runner.log').read_text():
                raise ValueError('Inventory did not complete')
            fingerprints(record)
            for case, (kind, values, cycles) in CASES.items():
                text = (run / (case + '.log')).read_text(errors='replace')
                required = [f'PASS SHARED: kind={kind} layers=1 values={values} cycles={cycles} ',
                            'ICB_MIRROR_FINAL: divergence_observed=0', 'released=1 checked=1 new_control_QX=0']
                if not all(item in text for item in required) or re.search(r'Fatal:|FATAL:|Error-\[', text):
                    raise ValueError('Expected fully passed golden task: ' + case)
            return run, record
        except (OSError, KeyError, ValueError):
            if previous:
                raise
    raise ValueError('No unchanged, fully passed inventory run found')


def text_file(path):
    data = path.read_bytes()
    if path.suffix == '.gz':
        data = gzip.decompress(data)
    return data.decode('utf-8', errors='replace')


def lef_geometry(text):
    cells = {}
    for match in re.finditer(r'(?ms)^\s*MACRO\s+(\S+)\s+(.*?)^\s*END\s+\1\s*(?=\n|$)', text):
        size = re.search(r'\bSIZE\s+([0-9.eE+-]+)\s+BY\s+([0-9.eE+-]+)\s*;', match[2])
        if size:
            width, height = map(float, size.groups())
            if width > 0 and height > 0:
                cells[match[1]] = {'width_um': width, 'height_um': height, 'area_um2': width*height}
    return cells


def inspect_libraries(roots, std_db, macro_root):
    geometry, evidence, inputs = {}, [], {}
    for root in roots:
        lef_paths = set()
        for pattern in ('*.lef','*.lef.gz','*.LEF','*.LEF.gz','*.LEF.GZ'):
            lef_paths.update(root.rglob(pattern))
        for path in sorted(lef_paths):
            if path.stat().st_size > 100_000_000:
                continue
            text = text_file(path)
            cells = lef_geometry(text)
            inputs[str(path)] = sha(path)
            for name, values in cells.items():
                geometry.setdefault(name, []).append(dict(values, source=str(path), sha256=inputs[str(path)]))
    lib_paths = set()
    for root, stem in ((roots[0], std_db.stem), (macro_root, 'RAMSP1024X16_tt_1p10v_1p10v_25c')):
        for suffix in ('.lib', '.lib.gz'):
            lib_paths.update(root.rglob(stem + suffix))
    for path in sorted(lib_paths):
        text = text_file(path)
        inputs[str(path)] = sha(path)
        if path.name == 'RAMSP1024X16_tt_1p10v_1p10v_25c.lib' and inputs[str(path)] != '7cf092257dfe18f32affee2d1a071b198b7cc68cb50b5bc71b0fdc98a79cfdb1':
            raise ValueError('Raw SRAM Liberty differs from reviewed source: ' + str(path))
        units = {key: re.findall(r'\b' + key + r'\s*:\s*([^;]+);', text)[:4]
                 for key in ('time_unit', 'voltage_unit', 'current_unit', 'leakage_power_unit', 'area_unit')}
        evidence.append({'path': str(path), 'sha256': inputs[str(path)], 'units': units,
                         'internal_power_groups': len(re.findall(r'\binternal_power\s*\(', text)),
                         'leakage_power_groups': len(re.findall(r'\bleakage_power\s*\(', text)),
                         'cell_leakage_power_entries': len(re.findall(r'\bcell_leakage_power\s*:', text))})
    return geometry, evidence, inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    run, record = select(args.inventory)
    out = args.out.resolve()
    boot = Path(record['boot'])
    cone = Path(json.loads((boot / 'BootInputs.json').read_text())['cone'])
    probe = Path(json.loads((cone / 'ConeInputs.json').read_text())['probe'])
    gate = Path(json.loads((probe / 'ProbeInputs.json').read_text())['gate'])
    gate_record = json.loads((gate / 'GateInputs.json').read_text())
    report = Path(gate_record['report'])
    report_record = json.loads((report / 'ReportInputs.json').read_text())
    fingerprints(report_record)
    original = Path(gate_record['original'])
    ddc = original / 'mapped/candidate.ddc'
    netlist = original / 'mapped/candidate.v'
    if sha(run / 'candidate.v') != sha(netlist) or sha(netlist) != gate_record['candidate_sha256']:
        raise ValueError('Activity run and checkpoint netlist do not match')
    std_db = Path((gate / 'StdDb.txt').read_text().strip())
    sp_db = Path((gate / 'SpDb.txt').read_text().strip())
    for path in (ddc, std_db, sp_db):
        if report_record['inputs'].get(str(path)) != sha(path):
            raise ValueError('Checkpoint/library not in frozen report: ' + str(path))
    macro_root = Path(gate_record['vendor_model']).parents[1]
    roots = [std_db.parents[2], macro_root]
    geometry, library_evidence, extra = inspect_libraries(roots, std_db, macro_root)
    (out / 'Geometry.json').write_text(json.dumps(geometry, indent=2) + '\n')
    (out / 'LibraryEvidence.json').write_text(json.dumps(library_evidence, indent=2) + '\n')
    lines = (run / 'full.f').read_text().splitlines()
    platform_memories = []
    for line in lines:
        if line and not line.startswith(('+','-')):
            path = Path(line)
            if any(part in path.name.lower() for part in ('itcm_ram','dtcm_ram','gnrl_ram','sim_ram','srams')):
                source = path.read_text(errors='replace')
                platform_memories.append({'path':str(path),'sha256':sha(path),
                    'modules':re.findall(r'\bmodule\s+(\w+)',source),
                    'simulation_array_present':bool(re.search(r'\b(?:reg|logic)\s+\[[^]]+\]\s+\w+\s*\[',source))})
    catalog = []
    for directory in sorted(macro_root.parent.glob('RAM*')):
        if directory.is_dir():
            catalog.append({'directory':str(directory),
                'verilog':[str(path) for path in directory.rglob('*.v')][:16],
                'tt_liberty':[str(path) for path in directory.rglob('*.lib*') if 'tt' in path.name.lower()][:16]})
    (out / 'SystemMemoryCatalog.json').write_text(json.dumps({'platform_sources':platform_memories,
        'available_sram_packages':catalog,'system_power_status':'CPU/interconnect/shared SRAM estimation not yet established'},indent=2)+'\n')
    (out / 'Smoke.f').write_text('\n'.join(line for line in lines if line.startswith(('-v ', '+incdir+'))) + '\n')
    paths = {'inventory': str(run), 'ddc': str(ddc), 'std_db': str(std_db), 'sram_db': str(sp_db),
             'report': str(report), 'original': str(original), 'candidate_sha256': sha(netlist)}
    (out / 'Paths.json').write_text(json.dumps(paths, indent=2) + '\n')
    for name, value in (('Ddc.txt', ddc), ('StdDb.txt', std_db), ('SpDb.txt', sp_db)):
        (out / name).write_text(str(value) + '\n')
    tracked = dict(record['inputs'], **report_record['inputs'], **extra)
    for path in [run / (name+'.log') for name in CASES] + [run / 'InventoryInputs.json', run / 'full.f',
            gate / 'GateInputs.json', report / 'ReportInputs.json']:
        tracked[str(path)] = sha(path)
    (out / 'PowerInputs.json').write_text(json.dumps({'paths': paths, 'inputs': tracked,
        'scope': 'NICE+TPU+DMA+ICB+112KiB private SRAM; excludes CPU/shared TCM'}, indent=2) + '\n')
    print('FROZEN_FUNCTIONAL_RUN:', run)
    print('MATCHED_CANDIDATE_SHA256:', sha(netlist))
    print('PPA_BOUNDARY: NICE+TPU+DMA+ICB+112KiB private SRAM; CPU/shared TCM excluded')
    print('SYSTEM_POWER_SCOPE_GAP: CPU/interconnect/shared SRAM must be added before claiming contest total power/energy')
    print('PLATFORM_MEMORY_SOURCES:',len(platform_memories),'SRAM_PACKAGES_AVAILABLE:',len(catalog))
    print('LEF_GEOMETRY_REFERENCES:', len(geometry), 'RAW_LIBRARIES:', len(library_evidence))
    for item in library_evidence:
        print('LIB_POWER_METADATA:', json.dumps(item, sort_keys=True))


if __name__ == '__main__':
    main()
