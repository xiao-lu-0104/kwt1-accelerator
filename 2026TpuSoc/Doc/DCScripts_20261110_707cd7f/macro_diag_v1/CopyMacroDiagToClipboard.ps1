[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$taskRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$taskEntry = Join-Path $taskRoot 'workspace\Server\tpusoc_macro_diag_20261110_707cd7f_v1.sh'
if ((Get-FileHash -LiteralPath $taskEntry -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'eb15ba5683516ca6ccfa21ac1c144683ab19119b64a9db39f823118e25a4a571') {
    throw 'Frozen new PG entry changed; clipboard not modified.'
}
Set-Clipboard -Value ([System.IO.File]::ReadAllText($taskEntry, [System.Text.Encoding]::UTF8))
Write-Host 'CLIPBOARD_READY: paste and save Desktop/tpusoc_macro_diag_20261110_707cd7f_v1.sh, then run NormalizeMacroDiagCommand.txt.'
