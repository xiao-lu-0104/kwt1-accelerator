[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$taskRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$taskEntry = Join-Path $taskRoot 'workspace\Server\tpusoc_full_pr_recovery_20261109_v1.sh'
$taskExpected = 'afa238b8af3782ebbf91f906298cf25637bedaa85a38e7081436583f310a056d'
if ((Get-FileHash -LiteralPath $taskEntry -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskExpected) {
    throw 'Frozen recovery entry changed; clipboard not modified.'
}
Set-Clipboard -Value ([System.IO.File]::ReadAllText($taskEntry, [System.Text.Encoding]::UTF8))
Write-Host 'CLIPBOARD_READY: recovery entry. Paste into the VNC text editor and save to Desktop/tpusoc_full_pr_recovery_20261109_v1.sh.'
Write-Host 'Do not copy another command before pasting.'
Write-Host ('EXPECTED_SHA256: ' + $taskExpected)
