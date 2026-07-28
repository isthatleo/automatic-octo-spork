import { NextResponse } from 'next/server'

const BACKEND = process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

export async function GET(req: Request) {
  const includeResolved = new URL(req.url).searchParams.get('include_resolved') ?? 'false'
  try {
    const res = await fetch(`${BACKEND}/memory/commitments?include_resolved=${includeResolved}`, { cache: 'no-store' })
    if (!res.ok) return NextResponse.json({ success: false, commitments: [] }, { status: res.status })
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ success: false, commitments: [] }, { status: 502 })
  }
}
