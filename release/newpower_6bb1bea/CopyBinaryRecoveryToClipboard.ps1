$ErrorActionPreference='Stop'
Set-Clipboard -Value ([IO.File]::ReadAllText((Join-Path $PSScriptRoot 'ResumePowerBinary_6bb1bea.sh'),[Text.Encoding]::UTF8))
Write-Host 'COPIED: ResumePowerBinary_6bb1bea.sh'
