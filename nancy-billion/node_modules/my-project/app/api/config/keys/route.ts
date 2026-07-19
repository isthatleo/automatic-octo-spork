import { NextResponse } from 'next/server'

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const res = await fetch(`${BACKEND}/config/keys`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const json = await res.json()
    return NextResponse.json(json, { status: res.status })
  } catch {
    return NextResponse.json({ success: false }, { status: 502 })
  }
}
