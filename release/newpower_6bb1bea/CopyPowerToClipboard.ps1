[CmdletBinding()]
param([ValidateRange(0,3)][int]$Part = 0)
$ErrorActionPreference = 'Stop'
$taskFile = Join-Path $PSScriptRoot 'RunPower_6bb1bea.sh'
$taskText = [IO.File]::ReadAllText($taskFile,[Text.Encoding]::UTF8)
if ($Part -eq 0) {
    Set-Clipboard -Value $taskText
    Write-Host "COPIED_FULL: $($taskText.Length) characters. Prefer -Part 1, 2, 3 if VNC clips large text."
    return
}
$taskParts = [Collections.Generic.List[string]]::new()
$taskOffset = 0
while ($taskOffset -lt $taskText.Length) {
    $taskLength = [Math]::Min(170000,$taskText.Length-$taskOffset)
    if ($taskOffset+$taskLength -lt $taskText.Length) {
        $taskBoundary = $taskText.LastIndexOf("`n",$taskOffset+$taskLength-1,$taskLength)
        if ($taskBoundary -ge $taskOffset) { $taskLength = $taskBoundary-$taskOffset+1 }
    }
    $taskParts.Add($taskText.Substring($taskOffset,$taskLength))
    $taskOffset += $taskLength
}
if ($taskParts.Count -ne 3) { throw "Expected three transfer parts; actual $($taskParts.Count). Review generated package size." }
Set-Clipboard -Value $taskParts[$Part-1]
Write-Host "COPIED_PART: $Part/3"
if ($Part -eq 1) { Write-Host 'Server pluma: Ctrl+A then paste. Keep editor open.' }
elseif ($Part -eq 2) { Write-Host 'Server pluma: Ctrl+End then paste. Keep editor open.' }
else { Write-Host 'Server pluma: Ctrl+End then paste, save; then run bash ~/Desktop/RunPower_6bb1bea.sh' }
