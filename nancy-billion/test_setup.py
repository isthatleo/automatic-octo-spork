#!/usr/bin/env python3
"""
Quick test script to verify Nancy/Billion backend is configured correctly.
Run: python test_setup.py
"""

import os
import sys
import asyncio
import subprocess
from pathlib import Path

def colored(text, color):
    colors = {
        'green': '\033[92m',
        'red': '\033[91m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'reset': '\033[0m'
    }
    return f"{colors.get(color, '')}{text}{colors['reset']}"

def check_python_version():
    print(f"\n{colored('📋 Checking Python version...', 'blue')}")
    v = sys.version_info
    if v.major >= 3 and v.minor >= 10:
        print(colored(f"✓ Python {v.major}.{v.minor}.{v.micro} OK", 'green'))
        return True
    print(colored(f"✗ Python 3.10+ required, found {v.major}.{v.minor}", 'red'))
    return False

def check_venv():
    print(f"\n{colored('📋 Checking virtual environment...', 'blue')}")
    in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    if in_venv:
        print(colored(f"✓ Virtual environment active: {sys.prefix}", 'green'))
        return True
    print(colored("⚠ No virtual environment detected (not required, but recommended)", 'yellow'))
    return True

def check_dependencies():
    print(f"\n{colored('📋 Checking Python dependencies...', 'blue')}")
    required = ['fastapi', 'uvicorn', 'pydantic', 'aiohttp', 'python-dotenv']
    missing = []

    for pkg in required:
        try:
            __import__(pkg.replace('-', '_'))
            print(colored(f"✓ {pkg}", 'green'))
        except ImportError:
            print(colored(f"✗ {pkg} missing", 'red'))
            missing.append(pkg)

    if missing:
        print(f"\n{colored('To install missing packages:', 'yellow')}")
        print(f"  pip install -r backend/requirements.txt")
        return False
    return True

def check_ollama():
    print(f"\n{colored('📋 Checking Ollama...', 'blue')}")
    try:
        result = subprocess.run(['ollama', '--version'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print(colored(f"✓ Ollama installed: {result.stdout.strip()}", 'green'))

            # Check if service is running
            try:
                result = subprocess.run(['ollama', 'list', '--format', 'json'], capture_output=True, text=True, timeout=3)
                if result.returncode == 0:
                    print(colored("✓ Ollama service is running", 'green'))
                    import json
                    try:
                        data = json.loads(result.stdout)
                        if isinstance(data, list) and data:
                            models = [m.get('name') or m.get('model') for m in data]
                            print(colored(f"✓ Available models: {', '.join(models[:3])}", 'green'))
                            return True
                    except:
                        pass
                    return True
            except:
                print(colored("⚠ Ollama service not responding (not running, or will start on first use)", 'yellow'))
                return True
        return False
    except FileNotFoundError:
        print(colored("⚠ Ollama not found (not required, but recommended for fast local responses)", 'yellow'))
        print(colored("  Download from: https://ollama.ai", 'yellow'))
        return True
    except Exception as e:
        print(colored(f"⚠ Could not check Ollama: {e}", 'yellow'))
        return True

def check_api_keys():
    print(f"\n{colored('📋 Checking API keys...', 'blue')}")
    from dotenv import load_dotenv
    load_dotenv()

    keys = {
        'ANTHROPIC_API_KEY': 'Claude (Anthropic)',
        'GROQ_API_KEY': 'Groq (Fast)',
        'OPENAI_API_KEY': 'OpenAI (GPT)',
        'GEMINI_API_KEY': 'Gemini (Google)',
        'OPENROUTER_API_KEY': 'OpenRouter (Aggregator)',
    }

    found = 0
    for key, name in keys.items():
        if os.getenv(key):
            print(colored(f"✓ {name} API key configured", 'green'))
            found += 1
        else:
            print(colored(f"  {name} API key not configured", 'yellow'))

    print(colored(f"\nCloud providers configured: {found}/5", 'blue'))
    if found == 0:
        print(colored("ℹ Using Ollama (local) for responses", 'blue'))
    return True

def check_backend_imports():
    print(f"\n{colored('📋 Testing backend imports...', 'blue')}")
    try:
        os.chdir('backend')
        from llm import llm_backend, get_llm_backends
        print(colored("✓ LLM backend imports successful", 'green'))

        backends = get_llm_backends()
        print(colored(f"✓ LLM chain configured with {len(backends)} backend(s):", 'green'))
        for b in backends:
            print(f"  - {b.__class__.__name__}")

        os.chdir('..')
        return True
    except Exception as e:
        print(colored(f"✗ Backend import failed: {e}", 'red'))
        return False

async def test_llm_generation():
    print(f"\n{colored('📋 Testing LLM generation...', 'blue')}")
    try:
        os.chdir('backend')
        from llm import llm_backend

        print(colored("  Generating test response...", 'blue'))
        response = await llm_backend.generate("Say hello", max_tokens=20, temperature=0.5)
        print(colored(f"✓ Generated: {response[:50]}...", 'green'))

        os.chdir('..')
        return True
    except Exception as e:
        print(colored(f"✗ LLM generation failed: {e}", 'red'))
        print(colored("  (This is OK if all cloud providers are misconfigured)", 'yellow'))
        os.chdir('..')
        return False

def main():
    os.chdir(Path(__file__).parent)
    print(colored("\n🚀 Nancy/Billion Backend Setup Test\n", 'blue'))

    checks = [
        ("Python version", check_python_version),
        ("Virtual environment", check_venv),
        ("Dependencies", check_dependencies),
        ("Ollama", check_ollama),
        ("API keys", check_api_keys),
        ("Backend imports", check_backend_imports),
    ]

    results = []
    for name, check in checks:
        try:
            result = check()
            results.append((name, result))
        except Exception as e:
            print(colored(f"✗ {name} check failed: {e}", 'red'))
            results.append((name, False))

    # Test LLM generation
    try:
        asyncio.run(test_llm_generation())
        results.append(("LLM generation", True))
    except Exception as e:
        print(colored(f"✗ LLM generation test failed: {e}", 'red'))
        results.append(("LLM generation", False))

    # Summary
    print(f"\n{colored('═' * 60, 'blue')}")
    print(f"\n{colored('Test Summary:', 'blue')}")
    passed = sum(1 for _, r in results if r)
    total = len(results)
    print(colored(f"{passed}/{total} checks passed\n", 'green' if passed == total else 'yellow'))

    if passed == total:
        print(colored("✓ Backend is ready! Start with:", 'green'))
        print(colored("  cd nancy-billion/backend", 'blue'))
        print(colored("  python main_new.py", 'blue'))
    else:
        print(colored("⚠ Some checks failed. See above for details.", 'yellow'))
        print(colored("  Most tests are informational; proceed if Ollama or API keys are configured.", 'yellow'))

if __name__ == '__main__':
    main()

