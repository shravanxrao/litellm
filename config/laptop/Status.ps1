$ErrorActionPreference = 'Stop'
try {
    $taskResponse = Invoke-WebRequest 'http://127.0.0.1:4000/health/liveliness' -TimeoutSec 4 -UseBasicParsing
    Write-Host ('Local gateway HTTP ' + [int]$taskResponse.StatusCode)
} catch {
    Write-Host 'Local gateway is not ready'
}
Write-Host 'Admin portal: http://127.0.0.1:4000/ui/'
Write-Host 'Run Verify.ps1 to check authenticated readiness and budget rejection'
