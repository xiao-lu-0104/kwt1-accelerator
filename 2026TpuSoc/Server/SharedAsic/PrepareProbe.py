"""Prepare strict-handshake baseline/candidate probes with a passive RTL ICB mirror."""
import argparse
import json
from pathlib import Path
import re
import shutil
from PrepareGate import check_manifest, recheck_gate
from RecoverReport import sha
from Verify import verify


def strict_test(text):
    changes = {
        'do @(posedge Clock); while (!CommandReady);':
        'do begin @(posedge Clock); if ($isunknown(CommandReady)) $fatal(1, "UNKNOWN_LOADER_COMMAND_READY cycle=%0d", Cycles); end while (!CommandReady);',
        'do @(posedge Clock); while (!ResponseValid);':
        'do begin @(posedge Clock); if ($isunknown(ResponseValid)) $fatal(1, "UNKNOWN_LOADER_RESPONSE_VALID cycle=%0d", Cycles); end while (!ResponseValid);'
    }
    for before, after in changes.items():
        if text.count(before) != 1:
            raise ValueError('Unexpected testbench handshake source')
        text = text.replace(before, after)
    before = 'Result = ResponseData;'
    if text.count(before) != 1:
        raise ValueError('Unexpected response sampling source')
    return text.replace(before, 'if (Read && $isunknown(ResponseData)) $fatal(1, "UNKNOWN_LOADER_READ_DATA cycle=%0d", Cycles);\n        ' + before)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gate', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--tools-sha', required=True)
    args = parser.parse_args()
    choices = [args.gate.resolve()] if args.gate else sorted(
        (Path.home() / 'soc').glob('tpusoc_shared_gate_20261105_*'), key=lambda path: path.stat().st_mtime, reverse=True)
    for gate in choices:
        try:
            check_manifest(gate / 'tools', args.tools_sha)
            recheck_gate(gate)
            if 'RESULT: FAIL stage=simulate_ff1' not in (gate / 'runner.log').read_text():
                raise ValueError('Expected failed gate v1 run')
            break
        except (OSError, ValueError, KeyError):
            if args.gate:
                raise
    else:
        raise ValueError('No unchanged gate v1 failure found')
    out = args.out.resolve()
    record = json.loads((gate / 'GateInputs.json').read_text())
    original = Path(record['original'])
    functional = Path((gate / 'Functional.txt').read_text().strip())
    bundle, _, _ = verify(functional, 'baeeca78a1b60d921fd7de97397946457b39f63cde73d126880ca763a2b1ec83')
    bench = out / 'StrictSharedTest.sv'
    bench.write_text(strict_test((bundle / 'Sim/SharedTest.sv').read_text()))
    rtl = (bundle / 'Rtl/TpuIcb.sv').read_text()
    reference, count = re.subn(r'\bmodule\s+TpuIcb\b', 'module IcbRtlReference', rtl)
    if count != 1:
        raise ValueError('Expected one tested TpuIcb definition')
    (out / 'IcbRtlReference.sv').write_text(reference)
    base_lines = (gate / 'Gate.f').read_text().splitlines()
    fingerprints = {}
    for mode in ('baseline', 'candidate'):
        source = original / 'mapped' / (mode + '.v')
        target = out / (mode + '.v')
        shutil.copy2(source, target)
        lines = [str(target) if line == str(gate / 'candidate.v') else
                 str(bench) if line == str(bundle / 'Sim/SharedTest.sv') else line for line in base_lines]
        lines.append(str(out / 'IcbRtlReference.sv'))
        (out / (mode + '.f')).write_text('\n'.join(lines) + '\n')
        fingerprints[str(source)] = sha(source)
        fingerprints[str(target)] = sha(target)
    candidate = (out / 'candidate.v').read_text()
    top = re.search(r'\bmodule\s+e203_subsys_nice_core\b.*?\bendmodule\b', candidate, re.S)
    instance = re.search(r'\b(\w+)\s+Bus\s*\(', top[0]) if top else None
    if not instance or not instance[1].startswith('TpuIcb'):
        raise ValueError('Cannot locate mapped Bus module')
    bus_name = instance[1]
    match = re.search(r'\bmodule\s+' + re.escape(bus_name) + r'\b.*?\bendmodule\b', candidate, re.S)
    if not match:
        raise ValueError('Mapped Bus definition missing')
    (out / 'MappedBus.v').write_text(match[0] + '\n')
    # Diagnostic substitution only. It is never accepted as the final netlist.
    replacement = re.sub(r'\bmodule\s+TpuIcb\b', 'module ' + bus_name, rtl, count=1)
    hybrid = candidate[:match.start()] + replacement + candidate[match.end():]
    (out / 'bus_rtl_control.v').write_text(hybrid)
    lines = (out / 'candidate.f').read_text().splitlines()
    lines = [str(out / 'bus_rtl_control.v') if line == str(out / 'candidate.v') else line for line in lines]
    (out / 'bus_rtl_control.f').write_text('\n'.join(lines) + '\n')
    models = [Path(line[3:]) for line in base_lines if line.startswith('-v ')]
    cells = sorted(set(re.findall(r'^\s*(\w+)\s+(?:\\\S+|\w+)\s*\(', match[0], re.M)) - {'module'})
    evidence = ['MAPPED_BUS_MODULE: ' + bus_name, 'MAPPED_BUS_CELL_TYPES: ' + ','.join(cells)]
    for path in models:
        text = path.read_text(errors='replace')
        for cell in cells:
            found = re.search(r'\bmodule\s+' + re.escape(cell) + r'\b.*?\bendmodule\b', text, re.S)
            if found and re.search(r'(?:DFF|SDFF|DF|LAT)', cell):
                evidence.append('SEQUENTIAL_MODEL: ' + cell)
                evidence.extend(found[0].splitlines()[:18])
        fingerprints[str(path)] = sha(path)
    warning_lines = (gate / 'compile.log').read_text(errors='replace').splitlines()
    warnings = []
    for index, line in enumerate(warning_lines):
        if re.search(r'Warning-|Error-|port|undriven', line, re.I):
            warnings += warning_lines[index:index+3]
    (out / 'compile_warnings.txt').write_text('\n'.join(warnings) + '\n')
    (out / 'bus_models.txt').write_text('\n'.join(evidence) + '\n')
    (out / 'Bundle.txt').write_text(str(bundle) + '\n')
    (out / 'Functional.txt').write_text(str(functional) + '\n')
    (out / 'ProbeInputs.json').write_text(json.dumps({'gate': str(gate), 'inputs': fingerprints,
        'strict_handshake_only': True, 'hybrid': 'diagnostic ICB substitution, not implementation'}, indent=2) + '\n')
    print('VERIFIED_GATE:', gate)
    print('STRICT_HANDSHAKE: reject unknown ready/valid and accepted read data; original comparisons preserved')
    print('\n'.join(evidence))
    print('COMPILE_WARNINGS_HEAD:')
    print('\n'.join(warnings[:30]))


if __name__ == '__main__':
    main()
