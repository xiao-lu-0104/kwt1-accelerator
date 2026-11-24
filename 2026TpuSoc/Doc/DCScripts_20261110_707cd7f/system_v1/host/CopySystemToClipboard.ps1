[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$taskRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$taskEntry = Join-Path $taskRoot 'workspace\Server\tpusoc_system_dc_20261110_707cd7f_v1.sh'
$taskExpected = '26f649b7044ba2a9f184cec008585f96ec27c8689e67c51b0d500c10a28c7124'
if ((Get-FileHash -LiteralPath $taskEntry -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskExpected) {
    throw 'Frozen 707cd7f system entry changed; clipboard not modified.'
}
Set-Clipboard -Value ([System.IO.File]::ReadAllText($taskEntry, [System.Text.Encoding]::UTF8))
Write-Host 'CLIPBOARD_READY: paste into VNC editor and save Desktop/tpusoc_system_dc_20261110_707cd7f_v1.sh.'
Write-Host 'Paste and save before copying another command.'
Write-Host ('EXPECTED_SHA256: ' + $taskExpected)
