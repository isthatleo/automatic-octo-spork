'use client'

export interface SynthesizeResult {
  audioUrl: string
  durationMs: number
}

/** Synthesize text to speech via the backend's real neural TTS (backend/neu_tts.py). */
export async function synthesizeSpeech(text: string): Promise<SynthesizeResult> {
  const res = await fetch('/api/tts/synthesize', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  if (!res.ok) throw new Error(`TTS synthesis failed: ${res.status}`)

  const blob = await res.blob()
  const audioUrl = URL.createObjectURL(blob)
  const durationMs = await getAudioDurationMs(audioUrl)
  return { audioUrl, durationMs }
}

function getAudioDurationMs(url: string): Promise<number> {
  return new Promise((resolve) => {
    const audio = new Audio(url)
    audio.addEventListener('loadedmetadata', () => {
      resolve(Number.isFinite(audio.duration) ? audio.duration * 1000 : 0)
    })
    audio.addEventListener('error', () => resolve(0))
  })
}
