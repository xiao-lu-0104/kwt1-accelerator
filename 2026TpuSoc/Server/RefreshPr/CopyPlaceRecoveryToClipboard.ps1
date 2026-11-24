[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$taskRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$taskEntry = Join-Path $taskRoot 'workspace\Server\tpusoc_place_resume_20261109_v1.sh'
$taskExpected = 'de28fbb51cc22dfb264e65147e920a17ef3ad72e7a8493b6929896da6e4fffeb'
if ((Get-FileHash -LiteralPath $taskEntry -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskExpected) {
    throw 'Frozen placement recovery entry changed; clipboard not modified.'
}
Set-Clipboard -Value ([System.IO.File]::ReadAllText($taskEntry, [System.Text.Encoding]::UTF8))
Write-Host 'CLIPBOARD_READY: paste into VNC text editor, save as Desktop/tpusoc_place_resume_20261109_v1.sh.'
Write-Host 'Do not copy another command before pasting.'
Write-Host ('EXPECTED_SHA256: ' + $taskExpected)
