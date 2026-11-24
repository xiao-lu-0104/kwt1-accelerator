[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$taskRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$taskEntry = Join-Path $taskRoot 'workspace\Server\tpusoc_pg_resume_20261110_707cd7f_v1.sh'
if ((Get-FileHash -LiteralPath $taskEntry -Algorithm SHA256).Hash.ToLowerInvariant() -ne '77c139483361d2f73633a50641615b17f64e21db8791411600d63f825da638c5') {
    throw 'Frozen new PG entry changed; clipboard not modified.'
}
Set-Clipboard -Value ([System.IO.File]::ReadAllText($taskEntry, [System.Text.Encoding]::UTF8))
Write-Host 'CLIPBOARD_READY: paste and save Desktop/tpusoc_pg_resume_20261110_707cd7f_v1.sh, then run NormalizePgResumeCommand.txt.'
