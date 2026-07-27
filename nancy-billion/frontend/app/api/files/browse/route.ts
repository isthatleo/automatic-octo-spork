import { NextResponse } from 'next/server'

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const path = searchParams.get('path') ?? '.'
  try {
    const url = new URL(`${BACKEND}/files/browse`)
    url.searchParams.set('path', path)
    const res = await fetch(url.toString(), { cache: 'no-store' })
    const json = await res.json().catch(() => ({}))
    return NextResponse.json(json, { status: res.status })
  } catch {
    return NextResponse.json({ success: false, error: 'network error' }, { status: 502 })
  }
}
