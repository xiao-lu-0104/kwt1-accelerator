[CmdletBinding()]
param(
    [ValidateSet('prep','assets','wheels','source')][string]$Stage = 'prep',
    [string]$File = '',
    [switch]$ConnectionOnly
)
$ErrorActionPreference = 'Stop'
$taskRelease = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..\release'))
if (-not $File) {
    $taskNames = @{
        prep='SubmissionPrep_20261113.tar.gz'
        assets='EvaluationAssets_20261113.tar.gz'
        wheels='ServerWheels_py36_20261113.tar.gz'
    }
    if (-not $taskNames.ContainsKey($Stage)) { throw 'Source package is not ready until frontend arrives. Supply -File after binding.' }
    $File = Join-Path $taskRelease $taskNames[$Stage]
}
$File = [IO.Path]::GetFullPath($File)
if (-not (Test-Path -LiteralPath $File)) { throw "File not found: $File" }
$taskRemoteName = [IO.Path]::GetFileName($File)
$taskProbe = [Net.Sockets.TcpClient]::new()
try {
    $taskConnect = $taskProbe.ConnectAsync('icdesigns0.nicu.cn',18888)
    if (-not $taskConnect.Wait(8000)) { throw 'FTP connect timeout; no login attempted.' }
    $taskStream = $taskProbe.GetStream(); $taskStream.ReadTimeout = 5000
    $taskBuffer = New-Object byte[] 2048
    $taskRead = $taskStream.Read($taskBuffer,0,2048)
    $taskGreeting = [Text.Encoding]::ASCII.GetString($taskBuffer,0,$taskRead).Trim()
    if ($taskGreeting -notmatch '^220') { throw "FTP unavailable: $taskGreeting. No login or upload attempted." }
} finally { $taskProbe.Dispose() }
Write-Host 'FTP_READY'
if ($ConnectionOnly) { return }
Write-Host "FILE: $File ($((Get-Item -LiteralPath $File).Length) bytes)"
$taskSecure = Read-Host 'Server password for s1_12usr (not echoed)' -AsSecureString
$taskCredential = [Management.Automation.PSCredential]::new('s1_12usr',$taskSecure)
function Quote-Curl([string]$Value) {
    if ($Value.Contains("`r") -or $Value.Contains("`n")) { throw 'Unexpected newline in curl config.' }
    return '"' + $Value.Replace('\','\\').Replace('"','\"') + '"'
}
$taskAuth = $taskCredential.GetNetworkCredential()
$taskCurlConfig = @(
    ('url = ' + (Quote-Curl ('ftp://icdesigns0.nicu.cn:18888/' + $taskRemoteName))),
    ('user = ' + (Quote-Curl ('s1_12usr:' + $taskAuth.Password))),
    ('upload-file = ' + (Quote-Curl $File)),
    'connect-timeout = 15','max-time = 1800','silent','show-error',
    'write-out = "\nFTP_RESPONSE:%{response_code}\nBYTES_SENT:%{size_upload}\n"'
) -join "`n"
$taskInfo = [Diagnostics.ProcessStartInfo]::new()
$taskInfo.FileName = (Get-Command curl.exe -ErrorAction Stop).Source
$taskInfo.Arguments = '-q --config -'
$taskInfo.UseShellExecute=$false; $taskInfo.CreateNoWindow=$true
$taskInfo.RedirectStandardInput=$true; $taskInfo.RedirectStandardOutput=$true; $taskInfo.RedirectStandardError=$true
$taskProcess = [Diagnostics.Process]::new(); $taskProcess.StartInfo=$taskInfo
try {
    [void]$taskProcess.Start()
    $taskOut=$taskProcess.StandardOutput.ReadToEndAsync(); $taskErr=$taskProcess.StandardError.ReadToEndAsync()
    $taskProcess.StandardInput.WriteLine($taskCurlConfig); $taskProcess.StandardInput.Close()
    $taskSeconds=0
    while (-not $taskProcess.WaitForExit(1000)) {
        $taskSeconds++
        if (($taskSeconds % 30) -eq 0) { Write-Host "Uploading: $taskSeconds seconds" }
    }
    $taskResult=$taskOut.Result; $taskError=$taskErr.Result
    if ($taskProcess.ExitCode -ne 0 -or $taskResult -notmatch 'FTP_RESPONSE:2\d\d') { throw "UPLOAD_FAILED: $taskError $taskResult" }
    Write-Host "UPLOAD_OK: ~/Desktop/$taskRemoteName"
} finally { $taskAuth=$null; $taskCredential=$null; $taskSecure=$null; $taskCurlConfig=$null }
