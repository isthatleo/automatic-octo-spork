/**
 * Nancy Chat Client — connects directly to the Nancy/Billion backend
 * Uses task-aware LLM routing for optimal performance and quality
 *
 * Example:
 *   const reply = await sendChatMessage("Hello Nancy", history, "general");
 *   const code = await sendChatMessage("Write a React component", history, "coding");
 */

import type { NancyDecision } from './nancy-client'

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatResponse extends NancyDecision {
  llm_backend?: string // Which LLM was used
  latency_ms?: number   // Response time
}

/**
 * Send a message to Nancy and get a decision + response.
 * @param text The user message
 * @param history Chat history for context
 * @param taskHint Optional hint for LLM selection:
 *   - "coding" → Claude (best for code)
 *   - "fast_response" → Groq (fastest inference)
 *   - "multimodal" → Gemini (vision support)
 *   - "general" or null → Ollama first, then cloud fallbacks
 * @param timeoutMs Request timeout in milliseconds (default: 30s)
 */
export async function sendChatMessage(
  text: string,
  history: ChatMessage[] = [],
  taskHint?: string | null,
  timeoutMs = 30_000
): Promise<ChatResponse> {
  const controller = new AbortController()
  const tid = setTimeout(() => controller.abort(), timeoutMs)
  const startTime = Date.now()

  try {
    const response = await fetch(`${BACKEND_URL}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        text,
        history: history.map(m => ({ role: m.role, content: m.content })),
        task_hint: taskHint || null,
      }),
      signal: controller.signal,
    })

    clearTimeout(tid)

    if (!response.ok) {
      const error = await response.text()
      const message = `HTTP ${response.status}: ${error}`
      console.error('[chat-client] Error:', message)
      throw new Error(message)
    }

    const data = (await response.json()) as ChatResponse
    const latency = Date.now() - startTime

    return {
      ...data,
      latency_ms: latency,
    }
  } catch (err) {
    clearTimeout(tid)
    console.error('[chat-client] sendChatMessage failed:', err)
    return {
      reply: `Error: ${err instanceof Error ? err.message : String(err)}`,
      action: 'none',
      category: null,
      topic: null,
      symbol: null,
      panel: null,
      target: null,
      media: null,
      autoOpenTop: false,
      latency_ms: Date.now() - startTime,
    }
  }
}

/**
 * Detect the task type from user input to enable smart LLM routing.
 * @param text User message
 * @returns Task hint string or null for general
 * @internal Used by sendChatMessage if taskHint not provided
 */
export function detectTaskType(text: string): string | null {
  const lower = text.toLowerCase()

  // Coding detection
  if (
    /\b(code|debug|write\s+code|program|algorithm|implementation|refactor|testing|test)\b/i.test(lower) ||
    /\b(python|javascript|typescript|rust|go|java|c\+\+|react|node|express)\b/i.test(lower) ||
    /```|def\s|const\s|function\s/i.test(lower)
  ) {
    return 'coding'
  }

  // Fast response needed
  if (/\b(quick|fast|urgent|asap|now|quickly|hurry)\b/i.test(lower)) {
    return 'fast_response'
  }

  // Multimodal/vision tasks
  if (/\b(image|picture|photo|vision|visual|see|look at|draw|create image)\b/i.test(lower)) {
    return 'multimodal'
  }

  // Research/learning
  if (/\b(research|explain|what is|how does|definition|learn|teach|summarize)\b/i.test(lower)) {
    return 'general'
  }

  // Conversation/general
  return null // Use full fallback chain
}

/**
 * Stream chat messages from Nancy (for future websocket support)
 * For now, returns a single response, but structure allows for future streaming
 * @internal For future use with WebSocket streaming
 */
export async function* streamChatMessage(
  text: string,
  history: ChatMessage[] = [],
  taskHint?: string | null
): AsyncGenerator<ChatResponse, void, unknown> {
  const response = await sendChatMessage(text, history, taskHint)
  yield response
}

