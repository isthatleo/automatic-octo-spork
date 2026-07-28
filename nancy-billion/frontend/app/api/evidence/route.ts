import { NextResponse } from 'next/server'

const BACKEND = process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const limit = searchParams.get('limit') ?? '20'
  const kind = searchParams.get('kind')
  try {
    const url = new URL(`${BACKEND}/evidence`)
    url.searchParams.set('limit', limit)
    if (kind) url.searchParams.set('kind', kind)
    const res = await fetch(url.toString(), { cache: 'no-store' })
    if (!res.ok) return NextResponse.json({ success: false, evidence: [] }, { status: res.status })
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ success: false, evidence: [] }, { status: 502 })
  }
}
