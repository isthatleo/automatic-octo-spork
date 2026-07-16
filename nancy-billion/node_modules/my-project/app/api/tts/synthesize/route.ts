import { NextResponse } from 'next/server'

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

export async function POST(request: Request) {
  try {
    const { text } = await request.json()
    const res = await fetch(`${BACKEND}/tts/synthesize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    })
    if (!res.ok) return NextResponse.json({ success: false }, { status: res.status })
    const buf = await res.arrayBuffer()
    return new NextResponse(buf, { headers: { 'Content-Type': 'audio/wav' } })
  } catch {
    return NextResponse.json({ success: false }, { status: 502 })
  }
}
