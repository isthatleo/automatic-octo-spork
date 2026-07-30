import { NextResponse } from 'next/server'
import { BACKEND_URL as BACKEND, backendHeaders } from '@/lib/nancy/backend-server'


export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const pairs = searchParams.get('pairs') ?? ''
  try {
    const url = new URL(`${BACKEND}/trading/quotes`)
    if (pairs) url.searchParams.set('pairs', pairs)
    const res = await fetch(url.toString(), { headers: backendHeaders(), cache: 'no-store' })
    if (!res.ok) return NextResponse.json({ success: false, quotes: [] }, { status: res.status })
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ success: false, quotes: [] }, { status: 502 })
  }
}
