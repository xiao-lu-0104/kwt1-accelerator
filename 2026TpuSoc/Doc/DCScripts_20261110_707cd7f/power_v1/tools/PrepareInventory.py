"""Inventory mapped FF reset unknowns and prepare explicit binary-start comparisons."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
from ReadProbe import module, instances, bindings, input_names, sha

ROOT_SCOPE = 'SharedTest.Cpu.u_e203_cpu.u_e203_nice_core'


def select(previous):
    choices = [previous.resolve()] if previous else sorted(
        (Path.home() / 'soc').glob('tpusoc_gate_boot_20261105_*'),
        key=lambda path: path.stat().st_mtime, reverse=True)
    for path in choices:
        try:
            record = json.loads((path / 'BootInputs.json').read_text())
            if 'BOOT_CASE: ff1_seed0 FAIL' not in (path / 'runner.log').read_text():
                raise ValueError('Expected recorded full-system failure after unit reset tests')
            for name, expected in record['inputs'].items():
                if sha(Path(name)) != expected:
                    raise ValueError('Input changed: ' + name)
            for line in (path / 'tools/MANIFEST.sha256').read_text().splitlines():
                expected, name = line.split(None, 1)
                if sha(path / 'tools' / name.strip()) != expected:
                    raise ValueError('Tool changed: ' + name)
            return path, record
        except (OSError, ValueError, KeyError):
            if previous:
                raise
    raise ValueError('No unchanged boot failure found')


def designs(text):
    return {match[1]: match[0] for match in re.finditer(
        r'(?m)^\s*module\s+([A-Za-z_]\w*)\b.*?\bendmodule\b', text, re.S)}


def path_join(parent, child):
    return parent + '.' + child + (' ' if child.startswith('\\') else '')


def inventory(candidate, models):
    rows, unsupported, opaque = [], [], Counter()

    def walk(ref, scope, chain):
        if ref in chain:
            raise ValueError('Recursive design hierarchy: ' + ref)
        clean_design = re.sub(r'/\*.*?\*/|//[^\n]*', '', candidate[ref], flags=re.S)
        if re.search(r'\balways(?:_ff|_comb|_latch)?\b', clean_design):
            raise ValueError('Procedural candidate module requires separate inventory: ' + ref)
        for cell, name, ports in instances(candidate[ref]):
            where = path_join(scope, name)
            if cell in candidate:
                walk(cell, where, chain + [ref])
                continue
            body = models.get(cell, '')
            clean = re.sub(r'/\*.*?\*/|//[^\n]*', '', body, flags=re.S)
            if not re.search(r'\budp_\w*(?:dff|latch)\w*\b', clean, re.I):
                if not body:
                    opaque[cell] += 1
                continue
            ins = input_names(body)
            outs = []
            for match in re.finditer(r'\boutput\s+([^;]+);', body):
                outs += [value.strip() for value in re.sub(r'\[[^\]]*\]|\b(?:wire|reg|logic)\b', '', match[1]).split(',')]
            outs = [pin for pin in ('Q', 'QN') if pin in outs]
            clock = next((pin for pin in ('CK', 'CP', 'CLK', 'C') if pin in ins), None)
            if not clock or 'D' not in ins or not outs or 'latch' in clean.lower():
                unsupported.append((where, cell))
                continue
            links = bindings(ports)
            if any(not links.get(pin) for pin in (clock, 'D')):
                raise ValueError('Unconnected clock/data: ' + where)
            rows.append({'scope': where, 'ref': cell, 'clock': clock, 'outputs': outs,
                         'primary': outs[0], 'data': 'D', 'random': hashlib.sha256(where.encode()).digest()[0] & 1})
            if len(rows) > 100000:
                raise ValueError('Unexpectedly large register inventory')
    walk('e203_subsys_nice_core', ROOT_SCOPE, [])
    if unsupported:
        raise ValueError('Sequential models not covered: ' + repr(unsupported[:12]))
    if not rows:
        raise ValueError('No mapped FFs found')
    if any(not name.startswith('RAMSP') for name in opaque):
        raise ValueError('Unclassified opaque leaves: ' + repr(dict(opaque)))
    return rows, opaque


def monitor(rows):
    controls = [row for row in rows if re.search(
        r'(?:State|Word|Beat|Beats|Count|Received|BufferValid|Direction|Invalid|Error|Busy|Valid|Ready|Index|Counter).*_reg', row['scope'].rsplit('.',1)[-1], re.I)]
    controls.sort(key=lambda row: (0 if '.Bus.' in row['scope'] else 1 if '.Dma.' in row['scope'] else 2, row['scope']))
    # Counter/state observations exclude PE arithmetic data arrays and SRAM internals.
    if not controls or len(controls) > 2500:
        raise ValueError('Unexpectedly broad control monitor: ' + str(len(controls)))
    word = [row for row in rows if row['scope'].endswith(r'.Bus.\Word_reg[0] ')]
    if len(word) != 1:
        raise ValueError('Expected diagnosed Word[0] FF')
    force_groups, releases = {0: [], 1: [], 2: []}, []
    snapshot, checks, control_snapshot = [], [], []
    for index, row in enumerate(rows):
        q = row['scope'] + '.' + row['primary']
        d = row['scope'] + '.D'
        label = json.dumps('RESET_QX: path=' + row['scope'] + ' ref=' + row['ref'] + ' Q=%b D=%b')
        snapshot.append(f'if ($isunknown({q})) begin UnknownCount++; $fdisplay(Fd, {label}, {q}, {d}); end')
        for pin in row['outputs']:
            target = row['scope'] + '.' + pin
            releases.append(f'release {target};')
            for pattern in (0, 1, 2):
                value = row['random'] if pattern == 2 else pattern
                if pin == 'QN' and 'Q' in row['outputs']:
                    value = 1 - value
                force_groups[pattern].append(f"force {target} = 1'b{value};")
    for index, row in enumerate(controls):
        q, d = row['scope'] + '.' + row['primary'], row['scope'] + '.D'
        label = json.dumps('RESET_CONTROL_QX: path=' + row['scope'] + ' Q=%b D=%b')
        control_snapshot.append(f'if ($isunknown({q})) begin ControlUnknown++; if (ControlUnknown <= 24) $display({label}, {q}, {d}); end')
        label = json.dumps('NEW_CONTROL_QX: path=' + row['scope'] + ' cycle=%0d previous_D=%b current_D=%b Q=%b')
        checks.append(f'''if (Seen[{index}] && $isunknown({q}) && Reports < 24) begin
    $display({label}, SharedTest.Cycles, PreviousD[{index}], {d}, {q}); Reports++; Seen[{index}]=0;
end
if (!$isunknown({q})) Seen[{index}] = 1;
PreviousD[{index}] = {d};''')
    word_q = word[0]['scope'] + '.' + word[0]['primary']
    parts = ['`timescale 1ns/1ps', 'module GateResetInventory;',
             f'bit [{len(controls)-1}:0] Seen = 0;', f'logic PreviousD [0:{len(controls)-1}];',
             'integer Mode, Pattern, Fd, UnknownCount=0, ControlUnknown=0, Reports=0;',
             'bit Released=0, Checked=0;', 'string SnapshotFile;', 'initial begin',
             'if (!$value$plusargs("INIT_ALL=%d",Mode) || (Mode!=0 && Mode!=1)) $fatal(1,"Explicit INIT_ALL=0/1 required");',
             'if (!$value$plusargs("INIT_PATTERN=%d",Pattern) || Pattern<0 || Pattern>2) $fatal(1,"Explicit INIT_PATTERN=0/1/2 required");',
             'if (!$value$plusargs("RESET_X_LIST=%s",SnapshotFile)) $fatal(1,"RESET_X_LIST required");',
             f'wait ({ROOT_SCOPE}.nice_rst_n === 1\'b0); #0.001;',
             'if (Mode==0) begin', f"force {word_q} = 1'b0;", 'end else begin', 'case(Pattern)']
    for pattern in (0, 1, 2):
        parts += [f'{pattern}: begin', '\n'.join(force_groups[pattern]), 'end']
    parts += ['endcase', 'end',
              '$display("INIT_APPLIED: all=%0d pattern=%0d; reset only",Mode,Pattern);',
              f'@(posedge {ROOT_SCOPE}.nice_clk); @(negedge {ROOT_SCOPE}.nice_clk); #0.001;',
              'if (Mode==0) begin', f'release {word_q};', 'end else begin', '\n'.join(releases), 'end',
              'Released=1;', '$display("INIT_RELEASED: time=%0t; no further DUT drive",$time);',
              f'repeat(2) @(negedge {ROOT_SCOPE}.nice_clk); #0.001;',
              f'if ({ROOT_SCOPE}.nice_rst_n !== 1\'b0) $fatal(1,"Reset released before inventory snapshot");',
              f'if ({ROOT_SCOPE}.Bus.Word !== 2\'b00 || {ROOT_SCOPE}.Bus.State !== 3\'b000) $fatal(1,"ICB reset state mismatch");',
              'Fd=$fopen(SnapshotFile,"w"); if (!Fd) $fatal(1,"Cannot open reset inventory output");',
              '\n'.join(snapshot), '\n'.join(control_snapshot), '$fclose(Fd);',
              f'$display("RESET_INVENTORY: total_FF={len(rows)} control_FF={len(controls)} unknown_Q=%0d unknown_control_Q=%0d file=%s",UnknownCount,ControlUnknown,SnapshotFile);',
              'Checked=1;', 'end',
              f'always @(posedge {ROOT_SCOPE}.nice_rst_n) if (!Released || !Checked) $fatal(1,"Reset deasserted before init release/check");',
              f'always @(negedge {ROOT_SCOPE}.nice_clk) if ({ROOT_SCOPE}.nice_rst_n === 1\'b1) begin',
              '\n'.join(checks), 'end',
              'final $display("INIT_FINAL: all=%0d pattern=%0d released=%b checked=%b new_control_QX=%0d",Mode,Pattern,Released,Checked,Reports);',
              'endmodule']
    return '\n'.join(parts) + '\n', controls


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--boot', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    boot, previous = select(args.boot)
    out = args.out.resolve()
    candidate = out / 'candidate.v'
    shutil.copy2(boot / 'candidate.v', candidate)
    lines = (boot / 'full.f').read_text().splitlines()
    models = {}
    for line in lines:
        if line.startswith('-v '):
            models.update(designs(Path(line[3:]).read_text(errors='replace')))
    rows, opaque = inventory(designs(candidate.read_text()), models)
    source, controls = monitor(rows)
    (out / 'GateResetInventory.sv').write_text(source)
    (out / 'Registers.json').write_text(json.dumps({'registers': rows, 'controls': controls, 'opaque': dict(opaque)}, indent=2) + '\n')
    (out / 'full.f').write_text('\n'.join(str(candidate) if line==str(boot / 'candidate.v') else line for line in lines) + '\n')
    for name in ('Bundle.txt', 'Functional.txt'):
        shutil.copy2(boot / name, out / name)
    fingerprints = dict(previous['inputs'])
    for name in ('candidate.v', 'GateResetInventory.sv', 'Registers.json', 'full.f'):
        path = out / name
        fingerprints[str(path)] = sha(path)
    (out / 'InventoryInputs.json').write_text(json.dumps({'boot': str(boot), 'inputs': fingerprints}, indent=2) + '\n')
    print('VERIFIED_BOOT_FAILURE:', boot)
    print('MAPPED_FF_INVENTORY:', len(rows), 'CONTROL_OBSERVATIONS:', len(controls), 'OPAQUE_LEAVES:', dict(opaque))
    print('SCOPE: only mapped accelerator FF output initial states; CPU and SRAM arrays untouched; all forces released after one reset clock')


if __name__ == '__main__':
    main()
