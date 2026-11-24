[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$taskRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$taskEntry = Join-Path $taskRoot 'workspace\Server\tpusoc_initial_pr_20261110_707cd7f_v2.sh'
if ((Get-FileHash -LiteralPath $taskEntry -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'f993857c0a9cd58739c08798a6c829dbd6464fc9615f29ef47894a7be091bfd3') {
    throw 'Frozen initial PR v2 changed; clipboard not modified.'
}
Set-Clipboard -Value ([System.IO.File]::ReadAllText($taskEntry, [System.Text.Encoding]::UTF8))
Write-Host 'CLIPBOARD_READY: paste and save Desktop/tpusoc_initial_pr_20261110_707cd7f_v2.sh, then run NormalizePrV2Command.txt.'
