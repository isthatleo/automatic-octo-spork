import { NextResponse } from 'next/server'
import { BACKEND_URL as BACKEND, backendHeaders } from '@/lib/nancy/backend-server'


export async function GET(_request: Request, { params }: { params: Promise<{ pair: string }> }) {
  try {
    const { pair } = await params
    const res = await fetch(`${BACKEND}/trading/recommendation/${encodeURIComponent(pair)}`, { headers: backendHeaders(), cache: 'no-store' })
    if (!res.ok) return NextResponse.json({ success: false, recommendation: null }, { status: res.status })
    const json = await res.json()
    return NextResponse.json(json)
  } catch {
    return NextResponse.json({ success: false, recommendation: null }, { status: 502 })
  }
}
