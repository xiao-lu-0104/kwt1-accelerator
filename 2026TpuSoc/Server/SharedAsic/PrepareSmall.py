"""Reuse verified probe inputs, emit small mapped-cell and bridge tests."""
import argparse
import json
from pathlib import Path
import re
import shutil
from ReadProbe import select, module, instances, bindings, declarations, sha


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
    bus = module(candidate.read_text(), 'TpuIcb')
    (out / 'MappedBus.v').write_text(bus + '\n')
    lines = (probe / 'candidate.f').read_text().splitlines()
    libraries = [line for line in lines if line.startswith(('-v ', '+incdir+'))]
    vendor = gate_record['vendor_model']
    (out / 'cell_std.f').write_text('\n'.join(libraries) + '\n')
    (out / 'cell_sram.f').write_text('\n'.join(libraries + [vendor]) + '\n')
    # Keep all emitted arithmetic helper definitions, but elaborate only TpuIcb.
    (out / 'icb.f').write_text('\n'.join(libraries + [str(candidate), vendor]) + '\n')
    # Preserve strict test and reference byte-for-byte from the previous probe.
    for name in ('StrictSharedTest.sv', 'IcbRtlReference.sv'):
        shutil.copy2(probe / name, out / name)
    full = [str(candidate) if line == str(probe / 'candidate.v') else
            str(out / 'StrictSharedTest.sv') if line == str(probe / 'StrictSharedTest.sv') else
            str(out / 'IcbRtlReference.sv') if line == str(probe / 'IcbRtlReference.sv') else line for line in lines]
    (out / 'full.f').write_text('\n'.join(full) + '\n')
    for name in ('Bundle.txt', 'Functional.txt'):
        shutil.copy2(probe / name, out / name)
    models = [Path(line[3:]).read_text(errors='replace') for line in libraries if line.startswith('-v ')]
    models.append(candidate.read_text())
    cache = {}
    def outputs(ref):
        if ref not in cache:
            for text in models:
                try:
                    body = module(text, ref)
                    names = []
                    for declaration in declarations(body):
                        if declaration.startswith('output '):
                            names += [part.strip() for part in re.sub(r'\[[^\]]*\]|\b(?:output|wire|reg|logic|signed)\b', '', declaration).strip(' ;').split(',')]
                    cache[ref] = names
                    break
                except ValueError:
                    continue
            cache.setdefault(ref, [])
        return cache[ref]
    drivers, seeds = {}, []
    for ref, name, ports in instances(bus):
        links = bindings(ports)
        if re.search(r'State_reg|Word_reg|Direction_reg', name) and 'D' in links:
            seeds.append(links['D'])
        for pin in outputs(ref):
            if links.get(pin):
                drivers.setdefault(links[pin], []).append((ref, name, links, pin))
                if links[pin].startswith('{'):
                    for bit in links[pin].strip('{} ').split(','):
                        bit = bit.strip()
                        if re.fullmatch(r'[A-Za-z_]\w*(?:\[\d+\])?', bit):
                            drivers.setdefault(bit, []).append((ref, name, links, pin))
    emitted = set()
    cone = []
    def visit(net, depth):
        if net in emitted or depth > 2:
            return
        emitted.add(net)
        found = drivers.get(net, [])
        if not found:
            cone.append('CONE_LEAF: ' + net)
            return
        for ref, name, links, pin in found:
            cone.append('CONE: ' + net + ' <- ' + ref + ' ' + name + ' ' + str(links))
            if len(found) > 1:
                cone.append('CONE_MULTIPLE_DRIVERS: ' + net)
            if 'DQV' not in ref:
                for key, value in links.items():
                    if key not in outputs(ref):
                        visit(value, depth + 1)
    for seed in seeds:
        visit(seed, 0)
    (out / 'control_cones.txt').write_text('\n'.join(cone) + '\n')
    fingerprints = dict(record['inputs'])
    for name in ('candidate.v', 'MappedBus.v', 'StrictSharedTest.sv', 'IcbRtlReference.sv'):
        fingerprints[str(out / name)] = sha(out / name)
    (out / 'SmallInputs.json').write_text(json.dumps({'probe': str(probe), 'inputs': fingerprints}, indent=2) + '\n')
    print('VERIFIED_PROBE:', probe)
    print('MIRROR_FIX: compare actual top-level nice_icb_cmd_size; unused child size is not a functional output')
    print('CONTROL_CONES_BEGIN')
    print('\n'.join(cone[:65]))
    print('CONTROL_CONES_END')


if __name__ == '__main__':
    main()
