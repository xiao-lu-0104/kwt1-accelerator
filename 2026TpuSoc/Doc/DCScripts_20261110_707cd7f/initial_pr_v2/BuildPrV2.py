"""Freeze new grouped-IO initial placement; retain old package unchanged."""
import base64
import io
import json
from pathlib import Path
import tarfile
from BuildPr import build_files as base_files, ROOT, HERE, sha


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Expected unique insertion: '+old[:100])
    return text.replace(old, new, 1)


def build_files():
    files = base_files()
    place = files['tools/Place.tcl'].decode()
    place = replace_once(place, '    PrReport report_placement -hard_macro_overlap',
        '    source [file join [file dirname [info script]] RegularIo.tcl]\n'
        '    # IO changes physical terminals only; retain the exact logical leaf mapping.\n'
        '    set IoAfter [CurrentSignature]\n'
        '    if {[dict size $Before]!=[dict size $IoAfter]} {error "IO placement changed leaves"}\n'
        '    dict for {Name Ref} $Before {\n'
        '        if {![dict exists $IoAfter $Name] || [dict get $IoAfter $Name] ne $Ref} {error "IO changed leaf $Name"}\n'
        '    }\n'
        '    PrReport report_placement -hard_macro_overlap')
    files['tools/Place.tcl'] = place.encode()
    flow = files['tools/PrFlow.py'].decode()
    flow = replace_once(flow, 'from SelectSystem import select_system',
        'from SelectSystem import select_system\nfrom PinPlan import validate as validate_io')
    flow = replace_once(flow, '    geometry(stage, out, record[\'lef_macro_sizes\'])',
        "    geometry(stage, out, record['lef_macro_sizes'])\n"
        "    io_summary = validate_io(stage)\n"
        "    print('IO_VALIDATION:', json.dumps(io_summary, sort_keys=True), flush=True)\n")
    flow = replace_once(flow, "    (stage / 'CurrentConfig.tcl').write_text(cfg)",
        "    (stage / 'CurrentConfig.tcl').write_text(cfg)\n"
        "    shutil.copy2(HERE / 'PgCandidate.json', stage / 'PgCandidate.json')\n"
        "    shutil.copy2(HERE / 'PgCandidate.tcl', stage / 'PgCandidate.tcl')\n")
    flow = replace_once(flow, "        'original_inputs_unchanged': True, 'macro_count': 120, 'macro_bbox_overlap_count': 0,",
        "        'original_inputs_unchanged': True, 'macro_count': 120, 'macro_bbox_overlap_count': 0,\n"
        "        'io_validation': io_summary, 'pg_candidate_pitch_um': 42, 'pg_compiled': False,")
    files['tools/PrFlow.py'] = flow.encode()
    for name in ('PinPlan.py', 'RegularIo.tcl'):
        files['tools/'+name] = (HERE / name).read_bytes().replace(b'\r\n', b'\n')
    files['tools/PgCandidate.json'] = (json.dumps({'source_commit': '707cd7f4a0a4d416d11bac71112980079e0a9d34',
        'mesh_pitch_um': 42, 'historical_pitch_um': 84, 'status': 'CANDIDATE_ONLY_NOT_COMPILED',
        'requirement': 'denser mesh; do not reduce foundry minimum spacing',
        'blocking_review': 'old PG had 120 floating macros per net and 939 DRC including 776 M4 spacing; require new native macro shapes and via/blockage strategy before compile',
        'geometry_file': 'MacroPgGeometry.tsv', 'no_connectivity_drc_ir_em_acceptance': True}, indent=2)+'\n').encode()
    # Deliberately a guarded, separately saved proposal. No blind PG compile after initial placement.
    files['tools/PgCandidate.tcl'] = b'''# 42um pitch proposal only. Source only after macro-pin/via/blockage review.
if {![info exists PgGeometryReviewed] || !$PgGeometryReviewed} {
    error "Review current MacroPgGeometry.tsv and resolve macro/via/M4 blockage strategy before PG generation"
}
create_pg_mesh_pattern MESH707CD7F_42_CANDIDATE -layers {
    {{vertical_layer: M2} {width: 0.28} {spacing: interleaving} {pitch: 42} {offset: 10.08}}
    {{horizontal_layer: M3} {width: 0.28} {spacing: interleaving} {pitch: 42} {offset: 10.08}}
    {{vertical_layer: M4} {width: 0.28} {spacing: interleaving} {pitch: 42} {offset: 10.08}}
    {{horizontal_layer: M5} {width: 0.28} {spacing: interleaving} {pitch: 42} {offset: 10.08}}
    {{vertical_layer: M6} {width: 0.56} {spacing: interleaving} {pitch: 42} {offset: 10.08}}
    {{horizontal_layer: M7} {width: 1.12} {spacing: interleaving} {pitch: 42} {offset: 10.08}}
    {{vertical_layer: TM2} {width: 1.68} {spacing: interleaving} {pitch: 42} {offset: 10.08}}
}
# No strategies/compile_pg: all widths/offsets/vias/blockages remain candidate values.
'''
    config = json.loads(files['Config.json'].decode())
    config.update(io_scope='grouped complete interfaces and ascending bus bits; native terminal coordinate/layer/order audit',
                  pg_scope='42um candidate only, actual PG compile follows native macro geometry review',
                  layout_api_evidence='user native screenshot layout_api_20261110_707cd7f_qkcBsH exit0 elapsed11s')
    files['Config.json'] = (json.dumps(config, indent=2)+'\n').encode()
    return files


def main():
    files = build_files()
    files['PACKAGE.sha256'] = ''.join(sha(b)+'  '+n+'\n' for n, b in sorted(files.items())).encode()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as z:
        for n, b in sorted(files.items()):
            item = tarfile.TarInfo(n); item.size=len(b); item.mode=0o644; item.mtime=1704067200
            z.addfile(item, io.BytesIO(b))
    data = buf.getvalue()
    entry = '''#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$HOME/soc"
work=$(mktemp -d "$HOME/soc/tpusoc_initial_pr_v2_20261110_707cd7f_XXXXXX")
echo "WORK_DIR: $work"
base64 -d > "$work/payload.tar.gz" <<'INITIAL_PR_V2_707CD7F'
''' + base64.encodebytes(data).decode() + '''INITIAL_PR_V2_707CD7F
echo "''' + sha(data) + '''  $work/payload.tar.gz" | sha256sum -c -
tar -xzf "$work/payload.tar.gz" -C "$work"
cd "$work"
sha256sum --quiet -c PACKAGE.sha256
exec > >(tee "$work/runner.log") 2>&1
trap 'rc=$?; echo "INITIAL_PR_EXIT: $rc"; echo "WORK_DIR: $work"' EXIT
export PYTHONDONTWRITEBYTECODE=1
python3 -u tools/PrFlow.py "$work"
sha256sum --quiet -c PACKAGE.sha256
'''
    path = ROOT / 'workspace/Server/tpusoc_initial_pr_20261110_707cd7f_v2.sh'
    with path.open('xb') as f:
        f.write(entry.encode())
    digest=sha(path.read_bytes())
    template=(HERE/'NormalizePrCommand.txt').read_text()
    command=template.replace('tpusoc_initial_pr_20261110_707cd7f_v1.sh',path.name)
    command=command.replace('tpusoc_initial_pr_20261110_707cd7f_verified.sh','tpusoc_initial_pr_20261110_707cd7f_v2_verified.sh')
    command=command.replace('c1ee5c0fe4eebc58c5d85d6e9e51c717f7be8006c0a2bf0b439f9b67d3e4af8f',digest)
    (HERE/'NormalizePrV2Command.txt').write_text(command)
    helper='''[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$taskRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\\..'))
$taskEntry = Join-Path $taskRoot 'workspace\\Server\\NAME'
if ((Get-FileHash -LiteralPath $taskEntry -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'DIGEST') {
    throw 'Frozen initial PR v2 changed; clipboard not modified.'
}
Set-Clipboard -Value ([System.IO.File]::ReadAllText($taskEntry, [System.Text.Encoding]::UTF8))
Write-Host 'CLIPBOARD_READY: paste and save Desktop/NAME, then run NormalizePrV2Command.txt.'
'''.replace('NAME',path.name).replace('DIGEST',digest)
    (HERE/'CopyPrV2ToClipboard.ps1').write_text(helper)
    print(path.name, path.stat().st_size, digest)


if __name__ == '__main__':
    main()
