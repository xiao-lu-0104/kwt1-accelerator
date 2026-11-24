"""Stage exactly the sources from a successful, immutable shared-SRAM run."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

TOP = 'e203_subsys_nice_core'
RTL = ('TpuPkg TpuLut TpuDot TpuDivide TpuSqrt TpuSram TpuRowBuffer '
       'TpuMatmul TpuGelu TpuVector TpuDma TpuTop TpuNice TpuIcb').split()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(run, expected_manifest):
    run = run.resolve()
    if 'RESULT: PASS SHARED_FUNCTIONAL (17 tasks;' not in (run / 'runner.log').read_text():
        raise ValueError('Shared functional run is not complete')
    cases = ['ff1_' + name for name in ('normal', 'zero', 'extreme',
             *(f'Layer{index}' for index in range(12)))] + ['encoder_one', 'encoder_twelve']
    for case in cases:
        text = (run / (case + '.log')).read_text()
        lines = [line for line in text.splitlines() if line.startswith('PASS SHARED:')]
        if len(lines) != 1:
            raise ValueError('Missing/ambiguous case result: ' + case)
        ff1 = case.startswith('ff1_')
        layers = 12 if case == 'encoder_twelve' else 1
        required = {'kind': int(ff1), 'layers': layers, 'values': 25344 if ff1 else 6336,
                    'DMA_read_bytes': 45952 if ff1 else 12672 + 99584 * layers,
                    'DMA_write_bytes': 50688 if ff1 else 12672,
                    'loaded_bytes': 45960 if ff1 else 12672 + 99592 * layers}
        fields = dict(field.split('=', 1) for field in lines[0].split()[2:])
        if any(int(fields.get(key, -1)) != value for key, value in required.items()):
            raise ValueError('Unexpected counts in ' + case)
        if int(fields.get('cycles', 0)) <= 0:
            raise ValueError('Missing measured cycles: ' + case)
    project = run / 'project'
    scope = json.loads((project / 'Scope.json').read_text())
    if (scope['scope'] != 'COMPETITION_CPU_TCM_FUNCTIONAL'
            or scope['configuration_modified'] or scope['cpu_datapath_modified']):
        raise ValueError('Not an unchanged competition-platform run')
    copied = project / 'e203_hbirdv2/rtl/e203'
    for name, sha in scope['copied_platform_sha256'].items():
        if digest(copied / name) != sha:
            raise ValueError('Copied platform changed: ' + name)
    sources = [Path(line) for line in (project / 'Files.f').read_text().splitlines()
               if line and not line.startswith('+')]
    wrappers = [path for path in sources if path.name == TOP + '.sv']
    if len(wrappers) != 1:
        raise ValueError('Expected one tested NICE wrapper')
    bundle = wrappers[0].parents[1]
    if digest(bundle / 'MANIFEST.sha256') != expected_manifest:
        raise ValueError('Expected reviewed shared_v1 bundle')
    for line in (bundle / 'MANIFEST.sha256').read_text().splitlines():
        sha, name = line.split('  ', 1)
        path = (bundle / name).resolve()
        if bundle.resolve() not in path.parents or digest(path) != sha:
            raise ValueError('Bundle changed: ' + name)
    design = [bundle / 'Rtl' / (name + '.sv') for name in RTL] + wrappers
    for path in design:
        if path not in sources:
            raise ValueError('Source was not in functional compilation: ' + str(path))
    return bundle, design, scope


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--manifest-sha', required=True)
    args = parser.parse_args()
    if args.run:
        run = args.run.expanduser().resolve()
        bundle, design, scope = verify(run, args.manifest_sha)
    else:
        runs = sorted((Path.home() / 'soc').glob('tpusoc_shared_20261105_*'),
                      key=lambda path: path.stat().st_mtime, reverse=True)
        for run in runs:
            try:
                bundle, design, scope = verify(run, args.manifest_sha)
                break
            except (ValueError, OSError, KeyError):
                continue
        else:
            raise ValueError('No unchanged successful shared_v1 run found')
    out = args.out.resolve()
    if out.exists():
        raise ValueError('Refusing existing synthesis source directory')
    out.mkdir(parents=True)
    for path in design + [bundle / 'Server/Backend/SpFoundry.sv']:
        shutil.copy2(path, out / path.name)
    synthesis = [out / path.name for path in design] + [out / 'SpFoundry.sv']
    (out / 'Sources.tcl').write_text('set Sources [list ' + ' '.join(
        '{' + str(path) + '}' for path in synthesis) + ']\n')
    record = {'functional_run': str(run), 'bundle': str(bundle), 'top': TOP,
              'bundle_manifest_sha256': args.manifest_sha,
              'scope': 'accelerator + NICE + DMA + ICB + 112 KiB private SRAM; CPU/shared TCM excluded',
              'source_sha256': {path.name: digest(path) for path in synthesis},
              'platform_scope': scope}
    (out / 'Evidence.json').write_text(json.dumps(record, indent=2) + '\n')
    print('VERIFIED_SHARED_RUN:', run)
    print('SYNTHESIS_BOUNDARY:', record['scope'])


if __name__ == '__main__':
    main()
