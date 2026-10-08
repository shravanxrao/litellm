param([Parameter(Mandatory=$true)][string]$Hostname, [string]$TunnelName = 'litellm-laptop')
$ErrorActionPreference = 'Stop'
if ($Hostname -notmatch '^(?=.{1,253}$)([a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$') { throw 'Provide a hostname such as api.example.com' }
if ($TunnelName -notmatch '^[a-zA-Z0-9-]{1,63}$') { throw 'Invalid tunnel name' }
$taskRuntime = Join-Path $PSScriptRoot '.runtime'
$taskBinary = Join-Path $taskRuntime 'cloudflared.exe'
$taskCertificate = Join-Path $taskRuntime 'cert.pem'
$taskCredentials = Join-Path $taskRuntime 'tunnel.json'
if (-not (Test-Path $taskCertificate)) {
    & $taskBinary tunnel --origincert $taskCertificate login
    if ($LASTEXITCODE -ne 0) { throw 'Cloudflare authorization did not complete' }
}
if (-not (Test-Path $taskCredentials)) {
    & $taskBinary tunnel --origincert $taskCertificate --credentials-file $taskCredentials create $TunnelName
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Cloudflare tunnel; no existing tunnel was changed' }
}
$taskTunnelId = (Get-Content $taskCredentials -Raw | ConvertFrom-Json).TunnelID
if ($taskTunnelId -notmatch '^[a-fA-F0-9-]{36}$') { throw 'Invalid saved tunnel identity' }
& $taskBinary tunnel --origincert $taskCertificate route dns $taskTunnelId $Hostname
if ($LASTEXITCODE -ne 0) { throw 'DNS connection failed; an existing DNS record may need review' }
$taskConfig = @"
tunnel: $taskTunnelId
credentials-file: '$($taskCredentials.Replace('\', '/'))'
metrics: 127.0.0.1:20241
ingress:
  - hostname: $Hostname
    service: http://127.0.0.1:4000
    originRequest:
      connectTimeout: 10s
      disableChunkedEncoding: false
  - service: http_status:404
"@
Set-Content -LiteralPath (Join-Path $taskRuntime 'tunnel.yaml') -Value $taskConfig -Encoding utf8
Set-Content -LiteralPath (Join-Path $taskRuntime 'public-url.txt') -Value ('https://' + $Hostname) -Encoding utf8
foreach ($taskPrivateFile in @($taskCertificate, $taskCredentials)) {
    & icacls $taskPrivateFile /inheritance:r /grant:r ($env:USERNAME + ':(F)') | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not restrict Cloudflare credentials to the current Windows account' }
}
Write-Host ('Public API address configured: https://' + $Hostname + '/v1')
Write-Host 'Run Start-Tunnel.ps1 after the local gateway is ready'
