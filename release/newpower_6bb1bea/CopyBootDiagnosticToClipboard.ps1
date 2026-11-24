$ErrorActionPreference = 'Stop'
$taskBootDiagnostic = Join-Path $PSScriptRoot 'DiagnoseGateBoot_6bb1bea.sh'
Set-Clipboard -Value ([IO.File]::ReadAllText($taskBootDiagnostic,[Text.Encoding]::UTF8))
Write-Host 'COPIED: DiagnoseGateBoot_6bb1bea.sh; paste, save, run.'
