"""Summarize read-only PPA units and the small native-SAIF capability probe."""
import argparse
import json
from pathlib import Path
import re
from PreparePower import fingerprints


def saif_duration_seconds(text):
    scale = re.search(r'\(TIMESCALE\s+([0-9.eE+-]+)\s+(fs|ps|ns|us|ms|s)\s*\)', text, re.I)
    duration = re.search(r'\(DURATION\s+([0-9.eE+-]+)\s*\)', text, re.I)
    if not scale or not duration:
        raise ValueError('SAIF lacks timescale/duration')
    unit = {'fs':1e-15,'ps':1e-12,'ns':1e-9,'us':1e-6,'ms':1e-3,'s':1}[scale[2].lower()]
    value = float(duration[1])*float(scale[1])*unit
    if value <= 0:
        raise ValueError('Nonpositive SAIF duration')
    return value


def compare_area(used, geometry):
    rows, complete = [], True
    for ref, count, area in used:
        candidates = geometry.get(ref, [])
        matches = [item for item in candidates if abs(item['area_um2']-area) <= max(0.0001, area*0.001)]
        okay = bool(candidates) and len(matches)==len(candidates)
        complete &= okay
        rows.append({'reference':ref, 'count':count, 'library_area':area,
                     'status':'MATCH_UM2' if okay else 'MISSING_OR_INCONSISTENT_LEF', 'geometry':candidates})
    return rows, bool(used) and complete


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    record = json.loads((out / 'PowerInputs.json').read_text())
    fingerprints(record)
    used = []
    for line in (out / 'used_lib_cells.tsv').read_text().splitlines()[1:]:
        ref, count, area = line.split('\t')
        used.append((ref,int(count),float(area)))
    geometry = json.loads((out / 'Geometry.json').read_text())
    area_rows, physical = compare_area(used, geometry)
    (out / 'AreaGeometryReview.json').write_text(json.dumps(area_rows,indent=2)+'\n')
    total = sum(count*area for _,count,area in used)
    sram = sum(count*area for ref,count,area in used if ref=='RAMSP1024X16')
    smoke_status = (out / 'smoke_status.txt').read_text().strip()
    native = False
    duration = None
    try:
        text = (out / 'smoke/smoke.saif').read_text()
        duration = saif_duration_seconds(text)
        native = smoke_status=='PASS' and abs(duration-320e-9)<1e-12 and bool(re.search(r'\(TC\s+[1-9]\d*\s*\)',text))
    except (OSError,ValueError):
        pass
    capabilities = dict(line.split('\t') for line in (out / 'capabilities.tsv').read_text().splitlines())
    required = all(capabilities.get(name)=='1' for name in ('read_saif','report_saif','report_power'))
    units = (out / 'units.rpt').read_text(errors='replace')
    summary = ['PPA_PREFLIGHT_SUMMARY:', 'PPA_BOUNDARY: accelerator+112KiB private SRAM; CPU/shared TCM excluded',
               f'LIBRARY_LEAF_AREA: {total:.6f}', f'PRIVATE_SRAM_LIBRARY_AREA: {sram:.6f}',
               'AREA_PHYSICAL_UNIT: '+('UM2_CONFIRMED_AGAINST_ALL_USED_REFERENCE_LEF' if physical else 'PENDING_LEF_REVIEW'),
               f'LEF_MATCHED_REFERENCES: {sum(row["status"]=="MATCH_UM2" for row in area_rows)}/{len(area_rows)}',
               'POWER_COMMANDS_AVAILABLE: '+str(required), 'NATIVE_SAIF_SMOKE: '+('PASS' if native else 'NOT_READY'),
               'SAIF_SMOKE_STATUS: '+smoke_status, 'SAIF_SMOKE_DURATION_SECONDS: '+str(duration),
               'NEXT_FULL_TASK_ACTIVITY: '+('READY_TO_PREPARE' if native and required else 'REQUIRES_CAPABILITY_REVIEW'),
               'SYSTEM_POWER_STATUS: CPU/interconnect/shared SRAM still require estimation; accelerator result is not contest total',
               'POWER_NUMBERS: NOT_MEASURED; no full-task activity or annotated power run yet']
    if physical:
        summary += [f'TOTAL_CELL_FOOTPRINT_MM2: {total/1e6:.9f}', f'PRIVATE_SRAM_FOOTPRINT_MM2: {sram/1e6:.9f}',
                    f'LOGIC_CELL_FOOTPRINT_MM2: {(total-sram)/1e6:.9f}',
                    'AREA_SCOPE: sum of library cell footprints, excludes floorplan whitespace/CTS/routing/CPU/shared TCM']
    (out / 'summary.txt').write_text('\n'.join(summary)+'\n')
    print('\n'.join(summary))
    print('POWER_UNITS_REPORT_BEGIN')
    print('\n'.join(units.splitlines()[-28:]))
    print('POWER_UNITS_REPORT_END')
    for name in ('read_saif','report_saif','report_power'):
        path = out / 'help' / (name + '.txt')
        if path.exists():
            print('INSTALLED_COMMAND_HELP:',name)
            print('\n'.join(path.read_text(errors='replace').splitlines()[:30]))


if __name__ == '__main__':
    main()
