import { NextResponse } from 'next/server'
import { BACKEND_URL as BACKEND, backendHeaders } from '@/lib/nancy/backend-server'


export async function POST(_req: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params
  try {
    const res = await fetch(`${BACKEND}/skills/library/${encodeURIComponent(name)}/archive`, { headers: backendHeaders(), method: 'POST' })
    const json = await res.json().catch(() => ({}))
    if (!res.ok) return NextResponse.json({ success: false, detail: json.detail ?? 'request failed' }, { status: res.status })
    return NextResponse.json(json)
  } catch {
    return NextResponse.json({ success: false, detail: 'network error' }, { status: 502 })
  }
}
