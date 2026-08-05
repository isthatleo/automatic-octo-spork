import { NextResponse } from 'next/server'
import { BACKEND_URL as BACKEND, backendHeaders } from '@/lib/nancy/backend-server'


export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const symbols = searchParams.get('symbols') ?? ''
  try {
    const url = new URL(`${BACKEND}/trading/crypto-quotes`)
    if (symbols) url.searchParams.set('symbols', symbols)
    const res = await fetch(url.toString(), { headers: backendHeaders(), cache: 'no-store' })
    if (!res.ok) return NextResponse.json({ success: false, quotes: [] }, { status: res.status })
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ success: false, quotes: [] }, { status: 502 })
  }
}
