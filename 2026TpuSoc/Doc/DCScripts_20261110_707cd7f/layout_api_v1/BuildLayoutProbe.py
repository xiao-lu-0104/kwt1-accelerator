"""Freeze a short installed-API inspection; never opens historical designs."""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    tcl = (HERE / 'LayoutApiProbe.tcl').read_text(encoding='utf-8')
    entry = '''#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$HOME/soc"
work=$(mktemp -d "$HOME/soc/tpusoc_layout_api_20261110_707cd7f_XXXXXX")
echo "WORK_DIR: $work"
cat > "$work/LayoutApiProbe.tcl" <<'LAYOUT_API_707CD7F'
''' + tcl + '''LAYOUT_API_707CD7F
icc=/eda/synopsys/icc2/icc2_2022.03-SP2-1/bin/icc2_shell
test -x "$icc"
cd "$work"
exec > >(tee "$work/probe.log") 2>&1
trap 'rc=$?; echo "LAYOUT_API_EXIT: $rc"; echo "WORK_DIR: $work"' EXIT
timeout --signal=TERM --kill-after=15s 180s "$icc" -file "$work/LayoutApiProbe.tcl"
'''
    name = 'tpusoc_layout_api_20261110_707cd7f_v1.sh'
    p = ROOT / 'workspace/Server' / name
    data = entry.encode('utf-8')
    with p.open('xb') as f:
        f.write(data)
    digest = hashlib.sha256(data).hexdigest()
    command = '''python3 -c 'from pathlib import Path; import hashlib,sys; p=Path.home()/"Desktop/NAME"; b=p.read_bytes(); d=(b.decode("utf-8-sig").replace("\\r\\n","\\n").replace("\\r","\\n").strip("\\n")+"\\n").encode("utf-8"); h=hashlib.sha256(d).hexdigest(); print("BYTES:",len(d),"SHA:",h); h=="SHA" or sys.exit("SHA_MISMATCH: not executed"); q=p.with_name("tpusoc_layout_api_20261110_707cd7f_verified.sh"); q.open("xb").write(d)' && bash ~/Desktop/tpusoc_layout_api_20261110_707cd7f_verified.sh
'''.replace('NAME', name).replace('"SHA"', '"' + digest + '"')
    (HERE / 'NormalizeLayoutApiCommand.txt').write_text(command, encoding='utf-8')
    helper = '''[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$taskRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\\..'))
$taskEntry = Join-Path $taskRoot 'workspace\\Server\\NAME'
if ((Get-FileHash -LiteralPath $taskEntry -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'DIGEST') {
    throw 'Frozen layout API probe changed; clipboard not modified.'
}
Set-Clipboard -Value ([System.IO.File]::ReadAllText($taskEntry, [System.Text.Encoding]::UTF8))
Write-Host 'CLIPBOARD_READY: paste and save Desktop/NAME, then run NormalizeLayoutApiCommand.txt.'
'''.replace('NAME', name).replace('DIGEST', digest)
    (HERE / 'CopyLayoutApiToClipboard.ps1').write_text(helper, encoding='utf-8')
    print(name, len(data), digest)


if __name__ == '__main__':
    main()
