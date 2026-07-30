<#
  Turn on authentication for Billion.

    .\scripts\lock-down.ps1              # generate a token + passcode, write them to backend\.env
    .\scripts\lock-down.ps1 -Passcode "my own words"
    .\scripts\lock-down.ps1 -Off         # turn it back off

  What this switches on:
    BACKEND_AUTH_TOKEN  - every backend route needs it (health checks excepted)
    BILLION_PASSCODE    - the control room asks for it once per device

  You never type the token anywhere. The frontend holds it server-side and
  attaches it to calls the browser makes through /api/backend/*; the CLI reads
  it from the same .env. The passcode is the only thing you enter by hand.
#>
param(
  [string]$Passcode,
  [switch]$Off
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $Root "backend\.env"

function Note ($m) { Write-Host "  $m" -ForegroundColor DarkGray }
function Die  ($m) { Write-Host "x $m" -ForegroundColor Red; exit 1 }

if (-not (Test-Path $EnvFile)) { Die "backend\.env not found. Copy backend\.env.example to backend\.env first." }

function Set-EnvVar([string]$name, [string]$value) {
  $lines = Get-Content $EnvFile
  $found = $false
  $out = foreach ($line in $lines) {
    if ($line -match "^\s*#?\s*$name=") { $found = $true; "$name=$value" } else { $line }
  }
  if (-not $found) { $out = $out + "$name=$value" }
  Set-Content $EnvFile $out
}

function New-Secret([int]$bytes) {
  $b = New-Object 'System.Byte[]' $bytes
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
  [Convert]::ToBase64String($b).TrimEnd('=').Replace('+','-').Replace('/','_')
}

Write-Host ""
if ($Off) {
  Set-EnvVar "BACKEND_AUTH_TOKEN" ""
  Set-EnvVar "BILLION_PASSCODE" ""
  Write-Host "  Authentication is OFF." -ForegroundColor Yellow
  Note "Fine on a machine only you can reach. Not fine on a shared network."
  Note "Restart to apply:  docker compose up -d"
  Write-Host ""
  exit 0
}

$backup = "$EnvFile.bak-$(Get-Date -Format yyyyMMdd-HHmmss)"
Copy-Item $EnvFile $backup

$token = New-Secret 32
if (-not $Passcode) { $Passcode = New-Secret 9 }

Set-EnvVar "BACKEND_AUTH_TOKEN" $token
Set-EnvVar "BILLION_PASSCODE" $Passcode
Set-EnvVar "BILLION_SESSION_SECRET" (New-Secret 32)

Write-Host "  Billion is locked." -ForegroundColor Cyan
Write-Host ""
Write-Host "  Your passcode:  " -NoNewline -ForegroundColor DarkGray
Write-Host $Passcode -ForegroundColor Yellow
Write-Host ""
Note "The control room asks for it once per device, then remembers for 30 days."
Note "The API token was generated too - you never need to see or type it."
Note "Previous .env kept as $(Split-Path $backup -Leaf)"
Write-Host ""
Note "Apply it:  docker compose up -d"
Write-Host ""
