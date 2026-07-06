import { NextResponse } from 'next/server'

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

export async function GET() {
  try {
    const res = await fetch(`${BACKEND}/trading/risk-assessment`, { cache: 'no-store' })
    if (!res.ok) return NextResponse.json({ success: false, risk_assessment: null }, { status: res.status })
    const json = await res.json()
    return NextResponse.json(json)
  } catch {
    return NextResponse.json({ success: false, risk_assessment: null }, { status: 502 })
  }
}
