import { NextResponse } from 'next/server'
import { BACKEND_URL as BACKEND, backendHeaders } from '@/lib/nancy/backend-server'


export async function POST(request: Request) {
  try {
    const body = await request.json()
    const res = await fetch(`${BACKEND}/context/analyze`, {
      method: 'POST',
      headers: backendHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ text: body.text ?? '', history: [], task_hint: null }),
    })
    if (!res.ok) return NextResponse.json({ success: false, error: 'Context analysis failed' }, { status: res.status })
    const json = await res.json()
    return NextResponse.json(json)
  } catch {
    return NextResponse.json({ success: false, error: 'Backend unreachable' }, { status: 502 })
  }
}
