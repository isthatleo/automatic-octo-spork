import { NextResponse } from 'next/server'
import { BACKEND_URL as BACKEND, backendHeaders } from '@/lib/nancy/backend-server'


export async function GET() {
  try {
    const res = await fetch(`${BACKEND}/persona/preview`, { headers: backendHeaders(), cache: 'no-store' })
    if (!res.ok) return NextResponse.json({ success: false, personas: {} }, { status: res.status })
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ success: false, personas: {} }, { status: 502 })
  }
}
