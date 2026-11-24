[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$taskRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$taskEntry = Join-Path $taskRoot 'workspace\Server\tpusoc_layout_api_20261110_707cd7f_v1.sh'
if ((Get-FileHash -LiteralPath $taskEntry -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'ae13d79a5d003010ab8b40c7ef312be0fff95ad877c170ce7d869c389e666d5e') {
    throw 'Frozen layout API probe changed; clipboard not modified.'
}
Set-Clipboard -Value ([System.IO.File]::ReadAllText($taskEntry, [System.Text.Encoding]::UTF8))
Write-Host 'CLIPBOARD_READY: paste and save Desktop/tpusoc_layout_api_20261110_707cd7f_v1.sh, then run NormalizeLayoutApiCommand.txt.'
