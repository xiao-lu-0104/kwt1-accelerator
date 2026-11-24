[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$taskRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$taskEntry = Join-Path $taskRoot 'workspace\Server\tpusoc_frontend_20261110_707cd7f_v1.sh'
$taskExpected = '1f60d5372532e8e778fd5980df6e3fdf8e3a829908cad1446aea3900355975bb'
if ((Get-FileHash -LiteralPath $taskEntry -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskExpected) {
    throw 'Frozen 707cd7f entry changed; clipboard not modified.'
}
Set-Clipboard -Value ([System.IO.File]::ReadAllText($taskEntry, [System.Text.Encoding]::UTF8))
Write-Host 'CLIPBOARD_READY: paste into VNC text editor and save Desktop/tpusoc_frontend_20261110_707cd7f_v1.sh.'
Write-Host 'Do not copy a command until after pasting and saving.'
Write-Host ('EXPECTED_SHA256: ' + $taskExpected)
