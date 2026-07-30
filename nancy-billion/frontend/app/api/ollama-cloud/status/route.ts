import { NextResponse } from 'next/server'
import { BACKEND_URL as BACKEND, backendHeaders } from '@/lib/nancy/backend-server'


export async function GET() {
  try {
    const res = await fetch(`${BACKEND}/ollama-cloud/status`, { headers: backendHeaders(), signal: AbortSignal.timeout(8_000), cache: 'no-store' })
    return NextResponse.json(await res.json(), { status: res.status })
  } catch {
    return NextResponse.json({ success: false, error: 'Backend unreachable' }, { status: 502 })
  }
}
