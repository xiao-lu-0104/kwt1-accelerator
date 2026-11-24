[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$taskRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$taskEntry = Join-Path $taskRoot 'workspace\Server\tpusoc_full_pr_20261109_v1.sh'
$taskExpected = '0d863fe2b854dacf66fe0496d913730b1fd467a0e2cc98a84465b37925f35db6'
if ((Get-FileHash -LiteralPath $taskEntry -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskExpected) {
    throw 'Frozen full PR entry changed; clipboard not modified.'
}
Set-Clipboard -Value ([System.IO.File]::ReadAllText($taskEntry, [System.Text.Encoding]::UTF8))
Write-Host 'CLIPBOARD_READY: full PR entry, 12933 bytes; no FTP used.'
Write-Host 'Paste into the VNC text editor, replace all, save to Desktop/tpusoc_full_pr_20261109_v1.sh and close.'
Write-Host 'Do not copy another command before pasting.'
Write-Host ('EXPECTED_SHA256: ' + $taskExpected)
