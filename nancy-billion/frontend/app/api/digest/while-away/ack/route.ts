import { NextResponse } from 'next/server'
import { BACKEND_URL as BACKEND, backendHeaders } from '@/lib/nancy/backend-server'


export async function POST() {
  try {
    const res = await fetch(`${BACKEND}/digest/while-away/ack`, { headers: backendHeaders(), method: 'POST' })
    const json = await res.json()
    return NextResponse.json(json, { status: res.status })
  } catch {
    return NextResponse.json({ success: false }, { status: 502 })
  }
}
