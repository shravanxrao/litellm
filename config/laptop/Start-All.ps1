$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'Start.ps1')
& (Join-Path $PSScriptRoot 'Start-Tunnel.ps1')
