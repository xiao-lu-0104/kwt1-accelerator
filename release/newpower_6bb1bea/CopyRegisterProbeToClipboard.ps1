$ErrorActionPreference = 'Stop'
$taskProbePath = Join-Path $PSScriptRoot 'ProbeCopyRegister_6bb1bea.sh'
Set-Clipboard -Value ([IO.File]::ReadAllText($taskProbePath,[Text.Encoding]::UTF8))
Write-Host 'COPIED: ProbeCopyRegister_6bb1bea.sh'
