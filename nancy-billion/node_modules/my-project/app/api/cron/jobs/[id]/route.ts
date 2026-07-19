import { NextResponse } from 'next/server'

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params
    const { searchParams } = new URL(request.url)
    const enabled = searchParams.get('enabled') ?? 'true'
    const res = await fetch(`${BACKEND}/cron/jobs/${encodeURIComponent(id)}?enabled=${enabled}`, { method: 'PATCH' })
    const json = await res.json()
    return NextResponse.json(json, { status: res.status })
  } catch {
    return NextResponse.json({ success: false }, { status: 502 })
  }
}

export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params
    const res = await fetch(`${BACKEND}/cron/jobs/${encodeURIComponent(id)}`, { method: 'DELETE' })
    const json = await res.json()
    return NextResponse.json(json, { status: res.status })
  } catch {
    return NextResponse.json({ success: false }, { status: 502 })
  }
}
