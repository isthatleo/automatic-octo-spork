<#
  Waits for the Billion backend to actually answer, then opens the control room.

  `docker compose up -d` returns as soon as the containers exist, which is
  several seconds before they serve anything -- opening the browser straight
  away gets you a connection-refused page and the impression it's broken.
#>
$ErrorActionPreference = "SilentlyContinue"

Write-Host "Waiting for the backend..." -ForegroundColor DarkGray

$ready = $false
for ($i = 0; $i -lt 60; $i++) {
  try {
    $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "http://localhost:8000/health"
    if ($r.StatusCode -eq 200) { $ready = $true; break }
  } catch { }
  Start-Sleep -Seconds 2
}

if ($ready) {
  Write-Host "Backend is up." -ForegroundColor Cyan
} else {
  Write-Host "Backend did not answer within two minutes." -ForegroundColor Yellow
  Write-Host "Check its logs: docker compose logs -f backend" -ForegroundColor DarkGray
  Write-Host "Opening the control room anyway - it will connect once the backend catches up." -ForegroundColor DarkGray
}

Start-Process "http://localhost:3005"
