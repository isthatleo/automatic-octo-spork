import { NextResponse } from 'next/server'
import { BACKEND_URL as BACKEND, backendHeaders } from '@/lib/nancy/backend-server'

// Server-side proxy to the backend's one-shot STT endpoint -- used by the
// server-STT fallback loop in lib/nancy/use-voice.ts on browsers without
// the Web Speech API (Firefox, Safari). BACKEND_URL first: this route runs
// inside the frontend container where localhost:8000 is not the backend
// (see docker-compose.yml).

export async function POST(request: Request) {
  try {
    const body = await request.json()
    if (!body?.audio_b64 || typeof body.audio_b64 !== 'string') {
      return NextResponse.json({ success: false, error: 'audio_b64 required' }, { status: 400 })
    }
    const res = await fetch(`${BACKEND}/voice/transcribe`, {
      method: 'POST',
      headers: backendHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ audio_b64: body.audio_b64 }),
      // Whisper on CPU can take a few seconds for a long clip; still bound it.
      signal: AbortSignal.timeout(20_000),
    })
    if (!res.ok) {
      return NextResponse.json({ success: false, error: `Transcription failed (${res.status})` }, { status: res.status })
    }
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ success: false, error: 'Backend unreachable' }, { status: 502 })
  }
}
