'use client'

// Real raw-audio capture for voice_id (speaker verification) -- distinct
// from use-voice.ts's browser-native SpeechRecognition, which transcribes
// to text client-side and never exposes the underlying audio at all. This
// records an actual WebM/Opus clip via MediaRecorder, base64-encodes it,
// and sends it as-is: backend/audio_decode.py's decode_webm_opus_b64_to_pcm
// already knows how to decode exactly this format (the same one the
// (currently unused by the SpeechRecognition path, but real and tested)
// audio_chunk WS message expects).

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onloadend = () => {
      const result = reader.result as string
      // Strip the "data:audio/webm;base64," prefix -- the backend wants raw base64.
      const comma = result.indexOf(',')
      resolve(comma >= 0 ? result.slice(comma + 1) : result)
    }
    reader.onerror = () => reject(reader.error ?? new Error('Failed to read audio blob'))
    reader.readAsDataURL(blob)
  })
}

const PREFERRED_MIME_TYPES = ['audio/webm;codecs=opus', 'audio/webm']

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === 'undefined') return undefined
  return PREFERRED_MIME_TYPES.find((t) => MediaRecorder.isTypeSupported(t))
}

/** Records `durationMs` of real microphone audio and resolves with a base64
 *  WebM/Opus clip. Rejects if the mic can't be opened (permission denied,
 *  no device, unsupported browser) -- callers should surface that as a real
 *  error, not silently swallow it. */
export function recordAudioClip(durationMs = 3000): Promise<string> {
  return new Promise((resolve, reject) => {
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      reject(new Error('Microphone access is not available in this browser.'))
      return
    }
    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((stream) => {
        const mimeType = pickMimeType()
        const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
        const chunks: BlobPart[] = []
        recorder.ondataavailable = (e) => {
          if (e.data.size > 0) chunks.push(e.data)
        }
        recorder.onerror = (e) => {
          stream.getTracks().forEach((t) => t.stop())
          reject(new Error(`Recording failed: ${(e as unknown as { error?: { message?: string } }).error?.message ?? 'unknown error'}`))
        }
        recorder.onstop = () => {
          stream.getTracks().forEach((t) => t.stop())
          const blob = new Blob(chunks, { type: mimeType ?? 'audio/webm' })
          blobToBase64(blob).then(resolve).catch(reject)
        }
        recorder.start()
        setTimeout(() => {
          if (recorder.state !== 'inactive') recorder.stop()
        }, durationMs)
      })
      .catch((err) => reject(err instanceof Error ? err : new Error(String(err))))
  })
}

/** Live capture tied to an open-ended window (the wake-word "awake" period
 *  in use-voice.ts) rather than a fixed duration -- call stop() once a
 *  command's final transcript arrives to get exactly the audio spoken
 *  during that window, not a fixed guess at how long it'll take. */
export interface LiveRecording {
  stop: () => Promise<string | null>
}

export function startLiveRecording(): LiveRecording | null {
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) return null

  let recorder: MediaRecorder | null = null
  let stream: MediaStream | null = null
  const chunks: BlobPart[] = []
  let stopped = false
  let resolveStopPromise: ((v: string | null) => void) | null = null

  navigator.mediaDevices
    .getUserMedia({ audio: true })
    .then((s) => {
      if (stopped) {
        s.getTracks().forEach((t) => t.stop())
        return
      }
      stream = s
      const mimeType = pickMimeType()
      recorder = new MediaRecorder(s, mimeType ? { mimeType } : undefined)
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data)
      }
      recorder.onstop = () => {
        stream?.getTracks().forEach((t) => t.stop())
        const blob = new Blob(chunks, { type: mimeType ?? 'audio/webm' })
        if (blob.size === 0) {
          resolveStopPromise?.(null)
          return
        }
        blobToBase64(blob)
          .then((b64) => resolveStopPromise?.(b64))
          .catch(() => resolveStopPromise?.(null))
      }
      recorder.start()
    })
    .catch(() => {
      /* mic unavailable -- stop() below will just resolve null, no voice check for this turn */
    })

  return {
    stop: () =>
      new Promise<string | null>((resolve) => {
        stopped = true
        resolveStopPromise = resolve
        if (recorder && recorder.state !== 'inactive') {
          recorder.stop()
        } else if (!recorder) {
          // getUserMedia never resolved in time (denied/slow) -- nothing to capture.
          resolve(null)
        }
      }),
  }
}
