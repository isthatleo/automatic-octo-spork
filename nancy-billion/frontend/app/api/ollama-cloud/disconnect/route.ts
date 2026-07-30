import { NextResponse } from 'next/server'
import { BACKEND_URL as BACKEND, backendHeaders } from '@/lib/nancy/backend-server'


export async function POST() {
  try {
    const res = await fetch(`${BACKEND}/ollama-cloud/disconnect`, {
      headers: backendHeaders(),
      method: 'POST',
      signal: AbortSignal.timeout(10_000),
    })
    return NextResponse.json(await res.json().catch(() => ({ success: false, error: `Disconnect failed (${res.status})` })), { status: res.status })
  } catch {
    return NextResponse.json({ success: false, error: 'Backend unreachable' }, { status: 502 })
  }
}
