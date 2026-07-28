# Run this ONCE to make start-node-agent.ps1 launch automatically every
# time this user logs in -- via the Windows Startup folder, NOT Task
# Scheduler.
#
# Confirmed live this session: Task Scheduler, even with an explicit
# -LogonType Interactive principal, does not reliably attach a launched
# process to the real visible desktop session -- open_application calls
# dispatched to a Task-Scheduler-launched node_agent_stub.py reported
# success (the `start` command itself exited 0) but no window/process
# actually persisted anywhere, in any session. The exact same code,
# started via Start-Process in a genuine interactive session, worked
# correctly first try (a real, visible, persisting Notepad window). The
# Windows Startup folder runs its contents directly inside the user's own
# real logon/shell process tree, which is the standard, reliable mechanism
# for anything that needs actual desktop/GUI interaction -- unlike
# docker compose watch (register-docker-watch-task.ps1), which doesn't
# touch the GUI at all and works fine under Task Scheduler.

$scriptPath = Join-Path $PSScriptRoot "start-node-agent.ps1"
$startupDir = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupDir "NancyBillionNodeAgent.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$scriptPath`""
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Description = "Nancy/Billion node agent -- real GUI app launching for the containerized backend"
$shortcut.Save()

Write-Output "Created startup shortcut at: $shortcutPath"
Write-Output "The node agent will now start automatically at every login."
Write-Output "To start it right now without logging out/in, run:"
Write-Output "  Start-Process powershell -ArgumentList '-NoProfile','-WindowStyle','Hidden','-ExecutionPolicy','Bypass','-File','`"$scriptPath`"'"
Write-Output "To remove it later: Remove-Item `"$shortcutPath`""
