$ErrorActionPreference = 'Stop'
$taskGuardRecovery = Join-Path $PSScriptRoot 'ResumePowerGuard_6bb1bea.sh'
Set-Clipboard -Value ([IO.File]::ReadAllText($taskGuardRecovery,[Text.Encoding]::UTF8))
Write-Host 'COPIED: ResumePowerGuard_6bb1bea.sh; paste, save, run.'
