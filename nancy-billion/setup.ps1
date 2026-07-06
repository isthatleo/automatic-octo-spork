#!/usr/bin/env pwsh
# Nancy/Billion Quick Start Setup Script (Windows PowerShell)
# Run: .\setup.ps1

Write-Host "`n" -ForegroundColor Cyan
Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   Nancy/Billion — Quick Start Setup (Windows PowerShell)   ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host "`n"

$ErrorActionPreference = "Stop"

# 1. Check Python
Write-Host "📋 Checking Python installation..." -ForegroundColor Blue
$pythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $version = & $cmd --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            $pythonCmd = $cmd
            Write-Host "✓ Found Python: $version" -ForegroundColor Green
            break
        }
    } catch { }
}

if (-not $pythonCmd) {
    Write-Host "✗ Python 3.10+ not found in PATH" -ForegroundColor Red
    Write-Host "`nPlease install Python from: https://www.python.org" -ForegroundColor Yellow
    Write-Host "Make sure to check 'Add Python to PATH' during installation`n" -ForegroundColor Yellow
    exit 1
}

# 2. Create virtual environment
Write-Host "`n📦 Setting up Python virtual environment..." -ForegroundColor Blue
if (-not (Test-Path ".venv")) {
    Write-Host "Creating venv..." -ForegroundColor Yellow
    & $pythonCmd -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "✗ Failed to create virtual environment" -ForegroundColor Red
        exit 1
    }
    Write-Host "✓ Virtual environment created" -ForegroundColor Green
} else {
    Write-Host "✓ Virtual environment already exists" -ForegroundColor Green
}

# 3. Activate virtual environment
Write-Host "`n🚀 Activating virtual environment..." -ForegroundColor Blue
& ".\venv\Scripts\Activate.ps1"
Write-Host "✓ Virtual environment activated" -ForegroundColor Green

# 4. Install dependencies
Write-Host "`n📥 Installing backend dependencies..." -ForegroundColor Blue
$pip = if ($pythonCmd -eq "py") { "$pythonCmd -m pip" } else { "pip" }
& $pip install -r backend/requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Failed to install dependencies" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Dependencies installed" -ForegroundColor Green

# 5. Setup environment files
Write-Host "`n⚙️ Setting up environment configuration..." -ForegroundColor Blue
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "✓ Created .env from .env.example" -ForegroundColor Green
    Write-Host "  Note: Update .env with your API keys before running" -ForegroundColor Yellow
} else {
    Write-Host "✓ .env file already exists" -ForegroundColor Green
}

if (-not (Test-Path "frontend\.env.local")) {
    Copy-Item "frontend\.env.example" "frontend\.env.local"
    Write-Host "✓ Created frontend/.env.local" -ForegroundColor Green
}

# 6. Check Ollama
Write-Host "`n🤖 Checking Ollama (optional but recommended)..." -ForegroundColor Blue
$ollamaCmd = $null
try {
    $ollamaVersion = & ollama --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        $ollamaCmd = "ollama"
        Write-Host "✓ Ollama is installed: $ollamaVersion" -ForegroundColor Green

        # Check service
        try {
            $models = & ollama list 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Host "✓ Ollama service is running" -ForegroundColor Green
            } else {
                Write-Host "⚠ Ollama not responding (will start on first use)" -ForegroundColor Yellow
            }
        } catch {
            Write-Host "⚠ Could not check Ollama service" -ForegroundColor Yellow
        }
    }
} catch {
    Write-Host "ℹ Ollama not found (optional)" -ForegroundColor Yellow
    Write-Host "  Download from: https://ollama.ai (recommended for local responses)" -ForegroundColor Gray
}

# 7. Summary and next steps
Write-Host "`n"
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "✓ Setup Complete!" -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan

Write-Host "`n📝 Next Steps:" -ForegroundColor Blue
Write-Host ""
Write-Host "1️⃣  Configure LLM Providers:" -ForegroundColor Yellow
Write-Host "   • Edit .env file with your API keys" -ForegroundColor Gray
Write-Host "   • See LLM_SETUP_GUIDE.md for detailed instructions" -ForegroundColor Gray
Write-Host ""
Write-Host "2️⃣  Start Backend:" -ForegroundColor Yellow
Write-Host "   .\$pytenvCmd\Scripts\Activate.ps1" -ForegroundColor Gray
Write-Host "   python backend/main_new.py" -ForegroundColor Gray
Write-Host "   Backend runs on: http://localhost:8000" -ForegroundColor Gray
Write-Host ""
Write-Host "3️⃣  Start Frontend (in new terminal):" -ForegroundColor Yellow
Write-Host "   cd frontend" -ForegroundColor Gray
Write-Host "   npm install  (first time only)" -ForegroundColor Gray
Write-Host "   npm run dev" -ForegroundColor Gray
Write-Host "   Frontend runs on: http://localhost:3000" -ForegroundColor Gray
Write-Host ""
Write-Host "4️⃣  Test the System:" -ForegroundColor Yellow
Write-Host "   python test_setup.py" -ForegroundColor Gray
Write-Host "   python test_integration.py" -ForegroundColor Gray
Write-Host ""
Write-Host "📚 Documentation:" -ForegroundColor Blue
Write-Host "   • README.md — Project overview" -ForegroundColor Gray
Write-Host "   • LLM_SETUP_GUIDE.md — LLM configuration" -ForegroundColor Gray
Write-Host "   • INTEGRATION_GUIDE.md — Frontend/Backend architecture" -ForegroundColor Gray
Write-Host ""
Write-Host "🎯 Quick Start (with Ollama):" -ForegroundColor Green
Write-Host "   ollama serve  # Terminal 1" -ForegroundColor Gray
Write-Host "   ollama pull mistral" -ForegroundColor Gray
Write-Host "   python backend/main_new.py  # Terminal 2" -ForegroundColor Gray
Write-Host "   cd frontend && npm run dev  # Terminal 3" -ForegroundColor Gray
Write-Host "`n"

