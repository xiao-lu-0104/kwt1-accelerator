$ErrorActionPreference = 'Stop'
$taskPinRecovery = Join-Path $PSScriptRoot 'ResumePowerPinInit_6bb1bea.sh'
Set-Clipboard -Value ([IO.File]::ReadAllText($taskPinRecovery,[Text.Encoding]::UTF8))
Write-Host 'COPIED: ResumePowerPinInit_6bb1bea.sh; paste, save, run. System DC will be reused.'
