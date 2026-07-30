import { NextResponse } from 'next/server'
import { BACKEND_URL as BACKEND, backendHeaders } from '@/lib/nancy/backend-server'


export async function GET() {
  try {
    const res = await fetch(`${BACKEND}/trading/performance`, { headers: backendHeaders(), cache: 'no-store' })
    if (!res.ok) return NextResponse.json({ success: false, metrics: null }, { status: res.status })
    const json = await res.json()
    return NextResponse.json(json)
  } catch {
    return NextResponse.json({ success: false, metrics: null }, { status: 502 })
  }
}
