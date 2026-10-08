$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Tasks.ps1')
$taskRuntime = Join-Path $PSScriptRoot '.runtime'
Set-Content -LiteralPath (Join-Path $taskRuntime 'stop.request') -Value 'stop'
Write-Host 'Draining active requests and flushing accounting before disconnecting the tunnel'
for ($taskAttempt = 0; $taskAttempt -lt 300; $taskAttempt++) {
    $taskGateway = Get-ScheduledTask -TaskName (Get-LaptopTaskName -Kind Gateway) -ErrorAction SilentlyContinue
    if (-not $taskGateway -or $taskGateway.State -ne 'Running') {
        $taskTunnel = Get-ScheduledTask -TaskName (Get-LaptopTaskName -Kind Tunnel) -ErrorAction SilentlyContinue
        if ($taskTunnel -and $taskTunnel.State -eq 'Running') {
            Set-Content -LiteralPath (Join-Path $taskRuntime 'tunnel-stop.request') -Value 'stop'
            for ($taskTunnelAttempt = 0; $taskTunnelAttempt -lt 15; $taskTunnelAttempt++) {
                $taskTunnelState = Get-ScheduledTask -TaskName (Get-LaptopTaskName -Kind Tunnel)
                if ($taskTunnelState.State -ne 'Running') { break }
                Start-Sleep -Seconds 1
            }
            if ((Get-ScheduledTask -TaskName (Get-LaptopTaskName -Kind Tunnel)).State -eq 'Running') { throw 'The tunnel is still shutting down' }
        }
        Write-Host 'Gateway and public tunnel stopped'
        exit 0
    }
    Start-Sleep -Seconds 1
}
throw 'Gateway has not finished draining. The tunnel remains connected; no process was force-killed.'
