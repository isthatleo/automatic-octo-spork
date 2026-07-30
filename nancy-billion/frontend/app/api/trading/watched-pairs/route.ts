import { NextResponse } from 'next/server'
import { BACKEND_URL as BACKEND, backendHeaders } from '@/lib/nancy/backend-server'


export async function GET() {
  try {
    const res = await fetch(`${BACKEND}/trading/watched-pairs`, { headers: backendHeaders(), cache: 'no-store' })
    if (!res.ok) return NextResponse.json({ success: false, watched_pairs: [], relevant_pairs: [] }, { status: res.status })
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ success: false, watched_pairs: [], relevant_pairs: [] }, { status: 502 })
  }
}

export async function POST(req: Request) {
  try {
    const body = await req.json()
    const res = await fetch(`${BACKEND}/trading/watched-pairs`, {
      method: 'POST',
      headers: backendHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body),
    })
    if (!res.ok) return NextResponse.json({ success: false }, { status: res.status })
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ success: false }, { status: 502 })
  }
}
