import { NextResponse } from 'next/server'
import { BACKEND_URL as BACKEND, backendHeaders } from '@/lib/nancy/backend-server'


export async function DELETE(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  try {
    const res = await fetch(`${BACKEND}/nodes/${encodeURIComponent(id)}`, { headers: backendHeaders(), method: 'DELETE' })
    const json = await res.json().catch(() => ({}))
    if (!res.ok) return NextResponse.json({ success: false, detail: json.detail ?? 'request failed' }, { status: res.status })
    return NextResponse.json(json)
  } catch {
    return NextResponse.json({ success: false, detail: 'network error' }, { status: 502 })
  }
}
