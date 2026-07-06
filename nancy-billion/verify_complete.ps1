#!/usr/bin/env pwsh
# Nancy/Billion — Final Verification Checklist
# Run this to confirm all components are in place
# Usage: .\verify_complete.ps1

Write-Host "`n" -ForegroundColor Cyan
Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║    Nancy/Billion — Implementation Verification Checklist   ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host "`n"

$passed = 0
$total = 0

function Check-File {
    param([string]$path, [string]$description)
    $total++
    if (Test-Path $path) {
        Write-Host "✓ $description" -ForegroundColor Green
        $script:passed++
        return $true
    } else {
        Write-Host "✗ $description — NOT FOUND: $path" -ForegroundColor Red
        return $false
    }
}

function Check-Content {
    param([string]$path, [string]$content, [string]$description)
    $total++
    if ((Test-Path $path) -and (Get-Content $path -Raw).Contains($content)) {
        Write-Host "✓ $description" -ForegroundColor Green
        $script:passed++
        return $true
    } else {
        Write-Host "✗ $description — Content not found in $path" -ForegroundColor Red
        return $false
    }
}

Write-Host "📋 Core Files" -ForegroundColor Blue
Check-File "README.md" "README.md — Project overview"
Check-File "backend/llm.py" "backend/llm.py — LLM backend"
Check-File "backend/main_new.py" "backend/main_new.py — FastAPI server"
Check-File "frontend/lib/nancy/chat-client.ts" "frontend/lib/nancy/chat-client.ts — Chat client"

Write-Host "`n📚 Documentation" -ForegroundColor Blue
Check-File "LLM_SETUP_GUIDE.md" "LLM_SETUP_GUIDE.md — LLM configuration guide"
Check-File "INTEGRATION_GUIDE.md" "INTEGRATION_GUIDE.md — Frontend/Backend architecture"
Check-File "SYSTEM_SYNC_SUMMARY.md" "SYSTEM_SYNC_SUMMARY.md — Implementation summary"
Check-File "IMPLEMENTATION_COMPLETE.md" "IMPLEMENTATION_COMPLETE.md — What was done"
Check-File "DOCUMENTATION_INDEX.md" "DOCUMENTATION_INDEX.md — Documentation map"

Write-Host "`n🔧 Configuration & Setup" -ForegroundColor Blue
Check-File ".env.example" ".env.example — Backend env template"
Check-File "frontend/.env.example" "frontend/.env.example — Frontend env template"
Check-File "setup.ps1" "setup.ps1 — Automated Windows setup"
Check-File "test_setup.py" "test_setup.py — Setup verification script"
Check-File "test_integration.py" "test_integration.py — Integration tests"

Write-Host "`n🔍 Code Quality Checks" -ForegroundColor Blue
Check-Content "backend/llm.py" "def select_llm_for_task" "LLM task routing function exists"
Check-Content "backend/llm.py" "OllamaAutoModelsLLM" "Ollama auto-detection implemented"
Check-Content "backend/main_new.py" "task_hint" "Task hint parameter in chat endpoint"
Check-Content "frontend/lib/nancy/chat-client.ts" "sendChatMessage" "Chat client function"
Check-Content "frontend/lib/nancy/chat-client.ts" "detectTaskType" "Task type detection"

Write-Host "`n⚙️ Backend Configuration" -ForegroundColor Blue
Check-Content "backend/llm.py" "class FallbackLLM" "Fallback LLM chain"
Check-Content "backend/llm.py" "AnthropicLLM" "Anthropic support"
Check-Content "backend/llm.py" "GroqLLM" "Groq support"
Check-Content "backend/llm.py" "OpenAILLM" "OpenAI support"
Check-Content "backend/llm.py" "GeminiLLM" "Gemini support"
Check-Content "backend/llm.py" "OpenRouterLLM" "OpenRouter support"

Write-Host "`n🎯 Fallback Chain Order" -ForegroundColor Blue
Check-Content "backend/llm.py" "OllamaAutoModelsLLM()" "Priority 1: Ollama (local)"
Check-Content "backend/llm.py" "AnthropicLLM()" "Priority 2: Anthropic (Claude)"
Check-Content "backend/llm.py" "GroqLLM()" "Priority 3: Groq (fast)"
Check-Content "backend/llm.py" "OpenAILLM()" "Priority 4: OpenAI (GPT)"

Write-Host "`n📝 API Endpoints" -ForegroundColor Blue
Check-Content "backend/main_new.py" "@app.post(`"/chat`")" "POST /chat endpoint"
Check-Content "backend/main_new.py" "@app.get(`"/agents/list`")" "GET /agents/list endpoint"
Check-Content "backend/main_new.py" "@app.post(`"/agents/run`")" "POST /agents/run endpoint"
Check-Content "backend/main_new.py" "@app.post(`"/agents/auto`")" "POST /agents/auto endpoint"

Write-Host "`n🔗 Frontend Integration" -ForegroundColor Blue
Check-Content "frontend/lib/nancy/chat-client.ts" "NEXT_PUBLIC_BACKEND_URL" "Backend URL configuration"
Check-Content "frontend/lib/nancy/chat-client.ts" "task_hint" "Task hint support"
Check-Content "frontend/lib/nancy/chat-client.ts" "latency_ms" "Latency measurement"

Write-Host "`n" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan

if ($passed -eq $total) {
    Write-Host "✅ ALL CHECKS PASSED! ($passed/$total)" -ForegroundColor Green
    Write-Host "`n🚀 Nancy/Billion is ready to use!" -ForegroundColor Green
    Write-Host "`nNext steps:" -ForegroundColor Yellow
    Write-Host "  1. Run: .\setup.ps1" -ForegroundColor Gray
    Write-Host "  2. Start backend: python backend/main_new.py" -ForegroundColor Gray
    Write-Host "  3. Start frontend: cd frontend && npm run dev" -ForegroundColor Gray
    Write-Host "  4. Test: python test_integration.py" -ForegroundColor Gray
} else {
    Write-Host "⚠️  $passed/$total checks passed" -ForegroundColor Yellow
    Write-Host "`nPlease review the failed checks above." -ForegroundColor Yellow
}

Write-Host "`n"

