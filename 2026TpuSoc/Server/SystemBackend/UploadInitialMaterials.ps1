[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$ConnectionOnly,
    [System.Management.Automation.PSCredential]$Credential,
    [ValidateSet('initial', 'replay', 'backend', 'formal', 'pr', 'coarse', 'dc', 'dcreview', 'dcequiv', 'dcsystem', 'power', 'powerresume', 'pr1109', 'prresume', 'prprepare', 'prfull', 'prfullresume', 'prplaceresume', 'frontend707', 'frontend707resume', 'frontend707fast', 'frontend707system', 'frontend707power', 'frontend707pr', 'frontend707continue')]
    [string]$Stage = 'initial'
)

$ErrorActionPreference = 'Stop'
$taskProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
if ($Stage -eq 'frontend707continue') {
    $taskArtifact = Join-Path $taskProjectRoot 'workspace\Server\tpusoc_continue_pr_20261111_707cd7f_v1.sh'
    $taskExpectedSha = 'efb888b0e18e38e7e6187dac97b853bb5e8a5f67ff0ea766866738b4a85bf25c'
} elseif ($Stage -eq 'frontend707pr') {
    $taskArtifact = Join-Path $taskProjectRoot 'workspace\Server\tpusoc_initial_pr_20261110_707cd7f_v1.sh'
    $taskExpectedSha = 'c1ee5c0fe4eebc58c5d85d6e9e51c717f7be8006c0a2bf0b439f9b67d3e4af8f'
} elseif ($Stage -eq 'frontend707power') {
    $taskArtifact = Join-Path $taskProjectRoot 'workspace\Server\tpusoc_task_power_20261110_707cd7f_v1.sh'
    $taskExpectedSha = '8820e2f2f6ad4623013b2fbd3f07687ac0301864627c6e508bb351858d5d8876'
} elseif ($Stage -eq 'frontend707system') {
    $taskArtifact = Join-Path $taskProjectRoot 'workspace\Server\tpusoc_system_dc_20261110_707cd7f_v1.sh'
    $taskExpectedSha = '26f649b7044ba2a9f184cec008585f96ec27c8689e67c51b0d500c10a28c7124'
} elseif ($Stage -eq 'frontend707fast') {
    $taskArtifact = Join-Path $taskProjectRoot 'workspace\Server\tpusoc_hold_recovery_20261110_707cd7f_v2.sh'
    $taskExpectedSha = 'bc5c0f3cb403cca52ecdc68851cb182f7b77a24de00bfc691d9686dcf4cdf0df'
} elseif ($Stage -eq 'frontend707resume') {
    $taskArtifact = Join-Path $taskProjectRoot 'workspace\Server\tpusoc_hold_recovery_20261110_707cd7f_v1.sh'
    $taskExpectedSha = 'b96c55e8f2cc2c5d4b3bcb1de5ceea69da0d76d763020717cffe8d5b25b8bcaf'
} elseif ($Stage -eq 'frontend707') {
    $taskArtifact = Join-Path $taskProjectRoot 'workspace\Server\tpusoc_frontend_20261110_707cd7f_v1.sh'
    $taskExpectedSha = '1f60d5372532e8e778fd5980df6e3fdf8e3a829908cad1446aea3900355975bb'
} elseif ($Stage -eq 'prplaceresume') {
    $taskArtifact = Join-Path $taskProjectRoot 'workspace\Server\tpusoc_place_resume_20261109_v1.sh'
    $taskExpectedSha = 'de28fbb51cc22dfb264e65147e920a17ef3ad72e7a8493b6929896da6e4fffeb'
} elseif ($Stage -eq 'prfullresume') {
    $taskArtifact = Join-Path $taskProjectRoot 'workspace\Server\tpusoc_full_pr_recovery_20261109_v1.sh'
    $taskExpectedSha = 'afa238b8af3782ebbf91f906298cf25637bedaa85a38e7081436583f310a056d'
} elseif ($Stage -eq 'prfull') {
    $taskArtifact = Join-Path $taskProjectRoot 'workspace\Server\tpusoc_full_pr_20261109_v1.sh'
    $taskExpectedSha = '0d863fe2b854dacf66fe0496d913730b1fd467a0e2cc98a84465b37925f35db6'
} elseif ($Stage -eq 'prprepare') {
    $taskArtifact = Join-Path $taskProjectRoot 'workspace\Server\tpusoc_pr_prepare_20261109_v1.sh'
    $taskExpectedSha = 'fd3c7732a4cc6c6b19078bf0719d3461ebcd40c7eb4e17daa8fdf457acd35461'
} elseif ($Stage -eq 'prresume') {
    $taskArtifact = Join-Path $taskProjectRoot 'workspace\Server\tpusoc_system_pr_resume_20261109_v1.sh'
    $taskExpectedSha = 'c17c7d48f0dab525ca9325d6fdd99579dd1b84ec6bd1cdd447280230c155d2c1'
} elseif ($Stage -eq 'pr1109') {
    $taskArtifact = Join-Path $taskProjectRoot 'workspace\Server\tpusoc_new_system_pr_20261109_v1.sh'
    $taskExpectedSha = 'a02f5153bab9fe57fcabc18f19d2db14c9f5bd6d61da80d6799cebe3141d1954'
} elseif ($Stage -eq 'powerresume') {
    $taskArtifact = Join-Path $taskProjectRoot 'workspace\Server\tpusoc_power_resume_20261109_v1.sh'
    $taskExpectedSha = '959154034abbe81be494e7afbae986a882aac9489cc13eda6a0f0e2a89f8933a'
} elseif ($Stage -eq 'power') {
    $taskArtifact = Join-Path $taskProjectRoot 'workspace\Server\tpusoc_current_power_20261109_v1.sh'
    $taskExpectedSha = 'ad05fcd8608bded396df62f0891c28da36dec810dce17bc1c9bdff9e0da9f15f'
} elseif ($Stage -eq 'dcsystem') {
    $taskArtifact = Join-Path $taskProjectRoot 'workspace\Server\tpusoc_new_system_dc_20261109_v1.sh'
    $taskExpectedSha = 'c6d5b7571efaff6e342badab4ce4bfb64d5087c3d32c3abf75f8932bc6d6b19e'
} elseif ($Stage -eq 'dcequiv') {
    $taskArtifact = Join-Path $taskProjectRoot 'workspace\Server\tpusoc_hold_equiv_20261109_v1.sh'
    $taskExpectedSha = 'dbdf3635970b9a2d55d25fa9416e6f228b8ecfdee10c6beba2c6ba0fa15115d1'
} elseif ($Stage -eq 'dcreview') {
    $taskArtifact = Join-Path $taskProjectRoot 'workspace\Server\tpusoc_dc_review_20261109_v1.sh'
    $taskExpectedSha = '66203147cbf179254c2b306f7acd6f277fdd938445293f526699048820d731a1'
} elseif ($Stage -eq 'dc') {
    $taskArtifact = Join-Path $taskProjectRoot 'workspace\Server\tpusoc_refresh_dc_20261109_v1.sh'
    $taskExpectedSha = '4edc335d7c8166ca8afdccecca91d302630f179d6ce7210f94254f97c9c6330b'
} elseif ($Stage -eq 'coarse') {
    $taskArtifact = Join-Path $taskProjectRoot 'workspace\Server\tpusoc_icc2_coarse_20261108_v1.sh'
    $taskExpectedSha = 'd471c4183621005990bd0cd9933ed5551b1719acb55aea5d57d1923f1693127a'
} elseif ($Stage -eq 'pr') {
    $taskArtifact = Join-Path $taskProjectRoot 'workspace\Server\tpusoc_icc2_start_20261108_v4.sh'
    $taskExpectedSha = 'af4368f057f6c56a202b7448fecdeb867ae8d6c866f5507b4747e0954b23cf80'
} elseif ($Stage -eq 'formal') {
    $taskArtifact = Join-Path $taskProjectRoot 'workspace\Server\tpusoc_formal_accelerator_20261108_v5.sh'
    $taskExpectedSha = 'f30a105a7ed32208759e6f86a25c6faae227851f72a129a9507077cd837b9c06'
} elseif ($Stage -eq 'backend') {
    $taskArtifact = Join-Path $taskProjectRoot 'workspace\Server\tpusoc_final_preflight_20261108_v4.sh'
    $taskExpectedSha = '96241d21ad3cf47c23495da6ea72f452bd3af1edb7f9569e4ed3585d7fa895d5'
} elseif ($Stage -eq 'replay') {
    $taskArtifact = Join-Path $taskProjectRoot 'workspace\Server\tpusoc_numerical_replay_20261107_v1.sh'
    $taskExpectedSha = 'f1cbe937a4696c608438d9c173c13fde3da32a2d8312993f7541cc46c3e084a6'
} else {
    $taskArtifact = Join-Path $taskProjectRoot 'workspace\Server\tpusoc_initial_materials_20261107_v3.sh'
    $taskExpectedSha = '6f75a41cd2d267514317253cd3cc0eb5590a556e5d125b6725d21b432020b891'
}
$taskActualSha = (Get-FileHash -LiteralPath $taskArtifact -Algorithm SHA256).Hash.ToLowerInvariant()
if ($taskActualSha -ne $taskExpectedSha) { throw 'Local entry checksum differs; upload stopped.' }
$taskCurl = (Get-Command curl.exe -ErrorAction Stop).Source
$taskRemoteName = [System.IO.Path]::GetFileName($taskArtifact)
$taskUrl = 'ftp://icdesigns0.nicu.cn:18888/' + $taskRemoteName
$taskRunCommand = 'bash ~/Desktop/' + $taskRemoteName
Write-Host ('FILE: ' + $taskArtifact)
Write-Host ('BYTES: ' + (Get-Item -LiteralPath $taskArtifact).Length)
Write-Host ('SHA256: ' + $taskActualSha)
if ($CheckOnly) {
    Write-Host 'CHECK_ONLY: PASS; no login or transfer attempted.'
    Write-Host ('SERVER_COMMAND_AFTER_UPLOAD: ' + $taskRunCommand)
    return
}

function Assert-TaskFtpReady {
    # Read the greeting before requesting credentials. No login or upload.
    $taskProbeClient = [System.Net.Sockets.TcpClient]::new()
    try {
        $taskProbeConnect = $taskProbeClient.ConnectAsync('icdesigns0.nicu.cn', 18888)
        if (-not $taskProbeConnect.Wait(8000)) { throw 'FTP connection probe timed out; no login or upload attempted.' }
        [void]$taskProbeConnect.GetAwaiter().GetResult()
        $taskProbeStream = $taskProbeClient.GetStream()
        $taskProbeStream.ReadTimeout = 5000
        $taskProbeBuffer = [byte[]]::new(2048)
        $taskProbeRead = $taskProbeStream.Read($taskProbeBuffer, 0, $taskProbeBuffer.Length)
        $taskProbeGreeting = [System.Text.Encoding]::ASCII.GetString($taskProbeBuffer, 0, $taskProbeRead)
        if ($taskProbeGreeting -match '^421') {
            throw 'FTP_CAPACITY_FULL (421): server rejected the connection before login. No password or upload attempted; stop retrying and use the VNC clipboard fallback.'
        }
        if ($taskProbeGreeting -notmatch '^220') { throw 'FTP server did not return a ready greeting; no login or upload attempted.' }
        Write-Host 'FTP greeting: 220 ready; probe connection closed before login.'
    } finally {
        $taskProbeClient.Dispose()
    }
}
Assert-TaskFtpReady
if ($ConnectionOnly) {
    Write-Host 'CONNECTION_ONLY: PASS; no login or transfer attempted.'
    return
}

if ($null -eq $Credential) {
    Write-Host 'FTP user: s1_12usr'
    Write-Host 'Enter the Linux/FTP password below, then press Enter. It is not echoed. Do not send it in chat.'
    $taskSecurePassword = Read-Host -Prompt 'FTP password' -AsSecureString
    $Credential = [System.Management.Automation.PSCredential]::new('s1_12usr', $taskSecurePassword)
    $taskSecurePassword = $null
}
if ($null -eq $Credential) { throw 'No FTP credential supplied; upload stopped.' }
if ($Credential.UserName -ne 's1_12usr') { throw 'This entry is prepared for s1_12usr only.' }

function ConvertTo-TaskCurlQuoted([string]$Value) {
    if ($Value.Contains("`r") -or $Value.Contains("`n") -or $Value.Contains([char]0)) {
        throw 'Unexpected control character in curl configuration.'
    }
    return '"' + $Value.Replace('\', '\\').Replace('"', '\"') + '"'
}

# Credentials go to curl over its standard input, not command arguments or a file.
# curl verbose/trace output is deliberately never enabled.
$taskAuth = $Credential.GetNetworkCredential()
$taskConfigLines = @(
    ('url = ' + (ConvertTo-TaskCurlQuoted $taskUrl)),
    ('user = ' + (ConvertTo-TaskCurlQuoted ($Credential.UserName + ':' + $taskAuth.Password))),
    ('upload-file = ' + (ConvertTo-TaskCurlQuoted $taskArtifact)),
    'connect-timeout = 10',
    'max-time = 60',
    'silent',
    'show-error',
    'write-out = "\nFTP_RESPONSE:%{response_code}\nBYTES_SENT:%{size_upload}\n"'
)
$taskConfiguration = [string]::Join("`n", $taskConfigLines) + "`n"
$taskSucceeded = $false
try {
    for ($taskAttempt = 1; $taskAttempt -le 4; $taskAttempt++) {
        Write-Host ('UPLOAD attempt ' + $taskAttempt + '/4; credentials are not printed.')
        $taskStart = [System.Diagnostics.ProcessStartInfo]::new()
        $taskStart.FileName = $taskCurl
        $taskStart.Arguments = '-q --config -'
        $taskStart.UseShellExecute = $false
        $taskStart.CreateNoWindow = $true
        $taskStart.RedirectStandardInput = $true
        $taskStart.RedirectStandardOutput = $true
        $taskStart.RedirectStandardError = $true
        $taskProcess = [System.Diagnostics.Process]::new()
        $taskProcess.StartInfo = $taskStart
        $taskStarted = $false
        try {
            $taskStarted = $taskProcess.Start()
            $taskOutput = $taskProcess.StandardOutput.ReadToEndAsync()
            $taskErrors = $taskProcess.StandardError.ReadToEndAsync()
            $taskProcess.StandardInput.Write($taskConfiguration)
            $taskProcess.StandardInput.Close()
            $taskWaitSeconds = 0
            while (-not $taskProcess.WaitForExit(1000)) {
                $taskWaitSeconds++
                if (($taskWaitSeconds % 15) -eq 0) { Write-Host ('UPLOAD still running: ' + $taskWaitSeconds + 's') }
                if ($taskWaitSeconds -ge 75) {
                    $taskProcess.Kill()
                    $taskProcess.WaitForExit()
                    throw 'Upload process exceeded its time limit.'
                }
            }
            $taskText = $taskOutput.GetAwaiter().GetResult()
            $taskErrorText = $taskErrors.GetAwaiter().GetResult()
            # Only selected numeric counters are displayed; never echo raw configuration or diagnostics.
            $taskResponse = [regex]::Match($taskText, 'FTP_RESPONSE:(\d{3})').Groups[1].Value
            $taskSent = [regex]::Match($taskText, 'BYTES_SENT:(\d+)').Groups[1].Value
            Write-Host ('FTP response=' + $taskResponse + '; curl exit=' + $taskProcess.ExitCode + '; sent=' + $taskSent)
            if ($taskProcess.ExitCode -eq 0 -and $taskResponse -eq '226' -and
                [long]$taskSent -eq (Get-Item -LiteralPath $taskArtifact).Length) {
                $taskSucceeded = $true
                break
            }
            if ($taskResponse -eq '530') { throw 'FTP login was rejected. Check the Linux/FTP password; no further login retries.' }
            if ($taskResponse -eq '421') { throw 'FTP_CAPACITY_FULL (421): server unavailable or connection capacity exhausted; no automatic retry. Use the VNC clipboard fallback.' }
        } finally {
            if ($taskStarted -and -not $taskProcess.HasExited) { $taskProcess.Kill(); $taskProcess.WaitForExit() }
            $taskProcess.Dispose()
        }
        if ($taskAttempt -lt 4) { Start-Sleep -Seconds 2 }
    }
} finally {
    $taskConfiguration = $null
    $taskConfigLines = $null
    $taskAuth = $null
}
if (-not $taskSucceeded) {
    throw 'Upload was not confirmed after four attempts. Keep the file locally and report the numeric FTP response; do not paste the long payload.'
}
Write-Host 'UPLOAD_OK: entry sent to server Desktop. It has NOT been executed remotely.'
Write-Host 'Paste ONLY this short command in the server bash terminal:'
Write-Host $taskRunCommand
try {
    Set-Clipboard -Value $taskRunCommand
    Write-Host 'The short server command was copied to this computer clipboard.'
} catch {
    Write-Host 'Clipboard unavailable; type or copy the short command shown above.'
}
