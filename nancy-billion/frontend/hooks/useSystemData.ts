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

export interface ActivityMission {
  id: string
  title: string
  stage: string
  assigned_agent: string | null
  [key: string]: unknown
}
export interface ActivityWatch {
  id: string
  url: string
  description: string
  kind: string
  next_check_in_s: number
  [key: string]: unknown
}
export interface ActivityCronJob {
  id: string
  name: string
  hour: number
  minute: number
  [key: string]: unknown
}
export interface SystemActivity {
  success: boolean
  active_missions: ActivityMission[]
  active_watches: ActivityWatch[]
  upcoming_cron_jobs: ActivityCronJob[]
  macro_count: number
  lockdown: { locked_down: boolean; remaining_s: number; reason: string | null }
  focus_mode: { active: boolean; remaining_s: number; queued_count: number }
}
// Real, live "what is Billion doing right now" aggregation (see
// /system/activity) -- every in-flight background mission, active watch,
// upcoming scheduled job, and security-mode state in one poll, instead of
// only finding any of it out via a Telegram ping when something finishes.
export function useSystemActivity() {
  return useSimplePoll<SystemActivity>('/api/system/activity', 10000)
}

// Real non-secret backend configuration (see /config/public).
export function useConfigPublic() {
  return useSimplePoll<{ success: boolean; config: Record<string, string | number | boolean> }>('/api/config/public', 60000)
}

export interface CapabilityVendor {
  vendor: string
  configured: boolean
  env_var: string
}
// Real optional-integration status per provider registry (see /config/capabilities) --
// whether each vendor adapter actually self-registered, never the secret itself.
export function useConfigCapabilities() {
  return useSimplePoll<{ success: boolean; capabilities: Record<string, CapabilityVendor[]> }>('/api/config/capabilities', 60000)
}

export interface WritableKeyEntry {
  name: string
  label: string
  group: string
  configured: boolean | null
}
// The Keys page's full credential catalog (see /config/keys/catalog),
// assembled server-side from the same declarative lists that drive the live
// LLM chain, channel registry, and provider registries -- a new
// provider/channel/vendor added on the backend appears here automatically,
// with nothing to update on the frontend.
export function useWritableKeyCatalog() {
  const { data, loading } = useSimplePoll<{ success: boolean; entries: WritableKeyEntry[] }>('/api/config/keys/catalog', 60000)
  return { entries: data?.entries ?? [], loading }
}

// Real Telegram channel connectivity (see telegram_bot.py / /telegram/status).
export function useTelegramStatus() {
  return useSimplePoll<{ success: boolean; available: boolean; error: string | null; polling?: boolean }>('/api/telegram/status', 20000)
}

export interface TradingQuote {
  pair: string
  price: number
  bid: number
  ask: number
  change_24h: number
  high_24h: number
  low_24h: number
  timestamp: string
}
// Real live forex/metal quotes (Frankfurter/ECB + Yahoo COMEX -- see
// trading/forex_engine.py) for the user's real watched/relevant pairs.
export function useTradingQuotes(pairs?: string[]) {
  const path = pairs && pairs.length > 0 ? `/api/trading/quotes?pairs=${encodeURIComponent(pairs.join(','))}` : '/api/trading/quotes'
  return useSimplePoll<{ success: boolean; quotes: TradingQuote[] }>(path, 30000)
}

// Real watched/relevant trading pairs (trading/manager.py) -- whatever the
// user has actually told Nancy they trade, plus real trade-history pairs.
export function useWatchedPairs() {
  return useSimplePoll<{ success: boolean; watched_pairs: string[]; relevant_pairs: string[] }>('/api/trading/watched-pairs', 60000)
}

export interface ScreenContextStatus {
  success: boolean
  enabled: boolean
  last_summary: string | null
  last_at: number | null
  error: string | null
  configured: boolean
}
// Real ambient screen-awareness state (opt-in, see backend/screen_context.py).
// Off and empty until the user explicitly turns it on -- see useToggleScreenContext.
export function useScreenContextStatus() {
  return useSimplePoll<ScreenContextStatus>('/api/screen-context/status', 10000)
}

export async function setScreenContextEnabled(enabled: boolean): Promise<ScreenContextStatus> {
  const res = await fetch('/api/screen-context/toggle', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  })
  return res.json()
}

export async function captureScreenContextNow(): Promise<{ success: boolean; summary?: string; error?: string }> {
  const res = await fetch('/api/screen-context/capture-now', { method: 'POST' })
  return res.json()
}

export interface ChannelStatus {
  key: string
  label: string
  description: string
  configured: boolean
  detail: string | null
  two_way: boolean
  required_env: string[]
}
// Real per-channel configuration state for every channel this backend
// actually knows how to speak (Telegram + channels/registry.py). Never a
// fabricated "coming soon" entry -- see backend/channels/bootstrap.py for
// the definitive list of what's actually built.
export function useChannelsStatus() {
  return useSimplePoll<{ success: boolean; channels: ChannelStatus[] }>('/api/channels/status', 30000)
}

export async function sendChannelTest(key: string, message?: string): Promise<{ success: boolean; detail?: string }> {
  const res = await fetch(`/api/channels/${encodeURIComponent(key)}/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(message ? { message } : {}),
  })
  return res.json()
}

// ---------------------------------------------------------------------------
// Real paired nodes (node_host.py) -- a second machine running
// node_agent_stub.py that this backend can dispatch real commands to,
// gated by approval_policy.py's allow-once/allow-always/deny engine.
// ---------------------------------------------------------------------------
export function useNodes() {
  return useSimplePoll<{ success: boolean; nodes: Record<string, { base_url: string }> }>('/api/nodes', 20000)
}

export async function registerNode(nodeId: string, baseUrl: string, sharedSecret: string): Promise<{ success: boolean; detail?: string }> {
  const res = await fetch('/api/nodes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ node_id: nodeId, base_url: baseUrl, shared_secret: sharedSecret }),
  })
  return res.json()
}

export async function removeNode(nodeId: string): Promise<{ success: boolean }> {
  const res = await fetch(`/api/nodes/${encodeURIComponent(nodeId)}`, { method: 'DELETE' })
  return res.json()
}

export async function checkNodeHealth(nodeId: string): Promise<{ success: boolean; error?: string }> {
  const res = await fetch(`/api/nodes/${encodeURIComponent(nodeId)}/health`, { cache: 'no-store' })
  return res.json()
}

// ---------------------------------------------------------------------------
// Real Docker-backed multi-tenant fleet cells (fleet/manager.py, fleet/cell.py).
// ---------------------------------------------------------------------------
export interface FleetCell {
  cell_id: string
  tenant_id: string
  container_id: string
  image: string
  mem_limit: string
  nano_cpus: number
  allowed_env_keys: string[]
  created_at: number
  status: string
}
export function useFleetHealth() {
  return useSimplePoll<{ success: boolean; docker_available: boolean; containers_running?: number; error?: string }>('/api/fleet/health', 20000)
}
export function useFleetCells() {
  return useSimplePoll<{ success: boolean; cells: FleetCell[] }>('/api/fleet/cells', 15000)
}

export async function createFleetCell(params: {
  tenant_id: string
  image?: string
  mem_limit?: string
  nano_cpus?: number
}): Promise<{ success: boolean; detail?: string }> {
  const res = await fetch('/api/fleet/cells', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  return res.json()
}

export async function stopFleetCell(cellId: string): Promise<{ success: boolean }> {
  const res = await fetch(`/api/fleet/cells/${encodeURIComponent(cellId)}/stop`, { method: 'POST' })
  return res.json()
}

export async function removeFleetCell(cellId: string): Promise<{ success: boolean; detail?: string }> {
  const res = await fetch(`/api/fleet/cells/${encodeURIComponent(cellId)}`, { method: 'DELETE' })
  return res.json()
}

// ---------------------------------------------------------------------------
// Real LAN discovery (mdns_discovery.py) -- advertises this backend as
// _nancy-gateway._tcp.local. and/or browses for other instances.
// ---------------------------------------------------------------------------
export function useMdnsStatus() {
  return useSimplePoll<{ success: boolean; advertising: boolean; service_type: string; name: string | null }>('/api/mdns/status', 15000)
}

export async function mdnsAdvertise(): Promise<{ success: boolean; name?: string; address?: string; port?: number; error?: string }> {
  const res = await fetch('/api/mdns/advertise', { method: 'POST' })
  return res.json()
}

export async function mdnsStop(): Promise<{ success: boolean }> {
  const res = await fetch('/api/mdns/stop', { method: 'POST' })
  return res.json()
}

export interface MdnsService {
  name: string
  addresses: string[]
  port: number
  properties: Record<string, string>
}
export async function mdnsDiscover(): Promise<{ success: boolean; services: MdnsService[] }> {
  const res = await fetch('/api/mdns/discover', { cache: 'no-store' })
  return res.json()
}

// ---------------------------------------------------------------------------
// Real session-level state: how many WebSocket connections (tabs/devices)
// are actually open right now, and real persisted conversation history
// (memory graph CONVERSATION nodes) that survives a page reload -- distinct
// from the frontend's own in-tab `logs`, which resets on refresh.
// ---------------------------------------------------------------------------
export function useSessionsStatus() {
  return useSimplePoll<{ success: boolean; active_connections: number; uptime_hours: number }>('/api/sessions/status', 15000)
}

export interface ConversationMemory {
  id: string
  content: string
  source: string | null
  timestamp: string | null
  created_at: string
}
export function useConversationHistory(limit = 30) {
  return useSimplePoll<{ success: boolean; conversations: ConversationMemory[] }>(`/api/memory/conversations?limit=${limit}`, 20000)
}

// ---------------------------------------------------------------------------
// Real automation blueprints (blueprint_catalog.py) -- 14 pre-built
// parameterized cron templates. One slot schema drives both this form and
// the real job spec fill_blueprint() produces server-side.
// ---------------------------------------------------------------------------
export interface BlueprintField {
  name: string
  type: 'time' | 'enum' | 'text' | 'weekdays'
  label: string
  default: string | null
  options: string[]
  optional: boolean
  help: string
}
export interface CronBlueprint {
  key: string
  title: string
  description: string
  category: string
  tags: string[]
  fields: BlueprintField[]
  schedule: string
  scheduleHuman: string
}
export function useCronBlueprints() {
  return useSimplePoll<{ success: boolean; blueprints: CronBlueprint[] }>('/api/cron/blueprints', 120000)
}

export async function instantiateBlueprint(key: string, values: Record<string, string>): Promise<{ success: boolean; detail?: string; job?: unknown }> {
  const res = await fetch(`/api/cron/blueprints/${encodeURIComponent(key)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ values }),
  })
  return res.json()
}

// ---------------------------------------------------------------------------
// Real, invokable procedure skills (skill_loader.py's SKILL.md files) with
// real usage stats -- how many times each has actually been keyword-matched
// into a live prompt. Distinct from /skills/custom's purely descriptive
// user-created tags, which have no effect on real behavior.
// ---------------------------------------------------------------------------
export interface LibrarySkill {
  name: string
  description: string
  trigger_keywords: string[]
  match_count: number
  last_matched_at: number | null
}
export function useSkillLibrary() {
  return useSimplePoll<{ success: boolean; skills: LibrarySkill[]; archived: string[] }>('/api/skills/library', 30000)
}

export async function archiveSkill(name: string): Promise<{ success: boolean; detail?: string }> {
  const res = await fetch(`/api/skills/library/${encodeURIComponent(name)}/archive`, { method: 'POST' })
  return res.json()
}
export async function restoreSkill(name: string): Promise<{ success: boolean; detail?: string }> {
  const res = await fetch(`/api/skills/library/${encodeURIComponent(name)}/restore`, { method: 'POST' })
  return res.json()
}

export interface SkillBundle {
  id: string
  name: string
  skill_names: string[]
  description: string
  created_at: number
}
export function useSkillBundles() {
  return useSimplePoll<{ success: boolean; bundles: SkillBundle[] }>('/api/skills/bundles', 30000)
}
export async function createSkillBundle(name: string, skillNames: string[], description = ''): Promise<{ success: boolean; detail?: string }> {
  const res = await fetch('/api/skills/bundles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, skill_names: skillNames, description }),
  })
  return res.json()
}
export async function deleteSkillBundle(id: string): Promise<{ success: boolean }> {
  const res = await fetch(`/api/skills/bundles/${encodeURIComponent(id)}`, { method: 'DELETE' })
  return res.json()
}

