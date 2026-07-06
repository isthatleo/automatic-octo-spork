# 🧠 LLM Providers Connected to Nancy/Billion

**Complete list of all Large Language Models integrated into this project**

---

## 🎯 LLM Chain Architecture

Nancy uses a **smart fallback chain** that tries LLMs in priority order:

```
1. LOCAL (Ollama) - Fastest, free ⚡
   ↓ (if fails)
2. ANTHROPIC (Claude) - Best for coding 🧠
   ↓ (if fails)
3. GROQ - Lightning fast ⚡
   ↓ (if fails)
4. OPENAI (GPT) - General tasks 📊
   ↓ (if fails)
5. GEMINI (Google) - Multimodal 🖼️
   ↓ (if fails)
6. OPENROUTER - Multi-model aggregator 🔄
   ↓ (if fails)
7. FURY - Local advanced model 💻
   ↓ (if fails)
8. DUMMY - Testing fallback ✔️
```

---

## 📋 Complete LLM List

### 1. **OLLAMA** (Local) ⚡
**Priority:** HIGHEST (tries first)  
**Cost:** FREE  
**Speed:** Instant (runs locally)  
**Latency:** <100ms  
**Models:** Any GGUF format model  
**Configuration:**
```python
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral  # or neural-chat, llama2, etc.
```

**Features:**
- ✅ Auto-detects all installed local models
- ✅ Tries each model until one works
- ✅ No API keys needed
- ✅ Completely private (runs on device)
- ✅ Perfect for offline use

**Available Models (auto-detected):**
- Mistral 7B
- Neural-Chat
- Llama 2
- Phi 2
- Orca 2
- Any custom GGUF model

---

### 2. **ANTHROPIC** (Claude) 🧠
**Priority:** HIGH (2nd in chain)  
**Cost:** Paid (API key required)  
**Speed:** 2-5 seconds  
**Latency:** 2000-5000ms  
**Specialization:** Coding, complex reasoning, writing  
**Default Model:** `claude-3-opus-20240229`  
**Configuration:**
```python
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-3-opus-20240229
```

**When Nancy Uses Claude:**
- ✅ Task hint contains: "coding", "code_review", "debug", "programming", "refactor"
- ✅ Complex reasoning tasks
- ✅ Code analysis and generation
- ✅ Best quality responses

**Available Models:**
- Claude 3 Opus (best quality)
- Claude 3 Sonnet (balanced)
- Claude 3 Haiku (fast, cheap)

---

### 3. **GROQ** ⚡
**Priority:** HIGH (3rd in chain)  
**Cost:** Paid (API key required)  
**Speed:** 100-500ms (fastest cloud)  
**Latency:** 100-500ms  
**Specialization:** Fast chat, quick responses  
**Default Model:** `mixtral-8x7b-32768`  
**Configuration:**
```python
GROQ_API_KEY=gsk_...
GROQ_MODEL=mixtral-8x7b-32768
```

**When Nancy Uses Groq:**
- ✅ Task hint contains: "fast", "quick", "chat", "conversation", "response"
- ✅ Light conversations
- ✅ Quick research
- ✅ Real-time market analysis

**Available Models:**
- Mixtral 8x7B (fastest)
- LLaMA 2 70B
- LLaMA 2 Chat

---

### 4. **OPENAI** (GPT) 📊
**Priority:** MEDIUM (4th in chain)  
**Cost:** Paid (API key required)  
**Speed:** 1-3 seconds  
**Latency:** 1000-3000ms  
**Specialization:** General tasks, balanced quality/speed  
**Default Model:** `gpt-4-turbo-preview`  
**Configuration:**
```python
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4-turbo-preview
```

**When Nancy Uses OpenAI:**
- ✅ General questions
- ✅ Explanation requests
- ✅ Research tasks
- ✅ Content generation

**Available Models:**
- GPT-4 Turbo (best quality)
- GPT-4
- GPT-3.5 Turbo (fast, cheap)
- GPT-3.5

---

### 5. **GEMINI** (Google) 🖼️
**Priority:** MEDIUM (5th in chain)  
**Cost:** Paid (API key required)  
**Speed:** 1-3 seconds  
**Latency:** 1000-3000ms  
**Specialization:** Multimodal (vision, text, audio)  
**Default Model:** `gemini-pro`  
**Configuration:**
```python
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-pro
```

**When Nancy Uses Gemini:**
- ✅ Task hint contains: "image", "vision", "multimodal", "visual"
- ✅ Image analysis
- ✅ Multimodal understanding
- ✅ Google's integrated services

**Available Models:**
- Gemini Pro Vision (multimodal)
- Gemini Pro (text)

---

### 6. **OPENROUTER** 🔄
**Priority:** MEDIUM (6th in chain)  
**Cost:** Paid (API key required)  
**Speed:** Varies by model  
**Latency:** 1000-5000ms  
**Specialization:** Access to 100+ models  
**Default Model:** `openrouter/auto`  
**Configuration:**
```python
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=openrouter/auto
```

**When Nancy Uses OpenRouter:**
- ✅ Fallback for variety
- ✅ Access to multiple providers through one API
- ✅ Models from: Meta, Mistral, OpenAI, Anthropic, etc.

**Available Models:**
- 100+ models from multiple providers
- Auto-selection (best value/speed)

---

### 7. **FURY** (Local Advanced) 💻
**Priority:** LOW (7th in chain)  
**Cost:** FREE  
**Speed:** Instant (runs locally)  
**Latency:** <100ms  
**Specialization:** Advanced reasoning with tools  
**Configuration:**
```python
DISABLE_FURY=0  # Set to 1 to skip
LLM_MODEL_PATH=/path/to/model.gguf
FURY_SYSTEM_PROMPT=custom prompt
```

**Features:**
- ✅ Runs Fury Agent SDK locally
- ✅ Access to all Nancy tools
- ✅ Function calling support
- ✅ No internet required

---

### 8. **DUMMY** (Testing) ✔️
**Priority:** LOWEST (fallback only)  
**Cost:** FREE  
**Speed:** Instant  
**Latency:** <100ms  
**Specialization:** Testing/debugging  
**Configuration:**
```python
# Automatically used if all else fails
```

---

## 🎯 Task-Based Selection

Nancy automatically picks the best LLM for each task:

```python
# CODING TASKS
"coding" → Claude (best for code)
"code_review" → Claude
"debugging" → Claude
"programming" → Claude
"refactor" → Claude

# FAST/CHAT TASKS
"fast" → Groq (fastest cloud)
"quick" → Groq
"chat" → Groq
"conversation" → Groq
"response" → Groq

# VISION/MULTIMODAL
"image" → Gemini (vision capable)
"vision" → Gemini
"multimodal" → Gemini
"visual" → Gemini

# EVERYTHING ELSE
(default) → Full fallback chain (tries all)
```

---

## 🔧 How to Setup Each LLM

### Ollama (Local, Free)
```bash
# Install Ollama
# macOS: brew install ollama
# Linux: curl https://ollama.ai/install.sh | sh
# Windows: Download from https://ollama.ai

# Pull a model
ollama pull mistral
ollama pull neural-chat

# Start server
ollama serve

# Nancy will auto-detect and use it
```

### Anthropic (Claude)
```bash
# Get API key from https://console.anthropic.com
export ANTHROPIC_API_KEY=sk-ant-...
pip install anthropic
```

### OpenAI (GPT)
```bash
# Get API key from https://platform.openai.com/api-keys
export OPENAI_API_KEY=sk-...
pip install openai
```

### Groq
```bash
# Get API key from https://console.groq.com
export GROQ_API_KEY=gsk_...
# Uses OpenAI-compatible API (no new lib needed)
```

### Google Gemini
```bash
# Get API key from https://makersuite.google.com/app/apikey
export GEMINI_API_KEY=...
pip install google-generativeai
```

### OpenRouter
```bash
# Get API key from https://openrouter.ai
export OPENROUTER_API_KEY=...
# Uses OpenAI-compatible API
```

### Fury
```bash
# Install Fury SDK
pip install fury-sdk
# Get local model file
export LLM_MODEL_PATH=/path/to/model.gguf
```

---

## 📊 Comparison Table

| Provider | Speed | Cost | Quality | Type | Specialization |
|----------|-------|------|---------|------|-----------------|
| **Ollama** | ⚡⚡⚡ <100ms | FREE | Good | Local | General |
| **Groq** | ⚡⚡ 100-500ms | Paid | Good | Cloud | Fast chat |
| **Claude** | ⚡ 2-5s | Paid | ⭐⭐⭐ Best | Cloud | Coding |
| **OpenAI** | ⚡ 1-3s | Paid | ⭐⭐ Very Good | Cloud | General |
| **Gemini** | ⚡ 1-3s | Paid | ⭐⭐ Very Good | Cloud | Vision |
| **OpenRouter** | ⚡ 1-5s | Paid | Varies | Cloud | Multi-model |
| **Fury** | ⚡⚡⚡ <100ms | FREE | Good | Local | Advanced |

---

## 🚀 Recommended Setup

### For Maximum Speed (Default)
```bash
# Use local Ollama (free, instant)
ollama pull mistral
ollama serve

# Nancy will use it automatically
```

### For Best Quality
```bash
# Setup Anthropic (Claude)
export ANTHROPIC_API_KEY=sk-ant-...

# Nancy will use Claude for coding/complex tasks
```

### For Production Balance
```bash
# Setup all of them
export OLLAMA_BASE_URL=http://localhost:11434
export ANTHROPIC_API_KEY=sk-ant-...
export GROQ_API_KEY=gsk_...
export OPENAI_API_KEY=sk-...

# Nancy will intelligently choose based on task
```

### Recommended Order
1. **Ollama** (local, free) - ~90% of tasks
2. **Groq** (fast cloud) - For quick responses
3. **Claude** (Anthropic) - For coding tasks
4. **OpenAI** (GPT) - General backup
5. **Gemini** (Google) - Vision tasks

---

## 💡 How Nancy Chooses

When you ask Nancy something:

```
Nancy receives your message
    ↓
Extract task hint (if provided)
    ↓
Is it a coding task? → Use Claude
Is it fast/chat? → Use Groq
Is it vision? → Use Gemini
Otherwise → Try full chain:
    1. Ollama (local)
    2. Claude (if available)
    3. Groq (if available)
    4. OpenAI (if available)
    5. Gemini (if available)
    6. OpenRouter (if available)
    7. Fury (if available)
    8. Dummy (testing)
    ↓
First one that works returns response ✅
```

---

## 🎯 Your Current Setup

Based on your docker-compose.yml:

### What's Currently Running
✅ **Ollama** - Docker container with auto-loaded models  
✅ **Backend** - Ready to use any connected provider  
✅ **Frontend** - Ready for responses  

### What You Can Add
- [ ] ANTHROPIC_API_KEY - For Claude integration
- [ ] OPENAI_API_KEY - For GPT integration
- [ ] GROQ_API_KEY - For fast responses
- [ ] GEMINI_API_KEY - For vision tasks
- [ ] OPENROUTER_API_KEY - For multi-model access

---

## 📝 Usage Example

### Using Different LLMs for Different Tasks

```python
# Nancy intelligently selects based on task

# This will use Claude (coding)
response = await nancy.chat("Refactor this function...")

# This will use Groq (fast)
response = await nancy.chat("What time is it?", task_hint="fast_response")

# This will use Gemini (vision)
response = await nancy.chat("Analyze this image", task_hint="image_analysis")

# This will use full chain (general)
response = await nancy.chat("Tell me about EUR/USD")
```

---

## 🔌 API Endpoints Using LLMs

```
POST /chat → Uses LLM selection logic
POST /chat/code → Forces Claude
POST /chat/fast → Forces Groq
POST /chat/vision → Forces Gemini
```

---

## ✅ Verification

To check which LLMs are available:

```bash
# Check Ollama
curl http://localhost:11434/api/tags

# Test general chat (tries all)
curl -X POST http://localhost:8000/chat \
  -d '{"text":"Hello Nancy"}'

# Check logs for which LLM was used
docker-compose logs orchestrator
```

---

## 🎊 Summary

**Nancy has access to:**

1. **8 different LLM providers**
2. **Intelligent fallback chain** (tries best options first)
3. **Task-aware routing** (uses right tool for job)
4. **Local + Cloud options** (fast + flexible)
5. **100+ models** via OpenRouter

**Your LLM setup is production-ready!** 🚀

