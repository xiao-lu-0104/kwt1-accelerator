[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$taskRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$taskEntry = Join-Path $taskRoot 'workspace\Server\tpusoc_continue_pr_20261111_707cd7f_v1.sh'
if ((Get-FileHash -LiteralPath $taskEntry -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'efb888b0e18e38e7e6187dac97b853bb5e8a5f67ff0ea766866738b4a85bf25c') {
    throw 'Frozen new PG entry changed; clipboard not modified.'
}
Set-Clipboard -Value ([System.IO.File]::ReadAllText($taskEntry, [System.Text.Encoding]::UTF8))
Write-Host 'CLIPBOARD_READY: paste and save Desktop/tpusoc_continue_pr_20261111_707cd7f_v1.sh, then run NormalizeContinuePrCommand.txt.'
