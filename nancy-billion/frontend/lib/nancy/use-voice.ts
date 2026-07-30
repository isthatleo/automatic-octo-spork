'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { blobToBase64, pickMimeType, startLiveRecording, type LiveRecording } from './voice-capture'

// Minimal typings for the Web Speech API (not in standard lib DOM types).
interface SpeechRecognitionResultLike {
  transcript: string
  confidence: number
}
interface SpeechRecognitionEventLike {
  resultIndex: number
  results: ArrayLike<{
    isFinal: boolean
    0: SpeechRecognitionResultLike
  }>
}
interface SpeechRecognitionLike {
  continuous: boolean
  interimResults: boolean
  lang: string
  start: () => void
  stop: () => void
  abort: () => void
  onresult: ((e: SpeechRecognitionEventLike) => void) | null
  onerror: ((e: { error: string }) => void) | null
  onend: (() => void) | null
}

// SpeechSynthesis voice types
interface SpeechSynthesisVoice {
  name: string
  lang: string
  localService: boolean
  default: boolean
  voiceURI: string
}

type RecognitionCtor = new () => SpeechRecognitionLike

function getRecognitionCtor(): RecognitionCtor | null {
  if (typeof window === 'undefined') return null
  const w = window as unknown as {
    SpeechRecognition?: RecognitionCtor
    webkitSpeechRecognition?: RecognitionCtor
  }
  return w.SpeechRecognition || w.webkitSpeechRecognition || null
}

// Server-STT fallback availability (Firefox/Safari have no Web Speech API,
// but do have MediaRecorder + getUserMedia -- clips go to the backend's
// faster-whisper via /api/voice/transcribe instead).
function serverSttAvailable(): boolean {
  return (
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof MediaRecorder !== 'undefined'
  )
}

// Segment length for the fallback loop. Long enough that "nancy, what's the
// weather" fits in one segment most of the time; short enough that the
// wake-to-response latency stays tolerable without a real VAD.
const SERVER_STT_SEGMENT_MS = 5000
// Peak |amplitude| (0..1 from an AnalyserNode) below which a segment is
// treated as silence and never uploaded -- keeps an idle open mic from
// hammering the backend with empty transcriptions all day.
const SERVER_STT_SILENCE_PEAK = 0.04

const WAKE_WORDS = ['nancy', 'nance', 'nansi', 'billion', 'bilion', 'jarvis', 'jervis']
// Word-boundary matcher so "billionaire" or "cancy" don't false-trigger.
const WAKE_RE = new RegExp(`\\b(${WAKE_WORDS.join('|')})\\b`, 'i')

export interface VoiceState {
  supported: boolean
  listening: boolean
  awake: boolean
  conversationMode: boolean
  interim: string
  lastHeard: string
}

// Real exit phrases for continuous conversation mode -- checked before the
// wake-word/awake dispatch logic, so these are never sent to onCommand as
// an ordinary command while the mode is active.
const CONVERSATION_EXIT_RE = /\b(stop listening|end conversation|that'?s all( for now)?|goodbye (billion|nancy|jarvis))\b/i
// Real trigger phrases for entering continuous conversation mode -- checked
// ahead of the ordinary wake-word dispatch so "Nancy, let's talk" (or the
// phrase alone, once already awake) starts the mode instead of being sent to
// onCommand as a literal command.
const CONVERSATION_START_RE = /\b(let'?s talk|stay awake|keep listening|conversation mode|stay with me)\b/i

interface UseVoiceArgs {
  /** audioBase64 is a real raw-audio capture of exactly this command's
   *  utterance (WebM/Opus, see voice-capture.ts), present whenever the mic
   *  was actually available -- undefined only if getUserMedia failed/was
   *  denied, in which case this behaves exactly like before (no voice-ID
   *  check for that command, same as typed text). */
  onCommand: (command: string, audioBase64?: string) => void
  onWake?: () => void
  onTranscript?: (text: string, isFinal: boolean) => void
  /** Fired when continuous conversation mode ends, whether by an explicit
   *  exit phrase or a manual stopConversationMode() call. */
  onConversationEnd?: () => void
}

export function useVoice({ onCommand, onWake, onTranscript, onConversationEnd }: UseVoiceArgs) {
  const [state, setState] = useState<VoiceState>({
    supported: false,
    listening: false,
    awake: false,
    conversationMode: false,
    interim: '',
    lastHeard: '',
  })

  const recRef = useRef<SpeechRecognitionLike | null>(null)
  const awakeRef = useRef(false)
  const awakeTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const conversationModeRef = useRef(false)
  const wantListening = useRef(false)
  const cmdRef = useRef(onCommand)
  const wakeRef = useRef(onWake)
  const transRef = useRef(onTranscript)
  const conversationEndRef = useRef(onConversationEnd)
  // Real raw-audio capture for voice_id verification (see voice-capture.ts)
  // -- SpeechRecognition itself never exposes the underlying audio, so this
  // runs a second, parallel MediaRecorder specifically to get a real sample
  // of THIS command's utterance. null whenever nothing is currently being
  // captured (outside the wake window, or between commands within it).
  const liveRecordingRef = useRef<LiveRecording | null>(null)
  // Server-STT fallback state (no Web Speech API): the loop records
  // discrete WebM segments and transcribes them via /api/voice/transcribe.
  const serverModeRef = useRef(false)
  const serverStreamRef = useRef<MediaStream | null>(null)
  const serverAudioCtxRef = useRef<AudioContext | null>(null)
  // The segment that produced the current transcript -- doubles as the
  // voice-ID sample for captureAndDispatch (it IS this command's audio).
  const lastSegmentB64Ref = useRef<string | null>(null)

  cmdRef.current = onCommand
  wakeRef.current = onWake
  transRef.current = onTranscript
  conversationEndRef.current = onConversationEnd

  useEffect(() => {
    setState((s) => ({ ...s, supported: !!getRecognitionCtor() || serverSttAvailable() }))
  }, [])

  // Discards whatever's currently recording without dispatching it (window
  // closed with nothing said, or a stale capture from before a new one
  // starts) -- distinct from captureAndDispatch, which stops AND uses it.
  const discardCapture = useCallback(() => {
    const rec = liveRecordingRef.current
    liveRecordingRef.current = null
    rec?.stop().catch(() => {})
  }, [])

  const beginCapture = useCallback(() => {
    // Server-STT mode records its own segments -- a second parallel
    // recorder on the same mic would only fight over it.
    if (serverModeRef.current) return
    discardCapture()
    liveRecordingRef.current = startLiveRecording()
  }, [discardCapture])

  const setAwake = useCallback(
    (val: boolean) => {
      awakeRef.current = val
      setState((s) => ({ ...s, awake: val }))
      if (awakeTimer.current) clearTimeout(awakeTimer.current)
      if (val) {
        if (!liveRecordingRef.current) beginCapture()
        // Continuous conversation mode never times out on its own -- it's
        // "like a phone call," ended only by an explicit exit phrase or
        // stopConversationMode(), not a rolling 9s silence window.
        if (!conversationModeRef.current) {
          awakeTimer.current = setTimeout(() => {
            awakeRef.current = false
            setState((s) => ({ ...s, awake: false }))
            discardCapture()
          }, 9000)
        }
      } else {
        discardCapture()
      }
    },
    [beginCapture, discardCapture],
  )

  const startConversationMode = useCallback(() => {
    conversationModeRef.current = true
    setState((s) => ({ ...s, conversationMode: true }))
    setAwake(true)
  }, [setAwake])

  const stopConversationMode = useCallback(() => {
    conversationModeRef.current = false
    setState((s) => ({ ...s, conversationMode: false }))
    setAwake(false)
    conversationEndRef.current?.()
  }, [setAwake])

  // Stops the in-flight capture (the real audio spoken since the last
  // command, or since the wake word, whichever was most recent) and
  // dispatches it alongside the transcript -- then immediately starts
  // capturing again in case another command follows within the same awake
  // window. Async because getting the recorded blob out of MediaRecorder
  // is inherently async; the command still dispatches exactly once either way.
  const captureAndDispatch = useCallback(
    (text: string) => {
      // Server-STT mode: the transcribed segment itself is this command's
      // real audio -- pass it straight through for voice-ID, no second
      // recorder involved.
      if (serverModeRef.current) {
        cmdRef.current(text, lastSegmentB64Ref.current ?? undefined)
        return
      }
      const rec = liveRecordingRef.current
      liveRecordingRef.current = null
      if (!rec) {
        cmdRef.current(text)
        beginCapture()
        return
      }
      rec
        .stop()
        .then((audioBase64) => cmdRef.current(text, audioBase64 ?? undefined))
        .catch(() => cmdRef.current(text))
        .finally(() => beginCapture())
    },
    [beginCapture],
  )

  const handleText = useCallback(
    (raw: string, isFinal: boolean) => {
      const text = raw.trim()
      if (!text) return
      transRef.current?.(text, isFinal)
      setState((s) => ({ ...s, interim: isFinal ? '' : text }))
      if (!isFinal) return

      const lower = text.toLowerCase()
      setState((s) => ({ ...s, lastHeard: text }))

      if (conversationModeRef.current && CONVERSATION_EXIT_RE.test(lower)) {
        stopConversationMode()
        return
      }

      if (!conversationModeRef.current && CONVERSATION_START_RE.test(lower)) {
        startConversationMode()
        wakeRef.current?.()
        return
      }

      const match = lower.match(WAKE_RE)
      if (match) {
        const hitWake = match[1]
        const idx = lower.indexOf(hitWake) + hitWake.length
        const after = lower.slice(idx).replace(/^[\s,.:;!?-]+/, '').trim()
        setAwake(true)
        wakeRef.current?.()
        if (after.length > 1) {
          captureAndDispatch(after)
        }
        return
      }

      if (awakeRef.current) {
        setAwake(true) // refresh window (a no-op timer-wise in conversation mode)
        captureAndDispatch(lower)
      }
    },
    [setAwake, captureAndDispatch, stopConversationMode, startConversationMode],
  )

  // ── Server-STT fallback loop (Firefox/Safari) ─────────────────────────
  // Records back-to-back ~5s WebM segments from one shared mic stream; a
  // parallel AnalyserNode tracks the segment's peak level so silent
  // segments are dropped client-side. Non-silent segments go to the
  // backend's faster-whisper via /api/voice/transcribe and the transcript
  // feeds the exact same handleText pipeline (wake word, conversation
  // mode, command dispatch) the native path uses. Transcription of one
  // segment overlaps the recording of the next, so nothing said during a
  // whisper round-trip is lost.
  const startServerSttLoop = useCallback(async () => {
    if (serverModeRef.current) return
    serverModeRef.current = true
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      if (!serverModeRef.current) {
        stream.getTracks().forEach((t) => t.stop())
        return
      }
      serverStreamRef.current = stream
      const audioCtx = new AudioContext()
      serverAudioCtxRef.current = audioCtx
      const analyser = audioCtx.createAnalyser()
      analyser.fftSize = 2048
      audioCtx.createMediaStreamSource(stream).connect(analyser)
      const levelBuf = new Uint8Array(analyser.fftSize)
      setState((s) => ({ ...s, listening: true }))

      const mimeType = pickMimeType()
      const recordSegment = () =>
        new Promise<{ blob: Blob; peak: number } | null>((resolve) => {
          if (!serverModeRef.current || !serverStreamRef.current) return resolve(null)
          let peak = 0
          const recorder = new MediaRecorder(serverStreamRef.current, mimeType ? { mimeType } : undefined)
          const chunks: BlobPart[] = []
          recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data) }
          recorder.onerror = () => resolve(null)
          recorder.onstop = () => resolve({ blob: new Blob(chunks, { type: mimeType ?? 'audio/webm' }), peak })
          recorder.start()
          const meter = setInterval(() => {
            analyser.getByteTimeDomainData(levelBuf)
            for (let i = 0; i < levelBuf.length; i++) {
              const v = Math.abs(levelBuf[i] - 128) / 128
              if (v > peak) peak = v
            }
          }, 150)
          setTimeout(() => {
            clearInterval(meter)
            if (recorder.state !== 'inactive') recorder.stop()
          }, SERVER_STT_SEGMENT_MS)
        })

      const transcribeSegment = async (blob: Blob) => {
        try {
          const audio_b64 = await blobToBase64(blob)
          const res = await fetch('/api/voice/transcribe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ audio_b64 }),
          })
          if (!res.ok) return
          const json = await res.json()
          const transcript = String(json?.transcript ?? '').trim()
          if (transcript && serverModeRef.current) {
            lastSegmentB64Ref.current = audio_b64
            handleText(transcript, true)
          }
        } catch {
          /* transient network/backend failure -- next segment tries again */
        }
      }

      while (serverModeRef.current) {
        const seg = await recordSegment()
        if (!seg) break
        // Fire-and-forget: transcription overlaps the next segment's recording.
        if (seg.peak >= SERVER_STT_SILENCE_PEAK && seg.blob.size > 0) void transcribeSegment(seg.blob)
      }
    } catch {
      // Mic denied/unavailable -- honest unsupported state, same as native path.
      serverModeRef.current = false
      setState((s) => ({ ...s, supported: false, listening: false }))
    }
  }, [handleText])

  const stopServerSttLoop = useCallback(() => {
    serverModeRef.current = false
    serverStreamRef.current?.getTracks().forEach((t) => t.stop())
    serverStreamRef.current = null
    serverAudioCtxRef.current?.close().catch(() => {})
    serverAudioCtxRef.current = null
    lastSegmentB64Ref.current = null
  }, [])

  const start = useCallback(() => {
    const Ctor = getRecognitionCtor()
    if (!Ctor) {
      if (serverSttAvailable()) {
        wantListening.current = true
        void startServerSttLoop()
      } else {
        setState((s) => ({ ...s, supported: false }))
      }
      return
    }
    if (recRef.current) return

    const rec = new Ctor()
    rec.continuous = true
    rec.interimResults = true
    rec.lang = 'en-GB'

    rec.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i]
        handleText(r[0].transcript, r.isFinal)
      }
    }
    rec.onerror = (e) => {
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
        wantListening.current = false
        setState((s) => ({ ...s, listening: false }))
      }
    }
    rec.onend = () => {
      if (wantListening.current) {
        try {
          rec.start()
        } catch {
          /* restart race - ignore */
        }
      } else {
        setState((s) => ({ ...s, listening: false }))
      }
    }

    recRef.current = rec
    wantListening.current = true
    try {
      rec.start()
      setState((s) => ({ ...s, listening: true }))
    } catch {
      /* already started */
    }
  }, [handleText, startServerSttLoop])

  // Stops recognition only -- leaves conversationMode/awake state untouched.
  // Used internally (and by callers, e.g. page.tsx's echo-avoidance pause
  // while Nancy is speaking) whenever the mic needs to go quiet WITHOUT
  // ending an active continuous-conversation session.
  const pause = useCallback(() => {
    wantListening.current = false
    stopServerSttLoop()
    const rec = recRef.current
    recRef.current = null
    if (rec) {
      try {
        rec.stop()
      } catch {
        /* ignore */
      }
    }
    setState((s) => ({ ...s, listening: false, interim: '' }))
  }, [stopServerSttLoop])

  const stop = useCallback(() => {
    conversationModeRef.current = false
    setState((s) => ({ ...s, conversationMode: false }))
    setAwake(false)
    pause()
  }, [setAwake, pause])

  useEffect(() => {
    return () => {
      wantListening.current = false
      serverModeRef.current = false
      serverStreamRef.current?.getTracks().forEach((t) => t.stop())
      serverStreamRef.current = null
      serverAudioCtxRef.current?.close().catch(() => {})
      serverAudioCtxRef.current = null
      try {
        recRef.current?.abort()
      } catch {
        /* ignore */
      }
      if (awakeTimer.current) clearTimeout(awakeTimer.current)
      liveRecordingRef.current?.stop().catch(() => {})
      liveRecordingRef.current = null
    }
  }, [])

  return { state, start, stop, pause, setAwake, startConversationMode, stopConversationMode }
}

// Browser Web Speech API TTS used to back a "speak locally" fallback for
// when NeuTTS (the real neural voice) was unreachable. Removed: the OS-level
// synthetic voice it produced (a "hard rugged metallic male voice" on this
// machine) has nothing to do with NeuTTS's British female voice, and there's
// no way to make speechSynthesis actually use NeuTTS's voice model -- it's a
// different synthesis engine entirely. nancySay() in page.tsx now degrades
// silently (text only, no audio) if NeuTTS is unreachable, rather than ever
// substituting a different-sounding voice.

/** Cancel any in-flight browser speech, if the API exists and something was
 *  ever speaking through it. Safe no-op otherwise -- kept as a harmless
 *  defensive call at every interrupt point in page.tsx. */
export function cancelSpeech() {
  if (typeof window === 'undefined' || !window.speechSynthesis) return
  try { window.speechSynthesis.cancel() } catch { /* ignore */ }
}


