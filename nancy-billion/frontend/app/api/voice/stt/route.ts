import { NextResponse } from 'next/server'

export async function POST() {
  // STT is handled client-side via MediaRecorder + WebSocket.
  // This endpoint is kept for future REST-based STT.
  return NextResponse.json({ transcript: '' })
}
