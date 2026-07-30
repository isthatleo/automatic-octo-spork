<#
  Move Billion's runtime state out of the OneDrive-synced folder.

    .\scripts\move-data-off-onedrive.ps1                 # move to C:\billion-data
    .\scripts\move-data-off-onedrive.ps1 -Target D:\bd   # somewhere else
    .\scripts\move-data-off-onedrive.ps1 -WhatIf         # show the plan, change nothing

  Why: backend/data holds a live SQLite database (conversation_log.sqlite,
  opened in WAL mode, so it also has -wal and -shm sidecars) and JSON stores
  that get rewritten several times per chat turn. OneDrive opens, hashes,
  uploads and can dehydrate those files underneath a process that is holding
  them open. The failure isn't a sync conflict you'd notice -- it's a corrupt
  FTS5 index or a half-written JSON store that silently loads as empty.

  The repo itself stays in OneDrive. Only the state moves.

  Nothing is deleted: the old folders are renamed to *.moved-<timestamp> so
  you can check the copy landed before removing them yourself.
#>
param(
  [string]$Target = "C:\billion-data",
  [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

function Say  ($m) { Write-Host "> $m" -ForegroundColor Cyan }
function Note ($m) { Write-Host "  $m" -ForegroundColor DarkGray }
function Warn ($m) { Write-Host "! $m" -ForegroundColor Yellow }
function Die  ($m) { Write-Host "x $m" -ForegroundColor Red; exit 1 }

# The three state directories compose bind-mounts into the container.
$Dirs = @("data", "skills", "backups")

Write-Host ""
Write-Host "  Billion - moving runtime state out of OneDrive" -ForegroundColor Yellow
Note "from: $Root\backend\{$($Dirs -join ', ')}"
Note "to:   $Target"
Write-Host ""

# --- refuse to run while the stack is up ------------------------------------
$running = $false
try {
  $ps = docker ps --filter "name=nancy-backend" --format "{{.Names}}" 2>$null
  if ($ps -match "nancy-backend") { $running = $true }
} catch { Note "docker not reachable - skipping the running-stack check." }

if ($running) {
  Die "nancy-backend is running. Stop it first (docker compose down), then re-run - copying a live SQLite database is exactly the corruption this script exists to prevent."
}

if ($WhatIf) { Warn "-WhatIf: showing the plan only, nothing will change." }

# --- copy ---------------------------------------------------------------
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
foreach ($d in $Dirs) {
  $src = Join-Path $Root "backend\$d"
  $dst = Join-Path $Target $d

  if (-not (Test-Path $src)) {
    Note "$d - nothing there yet, creating it at the destination."
    if (-not $WhatIf) { New-Item -ItemType Directory -Force -Path $dst | Out-Null }
    continue
  }

  $size = (Get-ChildItem $src -Recurse -File -ErrorAction SilentlyContinue |
           Measure-Object -Property Length -Sum).Sum
  $mb = if ($size) { [math]::Round($size / 1MB, 1) } else { 0 }
  Say "$d ($mb MB)"

  if ($WhatIf) { Note "would copy $src -> $dst, then rename the original"; continue }

  New-Item -ItemType Directory -Force -Path $dst | Out-Null
  # /E all subdirs incl. empty, /COPY:DAT keep timestamps, /R:1 don't retry forever
  robocopy $src $dst /E /COPY:DAT /R:1 /W:1 /NFL /NDL /NJH /NJS | Out-Null
  if ($LASTEXITCODE -ge 8) { Die "robocopy failed on $d (exit $LASTEXITCODE). Nothing was renamed; your data is untouched." }

  $srcCount = (Get-ChildItem $src -Recurse -File -ErrorAction SilentlyContinue).Count
  $dstCount = (Get-ChildItem $dst -Recurse -File -ErrorAction SilentlyContinue).Count
  if ($dstCount -lt $srcCount) {
    Die "$d - copied $dstCount of $srcCount files. Stopping with the original intact."
  }
  Note "verified $dstCount file(s)"

  Rename-Item $src "$d.moved-$stamp"
  Note "original kept as backend\$d.moved-$stamp"
}

# --- point compose at the new location --------------------------------------
$compose = Join-Path $Root "docker-compose.yml"
$text = Get-Content $compose -Raw
$posix = $Target.Replace('\', '/')

$new = $text `
  -replace '- \./backend/data:/app/data',       "- $posix/data:/app/data" `
  -replace '- \./backend/skills:/app/skills',   "- $posix/skills:/app/skills" `
  -replace '- \./backend/backups:/app/backups', "- $posix/backups:/app/backups"

if ($new -eq $text) {
  Warn "docker-compose.yml already points somewhere else - left it alone. Check its backend volumes by hand."
} elseif (-not $WhatIf) {
  Copy-Item $compose "$compose.bak-$stamp"
  Set-Content $compose $new -NoNewline
  Say "docker-compose.yml updated (previous version kept as docker-compose.yml.bak-$stamp)"
} else {
  Note "would rewrite the three backend volume lines in docker-compose.yml"
}

Write-Host ""
if ($WhatIf) {
  Write-Host "Plan only - nothing changed. Re-run without -WhatIf to do it." -ForegroundColor Yellow
} else {
  Write-Host "Done." -ForegroundColor Cyan
  Note "start the stack:  docker compose up -d"
  Note "then check your memories and conversation search still work,"
  Note "and delete the backend\*.moved-$stamp folders once you're happy."
}
Write-Host ""
