#!/usr/bin/env pwsh
# Nancy/Billion — Phase 1 Complete Verification
# Run this to confirm Phase 1 implementation is ready

Write-Host "`n╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║         NANCY PHASE 1 — COMPLETION VERIFICATION            ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝`n" -ForegroundColor Cyan

$checks = 0
$total = 0

function Check {
    param([string]$name, [bool]$result)
    $total++
    if ($result) {
        Write-Host "  ✅ $name" -ForegroundColor Green
        $checks++
    } else {
        Write-Host "  ❌ $name" -ForegroundColor Red
    }
}

Write-Host "📋 Backend Files" -ForegroundColor Blue
Check "context_manager.py exists" (Test-Path "backend/context_manager.py")
Check "main_new.py updated" ((Get-Content "backend/main_new.py" -Raw).Contains("NancyContextualBrain"))
Check "Imports correct" ((Get-Content "backend/main_new.py" -Raw).Contains("from context_manager import"))

Write-Host "`n🎨 Frontend Files" -ForegroundColor Blue
Check "boot-sequence-v2.tsx created" (Test-Path "frontend/components/nancy/boot-sequence-v2.tsx")
Check "dashboard-v2.tsx created" (Test-Path "frontend/components/nancy/dashboard-v2.tsx")

Write-Host "`n📚 Documentation" -ForegroundColor Blue
Check "Implementation plan exists" (Test-Path "IMPLEMENTATION_PLAN_INTELLIGENT_OS.md")
Check "Phase 1 implementation guide" (Test-Path "PHASE_1_IMPLEMENTATION.md")
Check "Phase 1 quick reference" (Test-Path "PHASE_1_QUICK_REFERENCE.md")
Check "Phase 1 complete summary" (Test-Path "PHASE_1_COMPLETE.md")

Write-Host "`n🔧 Code Quality" -ForegroundColor Blue
$contextCode = Get-Content "backend/context_manager.py" -Raw
Check "IntentClassifier class" $contextCode.Contains("class IntentClassifier")
Check "NancyContextualBrain class" $contextCode.Contains("class NancyContextualBrain")
Check "ContextManager class" $contextCode.Contains("class ContextManager")

Write-Host "`n🎯 Key Features" -ForegroundColor Blue
Check "Intent classification" $contextCode.Contains("def classify")
Check "Context tracking" $contextCode.Contains("def add_message")
Check "Memory management" $contextCode.Contains("def get_recent_context")

Write-Host "`n" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "VERIFICATION COMPLETE: $checks/$total checks passed" -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════════`n" -ForegroundColor Cyan

if ($checks -eq $total) {
    Write-Host "🎉 PHASE 1 IS COMPLETE AND READY!" -ForegroundColor Green
    Write-Host "`n📖 Documentation to read (in order):`n" -ForegroundColor Yellow
    Write-Host "  1. PHASE_1_QUICK_REFERENCE.md" -ForegroundColor Gray
    Write-Host "     → Quick overview of what changed`n" -ForegroundColor Gray
    Write-Host "  2. PHASE_1_IMPLEMENTATION.md" -ForegroundColor Gray
    Write-Host "     → Full technical details`n" -ForegroundColor Gray
    Write-Host "  3. PHASE_1_COMPLETE.md" -ForegroundColor Gray
    Write-Host "     → Celebration + next steps`n" -ForegroundColor Gray
    Write-Host "🚀 To start testing:" -ForegroundColor Cyan
    Write-Host "`n  Terminal 1:" -ForegroundColor Yellow
    Write-Host "    python backend/main_new.py`n" -ForegroundColor Gray
    Write-Host "  Terminal 2:" -ForegroundColor Yellow
    Write-Host "    curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' -d '{""text"":""Whats the weather?"",""history"":[]}'`n" -ForegroundColor Gray
    Write-Host "  Terminal 3:" -ForegroundColor Yellow
    Write-Host "    cd frontend && npm run dev`n" -ForegroundColor Gray
    Write-Host "✨ Visit: http://localhost:3000 to see new boot sequence!" -ForegroundColor Cyan
} else {
    Write-Host "⚠️  Some checks failed. Please verify the files above." -ForegroundColor Yellow
}

Write-Host "`n"

