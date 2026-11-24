"""Clone verified failed gate inputs and collect default delay declarations."""
import argparse
import json
from pathlib import Path
import re
import shutil
from PrepareGate import check_manifest, recheck_gate
from RecoverReport import sha
from Verify import verify


def select(previous, tools_sha):
    choices = [previous.resolve()] if previous else sorted(
        (Path.home() / 'soc').glob('tpusoc_shared_gate_20261105_*'),
        key=lambda path: path.stat().st_mtime, reverse=True)
    for path in choices:
        try:
            check_manifest(path / 'tools', tools_sha)
            recheck_gate(path)
            text = (path / 'runner.log').read_text()
            if 'RESULT: FAIL stage=simulate_ff1' not in text:
                raise ValueError('Not the expected failed gate run')
            if 'ALL_OUTSIDE_ADDITIONS_ARE_LIBRARY_BUFFERS' not in text:
                raise ValueError('Missing successful buffer audit')
            return path
        except (ValueError, KeyError, OSError):
            if previous:
                raise
    raise ValueError('No unchanged failed gate v1 run found')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--tools-sha', required=True)
    args = parser.parse_args()
    previous = select(args.previous, args.tools_sha)
    out = args.out.resolve()
    functional = Path((previous / 'Functional.txt').read_text().strip())
    bundle, _, _ = verify(functional, 'baeeca78a1b60d921fd7de97397946457b39f63cde73d126880ca763a2b1ec83')
    candidate = out / 'candidate.v'
    shutil.copy2(previous / 'candidate.v', candidate)
    lines = (previous / 'Gate.f').read_text().splitlines()
    lines = [str(candidate) if line == str(previous / 'candidate.v') else line for line in lines]
    (out / 'Gate.f').write_text('\n'.join(lines) + '\n')
    original = (functional / 'project/Files.f').read_text().splitlines()
    # Control: same cell libraries/macros, original tested accelerator RTL.
    libraries = [line for line in lines if line.startswith(('-v ', '+incdir+'))]
    vendor = json.loads((previous / 'GateInputs.json').read_text())['vendor_model']
    control = libraries + original + [str(bundle / 'Server/Backend/SpFoundry.sv'), vendor]
    (out / 'Reference.f').write_text('\n'.join(control) + '\n')
    for name, value in [('Bundle.txt', bundle), ('Functional.txt', functional), ('Previous.txt', previous)]:
        (out / name).write_text(str(value) + '\n')
    evidence = []
    for line in lines:
        if not line.startswith('-v '):
            continue
        path = Path(line[3:])
        text = path.read_text(errors='replace')
        evidence.append('MODEL_FILE: ' + str(path) + ' SHA256=' + sha(path))
        selected = [(index, value.strip()) for index, value in enumerate(text.splitlines(), 1)
                    if re.search(r'`timescale|`ifdef.*(?:FUNC|DELAY)|specparam|\bspecify\b|=>|\*>', value)]
        evidence.extend(str(index) + ': ' + value[:240] for index, value in selected[:24])
    (out / 'model_delays.txt').write_text('\n'.join(evidence) + '\n')
    inputs = [candidate, Path(vendor), functional / 'project/Firmware.hex']
    inputs += [Path(line[3:]) for line in lines if line.startswith('-v ')]
    record = {'previous': str(previous), 'inputs': {str(path): sha(path) for path in inputs},
              'note': 'Only file list paths and passive observer added; no DUT edits'}
    (out / 'DiagInputs.json').write_text(json.dumps(record, indent=2) + '\n')
    print('VERIFIED_FAILED_GATE:', previous)
    print('CANDIDATE_SHA256:', sha(candidate))
    print('NO_DUT_CHANGES: input testbench, CPU, firmware, candidate and vendor models unchanged')
    print('\n'.join(evidence))


def recheck(out):
    record = json.loads((out / 'DiagInputs.json').read_text())
    for name, expected in record['inputs'].items():
        if sha(Path(name)) != expected:
            raise ValueError('Diagnostic input changed: ' + name)


if __name__ == '__main__':
    main()
