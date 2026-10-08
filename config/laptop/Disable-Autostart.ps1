$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Tasks.ps1')
foreach ($taskKind in @('Gateway','Tunnel')) {
    $taskName = Get-LaptopTaskName -Kind $taskKind
    $taskService = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($taskService -and $taskService.State -eq 'Running') { throw 'Run Stop.ps1 before removing background tasks' }
    if ($taskService) { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false }
}
Write-Host 'Windows background tasks removed; project files and credentials preserved'
