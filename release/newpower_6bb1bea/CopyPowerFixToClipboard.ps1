$ErrorActionPreference = 'Stop'
$taskFile = Join-Path $PSScriptRoot 'FixPowerBackendNewline_6bb1bea.sh'
Set-Clipboard -Value ([IO.File]::ReadAllText($taskFile,[Text.Encoding]::UTF8))
Write-Host 'COPIED: FixPowerBackendNewline_6bb1bea.sh (small repair; paste, save, run).'
