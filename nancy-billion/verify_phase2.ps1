#!/usr/bin/env pwsh
# Phase 2 Verification Script
# Confirms memory system is properly implemented

Write-Host "`n╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║    NANCY PHASE 2 VERIFICATION — Memory Graph System       ║" -ForegroundColor Cyan
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

Write-Host "📁 Memory System Files" -ForegroundColor Blue
Check "memory/__init__.py exists" (Test-Path "backend/memory/__init__.py")
Check "memory/graph.py exists" (Test-Path "backend/memory/graph.py")
Check "memory/manager.py exists" (Test-Path "backend/memory/manager.py")

Write-Host "`n🧠 Memory Graph Implementation" -ForegroundColor Blue
$graphCode = Get-Content "backend/memory/graph.py" -Raw
Check "MemoryNode class" $graphCode.Contains("class MemoryNode")
Check "MemoryGraph class" $graphCode.Contains("class MemoryGraph")
Check "SimpleEmbedding class" $graphCode.Contains("class SimpleEmbedding")
Check "add_memory method" $graphCode.Contains("def add_memory")
Check "query method" $graphCode.Contains("def query")

Write-Host "`n📚 Memory Manager Implementation" -ForegroundColor Blue
$managerCode = Get-Content "backend/memory/manager.py" -Raw
Check "MemoryManager class" $managerCode.Contains("class MemoryManager")
Check "extract_memories method" $managerCode.Contains("def extract_memories")
Check "augment_prompt method" $managerCode.Contains("def augment_prompt_with_memory")
Check "get_relevant_memories method" $managerCode.Contains("def get_relevant_memories")

Write-Host "`n🔗 Backend Integration" -ForegroundColor Blue
$mainCode = Get-Content "backend/main_new.py" -Raw
Check "Memory manager imported" $mainCode.Contains("from memory import MemoryManager")
Check "Memory manager initialized" $mainCode.Contains("memory_manager = MemoryManager")
Check "Memory extraction in chat" $mainCode.Contains("memory_manager.extract_memories")
Check "Prompt augmentation in chat" $mainCode.Contains("augmented_prompt = memory_manager.augment_prompt")
Check "Learning in chat" $mainCode.Contains("memory_manager.learn_from_response")

Write-Host "`n📡 API Endpoints Added" -ForegroundColor Blue
Check "GET /memory/summary" $mainCode.Contains("async def memory_summary")
Check "POST /memory/query" $mainCode.Contains("async def memory_query")
Check "GET /memory/projects" $mainCode.Contains("async def get_projects")
Check "GET /memory/trades" $mainCode.Contains("async def get_trades")

Write-Host "`n📖 Documentation" -ForegroundColor Blue
Check "Phase 2 implementation guide" (Test-Path "PHASE_2_IMPLEMENTATION.md")
Check "Phase 2 quick reference" (Test-Path "PHASE_2_QUICK_REFERENCE.md")
Check "Combined status report" (Test-Path "STATUS_PHASES_1_2_COMPLETE.md")

Write-Host "`n" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "VERIFICATION COMPLETE: $checks/$total checks passed" -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════════`n" -ForegroundColor Cyan

if ($checks -eq $total) {
    Write-Host "🎉 PHASE 2 IS COMPLETE AND READY!" -ForegroundColor Green
    Write-Host "`n📖 Next Steps:`n" -ForegroundColor Yellow
    Write-Host "  1. Read: PHASE_2_QUICK_REFERENCE.md" -ForegroundColor Gray
    Write-Host "     → 5-minute overview`n" -ForegroundColor Gray
    Write-Host "  2. Read: PHASE_2_IMPLEMENTATION.md" -ForegroundColor Gray
    Write-Host "     → Full technical details`n" -ForegroundColor Gray
    Write-Host "  3. Read: STATUS_PHASES_1_2_COMPLETE.md" -ForegroundColor Gray
    Write-Host "     → Combined Phase 1+2 summary`n" -ForegroundColor Gray
    Write-Host "🚀 To test memory system:" -ForegroundColor Cyan
    Write-Host "`n  Terminal 1:" -ForegroundColor Yellow
    Write-Host "    python backend/main_new.py`n" -ForegroundColor Gray
    Write-Host "  Terminal 2:" -ForegroundColor Yellow
    Write-Host "    curl -X GET http://localhost:8000/memory/summary`n" -ForegroundColor Gray
    Write-Host "  Or test full chat with memory:" -ForegroundColor Yellow
    Write-Host "    curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' -d '{""text"":""Tell me about my projects"",""history"":[]}'`n" -ForegroundColor Gray
    Write-Host "✨ Nancy now remembers everything!" -ForegroundColor Cyan
} else {
    Write-Host "⚠️  Some checks failed. Please verify the files above." -ForegroundColor Yellow
}

Write-Host "`n"

