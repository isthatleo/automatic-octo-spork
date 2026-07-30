import { NextResponse } from 'next/server'
import { BACKEND_URL as BACKEND, backendHeaders } from '@/lib/nancy/backend-server'


export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params
    const body = await request.json()
    const res = await fetch(`${BACKEND}/skills/custom/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      headers: backendHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body),
    })
    const json = await res.json()
    return NextResponse.json(json, { status: res.status })
  } catch {
    return NextResponse.json({ success: false }, { status: 502 })
  }
}

export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params
    const res = await fetch(`${BACKEND}/skills/custom/${encodeURIComponent(id)}`, { headers: backendHeaders(), method: 'DELETE' })
    const json = await res.json()
    return NextResponse.json(json, { status: res.status })
  } catch {
    return NextResponse.json({ success: false }, { status: 502 })
  }
}
