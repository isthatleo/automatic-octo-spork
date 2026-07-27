import { NextResponse } from 'next/server'

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

export async function GET() {
  try {
    const res = await fetch(`${BACKEND}/channels/status`, { cache: 'no-store' })
    if (!res.ok) return NextResponse.json({ success: false, channels: [] }, { status: res.status })
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ success: false, channels: [] }, { status: 502 })
  }
}
