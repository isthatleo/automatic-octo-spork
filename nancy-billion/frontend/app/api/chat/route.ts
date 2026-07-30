import { NextResponse } from 'next/server'
import { BACKEND_URL as BACKEND, backendHeaders } from '@/lib/nancy/backend-server'


export async function POST(request: Request) {
  try {
    const body = await request.json()
    const res = await fetch(`${BACKEND}/chat`, {
      method: 'POST',
      headers: backendHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        text: body.text ?? '',
        history: body.history ?? [],
        task_hint: body.task_hint ?? null,
      }),
    })
    if (!res.ok) return NextResponse.json({ reply: '', response: '', error: 'Chat failed' }, { status: res.status })
    const json = await res.json()
    return NextResponse.json({ ...json, response: json.reply ?? '' })
  } catch {
    return NextResponse.json({ reply: '', response: 'Sorry, I encountered an error.' }, { status: 502 })
  }
}
