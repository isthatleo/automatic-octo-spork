import { NextResponse } from 'next/server'
import { BACKEND_URL as BACKEND, backendHeaders } from '@/lib/nancy/backend-server'


export async function GET() {
  try {
    const res = await fetch(`${BACKEND}/plugins`, { headers: backendHeaders(), cache: 'no-store' })
    const json = await res.json()
    return NextResponse.json(json, { status: res.status })
  } catch {
    return NextResponse.json({ success: false, servers: [] }, { status: 502 })
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json()
    // Registering a server spawns a real subprocess -- the backend gates it
    // behind Telegram approval, which can take up to 2 minutes to resolve.
    const res = await fetch(`${BACKEND}/plugins`, {
      method: 'POST',
      headers: backendHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(130_000),
    })
    const json = await res.json()
    return NextResponse.json(json, { status: res.status })
  } catch {
    return NextResponse.json({ success: false, detail: 'Request timed out or failed' }, { status: 502 })
  }
}
