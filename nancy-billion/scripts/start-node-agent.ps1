# Runs node_agent_stub.py natively on THIS real Windows desktop, so the
# backend (which runs inside a Docker container with no display of its own)
# can dispatch real GUI actions here -- opening an application, taking a
# screenshot -- somewhere the user can actually see them, instead of only
# ever affecting the invisible container.
#
# Registered as node "host" in backend/data/nodes.json (bind-mounted into
# the container), reachable from inside the container at
# http://host.docker.internal:8100 -- the same host.docker.internal fix
# this session's Ollama connectivity bug needed.
#
# Self-healing retry loop, same reasoning as start-docker-watch.ps1: don't
# depend on Task Scheduler's own restart-on-failure policy actually firing
# (confirmed live this session that it silently didn't for the docker
# watch task).

# Deliberately NOT "Stop" -- confirmed live this session: with it set,
# uvicorn's own normal INFO logging on stderr gets wrapped by PowerShell's
# native-command-error handling into a terminating NativeCommandError,
# silently killing this whole script (breaking out of the retry loop below)
# the instant the server logs its very first line, even though it had
# actually started successfully.
$ErrorActionPreference = "Continue"

$backendDir = Join-Path (Split-Path -Parent $PSScriptRoot) "backend"
$logDir = Join-Path $PSScriptRoot "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$logFile = Join-Path $logDir "node-agent.log"

function Write-Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $logFile -Value $line
}

# Read NODE_SHARED_SECRET from backend/.env (never hardcoded here -- this
# script is git-tracked, .env is not) -- must match backend/data/nodes.json's
# "host" entry's shared_secret exactly; both were generated together when
# this was first set up.
$envFile = Join-Path $backendDir ".env"
$secretLine = Get-Content $envFile | Where-Object { $_ -match '^NODE_SHARED_SECRET=' } | Select-Object -First 1
if (-not $secretLine) {
    Write-Log "NODE_SHARED_SECRET not found in $envFile -- cannot start"
    exit 1
}
$env:NODE_SHARED_SECRET = ($secretLine -split '=', 2)[1].Trim()
$env:NODE_AGENT_PORT = "8100"

Write-Log "start-node-agent.ps1 starting"
Set-Location $backendDir

while ($true) {
    Write-Log "launching node_agent_stub.py"
    python node_agent_stub.py *>> $logFile
    Write-Log "node_agent_stub.py exited (exit code $LASTEXITCODE) -- restarting in 5s"
    Start-Sleep -Seconds 5
}
