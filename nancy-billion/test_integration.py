#!/usr/bin/env python3
"""
Nancy/Billion Frontend-Backend Integration Test
Run: python test_integration.py

Tests:
1. Backend HTTP endpoints
2. LLM generation with task hints
3. Agent endpoints
4. WebSocket connection (optional)
"""

import os
import sys
import asyncio
import json
import httpx
from pathlib import Path

BACKEND_URL = os.getenv("NANCY_BACKEND_URL", "http://localhost:8000")

def colored(text, color):
    colors = {
        'green': '\033[92m',
        'red': '\033[91m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'reset': '\033[0m'
    }
    return f"{colors.get(color, '')}{text}{colors['reset']}"

async def test_health():
    """Test if backend is running"""
    print(f"\n{colored('🔍 Testing backend health...', 'blue')}")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BACKEND_URL}/", timeout=5)
            if response.status_code == 200:
                print(colored(f"✓ Backend is online at {BACKEND_URL}", 'green'))
                return True
            else:
                print(colored(f"✗ Backend returned {response.status_code}", 'red'))
                return False
        except Exception as e:
            print(colored(f"✗ Cannot reach backend: {e}", 'red'))
            print(colored(f"  Make sure backend is running: python backend/main_new.py", 'yellow'))
            return False

async def test_chat_general():
    """Test chat endpoint with general task"""
    print(f"\n{colored('🗣️ Testing chat endpoint (general task)...', 'blue')}")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{BACKEND_URL}/chat",
                json={
                    "text": "What is 2+2?",
                    "history": [],
                    "task_hint": "general"
                },
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                reply = data.get('reply', '')[:80]
                print(colored(f"✓ Reply: {reply}...", 'green'))
                return True
            else:
                print(colored(f"✗ Chat failed with {response.status_code}", 'red'))
                print(colored(f"  Response: {response.text}", 'yellow'))
                return False
        except Exception as e:
            print(colored(f"✗ Chat request failed: {e}", 'red'))
            return False

async def test_chat_with_hints():
    """Test chat endpoint with task hints"""
    print(f"\n{colored('💡 Testing task-aware LLM routing...', 'blue')}")

    test_cases = [
        ("Write a Python function to sort a list", "coding", "Coding task"),
        ("Tell me a joke quickly", "fast_response", "Fast response task"),
        ("Analyze this image", "multimodal", "Multimodal task"),
    ]

    async with httpx.AsyncClient() as client:
        for text, hint, description in test_cases:
            try:
                response = await client.post(
                    f"{BACKEND_URL}/chat",
                    json={
                        "text": text,
                        "history": [],
                        "task_hint": hint
                    },
                    timeout=30
                )
                if response.status_code == 200:
                    print(colored(f"✓ {description} (hint={hint})", 'green'))
                else:
                    print(colored(f"⚠ {description} returned {response.status_code}", 'yellow'))
            except Exception as e:
                print(colored(f"⚠ {description} failed: {e}", 'yellow'))

async def test_agents_list():
    """Test agents endpoint"""
    print(f"\n{colored('🤖 Testing agents endpoint...', 'blue')}")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BACKEND_URL}/agents/list", timeout=10)
            if response.status_code == 200:
                data = response.json()
                agents_count = len(data.get('agents', []))
                print(colored(f"✓ Found {agents_count} agents", 'green'))
                return True
            else:
                print(colored(f"✗ Agents endpoint failed with {response.status_code}", 'red'))
                return False
        except Exception as e:
            print(colored(f"⚠ Agents endpoint unavailable: {e}", 'yellow'))
            return True  # Not critical

async def test_complete_conversation():
    """Test a multi-turn conversation"""
    print(f"\n{colored('💬 Testing multi-turn conversation...', 'blue')}")

    conversation = [
        ("Hello Nancy", None),
        ("What is your name?", None),
        ("Can you help me code?", "coding"),
    ]

    history = []
    async with httpx.AsyncClient() as client:
        for i, (text, hint) in enumerate(conversation):
            try:
                response = await client.post(
                    f"{BACKEND_URL}/chat",
                    json={
                        "text": text,
                        "history": history,
                        "task_hint": hint
                    },
                    timeout=30
                )
                if response.status_code == 200:
                    data = response.json()
                    reply = data.get('reply', '')[:60]
                    print(colored(f"  [{i+1}] User: {text}", 'blue'))
                    print(colored(f"      Nancy: {reply}...", 'green'))

                    # Add to history
                    history.append({"role": "user", "content": text})
                    history.append({"role": "assistant", "content": data.get('reply', '')})
                else:
                    print(colored(f"✗ Turn {i+1} failed", 'red'))
                    break
            except Exception as e:
                print(colored(f"✗ Turn {i+1} failed: {e}", 'red'))
                break

async def main():
    print(colored("\n═══════════════════════════════════════════════════════", 'blue'))
    print(colored("  Nancy/Billion — Frontend/Backend Integration Test", 'blue'))
    print(colored("═══════════════════════════════════════════════════════\n", 'blue'))

    # Test health first
    if not await test_health():
        print(colored("\n❌ Backend is not running. Start it with:", 'red'))
        print(colored("  cd nancy-billion/backend", 'yellow'))
        print(colored("  python main_new.py", 'yellow'))
        sys.exit(1)

    # Run tests
    await test_chat_general()
    await test_chat_with_hints()
    await test_agents_list()
    await test_complete_conversation()

    print(f"\n{colored('═══════════════════════════════════════════════════════', 'blue')}")
    print(colored("\n✓ Integration tests complete!", 'green'))
    print(colored("\nNext steps:", 'blue'))
    print(colored("  1. Start frontend: cd frontend && npm run dev", 'yellow'))
    print(colored("  2. Open browser: http://localhost:3000", 'yellow'))
    print(colored("  3. Try voice commands or use the dashboard", 'yellow'))

if __name__ == '__main__':
    asyncio.run(main())

