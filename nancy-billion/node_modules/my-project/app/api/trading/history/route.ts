import { NextResponse } from 'next/server'

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url)
    const limit = searchParams.get('limit') ?? '50'
    const res = await fetch(`${BACKEND}/trading/history?limit=${limit}`, { cache: 'no-store' })
    if (!res.ok) return NextResponse.json({ success: false, trades: [] }, { status: res.status })
    const json = await res.json()
    return NextResponse.json(json)
  } catch {
    return NextResponse.json({ success: false, trades: [] }, { status: 502 })
  }
}
