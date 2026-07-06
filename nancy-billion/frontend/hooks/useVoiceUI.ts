'use client'

import { useCallback, useState, useRef, useEffect } from 'react'

type VoiceState = 'idle' | 'listening' | 'processing' | 'speaking'

interface UseVoiceUIOptions {
  onWakeWord?: (word: string) => void
  onTranscript?: (transcript: string) => void
  onResponse?: (response: string) => void
  onStateChange?: (state: VoiceState) => void
}

export function useVoiceUI({
  onWakeWord,
  onTranscript,
  onResponse,
  onStateChange,
}: UseVoiceUIOptions = {}) {
  const [state, setState] = useState<VoiceState>('idle')
  const [transcript, setTranscript] = useState('')
  const [interim, setInterim] = useState('')
  const [audioLevel, setAudioLevel] = useState(0)

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const animationFrameRef = useRef<number | null>(null)

  // Initialize audio context
  const initAudio = useCallback(async () => {
    if (audioContextRef.current) return

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)()
      const analyser = audioContext.createAnalyser()
      const source = audioContext.createMediaStreamSource(stream)

      source.connect(analyser)
      analyser.fftSize = 256

      audioContextRef.current = audioContext
      analyserRef.current = analyser

      // Monitor audio level
      const monitorAudio = () => {
        if (!analyserRef.current) return

        const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount)
        analyserRef.current.getByteFrequencyData(dataArray)

        const average = dataArray.reduce((a, b) => a + b) / dataArray.length
        setAudioLevel(average / 255) // Normalize to 0-1

        animationFrameRef.current = requestAnimationFrame(monitorAudio)
      }

      monitorAudio()

      // Setup media recorder
      const mediaRecorder = new MediaRecorder(stream)
      mediaRecorderRef.current = mediaRecorder

      mediaRecorder.ondataavailable = (event) => {
        // Send audio chunks to backend
        const reader = new FileReader()
        reader.onload = async () => {
          const audioData = reader.result as string
          // Send to backend STT
          // await fetch('/api/voice/stt', { method: 'POST', body: audioData })
        }
        reader.readAsDataURL(event.data)
      }
    } catch (err) {
      console.error('Failed to initialize audio:', err)
      setState('idle')
    }
  }, [])

  // Start listening
  const start = useCallback(async () => {
    await initAudio()
    setState('listening')
    onStateChange?.('listening')

    if (mediaRecorderRef.current) {
      mediaRecorderRef.current.start()
    }

    setTranscript('')
    setInterim('')
  }, [initAudio, onStateChange])

  // Stop listening
  const stop = useCallback(() => {
    setState('idle')
    onStateChange?.('idle')

    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop()
    }

    if (audioContextRef.current) {
      audioContextRef.current.close()
      audioContextRef.current = null
    }

    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current)
    }
  }, [onStateChange])

  // Simulate voice interaction
  const simulateVoiceCommand = useCallback(
    async (command: string) => {
      setState('listening')
      onStateChange?.('listening')

      // Simulate STT
      await new Promise((resolve) => setTimeout(resolve, 500))
      setTranscript(command)
      onTranscript?.(command)

      // Check for wake word
      const wakeWords = ['nancy', 'billion', 'jarvis']
      const detectedWakeWord = wakeWords.find((word) => command.toLowerCase().includes(word))
      if (detectedWakeWord) {
        onWakeWord?.(detectedWakeWord)
      }

      // Simulate processing
      setState('processing')
      onStateChange?.('processing')
      await new Promise((resolve) => setTimeout(resolve, 800))

      // Simulate LLM response
      setState('speaking')
      onStateChange?.('speaking')

      const mockResponse = `Processing your request: ${command}`
      onResponse?.(mockResponse)

      // Simulate TTS
      await new Promise((resolve) => setTimeout(resolve, 1000))

      setState('idle')
      onStateChange?.('idle')
    },
    [onStateChange, onTranscript, onWakeWord, onResponse]
  )

  return {
    state,
    transcript,
    interim,
    audioLevel,
    start,
    stop,
    simulateVoiceCommand,
  }
}

export function useVoiceStreaming() {
  const [response, setResponse] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [audioChunks, setAudioChunks] = useState<string[]>([])

  const streamResponse = useCallback(async (query: string) => {
    setIsStreaming(true)
    setResponse('')
    setAudioChunks([])

    try {
      const response = await fetch('/api/voice/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
      })

      if (!response.body) throw new Error('No response body')

      const reader = response.body.getReader()
      const decoder = new TextDecoder()

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value)
        const lines = chunk.split('\n')

        for (const line of lines) {
          if (!line) continue

          try {
            const data = JSON.parse(line)

            if (data.type === 'text_chunk') {
              setResponse((prev) => prev + data.data)
            } else if (data.type === 'audio') {
              setAudioChunks((prev) => [...prev, data.data])
            }
          } catch (e) {
            // Skip malformed JSON
          }
        }
      }
    } catch (err) {
      console.error('Streaming error:', err)
    } finally {
      setIsStreaming(false)
    }
  }, [])

  return {
    response,
    isStreaming,
    audioChunks,
    streamResponse,
  }
}

