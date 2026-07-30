import { NextResponse } from 'next/server'
import { BACKEND_URL as BACKEND, backendHeaders } from '@/lib/nancy/backend-server'


export async function POST(request: Request) {
  try {
    const { text } = await request.json()
    const res = await fetch(`${BACKEND}/tts/synthesize`, {
      method: 'POST',
      headers: backendHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ text }),
    })
    if (!res.ok) return NextResponse.json({ success: false }, { status: res.status })
    const buf = await res.arrayBuffer()
    return new NextResponse(buf, { headers: { 'Content-Type': 'audio/wav' } })
  } catch {
    return NextResponse.json({ success: false }, { status: 502 })
  }
}
