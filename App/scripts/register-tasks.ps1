<#
Registers the OKEEF inbox watcher as a Scheduled Task that runs at user logon.
Safe to re-run -- unregisters any existing "OKEEF Watcher" task first.

Ollama needs no registration here: its own Windows installer already registers it
to auto-start at login. Open WebUI is deliberately NOT auto-started (see
scripts\start-openwebui.ps1) -- it's only needed when actively chatting.
#>

$ErrorActionPreference = "Stop"

$bundleRoot = (Resolve-Path "$PSScriptRoot\..").Path
$pythonw = Join-Path $bundleRoot ".venv\Scripts\pythonw.exe"

if (-not (Test-Path $pythonw)) {
    throw "pythonw.exe not found at $pythonw -- run setup.ps1 first to create the ingestion pipeline venv."
}

$taskName = "OKEEF Watcher"

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute $pythonw -Argument "-m okeef.cli watch" -WorkingDirectory $bundleRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries `
    -StartWhenAvailable

try {
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
        -Description "Watches $bundleRoot\_inbox and runs new files through the OKEEF ingestion pipeline." `
        -ErrorAction Stop | Out-Null
} catch {
    # Register-ScheduledTask's CIM provider can write a non-terminating error that
    # slips past $ErrorActionPreference, so this catch + an explicit existence check
    # below are both needed to avoid silently reporting success on a real failure.
    Write-Error "Register-ScheduledTask failed: $($_.Exception.Message)"
}

if (-not (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue)) {
    throw "Task '$taskName' was not actually registered (Task Scheduler write access was denied). " +
          "Run this script yourself in a normal (or elevated, if that's also denied) PowerShell window: " +
          "$PSCommandPath"
}

Write-Output "Registered scheduled task '$taskName' (runs at logon, restarts up to 3x on failure, works unplugged/offline)."
Write-Output "To start it right now without logging off: Start-ScheduledTask -TaskName '$taskName'"
Write-Output "To check status: Get-ScheduledTask -TaskName '$taskName' | Get-ScheduledTaskInfo"
Write-Output "Watcher logs: $bundleRoot\logs\watcher.log"
