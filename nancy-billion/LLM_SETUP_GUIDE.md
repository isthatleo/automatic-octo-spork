# Nancy/Billion — LLM Configuration & Setup Guide

## LLM Fallback Chain Strategy

Nancy is configured to prioritize **fast local responses** first, then fall back to specialized cloud LLMs:

```
┌─────────────────────────────────────────────────────────────┐
│  1. OLLAMA (LOCAL - FASTEST)                                 │
│  Try all locally installed models: llama2, mistral, phi, etc  │
│  → Instant responses, free, offline-capable                  │
└─────────────────────────────────────────────────────────────┘
                              ↓ (if Ollama fails)
┌─────────────────────────────────────────────────────────────┐
│  2. ANTHROPIC (Claude) - BEST FOR CODING & COMPLEX TASKS    │
│  Excellent at: code review, complex reasoning, writing       │
└─────────────────────────────────────────────────────────────┘
                              ↓ (if Claude fails)
┌─────────────────────────────────────────────────────────────┐
│  3. GROQ - FASTEST CLOUD INFERENCE                          │
│  Best for: quick conversational responses                    │
└─────────────────────────────────────────────────────────────┘
                              ↓ (if Groq fails)
┌─────────────────────────────────────────────────────────────┐
│  4. OPENAI (GPT) - GENERAL PURPOSE & BALANCED               │
│  Good at: most general tasks, research, explanations         │
└─────────────────────────────────────────────────────────────┘
                              ↓ (if OpenAI fails)
┌─────────────────────────────────────────────────────────────┐
│  5. GEMINI - MULTIMODAL & ALTERNATIVE                       │
│  Supports: vision/image analysis, multimodal inputs          │
└─────────────────────────────────────────────────────────────┘
                              ↓ (if Gemini fails)
┌─────────────────────────────────────────────────────────────┐
│  6. OPENROUTER - AGGREGATOR WITH 200+ MODELS               │
│  Fallback: access to many models via single API             │
└─────────────────────────────────────────────────────────────┘
                              ↓ (if all else fails)
┌─────────────────────────────────────────────────────────────┐
│  7. DUMMY LLM - TEST RESPONSES                              │
│  For testing when no real LLM is available                   │
└─────────────────────────────────────────────────────────────┘
```

## Installation & Configuration

### Step 1: Install Backend Dependencies

```bash
cd nancy-billion
python -m venv .venv
.venv\Scripts\Activate.ps1  # Windows PowerShell
# or on macOS/Linux: source .venv/bin/activate

pip install -r backend/requirements.txt
```

### Step 2: Install & Configure Ollama (Recommended for fastest responses)

**Download Ollama:**
- Visit https://ollama.ai
- Install for your OS

**Start Ollama Service:**
```bash
ollama serve
# Runs on http://localhost:11434
```

**Pull Local Models:**
```bash
ollama pull llama2            # 7B, fast
ollama pull mistral           # 7B, better quality
ollama pull neural-chat       # Conversation-focused
ollama pull phi               # Small but good
ollama pull neural-chat:7b    # 7B version

# Check installed models
ollama list
```

### Step 3: Configure Cloud LLM Keys

Create `.env` file in `nancy-billion/` directory:

```bash
# ============ OLLAMA (Local) ============
OLLAMA_BASE_URL=http://localhost:11434
# Auto-detection will try all installed models

# ============ ANTHROPIC (Claude) - Best for Coding ============
# Get key from: https://console.anthropic.com
ANTHROPIC_API_KEY=sk-ant-v0-xxxxxxxxxxxxxxxx
ANTHROPIC_MODEL=claude-3-opus-20240229
# Options: claude-3-opus-20240229, claude-3-sonnet-20240229, claude-3-haiku-20240307

# ============ GROQ (Fastest Cloud) ============
# Get key from: https://console.groq.com
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxx
GROQ_MODEL=mixtral-8x7b-32768
# Options: mixtral-8x7b-32768, gemma-7b-it, llama-3-70b, llama-3-8b

# ============ OPENAI (GPT - General Purpose) ============
# Get key from: https://platform.openai.com/api-keys
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxx
OPENAI_MODEL=gpt-4-turbo-preview
# Options: gpt-4-turbo-preview, gpt-4, gpt-3.5-turbo

# ============ GEMINI (Multimodal Support) ============
# Get key from: https://makersuite.google.com/app/apikey
GEMINI_API_KEY=AIzaxxxxxxxxxxxxxxxx
GEMINI_MODEL=gemini-pro

# ============ OPENROUTER (Aggregator - 200+ Models) ============
# Get key from: https://openrouter.ai
OPENROUTER_API_KEY=sk-or-xxxxxxxxxxxxxxxx
OPENROUTER_MODEL=openrouter/auto
# Options: openrouter/auto, meta-llama/llama-3-70b-instruct, mistralai/mistral-7b-instruct

# ============ BACKEND SERVER ============
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO

# ============ FURY (Optional Integration) ============
# DISABLE_FURY=0  # Set to 1 to disable if not installed

# ============ AUTO-OLLAMA ============
# DISABLE_AUTO_OLLAMA=0  # Set to 1 to disable auto-detection of local models
```

### Step 4: Run the Backend

```bash
cd nancy-billion/backend
python main_new.py
# or with uvicorn for production:
python -m uvicorn main_new:app --host 0.0.0.0 --port 8000
```

Check backend is running:
```bash
curl http://localhost:8000/
# Should return: <h1>Nancy/Billion Backend v2 — online</h1>
```

### Step 5: Run the Frontend

```bash
cd nancy-billion/frontend
npm install
npm run dev
# Opens http://localhost:3000
```

## Task-Aware LLM Routing

The frontend can send **task hints** to help Nancy pick the best LLM:

```typescript
import { sendChatMessage, detectTaskType } from '@/lib/nancy/chat-client'

// Automatic detection
const task = detectTaskType("Write me a React component for a form")
// Returns: "coding"

// Manual hints
const response = await sendChatMessage(
  "Write a function to sort an array",
  [],
  "coding"  // ← task hint: routes to Claude (Anthropic)
)

// Available hints:
// - "coding" → Uses Claude (best for code)
// - "fast_response" → Uses Groq (fastest)
// - "multimodal" → Uses Gemini (vision support)
// - null / "general" → Full fallback chain (best for balanced)
```

## Testing the Setup

### Test 1: Check LLM Backend

```bash
cd nancy-billion
python -c "from backend.llm import llm_backend; import asyncio; print(asyncio.run(llm_backend.generate('Hello', max_tokens=20)))"
```

### Test 2: Check Backend Endpoints

```bash
# List agents
curl http://localhost:8000/agents/list

# Chat endpoint
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "text": "What is 2+2?",
    "history": [],
    "task_hint": "general"
  }'

# Check which LLM was used (look at backend logs)
```

### Test 3: Test from Frontend

In the browser console (http://localhost:3000):

```javascript
import { sendChatMessage } from '@/lib/nancy/chat-client'

await sendChatMessage(
  "Hello Nancy, what can you do?",
  [],
  "general"
).then(r => console.log(r))
```

## Performance Tuning

### For Speed (Light Tasks, Conversations):
```bash
# Prioritize speed
OLLAMA_MODEL=phi              # Fastest local
GROQ_API_KEY=...             # Enable Groq
DISABLE_FURY=1               # Skip Fury overhead
```

### For Quality (Complex Tasks, Research):
```bash
# Prioritize quality
ANTHROPIC_API_KEY=...        # Enable Claude
OPENAI_API_KEY=...           # Enable GPT-4
```

### For Cost Efficiency:
```bash
# Use free/cheap options
# Ollama (free, local)
# Groq (free tier available)
# OpenRouter (pay-as-you-go)
# Disable expensive: OPENAI_API_KEY (unset)
```

## Troubleshooting

### 1. "No Ollama models found"
```bash
# Make sure Ollama is running
ollama serve

# Make sure you have models installed
ollama list

# Add a model if needed
ollama pull llama2
```

### 2. Backend shows "All LLM backends failed"
- Check `.env` for API keys
- Verify API keys are valid
- Check internet connection for cloud providers
- Look at backend logs for detailed errors

### 3. Slow responses
- Check if Ollama is running locally
- Verify `OLLAMA_BASE_URL` is correct (should be `http://localhost:11434`)
- If using cloud: check rate limits and API quotas
- Consider smaller models: `phi` instead of `llama2`

### 4. "Claude is excellent but I don't have an Anthropic API key"
- Get one at https://console.anthropic.com
- Free trial: $5 credit for testing
- Add to `.env` as `ANTHROPIC_API_KEY=sk-ant-...`

## Advanced: Adding More Models

To add a new LLM provider:

1. Create a new `class MyLLM(LLMBackend)` in `backend/llm.py`
2. Implement the `generate()` method
3. Add to `get_llm_backends()` function in priority order
4. Update this guide with setup instructions

Example:
```python
class MyLLM(LLMBackend):
    def __init__(self):
        self.api_key = os.getenv("MY_API_KEY")
    
    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        # Your implementation here
        return response
```

## Monitoring LLM Usage

Check logs to see which LLM Nancy used:

```bash
# Tail backend logs
tail -f nancy-billion.log

# Look for lines like:
# "Using AnthropicLLM for coding task"
# "Ollama model succeeded: mistral"
# "LLM backend GroqLLM succeeded"
```

---

**Questions?** Check the main README.md or examine `backend/llm.py` for the complete LLM chain implementation.

