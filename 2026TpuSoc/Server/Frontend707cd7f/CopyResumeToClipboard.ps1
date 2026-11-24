[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$taskRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$taskEntry = Join-Path $taskRoot 'workspace\Server\tpusoc_hold_recovery_20261110_707cd7f_v1.sh'
$taskExpected = 'b96c55e8f2cc2c5d4b3bcb1de5ceea69da0d76d763020717cffe8d5b25b8bcaf'
if ((Get-FileHash -LiteralPath $taskEntry -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskExpected) {
    throw 'Frozen recovery entry changed; clipboard not modified.'
}
Set-Clipboard -Value ([System.IO.File]::ReadAllText($taskEntry, [System.Text.Encoding]::UTF8))
Write-Host 'CLIPBOARD_READY: paste into VNC editor and save Desktop/tpusoc_hold_recovery_20261110_707cd7f_v1.sh.'
Write-Host 'Paste and save before copying another command.'
Write-Host ('EXPECTED_SHA256: ' + $taskExpected)
