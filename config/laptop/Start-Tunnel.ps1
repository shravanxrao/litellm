$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Tasks.ps1')
$taskRuntime = Join-Path $PSScriptRoot '.runtime'
if (-not (Test-Path (Join-Path $taskRuntime 'tunnel.yaml'))) { throw 'Run Connect-Cloudflare.ps1 first' }
$taskReady = Invoke-WebRequest 'http://127.0.0.1:4000/health/liveliness' -TimeoutSec 5 -UseBasicParsing
if ($taskReady.StatusCode -ne 200) { throw 'The local gateway is not ready' }
Remove-Item -LiteralPath (Join-Path $taskRuntime 'tunnel-stop.request') -ErrorAction SilentlyContinue
Start-LaptopTask -Kind Tunnel
Write-Host ('Tunnel is starting: ' + (Get-Content (Join-Path $taskRuntime 'public-url.txt') -Raw).Trim() + '/v1')
