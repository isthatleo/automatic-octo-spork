import { NextResponse } from 'next/server'
import { BACKEND_URL as BACKEND, backendHeaders } from '@/lib/nancy/backend-server'


export async function GET() {
  try {
    const res = await fetch(`${BACKEND}/mdns/status`, { headers: backendHeaders(), cache: 'no-store' })
    const json = await res.json().catch(() => ({}))
    return NextResponse.json(json, { status: res.status })
  } catch {
    return NextResponse.json({ success: false, advertising: false }, { status: 502 })
  }
}
