param([string]$BaseUrl = 'http://127.0.0.1:4000')
$ErrorActionPreference = 'Stop'
$taskPython = (Get-Content (Join-Path $PSScriptRoot '.runtime/python.path') -Raw).Trim()
& $taskPython (Join-Path $PSScriptRoot 'verify.py') --base-url $BaseUrl
if ($LASTEXITCODE -ne 0) { throw 'Gateway verification failed' }
