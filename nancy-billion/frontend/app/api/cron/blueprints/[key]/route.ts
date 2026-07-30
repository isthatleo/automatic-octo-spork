import { NextResponse } from 'next/server'
import { BACKEND_URL as BACKEND, backendHeaders } from '@/lib/nancy/backend-server'


export async function POST(req: Request, { params }: { params: Promise<{ key: string }> }) {
  const { key } = await params
  try {
    const body = await req.json().catch(() => ({}))
    const res = await fetch(`${BACKEND}/cron/blueprints/${encodeURIComponent(key)}`, {
      method: 'POST',
      headers: backendHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body),
    })
    const json = await res.json().catch(() => ({}))
    if (!res.ok) return NextResponse.json({ success: false, detail: json.detail ?? 'request failed' }, { status: res.status })
    return NextResponse.json(json)
  } catch {
    return NextResponse.json({ success: false, detail: 'network error' }, { status: 502 })
  }
}
