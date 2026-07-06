import { NextResponse } from 'next/server'

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const res = await fetch(`${BACKEND}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: body.query ?? '', history: [], task_hint: null }),
    })
    if (!res.ok) return NextResponse.json({ error: 'Stream failed' }, { status: res.status })
    const json = await res.json()
    const text = json.reply ?? ''
    const encoder = new TextEncoder()
    const stream = new ReadableStream({
      start(controller) {
        const words = text.split(' ')
        let i = 0
        function push() {
          if (i >= words.length) {
            controller.close()
            return
          }
          controller.enqueue(encoder.encode(JSON.stringify({ type: 'text_chunk', data: words[i] + ' ' }) + '\n'))
          i++
          setTimeout(push, 30)
        }
        push()
      },
    })
    return new Response(stream, {
      headers: { 'Content-Type': 'application/x-ndjson', 'Cache-Control': 'no-cache' },
    })
  } catch {
    return NextResponse.json({ error: 'Backend unreachable' }, { status: 502 })
  }
}
