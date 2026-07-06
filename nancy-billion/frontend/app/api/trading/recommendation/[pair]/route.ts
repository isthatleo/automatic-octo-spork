import { NextResponse } from 'next/server'

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

export async function GET(_request: Request, { params }: { params: Promise<{ pair: string }> }) {
  try {
    const { pair } = await params
    const res = await fetch(`${BACKEND}/trading/recommendation/${encodeURIComponent(pair)}`, { cache: 'no-store' })
    if (!res.ok) return NextResponse.json({ success: false, recommendation: null }, { status: res.status })
    const json = await res.json()
    return NextResponse.json(json)
  } catch {
    return NextResponse.json({ success: false, recommendation: null }, { status: 502 })
  }
}
