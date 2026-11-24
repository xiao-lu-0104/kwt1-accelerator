"""Make an isolated CPU/TCM regression using the platform's original sources."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
RTL = ['TpuPkg', 'TpuLut', 'TpuDot', 'TpuDivide', 'TpuSqrt', 'TpuSram',
       'TpuRowBuffer', 'TpuMatmul', 'TpuGelu', 'TpuVector', 'TpuDma', 'TpuTop', 'TpuNice', 'TpuIcb']


def generate_layout(out):
    layout = json.loads((ROOT / 'Sw/SharedLayout.json').read_text())
    number = lambda name: int(layout[name], 0)
    if number('input') + layout['input_bytes'] > number('output'):
        raise ValueError('Input overlaps output')
    if number('output') + layout['output_capacity'] > number('parameters'):
        raise ValueError('Output overlaps parameters')
    if number('parameters') + layout['parameters_capacity'] != number('work'):
        raise ValueError('Parameter/work boundary mismatch')
    end = number('dtcm_base') + layout['tcm_bytes']
    if not number('work') < end:
        raise ValueError('No firmware data/stack space')
    header = ['// Generated from Sw/SharedLayout.json.']
    sv = ['// Generated from Sw/SharedLayout.json.']
    for key, symbol in [('mailbox', 'MailboxBase'), ('input', 'InputBase'),
                        ('output', 'OutputBase'), ('parameters', 'ParameterBase'), ('dtcm_base', 'DTCMBase')]:
        header.append(f'#define TPU_{key.upper()} 0x{number(key):08x}')
        sv.append(f'localparam logic [31:0] {symbol} = 32\'h{number(key):08x};')
    offset = 0
    for name, size in layout['parameter_groups']:
        if size % 16:
            raise ValueError('Unaligned parameter group')
        header.append(f'#define TPU_PARAM_{name.upper()} {offset}')
        offset += size
    if offset != 99584 or offset > layout['parameters_capacity']:
        raise ValueError('Unexpected parameter layout')
    (out / 'SharedLayout.h').write_text('\n'.join(header) + '\n')
    (out / 'SharedLayout.svh').write_text('\n'.join(sv) + '\n')
    link = (ROOT / 'Sw/Link.ld').read_text()
    link = link.replace('ORIGIN = 0x80000000, LENGTH = 64K', 'ORIGIN = 0x80000000, LENGTH = 256K')
    link = link.replace('ORIGIN = 0x90000000, LENGTH = 64K',
                        f'ORIGIN = 0x{number("work"):08x}, LENGTH = {end-number("work")}')
    (out / 'Shared.ld').write_text(link)
    return layout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--local-widths', action='store_true', help='Local upstream comparison only; patch two widths in copied config')
    args = parser.parse_args()
    platform, out = args.platform.expanduser().resolve(), args.out.resolve()
    if out == platform or platform in out.parents or out == ROOT or out in ROOT.parents:
        raise ValueError('Output must be separate from original platform and project sources')
    installed = platform / 'vsim/install/rtl'
    source = installed if (installed / 'core/config.v').is_file() else platform / 'rtl/e203'
    if not (source / 'core/config.v').is_file():
        raise ValueError('Platform core/config.v not found')
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise ValueError('Output directory is not empty: ' + str(out))
    copied = out / 'e203_hbirdv2/rtl/e203'
    shutil.copytree(source, copied)
    config = copied / 'core/config.v'
    original = config.read_text()
    text = original
    if args.local_widths:
        for kind in ('ITCM', 'DTCM'):
            text, count = re.subn(r'(?m)^(`define\s+E203_CFG_' + kind + r'_ADDR_WIDTH\s+)16\b', r'\g<1>18', text)
            if count != 1:
                raise ValueError('Expected one upstream 64 KiB ' + kind + ' definition')
        config.write_text(text)
    for kind in ('ITCM', 'DTCM'):
        values = re.findall(r'(?m)^\s*`define\s+E203_CFG_' + kind + r'_ADDR_WIDTH\s+(\d+)\b', text)
        if values != ['18']:
            raise ValueError('Expected platform 256 KiB ' + kind)
    generate_layout(out)
    manifest = {str(path.relative_to(copied)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(copied.rglob('*')) if path.is_file()}
    # Copy is compiled. The original reference math/CPU assertions are retained.
    sources = [ROOT / 'Rtl' / (name + '.sv') for name in RTL]
    sources += [ROOT / 'Backend/e203_subsys_nice_core.sv', ROOT / 'Sim/SharedTest.sv']
    sources += [path for path in sorted(copied.rglob('*.v')) if path.name != 'e203_subsys_nice_core.v']
    include_dirs = [copied / 'core', out] + sorted({path.parent for path in copied.rglob('*.v')})
    lines = [*(f'+incdir+{path}' for path in dict.fromkeys(include_dirs)), *(str(path) for path in sources)]
    (out / 'Files.f').write_text('\n'.join(lines) + '\n')
    (out / 'Scope.json').write_text(json.dumps({
        'platform': str(platform), 'compiled_source': str(source),
        'scope': 'LOCAL_UPSTREAM_WIDTH_COMPARISON' if args.local_widths else 'COMPETITION_CPU_TCM_FUNCTIONAL',
        'configuration_modified': args.local_widths, 'cpu_datapath_modified': False,
        'original_config_sha256': hashlib.sha256((source / 'core/config.v').read_bytes()).hexdigest(),
        'copied_platform_sha256': manifest,
        'note': 'CPU/LSU/TCM integration; full peripheral SoC and STA are separate'
    }, indent=2) + '\n')
    print('SHARED_PREPARED', out)


if __name__ == '__main__':
    main()
