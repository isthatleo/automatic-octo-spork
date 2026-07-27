import { NextResponse } from 'next/server'

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

export async function GET(_req: Request, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params
  try {
    const res = await fetch(`${BACKEND}/memory/wiki/${encodeURIComponent(slug)}`, { cache: 'no-store' })
    const json = await res.json().catch(() => ({}))
    return NextResponse.json(json, { status: res.status })
  } catch {
    return NextResponse.json({ success: false, error: 'network error' }, { status: 502 })
  }
}
