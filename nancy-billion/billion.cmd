@echo off
REM Billion terminal launcher.
REM
REM Double-click this, or run `billion` from the repo root (add this folder to
REM PATH for the latter). Anything you pass through lands on the CLI, so
REM `billion "what's my disk looking like"` works as a one-shot too.
REM
REM The CLI is a client -- it needs the stack running. If nothing is answering
REM on port 8000 this offers to start it rather than dropping you into a dead
REM prompt.

setlocal
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
  echo.
  echo   Python was not found on PATH.
  echo   Install it from https://python.org and reopen this window.
  echo.
  pause
  exit /b 1
)

REM Is the backend answering?
python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health',timeout=2)" >nul 2>&1
if errorlevel 1 (
  echo.
  echo   Billion's backend isn't answering on port 8000.
  echo.
  choice /c YN /n /m "  Start the stack now with docker compose? [Y/N] "
  if errorlevel 2 goto :run
  echo.
  docker compose up -d
  if errorlevel 1 (
    echo.
    echo   Could not start the stack. Is Docker Desktop running?
    echo.
    pause
    exit /b 1
  )
  echo   Waiting for the backend...
  for /l %%i in (1,1,60) do (
    python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health',timeout=2)" >nul 2>&1
    if not errorlevel 1 goto :run
    timeout /t 2 /nobreak >nul
  )
  echo   Still no answer. Check: docker compose logs -f backend
  echo.
)

:run
python "%~dp0cli\billion.py" %*
endlocal
