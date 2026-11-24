[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$taskRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$taskEntry = Join-Path $taskRoot 'workspace\Server\tpusoc_pr_prepare_20261109_v1.sh'
$taskExpected = 'fd3c7732a4cc6c6b19078bf0719d3461ebcd40c7eb4e17daa8fdf457acd35461'
$taskActual = (Get-FileHash -LiteralPath $taskEntry -Algorithm SHA256).Hash.ToLowerInvariant()
if ($taskActual -ne $taskExpected) { throw 'Frozen prepare script checksum mismatch; nothing copied.' }
$taskText = [System.IO.File]::ReadAllText($taskEntry, [System.Text.Encoding]::UTF8)
Set-Clipboard -Value $taskText
Write-Host 'CLIPBOARD_READY: complete verified prepare script, 25898 bytes. No FTP connection attempted.'
Write-Host 'Return to the Linux text editor in VNC, paste with Ctrl+V, save with Ctrl+S, then close the editor.'
Write-Host 'Do not copy another command before pasting; doing so replaces this clipboard content.'
Write-Host ('EXPECTED_SHA256: ' + $taskExpected)
Write-Host 'After saving, verify on the server: sha256sum ~/Desktop/tpusoc_pr_prepare_20261109_v1.sh'
