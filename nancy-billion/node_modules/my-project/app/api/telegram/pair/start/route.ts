import { NextResponse } from 'next/server'

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

export async function POST() {
  try {
    const res = await fetch(`${BACKEND}/telegram/pair/start`, { method: 'POST' })
    const json = await res.json()
    return NextResponse.json(json, { status: res.status })
  } catch {
    return NextResponse.json({ success: false }, { status: 502 })
  }
}
