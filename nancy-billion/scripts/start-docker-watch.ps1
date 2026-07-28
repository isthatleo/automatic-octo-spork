# Keeps the nancy-backend/nancy-frontend Docker containers continuously
# in sync with source edits: launches Docker Desktop if it isn't already
# running, waits for its daemon, then runs `docker compose watch` in the
# foreground (this script's own process IS the watch process -- Task
# Scheduler keeps it alive across logins, see register-docker-watch-task.ps1).
#
# `docker compose watch` itself handles WHAT happens on a save (sync+restart
# for backend, rebuild for frontend/deps -- see docker-compose.yml's
# `develop.watch` blocks); this script only handles making sure watch is
# actually running in the first place, without a manual step every login.

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $PSScriptRoot "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$logFile = Join-Path $logDir "docker-watch.log"

function Write-Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $logFile -Value $line
}

Write-Log "start-docker-watch.ps1 starting"

$dockerDesktopExe = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
if (-not (Get-Process "Docker Desktop" -ErrorAction SilentlyContinue)) {
    Write-Log "Docker Desktop not running -- launching it"
    Start-Process $dockerDesktopExe
}

# Wait up to 5 minutes for the daemon to actually respond -- Docker Desktop
# itself can take a while to finish starting its Linux VM after the process
# launches.
$deadline = (Get-Date).AddMinutes(5)
$ready = $false
while ((Get-Date) -lt $deadline) {
    docker info *> $null
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep -Seconds 5
}

if (-not $ready) {
    Write-Log "Docker daemon never became ready after 5 minutes -- giving up"
    exit 1
}

Write-Log "Docker daemon ready -- starting docker compose watch"
Set-Location $repoRoot

# Self-healing retry loop -- confirmed live this session that `docker compose
# watch` can die (LastTaskResult 0xC000013A / STATUS_CONTROL_C_EXIT) without
# Task Scheduler's own RestartCount/RestartInterval policy actually relaunching
# it, silently ending real auto-sync until someone happened to notice. This
# script's own process (the one Task Scheduler keeps alive at logon) now owns
# retrying watch itself instead of depending on that policy working correctly.
while ($true) {
    Write-Log "launching docker compose watch"
    docker compose watch *>> $logFile
    Write-Log "docker compose watch exited (exit code $LASTEXITCODE) -- restarting in 5s"
    Start-Sleep -Seconds 5
}
