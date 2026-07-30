import { NextResponse } from 'next/server'
import { BACKEND_URL as BACKEND, backendHeaders } from '@/lib/nancy/backend-server'


export async function POST() {
  try {
    const res = await fetch(`${BACKEND}/screen-context/capture-now`, { headers: backendHeaders(), method: 'POST' })
    if (!res.ok) return NextResponse.json({ success: false }, { status: res.status })
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ success: false }, { status: 502 })
  }
}
