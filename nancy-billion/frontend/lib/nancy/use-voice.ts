'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

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

const WAKE_WORDS = ['nancy', 'nance', 'nansi', 'billion', 'bilion', 'jarvis', 'jervis']
// Word-boundary matcher so "billionaire" or "cancy" don't false-trigger.
const WAKE_RE = new RegExp(`\\b(${WAKE_WORDS.join('|')})\\b`, 'i')

export interface VoiceState {
  supported: boolean
  listening: boolean
  awake: boolean
  interim: string
  lastHeard: string
}

interface UseVoiceArgs {
  onCommand: (command: string) => void
  onWake?: () => void
  onTranscript?: (text: string, isFinal: boolean) => void
}

export function useVoice({ onCommand, onWake, onTranscript }: UseVoiceArgs) {
  const [state, setState] = useState<VoiceState>({
    supported: false,
    listening: false,
    awake: false,
    interim: '',
    lastHeard: '',
  })

  const recRef = useRef<SpeechRecognitionLike | null>(null)
  const awakeRef = useRef(false)
  const awakeTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const wantListening = useRef(false)
  const cmdRef = useRef(onCommand)
  const wakeRef = useRef(onWake)
  const transRef = useRef(onTranscript)

  cmdRef.current = onCommand
  wakeRef.current = onWake
  transRef.current = onTranscript

  useEffect(() => {
    setState((s) => ({ ...s, supported: !!getRecognitionCtor() }))
  }, [])

  const setAwake = useCallback((val: boolean) => {
    awakeRef.current = val
    setState((s) => ({ ...s, awake: val }))
    if (awakeTimer.current) clearTimeout(awakeTimer.current)
    if (val) {
      awakeTimer.current = setTimeout(() => {
        awakeRef.current = false
        setState((s) => ({ ...s, awake: false }))
      }, 9000)
    }
  }, [])

  const handleText = useCallback(
    (raw: string, isFinal: boolean) => {
      const text = raw.trim()
      if (!text) return
      transRef.current?.(text, isFinal)
      setState((s) => ({ ...s, interim: isFinal ? '' : text }))
      if (!isFinal) return

      const lower = text.toLowerCase()
      setState((s) => ({ ...s, lastHeard: text }))

      const match = lower.match(WAKE_RE)
      if (match) {
        const hitWake = match[1]
        const idx = lower.indexOf(hitWake) + hitWake.length
        const after = lower.slice(idx).replace(/^[\s,.:;!?-]+/, '').trim()
        setAwake(true)
        wakeRef.current?.()
        if (after.length > 1) {
          cmdRef.current(after)
        }
        return
      }

      if (awakeRef.current) {
        setAwake(true) // refresh window
        cmdRef.current(lower)
      }
    },
    [setAwake],
  )

  const start = useCallback(() => {
    const Ctor = getRecognitionCtor()
    if (!Ctor) {
      setState((s) => ({ ...s, supported: false }))
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
  }, [handleText])

  const stop = useCallback(() => {
    wantListening.current = false
    setAwake(false)
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
  }, [setAwake])

  useEffect(() => {
    return () => {
      wantListening.current = false
      try {
        recRef.current?.abort()
      } catch {
        /* ignore */
      }
      if (awakeTimer.current) clearTimeout(awakeTimer.current)
    }
  }, [])

  return { state, start, stop, setAwake }
}

let cachedVoice: SpeechSynthesisVoice | null = null

// Names known to be male — hard exclude so we never accidentally pick a male
// voice (some browsers ship "Daniel" as the default en-GB voice).
const MALE_NAME_RE =
  /\b(male|man|boy|daniel|george|arthur|oliver|thomas|james|edward|nathan|david|mark|paul|alex|fred|guy|ralph|reed|rocko|aaron|tom|jorge|luca|matteo|diego|carlos)\b/i

// Preferred female British voice tokens, in priority order.
const FEMALE_GB_HINTS = [
  /google uk english female/i,
  /kate/i, /serena/i, /martha/i, /amy/i, /emma/i, /libby/i, /sonia/i,
  /female/i, /woman/i, /girl/i,
]

function pickVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | null {
  const notMale = voices.filter((v) => !MALE_NAME_RE.test(v.name))
  const enGB = notMale.filter((v) => v.lang?.toLowerCase().startsWith('en-gb'))
  for (const hint of FEMALE_GB_HINTS) {
    const v = enGB.find((x) => hint.test(x.name))
    if (v) return v
  }
  // Any en-GB non-male voice.
  if (enGB[0]) return enGB[0]
  // Any en-* female voice.
  const enFemale = notMale.find(
    (v) => v.lang?.toLowerCase().startsWith('en') && /female|woman|girl|samantha|zira|ava/i.test(v.name),
  )
  if (enFemale) return enFemale
  // Any en-* non-male voice.
  return notMale.find((v) => v.lang?.toLowerCase().startsWith('en')) ?? null
}

// Initialize voice cache on load
if (typeof window !== 'undefined' && window.speechSynthesis) {
  const refresh = () => {
    cachedVoice = pickVoice(window.speechSynthesis.getVoices())
  }
  refresh()
  window.speechSynthesis.onvoiceschanged = refresh
}

export interface SpeakEvents {
  onStart?: () => void
  /** charIndex of the word about to be spoken. */
  onBoundary?: (charIndex: number, wordLength: number) => void
  onEnd?: () => void
}

export function speak(text: string, events: SpeakEvents = {}) {
  if (typeof window === 'undefined' || !window.speechSynthesis) {
    events.onStart?.()
    // Approximate for environments without TTS: fire end after estimated time.
    const ms = Math.min(14000, 900 + text.split(/\s+/).length * 320)
    setTimeout(() => events.onEnd?.(), ms)
    return
  }

  const synth = window.speechSynthesis
  const utter = new SpeechSynthesisUtterance(text)

  if (!cachedVoice) {
    cachedVoice = pickVoice(synth.getVoices())
  }
  if (cachedVoice) utter.voice = cachedVoice
  utter.lang = cachedVoice?.lang ?? 'en-GB'

  utter.rate = 1.05
  utter.pitch = 1.1
  utter.volume = 1.0
  utter.onstart = () => events.onStart?.()
  utter.onboundary = (ev) => {
    if (ev.name && ev.name !== 'word') return
    events.onBoundary?.(ev.charIndex ?? 0, ev.charLength ?? 0)
  }
  utter.onend = () => events.onEnd?.()
  utter.onerror = () => events.onEnd?.()
  synth.cancel()
  synth.speak(utter)
}

/** Cancel any in-flight speech immediately (used on interrupt). */
export function cancelSpeech() {
  if (typeof window === 'undefined' || !window.speechSynthesis) return
  try { window.speechSynthesis.cancel() } catch { /* ignore */ }
}


