# Nancy/Billion — Frontend & Backend Integration Guide

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    FRONTEND (Next.js @ :3000)                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Voice Interface  │  Dashboard  │  Command Console       │   │
│  └──────────────────────────────────────────────────────────┘   │
│           ↓ HTTP + WebSocket (port 8000)                        │
└─────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────┐
│                   BACKEND (FastAPI @ :8000)                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ /chat (general LLM)                                      │   │
│  │ /agents/list (specialised agents)                       │   │
│  │ /agents/run (run specific agent)                        │   │
│  │ /agents/auto (auto-route to best agent)                 │   │
│  │ /ws (WebSocket for real-time streaming)                │   │
│  └──────────────────────────────────────────────────────────┘   │
│           ↓ LLM Fallback Chain                                   │
└─────────────────────────────────────────────────────────────────┘
           ↓
   ┌──────────────────────────────────────────┐
   │     1. OLLAMA (local, fastest)           │
   │     2. ANTHROPIC (Claude, best for code) │
   │     3. GROQ (fastest cloud)              │
   │     4. OPENAI (GPT, general)             │
   │     5. GEMINI (multimodal)               │
   │     6. OPENROUTER (aggregator)           │
   └──────────────────────────────────────────┘
```

## How Frontend & Backend Communicate

### 1. REST API Endpoints

#### General Chat (`/chat`)
Frontend sends a chat message and receives a decision + response.

```typescript
// Frontend (lib/nancy/chat-client.ts)
const response = await sendChatMessage(
  "What's the weather?",           // user input
  [{role: "user", content: "..."}], // history
  "general"                         // task hint (optional)
)
// Returns:
{
  reply: "I don't have weather data, but...",
  action: "none",
  category: null,
  panel: null,
  task_hint: "general",
  latency_ms: 1240
}
```

Backend processes:
```python
@app.post("/chat")
async def chat_endpoint(payload: ChatRequest):
    # 1. Select LLM based on task_hint
    selected_llm = select_llm_for_task(payload.task_hint)
    
    # 2. Generate response
    response = await selected_llm.generate(prompt, ...)
    
    # 3. Return structured response
    return { "reply": response, "action": "none", ... }
```

#### Agents Endpoints
For more complex tasks, frontend can route to specialized agents.

```typescript
// List all agents
const agents = await listAgents()

// Auto-route natural language to best agent
const result = await autoRouteAgent("Generate quantum random numbers")

// Run specific agent with typed payload
const result = await runAgent(
  "quantum_reasoning",
  "qrng",
  { n_bits: 256 }
)
```

### 2. WebSocket for Real-Time Communication

For future streaming support and real-time agent updates:

```typescript
// Frontend (in useVoice hook or component)
const ws = new WebSocket('ws://localhost:8000/ws')

ws.onopen = () => {
  // Connection established
}

ws.onmessage = (event) => {
  const message = JSON.parse(event.data)
  // Handle real-time updates
}

ws.send(JSON.stringify({
  type: "audio_chunk",
  data: audioBuffer  // for STT
}))
```

## Task-Aware LLM Routing

The frontend can provide hints to Nancy about what type of task it is:

### Task Hints

| Hint | Best LLM | Use Case |
|------|----------|----------|
| `"coding"` | Claude (Anthropic) | Code review, debugging, implementation |
| `"fast_response"` | Groq | Quick chat, conversations, light tasks |
| `"multimodal"` | Gemini | Image analysis, vision tasks |
| `null` / `"general"` | Full chain | Research, explanations, general Q&A |

### Automatic Detection

```typescript
import { detectTaskType } from '@/lib/nancy/chat-client'

const hint = detectTaskType("Write a React component for a form")
// Returns: "coding"

// Now send with hint
await sendChatMessage(text, history, hint)
// Nancy will use Claude instead of Ollama first
```

### Manual Selection

```typescript
// Force fast response for quick chat
await sendChatMessage(
  "Hi Nancy!",
  history,
  "fast_response"  // Forces Groq
)

// Request coding help
await sendChatMessage(
  "Debug this Python code",
  history,
  "coding"  // Forces Claude
)
```

## Running the Full System

### Terminal 1: Backend

```bash
cd nancy-billion
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # Windows PowerShell

pip install -r backend/requirements.txt

# Optional: Install and run Ollama first
ollama serve
# In another window: ollama pull llama2

# Then run backend
python backend/main_new.py
# Backend runs on http://localhost:8000
```

### Terminal 2: Frontend

```bash
cd nancy-billion/frontend
npm install
npm run dev
# Frontend runs on http://localhost:3000
```

### Terminal 3: Test Integration (optional)

```bash
cd nancy-billion
python test_integration.py
```

## Frontend Files for Backend Integration

### Key Frontend Files

| File | Purpose |
|------|---------|
| `lib/nancy/chat-client.ts` | Chat client that calls `/chat` endpoint |
| `lib/nancy/agent-client.ts` | Agent management (list, run, auto-route) |
| `lib/nancy/types.ts` | TypeScript types for responses |
| `app/page.tsx` | Main voice interface and workspace |
| `components/nancy/panels.tsx` | Dashboard panels |

### How Frontend Calls Backend

```typescript
// 1. Simple chat (src/lib/nancy/chat-client.ts)
import { sendChatMessage, detectTaskType } from '@/lib/nancy/chat-client'

// 2. Agent management (lib/nancy/agent-client.ts)
import { listAgents, autoRouteAgent, runAgent } from '@/lib/nancy/agent-client'

// 3. In components or hooks
const response = await sendChatMessage(text, history, detectTaskType(text))
```

## Debugging & Monitoring

### Backend Logs

```bash
# Check what LLM Nancy used
tail -f nancy-billion.log | grep -i "llm\|backend\|generate"

# Expected output:
# [INFO] Using OllamaAutoModelsLLM for task: general
# [INFO] Chat endpoint using LLM: GroqLLM (task_hint: fast_response)
# [INFO] Ollama model succeeded: mistral
```

### Frontend Console

```javascript
// In browser console (F12)
import { sendChatMessage } from '@/lib/nancy/chat-client'

// Test backend connection
const result = await sendChatMessage("Hello", [], "general")
console.log(result)
// Should show response with latency
```

### Test Endpoints with curl

```bash
# Test health
curl http://localhost:8000/

# Test chat
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "text": "What is 2+2?",
    "history": [],
    "task_hint": "general"
  }'

# List agents
curl http://localhost:8000/agents/list

# Get specific agent status
curl http://localhost:8000/agents/quantum_reasoning/status
```

## Common Issues & Solutions

### Issue 1: Frontend Can't Reach Backend

**Error:** `Failed to fetch from http://localhost:8000`

**Solution:**
- Check backend is running: `curl http://localhost:8000/`
- Check CORS: Backend should allow `http://localhost:3000`
- Check port: Backend should be on 8000, frontend on 3000
- Firewall: Allow connection between ports

```bash
# Verify port is listening
netstat -ano | findstr :8000  # Windows
lsof -i :8000                 # macOS/Linux
```

### Issue 2: LLM Returns Empty or Error

**Error:** `LLM generation failed` or empty response

**Solution:**
- Check Ollama is running: `ollama list`
- Check API keys in `.env`: `ANTHROPIC_API_KEY`, etc.
- Check backend logs for detailed error
- Try DummyLLM for testing:
  ```bash
  LLM_BACKENDS=dummy python backend/main_new.py
  ```

### Issue 3: Slow Response Times

**Causes & Solutions:**
- **Using big Ollama model?** → Use smaller: `phi`, `neural-chat:7b`
- **All cloud APIs failing?** → Check API keys and rate limits
- **Network latency?** → Use faster provider or local Ollama

### Issue 4: WebSocket Connection Fails

**Error:** `WebSocket connection failed`

**Solution:**
- Check backend WS endpoint: `curl http://localhost:8000/ws` (should fail gracefully for HTTP)
- Browser console should show WebSocket errors
- May be working but frontend not using WebSocket yet (REST API fallback works)

## Scaling & Production

### For Development
```bash
# Fast setup (no cloud API needed)
docker pull ollama/ollama
docker run -p 11434:11434 ollama/ollama
ollama pull mistral

# Run both in development mode
python backend/main_new.py  # With auto-reload
npm run dev                 # Frontend with HMR
```

### For Production
```bash
# Backend
python -m uvicorn backend.main_new:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4 \
  --ssl-keyfile=key.pem \
  --ssl-certfile=cert.pem

# Frontend
npm run build
npm start  # Or use Next.js deployment (Vercel, etc.)
```

## API Contract

### Chat Request Format
```json
{
  "text": "User message",
  "history": [
    {"role": "user", "content": "Previous message"},
    {"role": "assistant", "content": "Nancy's previous response"}
  ],
  "task_hint": "general|coding|fast_response|multimodal|null"
}
```

### Chat Response Format
```json
{
  "reply": "Nancy's response text",
  "action": "none|knowledge|news|market|locate|navigate|launch|close",
  "category": "finance|medicine|science|...|null",
  "topic": "specific topic or null",
  "symbol": "stock symbol or null",
  "panel": "overview|core|agents|system|map|null",
  "target": "target entity or null",
  "media": "articles|videos|null",
  "autoOpenTop": false
}
```

## Next Steps

1. **Configure LLM chain** → See `LLM_SETUP_GUIDE.md`
2. **Run test suite** → `python test_setup.py` and `python test_integration.py`
3. **Start backend & frontend** → See "Running the Full System" above
4. **Try voice commands** → Say "Nancy, hello!" or use text input
5. **Monitor & debug** → Check logs and browser console

---

For more information:
- Backend setup: See `LLM_SETUP_GUIDE.md`
- Project overview: See `README.md`
- API details: See `backend/main_new.py`

