# SPDX-License-Identifier: MIT
param(
    [Parameter(Mandatory = $true)][string]$Command,
    [string]$Address = '172.16.42.1',
    [int]$Port = 2323,
    [string]$TokenPath = (Join-Path $PSScriptRoot '../.private/debug-console-token.txt'),
    [int]$TimeoutSeconds = 20
)
$ErrorActionPreference = 'Stop'
$token = (Get-Content -LiteralPath $TokenPath -Raw).Trim()
if ($token -notmatch '^[0-9a-f]{64}$') { throw 'Invalid local console token' }
$client = [System.Net.Sockets.TcpClient]::new()
$protocol = @{ State = 0; Command = 0 }
try {
    $connect = $client.ConnectAsync($Address, $Port)
    if (-not $connect.Wait(5000)) { throw 'USB console connection timed out' }
    [void]$connect.GetAwaiter().GetResult()
    $stream = $client.GetStream()
    $stream.ReadTimeout = 250
    function Send-MotoText([string]$Value) {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
        $stream.Write($bytes, 0, $bytes.Length)
    }
    function Read-MotoUntil([string]$Marker) {
        $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
        $result = [System.Text.StringBuilder]::new()
        while ([DateTime]::UtcNow -lt $deadline) {
            try { $value = $stream.ReadByte() }
            catch [System.IO.IOException] {
                if ($_.Exception.InnerException -is [System.Net.Sockets.SocketException] -and
                    $_.Exception.InnerException.SocketErrorCode -eq [System.Net.Sockets.SocketError]::TimedOut) {
                    continue
                }
                throw
            }
            if ($value -lt 0) { throw 'Device console closed before completing the request' }
            switch ($protocol.State) {
                0 {
                    if ($value -eq 255) { $protocol.State = 1 }
                    else { [void]$result.Append([char]$value) }
                }
                1 {
                    if ($value -in 251, 252, 253, 254) {
                        $protocol.Command = $value; $protocol.State = 2
                    } elseif ($value -eq 250) { $protocol.State = 3 }
                    else { $protocol.State = 0 }
                }
                2 {
                    # Refuse optional Telnet features; shell output needs none.
                    if ($protocol.Command -eq 251 -or $protocol.Command -eq 253) {
                        $reply = if ($protocol.Command -eq 251) { 254 } else { 252 }
                        $bytes = [byte[]]@(255, $reply, $value)
                        $stream.Write($bytes, 0, $bytes.Length)
                    }
                    $protocol.State = 0
                }
                3 { if ($value -eq 255) { $protocol.State = 4 } }
                4 { $protocol.State = if ($value -eq 240) { 0 } else { 3 } }
            }
            if ($result.ToString().Contains($Marker)) { return $result.ToString() }
        }
        throw "Timed out waiting for device console marker: $Marker"
    }
    [void](Read-MotoUntil 'Token: ')
    Send-MotoText "$token`r`n"
    [void](Read-MotoUntil 'MOTO_READY')
    $marker = 'MOTO_DONE_' + [guid]::NewGuid().ToString('N')
    Send-MotoText ($Command.Replace("`r", '') + "`r`nprintf '\n$marker\n'`r`n")
    $output = Read-MotoUntil $marker
    $output.Substring(0, $output.IndexOf($marker)).Trim()
} finally {
    $token = $null
    $client.Dispose()
}
