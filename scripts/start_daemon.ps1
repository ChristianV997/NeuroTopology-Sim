<#
.SYNOPSIS
    Registers the NeuroTopology autonomous orchestrator as a Windows Task
    Scheduler job that starts at login and restarts on failure.

.DESCRIPTION
    Does NOT start the daemon. It only registers the scheduled task. Start it
    manually with:
        Start-ScheduledTask -TaskName NeuroTopologyDaemon
#>

$ErrorActionPreference = "Stop"

$RepoRoot = "C:\Users\HP\OneDrive\Documentos\GitHub\NeuroTopology-Sim"

$action = New-ScheduledTaskAction `
    -Execute "python" `
    -Argument "-m orchestrator.main_loop" `
    -WorkingDirectory $RepoRoot

$trigger = New-ScheduledTaskTrigger -AtLogOn

$settings = New-ScheduledTaskSettingsSet `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0)

Register-ScheduledTask `
    -TaskName "NeuroTopologyDaemon" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -RunLevel Highest `
    -Force

Write-Host "Daemon registered. It will start at next login, or run now:"
Write-Host "  Start-ScheduledTask -TaskName NeuroTopologyDaemon"
