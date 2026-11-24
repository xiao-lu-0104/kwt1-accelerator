[CmdletBinding()]
param([int]$Part = 0)
$ErrorActionPreference = 'Stop'
$taskFile=Join-Path $PSScriptRoot 'RunNewDc_6bb1bea.sh'
$taskText=[IO.File]::ReadAllText($taskFile,[Text.Encoding]::UTF8)
if ($Part -eq 0) {
    Set-Clipboard -Value $taskText
    Write-Host ('COPIED_FULL: ' + $taskText.Length + ' characters')
    Write-Host 'Paste and save ~/Desktop/RunNewDc_6bb1bea.sh. If VNC truncates it, use -Part 1 through the last part.'
} else {
    $taskParts=[Collections.Generic.List[string]]::new()
    $taskOffset=0
    while ($taskOffset -lt $taskText.Length) {
        $taskLength=[Math]::Min(48000,$taskText.Length-$taskOffset)
        if (($taskOffset+$taskLength) -lt $taskText.Length) {
            $taskBoundary=$taskText.LastIndexOf("`n",$taskOffset+$taskLength-1,$taskLength)
            if ($taskBoundary -ge $taskOffset) { $taskLength=$taskBoundary-$taskOffset+1 }
        }
        $taskParts.Add($taskText.Substring($taskOffset,$taskLength))
        $taskOffset+=$taskLength
    }
    if ($Part -lt 1 -or $Part -gt $taskParts.Count) { throw "Part must be 1..$($taskParts.Count)" }
    Set-Clipboard -Value $taskParts[$Part-1]
    Write-Host "COPIED_PART: $Part/$($taskParts.Count)"
    Write-Host 'First part: Ctrl+A then paste. Later parts: Ctrl+End then paste. Save after all parts; do not execute an incomplete file.'
}
