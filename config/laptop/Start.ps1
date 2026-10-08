$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Tasks.ps1')
Start-LaptopTask -Kind Gateway
for ($taskAttempt = 0; $taskAttempt -lt 120; $taskAttempt++) {
    try {
        $taskReady = Invoke-WebRequest 'http://127.0.0.1:4000/health/liveliness' -TimeoutSec 2 -UseBasicParsing
        if ($taskReady.StatusCode -eq 200) {
            Write-Host 'Gateway is ready: http://127.0.0.1:4000/ui/'
            exit 0
        }
    } catch {}
    Start-Sleep -Seconds 1
}
throw 'Gateway startup did not reach readiness. Inspect the private server logs.'
