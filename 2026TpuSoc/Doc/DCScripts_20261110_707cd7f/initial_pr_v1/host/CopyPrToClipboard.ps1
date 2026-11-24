[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$taskRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$taskEntry = Join-Path $taskRoot 'workspace\Server\tpusoc_initial_pr_20261110_707cd7f_v1.sh'
$taskExpected = 'c1ee5c0fe4eebc58c5d85d6e9e51c717f7be8006c0a2bf0b439f9b67d3e4af8f'
if ((Get-FileHash -LiteralPath $taskEntry -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskExpected) {
    throw 'Frozen 707cd7f PR entry changed; clipboard not modified.'
}
Set-Clipboard -Value ([System.IO.File]::ReadAllText($taskEntry, [System.Text.Encoding]::UTF8))
Write-Host 'CLIPBOARD_READY: paste into VNC editor and save Desktop/tpusoc_initial_pr_20261110_707cd7f_v1.sh.'
Write-Host 'Paste and save before copying another command.'
Write-Host ('EXPECTED_SHA256: ' + $taskExpected)
