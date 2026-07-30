import { NextResponse } from 'next/server'
import { BACKEND_URL as BACKEND, backendHeaders } from '@/lib/nancy/backend-server'


export async function POST(request: Request) {
  try {
    const incoming = await request.formData()
    const file = incoming.get('file')
    if (!file) return NextResponse.json({ success: false, detail: 'file is required' }, { status: 400 })
    const forward = new FormData()
    forward.append('file', file)
    const res = await fetch(`${BACKEND}/voice/reference`, { headers: backendHeaders(), method: 'POST', body: forward })
    const json = await res.json()
    return NextResponse.json(json, { status: res.status })
  } catch {
    return NextResponse.json({ success: false, detail: 'upload failed' }, { status: 502 })
  }
}

export async function DELETE() {
  try {
    const res = await fetch(`${BACKEND}/voice/reference`, { headers: backendHeaders(), method: 'DELETE' })
    const json = await res.json()
    return NextResponse.json(json, { status: res.status })
  } catch {
    return NextResponse.json({ success: false }, { status: 502 })
  }
}
