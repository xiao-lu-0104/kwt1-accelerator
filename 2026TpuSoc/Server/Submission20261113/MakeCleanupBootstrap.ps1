[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$taskRelease = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..\release'))
$taskArchive = Join-Path $taskRelease 'CleanupBootstrap_20261113.tar.gz'
if (-not (Test-Path -LiteralPath $taskArchive)) { throw "Bootstrap not built: $taskArchive" }
$taskB64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($taskArchive))
$taskCommand = "bash -c 'set -e; printf %s " + $taskB64 + " | base64 -d | tar -xz -C /tmp; echo CLEANUP_BOOTSTRAP_READY'"
$taskOutput = Join-Path $taskRelease 'CleanupBootstrapCommand.txt'
[IO.File]::WriteAllText($taskOutput,$taskCommand,[Text.UTF8Encoding]::new($false))
Set-Clipboard -Value $taskCommand
Write-Host ('CLEANUP_COMMAND_COPIED: ' + $taskCommand.Length + ' characters')
Write-Host ('FILE: ' + $taskOutput)
Write-Host 'Paste into the server terminal. This only unpacks tools into /tmp; it does not delete anything.'
