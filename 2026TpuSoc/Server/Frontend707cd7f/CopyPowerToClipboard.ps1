[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$taskRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$taskEntry = Join-Path $taskRoot 'workspace\Server\tpusoc_task_power_20261110_707cd7f_v1.sh'
$taskExpected = '8820e2f2f6ad4623013b2fbd3f07687ac0301864627c6e508bb351858d5d8876'
if ((Get-FileHash -LiteralPath $taskEntry -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskExpected) {
    throw 'Frozen 707cd7f power entry changed; clipboard not modified.'
}
Set-Clipboard -Value ([System.IO.File]::ReadAllText($taskEntry, [System.Text.Encoding]::UTF8))
Write-Host 'CLIPBOARD_READY: 79017 bytes; paste into VNC editor and save Desktop/tpusoc_task_power_20261110_707cd7f_v1.sh.'
Write-Host 'Paste and save before copying any command.'
Write-Host ('EXPECTED_SHA256: ' + $taskExpected)
