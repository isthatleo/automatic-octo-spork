'use client'

import { useEffect, useState, useCallback } from 'react'

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

