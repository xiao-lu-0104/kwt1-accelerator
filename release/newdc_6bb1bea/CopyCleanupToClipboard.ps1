$ErrorActionPreference = 'Stop'
$taskCleanup = Join-Path $PSScriptRoot 'CleanPreviousDc_7cf5155.sh'
Set-Clipboard -Value ([IO.File]::ReadAllText($taskCleanup, [Text.Encoding]::UTF8))
Write-Host 'COPIED: CleanPreviousDc_7cf5155.sh; paste into server pluma and save.'
