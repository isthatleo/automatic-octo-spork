import { NextResponse } from 'next/server'
import { backendHeaders } from '@/lib/nancy/backend-server'
import {
  getContextMeta,
  getLatestContext,
  setLatestContext,
  validateContextPayload,
} from '@/app/lib/context-bridge'

// BACKEND_URL first: that's the server-only env var docker-compose.yml
// actually sets (http://backend:8000 on the Compose network). This route
// runs INSIDE the frontend container, where localhost:8000 is the frontend
// itself, not the backend -- the exact silent-502 failure mode documented
// in the README. NANCY_BACKEND_BASE_URL is kept as an override for
// non-Docker setups that already used it; NEXT_PUBLIC_BACKEND_URL and the
// localhost default make native `next dev` on the host keep working.
const BACKEND_BASE_URL =
  process.env.BACKEND_URL ??
  process.env.NANCY_BACKEND_BASE_URL ??
  process.env.NEXT_PUBLIC_BACKEND_URL ??
  'http://localhost:8000'
const BACKEND_CONTEXT_PATH = process.env.NANCY_BACKEND_CONTEXT_PATH ?? '/context'
const BACKEND_FORWARD_TIMEOUT_MS = 3_000

const RATE_LIMIT = {
  windowMs: 10_000,
  max: 30,
}

// In-memory per-process limiter. If you run multiple Next instances, replace with Redis.
const limiter = new Map<string, { windowStart: number; count: number }>()

// Prune limiter entries whose window has long expired so the Map doesn't
// grow unboundedly across many distinct client IPs.
function pruneLimiter(now: number) {
  for (const [key, entry] of limiter) {
    if (now - entry.windowStart > RATE_LIMIT.windowMs * 2) limiter.delete(key)
  }
}

function getClientKey(request: Request): string {
  // Best-effort. In production you should trust X-Forwarded-For only from your reverse proxy.
  const ip = request.headers.get('x-forwarded-for') ?? request.headers.get('x-real-ip') ?? 'unknown'
  return String(ip).split(',')[0].trim()
}

function rateLimited(request: Request): boolean {
  const key = getClientKey(request)
  const now = Date.now()
  pruneLimiter(now)

  const entry = limiter.get(key) ?? { windowStart: now, count: 0 }
  if (now - entry.windowStart > RATE_LIMIT.windowMs) {
    entry.windowStart = now
    entry.count = 0
  }

  entry.count += 1
  limiter.set(key, entry)
  return entry.count > RATE_LIMIT.max
}

function normalizeZodError(error: unknown): string {
  if (error instanceof Error) return error.message
  return 'Invalid request payload'
}

export async function POST(request: Request) {
  const requestIdHeader = request.headers.get('x-request-id') ?? undefined

  try {
    if (rateLimited(request)) {
      return NextResponse.json({ error: 'Rate limit exceeded' }, { status: 429 })
    }

    let body: unknown
    try {
      body = await request.json()
    } catch {
      return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 })
    }

    const payload = validateContextPayload(body)

    // Prefer client request id; otherwise keep schema-parsed payload requestId.
    const mergedPayload = {
      ...payload,
      requestId: requestIdHeader ?? payload.requestId,
    }

    const stored = setLatestContext(mergedPayload)
    const meta = getContextMeta()

    const backendUrl = `${BACKEND_BASE_URL}${BACKEND_CONTEXT_PATH}`
    let backend: { ok: boolean; status?: number; error?: string } = { ok: false }

    // Best-effort forward, with a hard timeout so a hung backend can never
    // stall the UI's context POSTs (the local store above already succeeded).
    try {
      const res = await fetch(backendUrl, {
        method: 'POST',
        headers: backendHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ ...mergedPayload, receivedAt: new Date().toISOString() }),
        signal: AbortSignal.timeout(BACKEND_FORWARD_TIMEOUT_MS),
      })

      if (!res.ok) {
        backend = { ok: false, status: res.status }
      } else {
        backend = { ok: true }
      }
    } catch (e) {
      backend = { ok: false, error: (e as Error).message }
    }

    const bridge_status = backend.ok ? 'connected' : 'degraded'

    return NextResponse.json({
      success: true,
      message: backend.ok
        ? 'Context stored and forwarded to backend'
        : 'Context stored locally; backend forward failed',
      requestId: mergedPayload.requestId,
      stored,
      meta,
      backend: { ...backend, bridge_status },
    })
  } catch (error) {
    const message = normalizeZodError(error)
    const status = message.toLowerCase().includes('required') ? 400 : 500
    return NextResponse.json({ error: message }, { status })
  }
}

export async function GET() {
  try {
    const stored = getLatestContext()
    const meta = getContextMeta()

    return NextResponse.json({
      context: stored
        ? {
            ...stored.payload,
            storedAt: stored.storedAt,
            expiresAt: stored.expiresAt,
            bridge_status: stored.payload.bridgeStatus ?? 'connected',
            active_suggestions: stored.payload.active_suggestions ?? 0,
          }
        : {
            bridge_status: 'disconnected',
            active_suggestions: 0,
            timestamp: new Date().toISOString(),
          },
      meta,
      health: {
        status: stored ? 'ready' : 'no_context',
      },
      updatedAt: new Date().toISOString(),
    })
  } catch {
    return NextResponse.json({ error: 'Failed to get context' }, { status: 500 })
  }
}



