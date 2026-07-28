# Run this ONCE (as the normal desktop user, not elevated -- the task runs
# under this same user account so it can see the Docker Desktop process and
# CLI context that only exist inside a real logged-in session) to make
# start-docker-watch.ps1 launch automatically every time this user logs in,
# so a saved code change keeps auto-syncing into the containers without
# ever having to remember to run `docker compose watch` by hand again.

$taskName = "NancyBillionDockerWatch"
$scriptPath = Join-Path $PSScriptRoot "start-docker-watch.ps1"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$scriptPath`""

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# Explicit Interactive logon type -- an -AtLogOn trigger with no principal
# specified defaults to an S4U (non-interactive) logon on some Windows
# builds, which doesn't get the same session/desktop context a real login
# has. Confirmed live: without this, docker.exe/docker-compose.exe never
# actually launched when the task fired (LastTaskResult 1), even though
# running the identical script directly in an interactive shell worked fine.
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

# ExecutionTimeLimit Zero = never time out, since watch is meant to run forever.
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null

Write-Output "Registered scheduled task '$taskName' -- docker compose watch will now start automatically at every login."
Write-Output "To start it right now without logging out/in, run: Start-ScheduledTask -TaskName '$taskName'"
Write-Output "To remove it later: Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false"
