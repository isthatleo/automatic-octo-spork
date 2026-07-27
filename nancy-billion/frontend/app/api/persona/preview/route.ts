import { NextResponse } from 'next/server'

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

export async function GET() {
  try {
    const res = await fetch(`${BACKEND}/persona/preview`, { cache: 'no-store' })
    if (!res.ok) return NextResponse.json({ success: false, personas: {} }, { status: res.status })
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ success: false, personas: {} }, { status: 502 })
  }
}
