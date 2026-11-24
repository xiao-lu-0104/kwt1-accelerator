from __future__ import annotations

import base64
import hashlib
import pathlib
import textwrap

root = pathlib.Path(r"e:\chipdesign")
payload = root / "release" / "shared_sram_payload_fa5f062.tar.gz"
out_shell = root / "release" / "ApplySharedSram_viaVNC.sh"
out_copy = root / "release" / "CopySharedSramToClipboard.ps1"

files = [
    ("Makefile", "1a08f958d00bc450266f1d75d2f794d4f17602f5b422ead80c060ade385a664a"),
    ("Model/Roofline.py", "60d45d352d294d7f680742274ac95d1d74c930a485725a38e0d3992aa41fe4cf"),
    ("Server/SingleClock/LocalTest.sh", "94ab6279ac41c1cefb507587a17bfe2e6d7415fea0bb2b30387062a3fed0a72e"),
    ("Server/SingleClock/MakeLocalTest.py", "648eb8056e087f639ecb03ac51392e994797952d4369aca33b9a1a5d3f019772"),
    ("Sim/SharedSramModel.h", "a8630bf268b17fcd8492b069f63823462c9bcfbd1da5b773339ef89f10044888"),
    ("Sim/SharedSramTest.cpp", "2a46ec37929508c60890764f0db1665e38ff5279f87698a77ca3b059e7782679"),
    ("Sim/SocTest.cpp", "337f2c491ca508a245ffebe91e6645784889895e9bf1675ab6f8723d1fcaf4c9"),
]

actual = hashlib.sha256(payload.read_bytes()).hexdigest()
expected_payload = "NOT_USED"
b64 = base64.b64encode(payload.read_bytes()).decode("ascii")
b64_lines = "\n".join(textwrap.wrap(b64, 76))
sums = "\n".join(f"{h}  {p}" for p, h in files)

shell = f'''#!/usr/bin/env bash
set -euo pipefail
dest="${{1:-$PWD}}"
if [[ ! -f "$dest/Makefile" || ! -d "$dest/Sim" || ! -d "$dest/Rtl" ]]; then
  echo "ERROR: run this from the 2026TpuSoc repo root, or pass that root as the first argument." >&2
  exit 2
fi
stamp=$(date +%Y%m%d_%H%M%S)
backup="$dest/workspace/Checks/SharedSramApply_$stamp"
mkdir -p "$backup"
for f in Makefile Model/Roofline.py Server/SingleClock/LocalTest.sh Server/SingleClock/MakeLocalTest.py Sim/SocTest.cpp Sim/SharedSramModel.h Sim/SharedSramTest.cpp; do
  if [[ -f "$dest/$f" ]]; then
    mkdir -p "$backup/$(dirname "$f")"
    cp -p "$dest/$f" "$backup/$f"
  fi
done
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
base64 -d > "$tmp" <<'B64'
{b64_lines}
B64
tar -xzf "$tmp" -C "$dest"
cd "$dest"
sha256sum -c <<'SUMS'
{sums}
SUMS
echo "SHARED_SRAM_PAYLOAD_OK"
echo "BACKUP: $backup"
echo "UNIT: make shared-sram-unit"
echo "FULL: make shared-sram"
'''

out_shell.write_text(shell, encoding="utf-8", newline="\n")

copy = '''[CmdletBinding()]
param([string]$File = (Join-Path $PSScriptRoot 'ApplySharedSram_viaVNC.sh'))
$ErrorActionPreference = 'Stop'
$File = [IO.Path]::GetFullPath($File)
if (-not (Test-Path -LiteralPath $File)) { throw "File not found: $File" }
$text = [IO.File]::ReadAllText($File, [Text.Encoding]::UTF8)
if (-not $text.StartsWith('#!/usr/bin/env bash')) { throw 'Unexpected script header.' }
Set-Clipboard -Value $text
Write-Host ('COPIED_TO_CLIPBOARD: ' + $File)
Write-Host ('BYTES: ' + ([Text.Encoding]::UTF8.GetByteCount($text)))
Write-Host 'Paste into the VNC editor (pluma/gedit), save as ~/Desktop/ApplySharedSram_viaVNC.sh, then run it from the repo root.'
'''
out_copy.write_text(copy, encoding="utf-8", newline="\n")

print("payload_sha256", actual)
print("shell_bytes", out_shell.stat().st_size)
print("copy_bytes", out_copy.stat().st_size)
