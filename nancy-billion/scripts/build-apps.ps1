<#
  Billion — one-command app builder for Windows.

    .\scripts\build-apps.ps1              # Windows desktop app (.exe installer + portable)
    .\scripts\build-apps.ps1 desktop      # same, explicitly
    .\scripts\build-apps.ps1 android      # generate + open the Android project
    .\scripts\build-apps.ps1 all          # both

  iOS cannot be built on Windows — that one needs a Mac with Xcode.
  Needs network on first run (npm downloads Electron / Capacitor).
#>
param([string]$Target = "desktop")

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

function Say  ($m) { Write-Host "> $m" -ForegroundColor Cyan }
function Note ($m) { Write-Host "  $m" -ForegroundColor DarkGray }
function Die  ($m) { Write-Host "x $m" -ForegroundColor Red; exit 1 }

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  Die "Node.js not found. Install Node 18+ from https://nodejs.org and re-run."
}
$nodeMajor = [int](node -p "process.versions.node.split('.')[0]")
if ($nodeMajor -lt 18) { Die "Node 18+ required (found $(node -v))." }

Write-Host ""
Write-Host "  B I L L I O N" -ForegroundColor Yellow -NoNewline
Write-Host "  app builder - host: windows" -ForegroundColor DarkGray
Write-Host ""

function Build-Desktop {
  Say "Desktop app (windows)"
  Push-Location "$Root\desktop"
  try {
    Note "installing electron + electron-builder (first run takes a few minutes)..."
    npm install --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { Die "npm install failed in desktop/." }
    Note "packaging..."
    npm run dist:win
    if ($LASTEXITCODE -ne 0) { Die "electron-builder failed." }
    Write-Host ""
    Write-Host "OK Desktop app built." -ForegroundColor Cyan
    Note "artifacts: desktop\dist\"
    Get-ChildItem "$Root\desktop\dist" -ErrorAction SilentlyContinue |
      ForEach-Object { Note "    $($_.Name)" }
  } finally { Pop-Location }
}

function Build-Android {
  Say "Mobile app (android)"
  Push-Location "$Root\mobile"
  try {
    Note "installing capacitor..."
    npm install --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { Die "npm install failed in mobile/." }
    if (-not (Test-Path "$Root\mobile\android")) {
      npx cap add android
    } else {
      Note "android project already exists - reusing it."
    }
    Note "generating app icons + splash..."
    npm run assets --silent
    if ($LASTEXITCODE -ne 0) { Note "icon generation skipped - the default icon will be used." }
    npx cap sync android
    node scripts\patch-native.js
    Write-Host ""
    Write-Host "OK Android project ready." -ForegroundColor Cyan
    Note "opening Android Studio - then press Run to launch the emulator."
    npx cap open android
    if ($LASTEXITCODE -ne 0) { Note "Android Studio not found. Open mobile\android manually." }
  } finally { Pop-Location }
}

switch ($Target.ToLower()) {
  "desktop" { Build-Desktop }
  "android" { Build-Android }
  "ios"     { Die "iOS apps can only be built on macOS with Xcode." }
  "all"     { Build-Desktop; Build-Android; Note "iOS skipped (needs macOS)." }
  default   { Die "Unknown target '$Target'. Use: desktop | android | all" }
}

Write-Host ""
Write-Host "Remember: the apps are a window onto your stack. Start it first with" -ForegroundColor DarkGray
Write-Host "  docker compose up -d" -ForegroundColor Yellow
Write-Host ""
