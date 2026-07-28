import { NextResponse } from 'next/server'

const BACKEND = process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

export async function POST(_req: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params
  try {
    const res = await fetch(`${BACKEND}/persona/${encodeURIComponent(name)}`, { method: 'POST' })
    const json = await res.json().catch(() => ({}))
    if (!res.ok) return NextResponse.json({ success: false, error: json.detail ?? 'request failed' }, { status: res.status })
    return NextResponse.json(json)
  } catch {
    return NextResponse.json({ success: false, error: 'network error' }, { status: 502 })
  }
}
