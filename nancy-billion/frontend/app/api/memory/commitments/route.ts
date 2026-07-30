import { NextResponse } from 'next/server'
import { BACKEND_URL as BACKEND, backendHeaders } from '@/lib/nancy/backend-server'


export async function GET(req: Request) {
  const includeResolved = new URL(req.url).searchParams.get('include_resolved') ?? 'false'
  try {
    const res = await fetch(`${BACKEND}/memory/commitments?include_resolved=${includeResolved}`, { headers: backendHeaders(), cache: 'no-store' })
    if (!res.ok) return NextResponse.json({ success: false, commitments: [] }, { status: res.status })
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ success: false, commitments: [] }, { status: 502 })
  }
}
