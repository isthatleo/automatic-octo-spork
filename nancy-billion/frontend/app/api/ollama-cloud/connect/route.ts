import { NextResponse } from 'next/server'
import { BACKEND_URL as BACKEND, backendHeaders } from '@/lib/nancy/backend-server'


export async function POST(request: Request) {
  try {
    const body = await request.json()
    if (!body?.api_key || typeof body.api_key !== 'string') {
      return NextResponse.json({ success: false, error: 'api_key required' }, { status: 400 })
    }
    // Backend validates the key live against ollama.com (can take a few
    // seconds) before persisting + hot-rebuilding the LLM chain.
    const res = await fetch(`${BACKEND}/ollama-cloud/connect`, {
      method: 'POST',
      headers: backendHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ api_key: body.api_key }),
      signal: AbortSignal.timeout(20_000),
    })
    return NextResponse.json(await res.json().catch(() => ({ success: false, error: `Connect failed (${res.status})` })), { status: res.status })
  } catch {
    return NextResponse.json({ success: false, error: 'Backend unreachable' }, { status: 502 })
  }
}
