'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

const WS_URL =
  process.env.NEXT_PUBLIC_BACKEND_WS_URL ??
  `${(process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000').replace(/^http/, 'ws')}/ws`

export interface ClapResult {
  isClap: boolean
  confidence: number
  at: number
}

function bufferToBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf)
  let binary = ''
  const chunkSize = 0x8000
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize))
  }
  return btoa(binary)
}

/**
 * Clap-detection listener — streams mic audio to the backend's clap_chunk
 * WS handler (see backend/clap_detection.py, satellite repo clap-detection-main).
 * That repo ships no pretrained weights, so `available` is false on a fresh
 * checkout until CLAP_MODEL_PATH points at real weights. Check `available`
 * before calling `start()` — this hook does not fabricate results.
 */
export function useClapDetection() {
  const [available, setAvailable] = useState<boolean | null>(null) // null = still checking
  const [unavailableReason, setUnavailableReason] = useState<string | null>(null)
  const [listening, setListening] = useState(false)
  const [lastResult, setLastResult] = useState<ClapResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch('/api/clap/status')
      .then((r) => r.json())
      .then((json) => {
        if (cancelled) return
        setAvailable(!!json.available)
        setUnavailableReason(json.error ?? null)
      })
      .catch(() => {
        if (cancelled) return
        setAvailable(false)
        setUnavailableReason('Could not reach the backend to check clap-detection status.')
      })
    return () => {
      cancelled = true
    }
  }, [])

  const stop = useCallback(() => {
    setListening(false)
    if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
    recorderRef.current = null
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    wsRef.current?.close()
    wsRef.current = null
  }, [])

  const start = useCallback(async () => {
    if (!available) {
      setError(unavailableReason ?? 'Clap detection is not available on this backend.')
      return
    }
    if (listening) return

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          if (msg.type === 'clap_result') {
            setLastResult({ isClap: msg.is_clap, confidence: msg.confidence, at: Date.now() })
          } else if (msg.type === 'clap_error') {
            setError(msg.error)
          }
        } catch {
          /* ignore malformed frame */
        }
      }
      ws.onerror = () => setError('WebSocket connection failed')
      ws.onclose = () => setListening(false)

      await new Promise<void>((resolve, reject) => {
        ws.onopen = () => resolve()
        setTimeout(() => reject(new Error('WebSocket connect timed out')), 8000)
      })

      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : undefined
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      recorderRef.current = recorder
      recorder.ondataavailable = async (event) => {
        if (event.data.size === 0 || ws.readyState !== WebSocket.OPEN) return
        const buf = await event.data.arrayBuffer()
        ws.send(JSON.stringify({ type: 'clap_chunk', data: bufferToBase64(buf) }))
      }
      recorder.start(500) // 0.5s chunks, matching clap-detection-main/live.py's window

      setListening(true)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start clap detection')
      stop()
    }
  }, [available, unavailableReason, listening, stop])

  useEffect(() => stop, [stop])

  return { available, unavailableReason, listening, lastResult, error, start, stop }
}
