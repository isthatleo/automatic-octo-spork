import { NextResponse } from 'next/server'

const BACKEND = process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const path = searchParams.get('path') ?? ''
  if (!path) return NextResponse.json({ success: false, error: 'path is required' }, { status: 400 })
  try {
    const url = new URL(`${BACKEND}/files/read`)
    url.searchParams.set('path', path)
    const offset = searchParams.get('offset')
    const limit = searchParams.get('limit')
    if (offset) url.searchParams.set('offset', offset)
    if (limit) url.searchParams.set('limit', limit)
    const res = await fetch(url.toString(), { cache: 'no-store' })
    const json = await res.json().catch(() => ({}))
    return NextResponse.json(json, { status: res.status })
  } catch {
    return NextResponse.json({ success: false, error: 'network error' }, { status: 502 })
  }
}
