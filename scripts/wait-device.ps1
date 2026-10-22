# SPDX-License-Identifier: MIT
param([int]$TimeoutSeconds = 120, [string]$PreviousBootId = '')
$ErrorActionPreference = 'Stop'
$taskDeadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
while ([DateTime]::UtcNow -lt $taskDeadline) {
    $taskClient = [System.Net.Sockets.TcpClient]::new()
    try {
        $taskConnect = $taskClient.ConnectAsync('172.16.42.1', 22)
        if ($taskConnect.Wait(700) -and $taskClient.Connected) {
            if ($PreviousBootId) {
                $taskBoot = & "$PSScriptRoot/device-ssh.ps1" -Command 'cat /proc/sys/kernel/random/boot_id' 2>$null
                if ($LASTEXITCODE -ne 0 -or -not $taskBoot -or
                    ($taskBoot -join '').Trim() -eq $PreviousBootId) {
                    Start-Sleep -Seconds 2
                    continue
                }
            }
            Write-Output 'Native USB SSH is reachable'
            exit 0
        }
    } catch {
        # Gadget enumeration and Windows DHCP can lag behind Linux startup.
    } finally { $taskClient.Dispose() }
    Start-Sleep -Seconds 2
}
throw 'Native USB SSH did not become reachable before the timeout'
