'use client'

import { useEffect, useState, useCallback, useRef } from 'react'

// Real psutil-backed system health (CPU/memory/disk/network/temperature).
// Replaces the old Math.random()-jittered gauges in the Overview/System panels.
export function useSystemHealth() {
  const [data, setData] = useState<{
    cpu: number | null
    memory: number | null
    disk: number | null
    networkPercent: number | null
    tempC: number | null
  }>({ cpu: null, memory: null, disk: null, networkPercent: null, tempC: null })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const prevNet = useRef<{ bytes: number; time: number; maxMbps: number } | null>(null)

  useEffect(() => {
    let cancelled = false

    const fetch_data = async () => {
      try {
        const res = await fetch('/api/system/health')
        if (!res.ok) throw new Error('Failed to fetch system health')
        const json = await res.json()
        if (cancelled || !json.success) throw new Error('System health unavailable')

        const now = Date.now()
        const netIo = json.network ?? {}
        const totalBytes = (netIo.bytes_sent ?? 0) + (netIo.bytes_recv ?? 0)
        const maxMbps = Math.max(
          1,
          ...Object.values(netIo.interfaces ?? {})
            .map((i: any) => (i.is_up ? i.speed_mbps : 0))
            .filter((s: number) => s > 0),
        )

        let networkPercent: number | null = null
        if (prevNet.current) {
          const deltaBytes = totalBytes - prevNet.current.bytes
          const deltaSeconds = (now - prevNet.current.time) / 1000
          if (deltaSeconds > 0 && deltaBytes >= 0) {
            const mbps = (deltaBytes * 8) / 1_000_000 / deltaSeconds
            networkPercent = Math.max(0, Math.min(100, (mbps / maxMbps) * 100))
          }
        }
        prevNet.current = { bytes: totalBytes, time: now, maxMbps }

        setData({
          cpu: json.cpu?.usage_percent ?? null,
          memory: json.memory?.usage_percent ?? null,
          disk: json.disk?.usage_percent ?? null,
          networkPercent,
          tempC: json.temperature?.max_temperature_celsius ?? null,
        })
        setError(null)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetch_data()
    const interval = setInterval(fetch_data, 4000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  return { ...data, loading, error }
}

export interface LlmStatus {
  primary_model: string | null
  backends: { name: string; model?: string }[]
  stt: { backend: string; model?: string; device?: string }
  tts: { backend: string }
  agents_ready: boolean
}

// Real LLM fallback chain + STT/TTS engine info (see backend's /llm/status).
// Replaces the AI Core panel's old fully-fictional "Model Stack" card.
export function useLlmStatus() {
  const [data, setData] = useState<LlmStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const fetch_data = async () => {
      try {
        const res = await fetch('/api/llm/status', { cache: 'no-store' })
        if (!res.ok) throw new Error('Failed to fetch LLM status')
        const json = await res.json()
        if (!cancelled && json.success) setData(json)
        if (!cancelled) setError(null)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    fetch_data()
    const interval = setInterval(fetch_data, 30000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  return { data, loading, error }
}

// Memory API
export function useMemorySummary() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetch_data = async () => {
      try {
        const res = await fetch('/api/memory/summary')
        if (!res.ok) throw new Error('Failed to fetch memory summary')
        const json = await res.json()
        setData(json.memory)
        setError(null)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        setLoading(false)
      }
    }
    fetch_data()
    const interval = setInterval(fetch_data, 5000)
    return () => clearInterval(interval)
  }, [])

  return { data, loading, error }
}

// Projects from memory
export function useProjects() {
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetch_data = async () => {
      try {
        const res = await fetch('/api/memory/projects')
        if (!res.ok) throw new Error('Failed to fetch projects')
        const json = await res.json()
        setData(json.projects || [])
        setError(null)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        setLoading(false)
      }
    }
    fetch_data()
    const interval = setInterval(fetch_data, 10000)
    return () => clearInterval(interval)
  }, [])

  return { data, loading, error }
}

// Trading data
export function useTradingPerformance() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetch_data = async () => {
      try {
        const res = await fetch('/api/trading/performance')
        if (!res.ok) throw new Error('Failed to fetch trading performance')
        const json = await res.json()
        setData(json.metrics)
        setError(null)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        setLoading(false)
      }
    }
    fetch_data()
    const interval = setInterval(fetch_data, 10000)
    return () => clearInterval(interval)
  }, [])

  return { data, loading, error }
}

// Trading history
export function useTradeHistory(limit: number = 10) {
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetch_data = async () => {
      try {
        const res = await fetch(`/api/trading/history?limit=${limit}`)
        if (!res.ok) throw new Error('Failed to fetch trade history')
        const json = await res.json()
        setData(json.trades || [])
        setError(null)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        setLoading(false)
      }
    }
    fetch_data()
    const interval = setInterval(fetch_data, 15000)
    return () => clearInterval(interval)
  }, [limit])

  return { data, loading, error }
}

// Context analysis
export function useContextAnalysis(text: string) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const analyze = useCallback(async () => {
    if (!text) return
    setLoading(true)
    try {
      const res = await fetch('/api/context/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
      })
      if (!res.ok) throw new Error('Failed to analyze context')
      const json = await res.json()
      setData(json)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }, [text])

  return { data, loading, error, analyze }
}

// Trading risk assessment
export function useRiskAssessment() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetch_data = async () => {
      try {
        const res = await fetch('/api/trading/risk-assessment')
        if (!res.ok) throw new Error('Failed to fetch risk assessment')
        const json = await res.json()
        setData(json.risk_assessment)
        setError(null)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        setLoading(false)
      }
    }
    fetch_data()
    const interval = setInterval(fetch_data, 15000)
    return () => clearInterval(interval)
  }, [])

  return { data, loading, error }
}

// Greeting
export function useGreeting(context?: any) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetch_data = async () => {
      try {
        const url = context ? '/api/greeting/personalized' : '/api/greeting'
        const options: any = {
          headers: { 'Content-Type': 'application/json' }
        }
        if (context) {
          options.method = 'POST'
          options.body = JSON.stringify(context)
        }
        const res = await fetch(url, options)
        if (!res.ok) throw new Error('Failed to fetch greeting')
        const json = await res.json()
        setData(json)
        setError(null)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        setLoading(false)
      }
    }
    fetch_data()
  }, [context])

  return { data, loading, error }
}

// Startup sequence
export function useStartupSequence() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetch_data = async () => {
      try {
        const res = await fetch('/api/startup')
        if (!res.ok) throw new Error('Failed to fetch startup sequence')
        const json = await res.json()
        setData(json)
        setError(null)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        setLoading(false)
      }
    }
    fetch_data()
  }, [])

  return { data, loading, error }
}

// Forex analysis
export function useForexAnalysis(pair: string) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const analyze = useCallback(async () => {
    if (!pair) return
    setLoading(true)
    try {
      const res = await fetch('/api/trading/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: pair })
      })
      if (!res.ok) throw new Error('Failed to analyze forex pair')
      const json = await res.json()
      setData(json)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }, [pair])

  useEffect(() => {
    analyze()
  }, [pair, analyze])

  return { data, loading, error }
}

// Chat function
export async function sendMessage(text: string, history: any[] = []) {
  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, history })
    })
    if (!res.ok) throw new Error('Failed to send message')
    const json = await res.json()
    return json.response
  } catch (err) {
    console.error('Chat error:', err)
    return 'Sorry, I encountered an error.'
  }
}

// Forex pair recommendation
export function useForexRecommendation(pair: string) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const getRec = useCallback(async () => {
    if (!pair) return
    setLoading(true)
    try {
      const res = await fetch(`/api/trading/recommendation/${encodeURIComponent(pair)}`)
      if (!res.ok) throw new Error('Failed to get recommendation')
      const json = await res.json()
      setData(json.recommendation)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }, [pair])

  useEffect(() => {
    getRec()
  }, [pair, getRec])

  return { data, loading, error }
}

/** Generic real-endpoint poller -- avoids re-writing the same fetch/loading/
 * error/interval boilerplate for every simple status-style endpoint. */
function useSimplePoll<T>(path: string, intervalMs: number) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const res = await fetch(path, { cache: 'no-store' })
        if (!res.ok) throw new Error(`Failed to fetch ${path}`)
        const json = await res.json()
        if (!cancelled) {
          if (json.success === false) throw new Error(json.error || 'Request failed')
          setData(json)
          setError(null)
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    const t = setInterval(load, intervalMs)
    return () => {
      cancelled = true
      clearInterval(t)
    }
  }, [path, intervalMs])

  return { data, loading, error }
}

export interface CronJob {
  name: string
  schedule: string
  next_run: string
  enabled: boolean
  description: string
}
// Real scheduled-job info (see backend's _daily_briefing_loop / /cron/status).
export function useCronStatus() {
  return useSimplePoll<{ success: boolean; jobs: CronJob[] }>('/api/cron/status', 60000)
}

// Real non-secret backend configuration (see /config/public).
export function useConfigPublic() {
  return useSimplePoll<{ success: boolean; config: Record<string, string | number | boolean> }>('/api/config/public', 60000)
}

// Real Telegram channel connectivity (see telegram_bot.py / /telegram/status).
export function useTelegramStatus() {
  return useSimplePoll<{ success: boolean; available: boolean; error: string | null; polling?: boolean }>('/api/telegram/status', 20000)
}

