param([string]$SecretsFile = '', [string]$Hostname = '', [string]$PythonExe = 'python', [switch]$UseExistingPython)
$ErrorActionPreference = 'Stop'
$taskRepository = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$taskRuntime = Join-Path $PSScriptRoot '.runtime'
New-Item -ItemType Directory -Path $taskRuntime -Force | Out-Null
& icacls $taskRuntime /inheritance:r /grant:r ($env:USERNAME + ':(OI)(CI)F') | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not restrict the private runtime directory' }
if (-not $UseExistingPython) {
    & $PythonExe -m venv (Join-Path $taskRuntime 'venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the project Python environment' }
    $PythonExe = Join-Path $taskRuntime 'venv/Scripts/python.exe'
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        & uv pip install --python $PythonExe 'litellm[proxy,extra_proxy]==1.104.0' 'litellm-proxy-extras==0.4.102.post1' --only-binary litellm
    } else {
        & $PythonExe -m pip install 'litellm[proxy,extra_proxy]==1.104.0' 'litellm-proxy-extras==0.4.102.post1' --only-binary litellm
    }
    if ($LASTEXITCODE -ne 0) { throw 'LiteLLM dependency installation failed' }
}
$taskArguments = @((Join-Path $PSScriptRoot 'setup.py'), '--hostname', $Hostname)
if ($SecretsFile) { $taskArguments += @('--import-secrets', (Resolve-Path -LiteralPath $SecretsFile).Path) }
& $PythonExe @taskArguments
if ($LASTEXITCODE -ne 0) { throw 'Laptop configuration failed' }
if (Test-Path (Join-Path $taskRuntime '.env')) {
    & icacls (Join-Path $taskRuntime '.env') /inheritance:r /grant:r ($env:USERNAME + ':(F)') | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not restrict private settings to the current Windows account' }
}
$taskBinary = Join-Path $taskRuntime 'cloudflared.exe'
if (-not (Test-Path $taskBinary)) {
    Invoke-WebRequest 'https://github.com/cloudflare/cloudflared/releases/download/2026.10.0/cloudflared-windows-amd64.exe' -OutFile $taskBinary
}
if ((Get-FileHash -LiteralPath $taskBinary -Algorithm SHA256).Hash.ToLowerInvariant() -ne '86aee4017b26625cee8484c113558f48effa4cd47f7aa05fcf425604e5d2b23c') { throw 'Cloudflare binary checksum failed' }
Write-Host 'The verified Cloudflare tunnel tool is ready'
& $PythonExe (Join-Path $PSScriptRoot 'generate_client.py')
if ($LASTEXITCODE -ne 0) { throw 'Database client generation failed; see the private client-generation.log' }
Write-Host 'Keep the private .runtime folder out of Git and backups shared with teammates'
