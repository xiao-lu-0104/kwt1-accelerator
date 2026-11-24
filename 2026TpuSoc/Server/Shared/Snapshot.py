"""Record or verify the exact files used by a shared-SRAM functional run."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('work', type=Path)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    work = args.work.resolve()
    target = work / 'SourceInputs.json'
    if args.verify:
        records = json.loads(target.read_text())
        changed = [record['path'] for record in records
                   if not Path(record['path']).is_file()
                   or hashlib.sha256(Path(record['path']).read_bytes()).hexdigest() != record['sha256']]
        if changed:
            raise ValueError('Inputs changed since compilation: ' + ', '.join(changed))
    else:
        if target.exists():
            raise ValueError('Snapshot already exists; preserve it and use --verify')
        paths = [Path(line) for line in (work / 'Files.f').read_text().splitlines() if not line.startswith('+')]
        paths += [ROOT / 'Sw' / name for name in ('SharedLayout.json', 'SharedStart.S', 'SharedMain.c',
                                                  'Encoder.c', 'Encoder.h', 'Tpu.h')]
        paths += [work / name for name in ('SharedLayout.h', 'SharedLayout.svh', 'Shared.ld',
                                          'Shared.bin', 'Firmware.hex', 'Files.f')]
        paths += [ROOT / 'Sim/E203.vlt', ROOT / 'Server/Shared/Local.vlt']
        records = [{'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                   for path in paths]
        target.write_text(json.dumps(records, indent=2) + '\n')
    print('SHARED_INPUTS_VERIFIED' if args.verify else 'SHARED_INPUTS_RECORDED', len(records))


if __name__ == '__main__':
    main()
