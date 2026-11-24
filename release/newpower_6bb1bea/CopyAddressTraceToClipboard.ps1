$ErrorActionPreference = 'Stop'
$taskAddressTrace = Join-Path $PSScriptRoot 'TraceBusAddress_6bb1bea.sh'
Set-Clipboard -Value ([IO.File]::ReadAllText($taskAddressTrace,[Text.Encoding]::UTF8))
Write-Host 'COPIED: TraceBusAddress_6bb1bea.sh; passive trace, no RTL/netlist changes.'
