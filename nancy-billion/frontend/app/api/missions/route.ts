import { NextResponse } from 'next/server'
import { BACKEND_URL as BACKEND, backendHeaders } from '@/lib/nancy/backend-server'


export async function GET() {
  try {
    const res = await fetch(`${BACKEND}/missions`, { headers: backendHeaders(), cache: 'no-store' })
    const json = await res.json()
    return NextResponse.json(json, { status: res.status })
  } catch {
    return NextResponse.json({ success: false, missions: [] }, { status: 502 })
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const res = await fetch(`${BACKEND}/missions`, {
      method: 'POST',
      headers: backendHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body),
    })
    const json = await res.json()
    return NextResponse.json(json, { status: res.status })
  } catch {
    return NextResponse.json({ success: false }, { status: 502 })
  }
}
