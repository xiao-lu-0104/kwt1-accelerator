"""Prepare bounded isolated diagnostics from unchanged, verified mapped inputs."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import shutil
from ReadProbe import select, module, instances, bindings, declarations, input_names, sha


def outputs(body):
    names = []
    for line in declarations(body):
        if line.startswith('output '):
            fields = re.sub(r'\[[^\]]*\]|\b(?:output|wire|reg|logic|signed)\b', '', line).strip(' ;')
            names.extend(part.strip() for part in fields.split(','))
    return names


def hierarchy(name, pin):
    # Whitespace terminates an escaped Verilog instance identifier.
    return 'GateIcbSmoke.Dut.' + name + (' ' if name.startswith('\\') else '') + '.' + pin


def observer(bus, definitions):
    statements, traces, driver_nets, used_nets = [], [], Counter(), set()
    for ref, name, ports in instances(bus):
        model = definitions[ref]
        links = bindings(ports)
        ins, outs = input_names(model), outputs(model)
        for pin in outs:
            net = links.get(pin, '')
            if re.fullmatch(r'n\d+', net):
                driver_nets[net] += 1
        for pin in ins:
            used_nets.update(re.findall(r'\bn\d+\b', links.get(pin, '')))
        if re.search(r'State_reg|Word_reg|Direction_reg|Invalid_reg', name):
            if not all(pin in links for pin in ('D', 'Q', 'CK')):
                raise ValueError('Unexpected control FF pins: ' + name)
            traces.append((name, hierarchy(name, 'D'), hierarchy(name, 'Q')))
        # Scan only connected pins. Raw declarations can contain conditional power pins.
        connected_inputs = [pin for pin in ins if links.get(pin)]
        if 'CK' in ins or not connected_inputs:
            continue
        vector = '{' + ','.join(hierarchy(name, pin) for pin in connected_inputs) + '}'
        for pin in outs:
            if not links.get(pin):
                continue
            value = hierarchy(name, pin)
            missing = [key for key in ins if not links.get(key)]
            label = json.dumps('CELL_XSOURCE: ref=' + ref + ' instance=' + name + ' output=' + pin
                               + ' connected_inputs=' + ','.join(connected_inputs)
                               + ' raw_unbound=' + ','.join(missing) + ' inputs=%h output=%h time=%0t')
            statements.append(f'if ($isunknown({value}) && !$isunknown({vector}) && Reports < 16) begin\n'
                              f'    $display({label}, {vector}, {value}, $time); Reports = Reports + 1;\nend')
    for match in re.finditer(r'\bassign\s+(n\d+)\s*=', bus):
        driver_nets[match[1]] += 1
    for net in sorted(used_nets - driver_nets.keys()):
        print('STATIC_NO_CELL_OR_ASSIGN_DRIVER:', net, '(inspect declaration/other driver before concluding)')
    for net, count in sorted(driver_nets.items()):
        if count > 1:
            print('STATIC_MULTIPLE_DRIVERS:', net, count)
    if not traces or not statements:
        raise ValueError('No control FF traces or combinational checks generated')
    body = ['`timescale 1ns/1ps', 'module IcbConeWatch;', 'integer Reports = 0, Edges = 0;',
            'task automatic Scan;', '\n'.join(statements), 'endtask',
            'always @(posedge GateIcbSmoke.Clock) begin', 'Edges = Edges + 1;',
            '$display("CONE_PRE: edge=%0d time=%0t reset=%b request=%b response=%b state=%b word=%b", Edges, $time, GateIcbSmoke.ResetN, GateIcbSmoke.RequestValid, GateIcbSmoke.ResponseValid, GateIcbSmoke.Dut.State, GateIcbSmoke.Dut.Word);']
    for name, data, q in traces:
        label = json.dumps('CONE_FF_PRE: ' + name + ' D=%b Q=%b')
        body.append(f'$display({label}, {data}, {q});')
    body += ['#0.001;', '$display("CONE_POST: edge=%0d time=%0t state=%b word=%b", Edges, $time, GateIcbSmoke.Dut.State, GateIcbSmoke.Dut.Word);', 'Scan();', 'end',
             'always @(negedge GateIcbSmoke.Clock) begin #0.001; Scan(); end', 'endmodule']
    return '\n'.join(body) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    probe, record = select(args.probe)
    out = args.out.resolve()
    gate = Path(record['gate'])
    gate_record = json.loads((gate / 'GateInputs.json').read_text())
    candidate = out / 'candidate.v'
    shutil.copy2(probe / 'candidate.v', candidate)
    text = candidate.read_text()
    bus = module(text, 'TpuIcb')
    libraries = [line for line in (probe / 'candidate.f').read_text().splitlines()
                 if line.startswith(('-v ', '+incdir+'))]
    model_paths = [Path(line[3:]) for line in libraries if line.startswith('-v ')]
    definitions = {}
    for path in model_paths:
        source = path.read_text(errors='replace')
        for match in re.finditer(r'(?m)^\s*module\s+([A-Za-z_]\w*)\b.*?\bendmodule\b', source, re.S):
            definitions.setdefault(match[1], match[0])
    primitive_lines = []
    for path in model_paths + [Path(gate_record['vendor_model'])]:
        source = path.read_text(errors='replace')
        for match in re.finditer(r'(?m)^\s*primitive\s+(\w+)\b.*?\bendprimitive\b', source, re.S):
            if match[1] == 'udp_dff':
                primitive_lines += ['PRIMITIVE_FILE: ' + str(path), match[0]]
    (out / 'DffPrimitives.txt').write_text('\n'.join(primitive_lines) + '\n')
    print('DFF_PRIMITIVES_BEGIN')
    print('\n'.join(primitive_lines))
    print('DFF_PRIMITIVES_END')
    (out / 'IcbConeWatch.sv').write_text(observer(bus, definitions))
    refs = {ref for ref, _, _ in instances(bus)}
    (out / 'BusModels.json').write_text(json.dumps({ref: definitions[ref] for ref in sorted(refs)}, indent=2) + '\n')
    real = libraries + [str(candidate), gate_record['vendor_model']]
    (out / 'real.f').write_text('\n'.join(real) + '\n')
    (out / 'cell.f').write_text('\n'.join(libraries + [gate_record['vendor_model']]) + '\n')
    # This clone isolates sequential-model semantics only. It is never a deliverable netlist.
    ff_refs = {ref for ref, _, _ in instances(bus) if ref.startswith('DQV')}
    if ff_refs != {'DQV0_12TR40'}:
        raise ValueError('Unexpected bridge FF types: ' + repr(ff_refs))
    clone = re.sub(r'(?m)^(\s*)DQV0_12TR40\b', r'\1NbaDffDiagnostic', bus)
    if clone == bus:
        raise ValueError('No diagnostic FF substitution')
    diag = out / 'DiagnosticOnly.v'
    diag.write_text(text.replace(bus, clone, 1) + '\nmodule NbaDffDiagnostic(input CK,D, output reg Q); always @(posedge CK) Q <= D; endmodule\n')
    (out / 'diagnostic.f').write_text('\n'.join(libraries + [str(diag), gate_record['vendor_model']]) + '\n')
    fingerprints = dict(record['inputs'])
    for path in (candidate, diag, out / 'IcbConeWatch.sv', out / 'BusModels.json'):
        fingerprints[str(path)] = sha(path)
    (out / 'ConeInputs.json').write_text(json.dumps({'probe': str(probe), 'inputs': fingerprints}, indent=2) + '\n')
    print('VERIFIED_PROBE:', probe)
    print('DIAGNOSTIC_SUBSTITUTION: only a separate clone uses NBA reference FFs; original candidate and foundry models remain unchanged')


if __name__ == '__main__':
    main()
