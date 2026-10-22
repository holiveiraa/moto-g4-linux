# SPDX-License-Identifier: MIT
param(
    [Parameter(Mandatory = $true)][string]$RemotePath,
    [Parameter(Mandatory = $true)][string]$Destination,
    [switch]$Gzip
)
$ErrorActionPreference = 'Stop'
if ($RemotePath -notmatch '^/[A-Za-z0-9_./-]+$') { throw 'Unsupported remote path' }
$project = Split-Path -Parent $PSScriptRoot
$process = [System.Diagnostics.Process]::new()
$process.StartInfo.FileName = 'ssh.exe'
$process.StartInfo.UseShellExecute = $false
$process.StartInfo.RedirectStandardOutput = $true
$arguments = @(
    '-i', (Join-Path $project '.private/device-debug-ed25519'),
    '-o', 'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=yes',
    '-o', ('UserKnownHostsFile=' + (Join-Path $project '.private/device-known-hosts')),
    '-o', 'ConnectTimeout=10', 'root@172.16.42.1', ('cat ' + $RemotePath)
)
foreach ($argument in $arguments) { [void]$process.StartInfo.ArgumentList.Add($argument) }
$fileOutput = [System.IO.File]::Create([System.IO.Path]::GetFullPath($Destination))
$output = $fileOutput
if ($Gzip) {
    # Compress on the PC: no phone CPU load or temporary copy on eMMC/RAM.
    $output = [System.IO.Compression.GZipStream]::new(
        $fileOutput, [System.IO.Compression.CompressionLevel]::Fastest, $true
    )
}
try {
    [void]$process.Start()
    $process.StandardOutput.BaseStream.CopyTo($output)
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) { throw "Device download failed: $($process.ExitCode)" }
} finally {
    $output.Dispose()
    if ($Gzip) { $fileOutput.Dispose() }
    $process.Dispose()
}
