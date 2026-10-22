# SPDX-License-Identifier: MIT
param(
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string]$RemotePath,
    [ValidateSet('600','644','700','755')][string]$Mode = '600'
)
$ErrorActionPreference = 'Stop'
if ($RemotePath -notmatch '^/[A-Za-z0-9_./-]+$') { throw 'Unsupported remote path' }
if ($Mode -eq '755') {
    $taskBytes = [byte[]]::new(256)
    $taskStream = [System.IO.File]::OpenRead([System.IO.Path]::GetFullPath($Source))
    try { $taskRead = $taskStream.Read($taskBytes, 0, $taskBytes.Length) } finally { $taskStream.Dispose() }
    if ($taskRead -ge 2 -and $taskBytes[0] -eq 35 -and $taskBytes[1] -eq 33) {
        $taskFirstNewline = [Array]::IndexOf($taskBytes, [byte]10)
        if ($taskFirstNewline -gt 0 -and $taskBytes[$taskFirstNewline - 1] -eq 13) {
            throw 'Executable has a Windows CRLF shebang. Convert it to LF before uploading.'
        }
    }
}
$project = Split-Path -Parent $PSScriptRoot
$process = [System.Diagnostics.Process]::new()
$process.StartInfo.FileName = 'ssh.exe'
$process.StartInfo.UseShellExecute = $false
$process.StartInfo.RedirectStandardInput = $true
$arguments = @(
    '-i', (Join-Path $project '.private/device-debug-ed25519'),
    '-o', 'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=yes',
    '-o', ('UserKnownHostsFile=' + (Join-Path $project '.private/device-known-hosts')),
    '-o', 'ConnectTimeout=10', 'root@172.16.42.1',
    ('umask 077; cat > ' + $RemotePath + '; chmod ' + $Mode + ' ' + $RemotePath)
)
foreach ($argument in $arguments) { [void]$process.StartInfo.ArgumentList.Add($argument) }
$inputFile = [System.IO.File]::OpenRead([System.IO.Path]::GetFullPath($Source))
try {
    [void]$process.Start()
    $inputFile.CopyTo($process.StandardInput.BaseStream)
    $process.StandardInput.Close()
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) { throw "Device upload failed: $($process.ExitCode)" }
} finally {
    $inputFile.Dispose()
    $process.Dispose()
}
