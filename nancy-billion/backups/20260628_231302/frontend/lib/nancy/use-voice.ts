'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useBluetoothAudio, isAirPodsConnected } from './bluetooth-audio'
import { initializeClapDetection } from './audio-processing'

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

const WAKE_WORDS = ['nancy', 'bilion', 'jarvis']

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
  
  const { connectedDevice, isConnected } = useBluetoothAudio()
  const isUsingAirPods = isConnected && isAirPodsConnected(connectedDevice?.name ?? '')

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

      const hitWake = WAKE_WORDS.find((w) => lower.includes(w))
      if (hitWake) {
        const after = lower.split(hitWake).slice(1).join(hitWake).trim()
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

// Initialize voice cache on load
if (typeof window !== 'undefined' && window.speechSynthesis) {
  window.speechSynthesis.onvoiceschanged = () => {
    cachedVoice = null // Force refresh on voices changed
  }
  
  // Pre-populate with a female voice if available
  const voices = window.speechSynthesis.getVoices()
  const femaleVoice = voices.find(v => 
    /female|woman|girl/i.test(v.name) && 
    v.lang.startsWith('en')
  ) || voices.find(v => /female/i.test(v.name))
  
  if (femaleVoice) {
    cachedVoice = femaleVoice
  }
}

export function speak(text: string, preferBluetooth = true) {
  if (typeof window === 'undefined' || !window.speechSynthesis) return
  
  // Try to use Bluetooth audio device if available and preferred
  if (preferBluetooth && typeof navigator !== 'undefined' && navigator.bluetooth) {
    // Note: Direct audio output routing to specific Bluetooth devices 
    // requires the Web Audio API and is browser-specific.
    // This is a placeholder for where such implementation would go.
    console.log('Would route audio to Bluetooth device if supported')
  }
  
  const synth = window.speechSynthesis
  const utter = new SpeechSynthesisUtterance(text)

  if (!cachedVoice) {
    const voices = synth.getVoices()
    // Exclusively use female voices for authentic JARVIS experience
    cachedVoice =
      voices.find((v) => 
        v.lang.startsWith('en-GB') && 
        /female|woman|girl/i.test(v.name)
      ) ||
      voices.find((v) => 
        v.lang.startsWith('en-GB') && 
        /samantha|zira|google uk/i.test(v.name)
      ) ||
      voices.find((v) => 
        v.lang.startsWith('en-GB')
      ) ||
      voices.find((v) => 
        /female|samantha|zira|google uk english female/i.test(v.name)
      ) ||
      voices.find((v) => 
        /female/i.test(v.name) && v.lang.startsWith('en')
      ) ||
      voices.find((v) => /female/i.test(v.name)) ||
      null
  }
  if (cachedVoice) {
    utter.voice = cachedVoice
  } else {
    // Fallback: search for any available female voice
    const voices = synth.getVoices()
    const femaleVoice = voices.find(v => 
      /female|woman|girl/i.test(v.name)
    ) || voices.find(v => /female/i.test(v.name))
    
    if (femaleVoice) {
      utter.voice = femaleVoice
    }
    // If still no female voice found, we'll use the default but log a warning
    else if (voices.length > 0) {
      console.warn('No female voice available for TTS, using default voice')
    }
  }
  
  // JARVIS-like speech characteristics: slightly faster, clear articulation
  utter.rate = 1.1
  utter.pitch = 0.9  // Slightly lower pitch for more authoritative tone
  utter.volume = 1.0
  synth.cancel()
  synth.speak(utter)
}

// Initialize proactive assistant, context systems, and audio processing
if (typeof window !== 'undefined') {
  // Initialize proactive assistant on load
  window.addEventListener('load', () => {
    if (!(window as any).__jrviss_proactive_initialized) {
      (window as any).__jrviss_proactive_initialized = true
      // Initialize the proactive assistant
      proactiveAssistant.initialize()
      
      // Initialize clap detection for alternative wake word
      initializeClapDetection()
      
      // Listen for clap detection events
      const handleClapDetected = () => {
        console.log('Clap wake detected!')
        // Note: Actual voice activation would be handled by the main useVoice hook
        // This is just for logging/audio processing integration
      }
      
      window.addEventListener('clapDetected', handleClapDetected)
      
      // Cleanup on unload
      return () => {
        window.removeEventListener('clapDetected', handleClapDetected)
      }
    }
  })
}
