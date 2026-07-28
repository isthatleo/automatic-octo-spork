import { NextResponse } from 'next/server'

const BACKEND = process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const pairs = searchParams.get('pairs') ?? ''
  try {
    const url = new URL(`${BACKEND}/trading/quotes`)
    if (pairs) url.searchParams.set('pairs', pairs)
    const res = await fetch(url.toString(), { cache: 'no-store' })
    if (!res.ok) return NextResponse.json({ success: false, quotes: [] }, { status: res.status })
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ success: false, quotes: [] }, { status: 502 })
  }
}
