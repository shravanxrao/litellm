function Get-LaptopTaskName {
    param([ValidateSet('Gateway','Tunnel')][string]$Kind)
    $taskBytes = [System.Text.Encoding]::UTF8.GetBytes($PSScriptRoot.ToLowerInvariant())
    $taskHasher = [System.Security.Cryptography.SHA256]::Create()
    try { $taskSuffix = ([BitConverter]::ToString($taskHasher.ComputeHash($taskBytes))).Replace('-','').Substring(0,10) }
    finally { $taskHasher.Dispose() }
    return ('LiteLLM-Laptop-' + $taskSuffix + '-' + $Kind)
}

function Start-LaptopTask {
    param([ValidateSet('Gateway','Tunnel')][string]$Kind)
    $taskName = Get-LaptopTaskName -Kind $Kind
    $taskArguments = '"' + (Join-Path $PSScriptRoot 'run_process.py') + '" --kind ' + $Kind
    $taskExisting = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($taskExisting -and $taskExisting.Actions.Arguments -ne $taskArguments) { throw 'A different task already uses this identity' }
    if (-not $taskExisting) {
        $taskPython = (Get-Content (Join-Path $PSScriptRoot '.runtime/python.path') -Raw).Trim()
        $taskPythonWindowless = Join-Path (Split-Path $taskPython -Parent) 'pythonw.exe'
        if (-not (Test-Path $taskPythonWindowless)) { throw 'The prepared Windows Python environment is missing pythonw.exe' }
        $taskAction = New-ScheduledTaskAction -Execute $taskPythonWindowless -Argument $taskArguments -WorkingDirectory $PSScriptRoot
        $taskIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        $taskPrincipal = New-ScheduledTaskPrincipal -UserId $taskIdentity -LogonType Interactive -RunLevel Limited
        $taskSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -Hidden
        $taskTrigger = New-ScheduledTaskTrigger -AtLogOn -User $taskIdentity
        Register-ScheduledTask -TaskName $taskName -Action $taskAction -Principal $taskPrincipal -Settings $taskSettings -Trigger $taskTrigger -Description 'Persistent local LiteLLM hosting independent of any Codex session' | Out-Null
    }
    if ($taskExisting -and $taskExisting.State -eq 'Running') {
        Write-Host ($Kind + ' is already running')
        return
    }
    Start-ScheduledTask -TaskName $taskName
}
