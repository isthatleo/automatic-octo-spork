import { NextResponse } from 'next/server'

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

export async function GET() {
  try {
    const res = await fetch(`${BACKEND}/memory/search`, {
      headers: { Accept: 'application/json' },
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const json = await res.json()
    return NextResponse.json({ ok: true, backend: json })
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: e?.message || 'memory search unavailable' }, { status: 502 })
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const res = await fetch(`${BACKEND}/memory/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({
        text: String(body?.text ?? ''),
        top_k: Number(body?.top_k ?? 10),
      }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const json = await res.json()
    return NextResponse.json({ ok: true, results: json?.results || [], backend: json })
  } catch {
    return NextResponse.json({ ok: false, results: [], error: 'Memory search failed' }, { status: 502 })
  }
}
