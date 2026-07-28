import { NextResponse } from 'next/server'

const BACKEND = process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const pattern = searchParams.get('pattern') ?? ''
  if (!pattern) return NextResponse.json({ success: false, error: 'pattern is required' }, { status: 400 })
  try {
    const url = new URL(`${BACKEND}/files/glob`)
    url.searchParams.set('pattern', pattern)
    url.searchParams.set('path', searchParams.get('path') ?? '.')
    const res = await fetch(url.toString(), { cache: 'no-store' })
    const json = await res.json().catch(() => ({}))
    return NextResponse.json(json, { status: res.status })
  } catch {
    return NextResponse.json({ success: false, error: 'network error' }, { status: 502 })
  }
}
