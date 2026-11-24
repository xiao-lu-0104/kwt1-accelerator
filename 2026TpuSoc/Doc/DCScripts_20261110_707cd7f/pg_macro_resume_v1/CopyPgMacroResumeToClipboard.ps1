[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$taskRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$taskEntry = Join-Path $taskRoot 'workspace\Server\tpusoc_pg_macro_resume_20261110_707cd7f_v1.sh'
if ((Get-FileHash -LiteralPath $taskEntry -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'be9d5c1b22d43362713282b7cdf9b93279c20253422bb1f1568178b53acc2575') {
    throw 'Frozen new PG entry changed; clipboard not modified.'
}
Set-Clipboard -Value ([System.IO.File]::ReadAllText($taskEntry, [System.Text.Encoding]::UTF8))
Write-Host 'CLIPBOARD_READY: paste and save Desktop/tpusoc_pg_macro_resume_20261110_707cd7f_v1.sh, then run NormalizePgMacroResumeCommand.txt.'
