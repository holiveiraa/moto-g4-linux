# SPDX-License-Identifier: MIT
# Deploy native audio userspace. Does not flash or reboot the phone.
$ErrorActionPreference = 'Stop'
$taskProject = Split-Path -Parent $PSScriptRoot
& "$PSScriptRoot/device-ssh.ps1" -Command 'umask 077; mkdir -p /var/lib/moto-audio-study; set --; for p in /etc/init.d/moto-network /etc/init.d/moto-audio /usr/sbin/moto-audio.py /etc/asound.conf /etc/moto-audio.json /usr/sbin/moto-audio-start; do [ ! -f "$p" ] || set -- "$@" "$p"; done; tar -czf "/var/lib/moto-audio-study/userspace-$(date -u +%Y%m%dT%H%M%SZ).tar.gz" "$@"'
if ($LASTEXITCODE -ne 0) { throw 'Audio userspace backup failed' }
$taskFiles = @(
    @('native/moto-audio-start.py', '/usr/sbin/moto-audio-start', '755'),
    @('native/moto-audio.py', '/usr/sbin/moto-audio.py', '644'),
    @('config/moto-audio.json', '/etc/moto-audio.json', '644'),
    @('config/moto-asound.conf', '/etc/asound.conf', '644'),
    @('config/moto-audio.openrc', '/etc/init.d/moto-audio', '755'),
    @('config/moto-network.openrc', '/etc/init.d/moto-network', '755')
)
foreach ($taskFile in $taskFiles) {
    & "$PSScriptRoot/device-upload.ps1" -Source (Join-Path $taskProject $taskFile[0]) -RemotePath $taskFile[1] -Mode $taskFile[2]
    if ($LASTEXITCODE -ne 0) { throw "Audio upload failed: $($taskFile[0])" }
}
& "$PSScriptRoot/device-ssh.ps1" -Command 'python3 -m py_compile /usr/sbin/moto-audio-start /usr/sbin/moto-audio.py && rc-update add moto-audio default && rc-update -u && rc-service moto-audio start'
if ($LASTEXITCODE -ne 0) { throw 'Audio startup failed; inspect /var/log/moto-audio-start.log over USB' }
