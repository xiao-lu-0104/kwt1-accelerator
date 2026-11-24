"""Regular interface-grouped IO plan and independent native-coordinate checks."""
import csv
import json
import math
from pathlib import Path
import re
import sys

GRID = 0.14
MIN_PITCH = 1.12
CORNER = 20.0
GROUP_GAP = 8


def natural(name):
    return tuple((1, int(x)) if x.isdigit() else (0, x) for x in re.split(r'(\d+)', name))


def family(name):
    base = name.split('[', 1)[0]
    if base in ('clk', 'rst_n', 'test_mode', 'core_csr_clk', 'inspect_core_clk'):
        return '00_clock_reset'
    for prefix in ('ext2itcm', 'ext2dtcm', 'ppi', 'clint', 'plic', 'fio', 'mem'):
        if base.startswith(prefix + '_'):
            return '10_' + prefix
    if base.startswith(('dbg_', 'cmt_', 'wr_', 'dcsr_', 'dpc_', 'dscratch_')):
        return '20_debug'
    if base.startswith('inspect_'):
        return '21_inspect'
    if base.startswith(('pc_rtvec', 'core_', 'tcm_', 'ext_irq', 'sft_irq', 'tmr_irq', 'tm_stop')):
        return '01_control'
    # Keep an unrecognized complete bus together; never silently omit a port.
    return '30_other_' + base


def quote_tcl(text):
    # Braced Tcl words are safe for ordinary netlist port names, including [bit].
    if any(c in text for c in '{}\\\n\r\t'):
        raise ValueError('Unsupported Tcl port spelling: ' + repr(text))
    return '{' + text + '}'


def plan(directory):
    directory = Path(directory)
    bounds = [float(v) for v in (directory / 'DieBoundary.txt').read_text().split()]
    if len(bounds) != 4 or not all(math.isfinite(v) for v in bounds):
        raise ValueError('Invalid native die boundary')
    x1, y1, x2, y2 = bounds
    if min(x2-x1, y2-y1) <= 2*CORNER:
        raise ValueError('Insufficient die edge length')
    groups, directions = {}, {}
    with (directory / 'PortInventory.tsv').open() as f:
        for row in csv.DictReader(f, delimiter='\t'):
            name, direction = row['port'], row['direction'].lower()
            quote_tcl(name)
            if name in directions or direction not in ('in', 'out', 'inout', 'input', 'output'):
                raise ValueError('Duplicate port or unexpected direction: ' + name)
            directions[name] = direction
            groups.setdefault(family(name), []).append(name)
    if len(directions) < 100:
        raise ValueError('Unexpectedly small full-system port inventory')
    # The side labels are geometric; no dependence on ICC2 side-number conventions.
    sides = {k: [] for k in ('left', 'bottom', 'right', 'top')}
    lengths = {'left': y2-y1, 'right': y2-y1, 'top': x2-x1, 'bottom': x2-x1}
    for group in sorted(groups):
        names = sorted(groups[group], key=natural)
        if group.startswith(('00_', '01_')):
            side = 'left'
        elif group in ('20_debug', '21_inspect'):
            side = 'top'
        else:
            # Balance complete interfaces by occupied edge fraction; never split a bus.
            side = min(sides, key=lambda s: (sum(len(v)+GROUP_GAP for _, v in sides[s])+len(names))/(lengths[s]-2*CORNER))
        sides[side].append((group, names))
    pins = []
    for side, interfaces in sides.items():
        count = sum(len(names) for _, names in interfaces)
        if not count:
            continue
        slots = count + GROUP_GAP * max(0, len(interfaces)-1) + 1
        pitch = math.floor((lengths[side]-2*CORNER)/slots/GRID)*GRID
        if pitch < MIN_PITCH:
            raise ValueError('IO side capacity exceeded: ' + side)
        slot = 1
        for group, names in interfaces:
            for name in names:
                along = round(CORNER + slot*pitch, 6)
                x = x1 if side == 'left' else x2 if side == 'right' else x1+along
                y = y1 if side == 'bottom' else y2 if side == 'top' else y1+along
                pins.append({'port': name, 'direction': directions[name], 'group': group, 'side': side,
                             'layer': 'M3' if side in ('left', 'right') else 'M4',
                             'x': round(x, 6), 'y': round(y, 6), 'pitch_um': round(pitch, 6)})
                slot += 1
            slot += GROUP_GAP
    if set(p['port'] for p in pins) != set(directions):
        raise ValueError('Incomplete plan')
    data = {'scope': 'signal ports only; no pad ring/package assignment', 'boundary_um': bounds,
            'grid_um': GRID, 'corner_keepout_um': CORNER, 'pins': pins}
    (directory / 'PinPlan.json').write_text(json.dumps(data, indent=2)+'\n')
    with (directory / 'PinPlan.tsv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=list(pins[0]), delimiter='\t', lineterminator='\n')
        writer.writeheader(); writer.writerows(pins)
    lines = ['# Generated from native die/port inventory; original netlist is unchanged.']
    for p in pins:
        lines.append('IoConstrain '+quote_tcl(p['port'])+' '+p['layer']+' '+str(p['x'])+' '+str(p['y']))
    (directory / 'PinPlan.tcl').write_text('\n'.join(lines)+'\n')
    print('IO_PLAN_READY: ports='+str(len(pins))+' groups='+str(len(groups)), flush=True)
    return data


def validate(directory):
    directory = Path(directory)
    data = json.loads((directory / 'PinPlan.json').read_text())
    wanted = {p['port']: p for p in data['pins']}
    actual = {}
    with (directory / 'PortTerminalGeometry.tsv').open() as f:
        for row in csv.DictReader(f, delimiter='\t'):
            name = row['port']
            if name in actual or name not in wanted:
                raise ValueError('Duplicate/unplanned native terminal: '+name)
            coords = [float(row[k]) for k in ('x1', 'y1', 'x2', 'y2')]
            if not all(math.isfinite(x) for x in coords) or coords[2] < coords[0] or coords[3] < coords[1]:
                raise ValueError('Invalid native pin bbox: '+name)
            x, y = (coords[0]+coords[2])/2, (coords[1]+coords[3])/2
            p = wanted[name]
            # Allow a maximum two-track snap; explicit targets are not free placement.
            if max(abs(x-p['x']), abs(y-p['y'])) > 2*GRID+1e-6:
                raise ValueError('Native pin moved from planned location: '+name)
            layers = set(row['layers'].split(','))
            if layers != {p['layer']}:
                raise ValueError('Native pin layer differs: '+name+' '+str(layers))
            actual[name] = {'x': x, 'y': y, 'bbox': coords}
    if set(actual) != set(wanted):
        raise ValueError('Missing native signal terminals: '+str(sorted(set(wanted)-set(actual))))
    for side in ('left', 'right', 'bottom', 'top'):
        pins = [p for p in data['pins'] if p['side'] == side]
        axis = 'y' if side in ('left', 'right') else 'x'
        previous = None
        for p in pins:
            a = actual[p['port']]
            along = a[axis]
            if previous is not None and along-previous < MIN_PITCH-4*GRID-1e-6:
                raise ValueError('IO order/spacing violated: '+p['port'])
            previous = along
        # Adjacent boxes must be separated along the edge, not merely different centers.
        indexes = (1, 3) if axis == 'y' else (0, 2)
        for p, q in zip(pins, pins[1:]):
            if actual[p['port']]['bbox'][indexes[1]] >= actual[q['port']]['bbox'][indexes[0]]:
                raise ValueError('Native adjacent pin shapes overlap: '+p['port'])
    result = {'status': 'NATIVE_IO_COORDINATES_MATCH_GROUPED_PLAN', 'port_count': len(actual),
              'group_count': len(set(p['group'] for p in data['pins'])), 'boundary_um': data['boundary_um'],
              'limitations': 'coordinate/layer/edge order checks; native pin check report retained separately; no full routing DRC claim'}
    (directory / 'IoValidation.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


if __name__ == '__main__':
    plan(Path(sys.argv[1]))
