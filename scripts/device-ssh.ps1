# SPDX-License-Identifier: MIT
param([string]$Command = '')

$ErrorActionPreference = 'Stop'
$taskProject = Split-Path -Parent $PSScriptRoot
$taskPrivate = Join-Path $taskProject '.private'
$taskHostPublic = Get-Content -LiteralPath (Join-Path $taskPrivate 'dropbear-host-public.txt') |
    Where-Object { $_ -match '^ssh-ed25519 ' } | Select-Object -First 1
if (-not $taskHostPublic) { throw 'Expected debug host public key is missing.' }
$taskHostFields = $taskHostPublic -split '\s+'
$taskKnownHosts = Join-Path $taskPrivate 'device-known-hosts'
Set-Content -LiteralPath $taskKnownHosts -Value (
    '172.16.42.1 ' + $taskHostFields[0] + ' ' + $taskHostFields[1]
)
$taskSshArguments = @(
    '-i', (Join-Path $taskPrivate 'device-debug-ed25519'),
    '-o', 'IdentitiesOnly=yes',
    '-o', 'StrictHostKeyChecking=yes',
    '-o', ('UserKnownHostsFile=' + $taskKnownHosts),
    '-o', 'ConnectTimeout=10',
    '-o', 'ServerAliveInterval=3',
    '-o', 'ServerAliveCountMax=3',
    'root@172.16.42.1'
)
if ($Command) { $taskSshArguments += $Command }
& ssh @taskSshArguments
exit $LASTEXITCODE
