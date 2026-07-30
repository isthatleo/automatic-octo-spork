import { NextResponse } from 'next/server'
import { BACKEND_URL as BACKEND, backendHeaders } from '@/lib/nancy/backend-server'


export async function POST(req: Request) {
  try {
    const body = await req.json()
    const res = await fetch(`${BACKEND}/files/write`, {
      method: 'POST',
      headers: backendHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body),
    })
    const json = await res.json().catch(() => ({}))
    if (!res.ok) return NextResponse.json({ success: false, error: json.detail ?? 'request failed' }, { status: res.status })
    return NextResponse.json(json)
  } catch {
    return NextResponse.json({ success: false, error: 'network error' }, { status: 502 })
  }
}
