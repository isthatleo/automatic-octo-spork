import { NextResponse } from 'next/server'
import { BACKEND_URL as BACKEND, backendHeaders } from '@/lib/nancy/backend-server'


export async function POST(_req: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params
  try {
    const res = await fetch(`${BACKEND}/persona/${encodeURIComponent(name)}`, { headers: backendHeaders(), method: 'POST' })
    const json = await res.json().catch(() => ({}))
    if (!res.ok) return NextResponse.json({ success: false, error: json.detail ?? 'request failed' }, { status: res.status })
    return NextResponse.json(json)
  } catch {
    return NextResponse.json({ success: false, error: 'network error' }, { status: 502 })
  }
}
