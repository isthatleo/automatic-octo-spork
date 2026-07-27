'use client'

import { useEffect, useCallback, useMemo, useRef, useState } from 'react'
import type { ElementType, ReactNode } from 'react'
import { ArcReactor, HudPanel, RadialGauge, StatBar, AnimatedNumber } from './hud-bits'
import type { AgentInfo, PanelKey } from '@/lib/nancy/types'
import { listAgents, type AgentListResponse } from '@/lib/nancy/agent-client'
import { useSystemHealth, useTradeHistory, useLlmStatus, useCronStatus, useTelegramStatus } from '@/hooks/useSystemData'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  Activity,
  Cpu,
  Database,
  Shield,
  Bot,
  Terminal,
  Folder,
  Globe2,
  Music,
  Mail,
  Camera,
  Calculator,
  Code2,
  RefreshCw,
  Zap,
  Waves,
  Signal,
  ShieldCheck,
  Eye,
  Thermometer,
  Brain,
  Award,
  FileClock,
  Send,
  ArrowRight,
  TrendingUp,
  AlertTriangle,
} from 'lucide-react'
import { cn } from '@/lib/utils'

function useTick(ms = 1000) {
  const [t, setT] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setT((n) => n + 1), ms)
    return () => clearInterval(id)
  }, [ms])
  return t
}

/* Rolling client-side buffer of real, currently-measured values — turns a
 * live instantaneous metric (CPU%, memory%, ...) into a genuine time series
 * for a chart, without inventing any history the backend never recorded. */
function useMetricHistory(values: Record<string, number | null | undefined>, maxPoints = 30) {
  const [history, setHistory] = useState<Array<{ t: number } & Record<string, number>>>([])
  const key = JSON.stringify(values)
  useEffect(() => {
    const parsed = JSON.parse(key) as Record<string, number | null | undefined>
    const point: { t: number } & Record<string, number> = { t: Date.now() } as { t: number } & Record<string, number>
    let hasValue = false
    for (const k of Object.keys(parsed)) {
      const v = parsed[k]
      if (v != null) {
        point[k] = v
        hasValue = true
      }
    }
    if (!hasValue) return
    setHistory((h) => [...h.slice(-(maxPoints - 1)), point])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, maxPoints])
  return history
}

/** Live agent roster + fleet stats, polled independently of the Agents tab
 * so the Overview's charts and stat cards reflect the real fleet instead of
 * static placeholder numbers. */
function useAgentsBrief(intervalMs = 15000) {
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [stats, setStats] = useState<AgentListResponse['stats'] | null>(null)
  useEffect(() => {
    let cancelled = false
    const load = async () => {
      const res = await listAgents()
      if (!cancelled && res.success) {
        setAgents(res.agents)
        setStats(res.stats)
      }
    }
    load()
    const t = setInterval(load, intervalMs)
    return () => {
      cancelled = true
      clearInterval(t)
    }
  }, [intervalMs])
  return { agents, stats }
}

/** Real logical core count, read client-side only (avoids an SSR/hydration
 * mismatch, since `navigator` doesn't exist on the server) — replaces a
 * fabricated "128 cores" figure. */
function useCpuCoreCount() {
  const [cores, setCores] = useState<number | null>(null)
  useEffect(() => {
    setCores(typeof navigator !== 'undefined' ? navigator.hardwareConcurrency ?? null : null)
  }, [])
  return cores
}

/** Real wall-clock time since this dashboard instance mounted — replaces a
 * fabricated "412d" uptime figure with an honestly-labelled session timer. */
function useSessionUptime() {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    const start = Date.now()
    const t = setInterval(() => setSeconds(Math.floor((Date.now() - start) / 1000)), 1000)
    return () => clearInterval(t)
  }, [])
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}

/** Real recent activity -- terminal commands + file writes actually
 * recorded by evidence_ledger.py, merged with real skill/memory events from
 * the journey timeline. Replaces the old ActivityTimeline, which just
 * re-described the same cpu/mem/fleet numbers already shown elsewhere in
 * this page as fake "log lines" -- this is genuinely new information. */
function useRecentActivity(intervalMs = 20000) {
  const [rows, setRows] = useState<Array<{ id: string; tag: string; text: string; tone: 'ok' | 'warn'; at: number }>>([])
  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const [evidenceRes, journeyRes] = await Promise.all([
          fetch('/api/evidence?limit=8').then((r) => r.json()),
          fetch('/api/memory/journey?limit=6').then((r) => r.json()).catch(() => null),
        ])
        if (cancelled) return
        const merged: Array<{ id: string; tag: string; text: string; tone: 'ok' | 'warn'; at: number }> = []
        if (evidenceRes?.success) {
          for (const e of evidenceRes.evidence) {
            merged.push({
              id: `ev-${e.id}`, tag: e.kind, tone: e.success ? 'ok' : 'warn',
              text: e.kind === 'write_file' ? `wrote ${e.action}` : e.kind === 'terminal_command' ? `ran: ${e.action}`.slice(0, 70) : `${e.kind}: ${e.action}`.slice(0, 70),
              at: e.timestamp * 1000,
            })
          }
        }
        if (journeyRes?.success) {
          for (const j of journeyRes.timeline) {
            merged.push({ id: `jr-${j.timestamp}`, tag: j.kind, tone: 'ok', text: j.label, at: j.timestamp * 1000 })
          }
        }
        merged.sort((a, b) => b.at - a.at)
        setRows(merged.slice(0, 8))
      } catch {
        // leave existing rows in place on a transient fetch failure
      }
    }
    load()
    const t = setInterval(load, intervalMs)
    return () => { cancelled = true; clearInterval(t) }
  }, [intervalMs])
  return rows
}

/** Real per-backend LLM call volume/latency/tokens/inference-speed --
 * usage_analytics.py, Batch 7 -- surfaced here since it previously had zero
 * presence on the main dashboard despite being real, live data. */
function useLlmUsageBrief(intervalMs = 30000) {
  const [usage, setUsage] = useState<{ overall_calls: number; per_backend: Array<Record<string, unknown>> } | null>(null)
  useEffect(() => {
    let cancelled = false
    const load = () => fetch('/api/usage/llm').then((r) => r.json()).then((json) => { if (!cancelled && json.success) setUsage(json) }).catch(() => {})
    load()
    const t = setInterval(load, intervalMs)
    return () => { cancelled = true; clearInterval(t) }
  }, [intervalMs])
  return usage
}

interface AchievementsBrief {
  unlocked: number
  total: number
  /** Real usage-derived counters already computed by achievements_store.py
   * (task/command/memory/skill history) -- previously only consumed to
   * compute the unlocked/total counts above, discarding the rest. Reused
   * here for the Memory & Growth tile and the header's real uptime figure
   * instead of fetching the same data twice. */
  activity: {
    total_tasks: number
    failed_tasks: number
    terminal_commands: number
    file_writes: number
    distinct_skills_used: number
    total_skills: number
    total_memories: number
    wiki_pages: number
    dream_cycles: number
    uptime_hours: number
  } | null
}

/** Real unlocked/total achievement counts + activity breakdown --
 * achievements_store.py, Batch 7. */
function useAchievementsBrief(intervalMs = 60000) {
  const [data, setData] = useState<AchievementsBrief | null>(null)
  useEffect(() => {
    let cancelled = false
    const load = () => fetch('/api/achievements').then((r) => r.json()).then((json) => {
      if (!cancelled && json.success) {
        setData({ unlocked: json.unlocked.length, total: json.unlocked.length + json.locked.length, activity: json.activity ?? null })
      }
    }).catch(() => {})
    load()
    const t = setInterval(load, intervalMs)
    return () => { cancelled = true; clearInterval(t) }
  }, [intervalMs])
  return data
}

/** Formats a real backend-process-uptime figure (achievements_store.py's
 * activity.uptime_hours, tracked since the process actually started) --
 * replaces the client-side "since this browser tab mounted" session timer
 * with the real thing now that the backend exposes it. */
function formatUptime(hours: number | null | undefined): string {
  if (hours == null) return '…'
  const totalMinutes = Math.round(hours * 60)
  const d = Math.floor(totalMinutes / 1440)
  const h = Math.floor((totalMinutes % 1440) / 60)
  const m = totalMinutes % 60
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

/** Real relative time to a cron job's next_run timestamp (cron_store.py). */
function formatRelative(iso: string | undefined): string {
  if (!iso) return '…'
  const diffMs = new Date(iso).getTime() - Date.now()
  if (diffMs <= 0) return 'due now'
  const mins = Math.round(diffMs / 60000)
  if (mins < 60) return `in ${mins}m`
  const hours = Math.round(mins / 60)
  if (hours < 48) return `in ${hours}h`
  return `in ${Math.round(hours / 24)}d`
}

/** Real arm-switch + egress-proxy state -- both are live, actionable safety
 * surfaces from Batches 1/6 with no visibility anywhere on the main
 * dashboard until now. */
function useSafetyBrief(intervalMs = 15000) {
  const [armed, setArmed] = useState<boolean | null>(null)
  const [proxyRunning, setProxyRunning] = useState<boolean | null>(null)
  useEffect(() => {
    let cancelled = false
    const load = () => {
      fetch('/api/safety/status').then((r) => r.json()).then((json) => { if (!cancelled && 'armed' in json) setArmed(json.armed) }).catch(() => {})
      fetch('/api/egress-proxy/status').then((r) => r.json()).then((json) => { if (!cancelled && 'running' in json) setProxyRunning(json.running) }).catch(() => {})
    }
    load()
    const t = setInterval(load, intervalMs)
    return () => { cancelled = true; clearInterval(t) }
  }, [intervalMs])
  return { armed, proxyRunning }
}

function HudTooltip({ active, payload, label, unit = '' }: { active?: boolean; payload?: Array<{ name: string; value: number; color?: string }>; label?: string | number; unit?: string }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded border border-primary/40 bg-background/90 px-2 py-1.5 font-mono text-[0.6rem] shadow-[0_0_12px_rgba(56,211,235,0.25)] backdrop-blur-sm">
      {label != null && <div className="mb-1 text-muted-foreground">{label}</div>}
      {payload.map((p, i) => (
        <div key={i} className="flex items-center gap-1.5" style={{ color: p.color }}>
          <span className="capitalize">{p.name}</span>
          <span className="ml-auto text-foreground">{typeof p.value === 'number' ? p.value.toFixed(1) : p.value}{unit}</span>
        </div>
      ))}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   OVERVIEW — Mission Control
   Big hero arc-reactor, live rings, world telemetry, comms feed.
   ═══════════════════════════════════════════════════════════════ */
export function OverviewPanel({ onNavigate }: { onNavigate?: (key: PanelKey) => void } = {}) {
  const health = useSystemHealth()
  const cpu = health.cpu ?? 0
  const mem = health.memory ?? 0
  const disk = health.disk ?? 0
  const tick = useTick(1200)
  const { agents, stats } = useAgentsBrief()
  const cores = useCpuCoreCount()
  const telemetryHistory = useMetricHistory({ cpu: health.cpu, mem: health.memory, net: health.networkPercent })
  const successPct = stats ? stats.success_rate * 100 : 100
  const usage = useLlmUsageBrief()
  const achievements = useAchievementsBrief()
  const { armed, proxyRunning } = useSafetyBrief()
  const { data: llm, loading: llmLoading } = useLlmStatus()

  // Real, honest two-state status -- no fabricated "critical" severity
  // level without an actual signal to back it. Each alert names the exact
  // data point that triggered it, so the headline is never a guess.
  const alerts: string[] = []
  if (armed) alerts.push('Arm switch is armed — approvals are being bypassed')
  if (stats && stats.failed_tasks > 0) alerts.push(`${stats.failed_tasks} failed task${stats.failed_tasks === 1 ? '' : 's'} recorded`)
  if (!llmLoading && !llm) alerts.push('LLM reasoning chain unavailable')
  const statusOk = alerts.length === 0

  const kpis: { label: string; v: number; suffix?: string }[] = [
    { label: 'Tasks run', v: stats?.total_tasks ?? 0 },
    { label: 'Agents online', v: stats?.agents_online ?? 0 },
    { label: 'Success rate', v: Math.round(successPct), suffix: '%' },
    { label: 'LLM calls', v: usage?.overall_calls ?? 0 },
    { label: 'Memories', v: achievements?.activity?.total_memories ?? 0 },
  ]

  return (
    <div className="mx-auto flex max-w-[1680px] flex-col gap-4">
      {/* ── Status bar: the one thing worth glancing at first. A plain
          colored-state line instead of decorative hero art -- real
          command-center UIs favor an unambiguous status signal over
          spectacle (operators stop consciously processing decorative
          motion within minutes of exposure). Two honest states (nominal /
          needs attention), each backed by a real, named signal. ── */}
      <div className="flex flex-col gap-2 rounded-xl border border-border bg-card/60 px-4 py-3">
        <div className="flex flex-wrap items-center gap-3">
          <span className={cn('h-2.5 w-2.5 shrink-0 rounded-full animate-hud-pulse', statusOk ? 'bg-primary' : 'bg-gold')} />
          <span className="font-heading text-sm text-foreground">
            {statusOk ? 'All systems nominal' : `${alerts.length} item${alerts.length === 1 ? '' : 's'} need attention`}
          </span>
          <span className="text-[0.6rem] text-muted-foreground">· backend uptime {formatUptime(achievements?.activity?.uptime_hours)}</span>
          <span className="ml-auto flex items-center gap-1.5 text-[0.55rem] text-muted-foreground">
            <Activity className="h-3 w-3 text-primary animate-hud-breathe" /> live · Δ{tick}
          </span>
        </div>
        {!statusOk && (
          <ul className="flex flex-wrap gap-x-4 gap-y-1 pl-[1.375rem] text-[0.6rem] text-gold">
            {alerts.map((a) => (
              <li key={a} className="flex items-center gap-1.5">
                <AlertTriangle className="h-3 w-3 shrink-0" /> {a}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* ── KPI strip: the numbers actually worth checking day to day, one
          dense row in priority order, instead of scattered across several
          separate boxes. ── */}
      <div className="flex flex-wrap items-center gap-x-8 gap-y-3 rounded-xl border border-border bg-card/60 px-5 py-4">
        {kpis.map((k) => (
          <div key={k.label} className="flex flex-col">
            <span className="font-display text-2xl text-foreground">
              <AnimatedNumber value={k.v} />{k.suffix}
            </span>
            <span className="text-[0.55rem] text-muted-foreground">{k.label}</span>
          </div>
        ))}
      </div>

      {/* ── Status cards: one consistent card grammar for every real
          subsystem instead of a different widget shape per capability
          (donut here, globe there, gauges elsewhere). Each card is both
          the summary AND, where a dedicated page exists, the navigation
          into it -- action lives with the data it acts on instead of a
          separate read-only tile plus an unrelated "quick actions" panel.
          Safety and Trading have no dedicated page yet, so they stay
          informational only rather than linking somewhere dishonest. ── */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <FleetCard stats={stats} onNavigate={onNavigate} />
        <ReasoningCard usage={usage} llm={llm} llmLoading={llmLoading} onNavigate={onNavigate} />
        <AutomationsCard onNavigate={onNavigate} />
        <SafetyCard armed={armed} proxyRunning={proxyRunning} />
        <ChannelsCard onNavigate={onNavigate} />
        <MemoryCard activity={achievements?.activity ?? null} onNavigate={onNavigate} />
        <AchievementsCard achievements={achievements} onNavigate={onNavigate} />
        <TradingCard />
        <SystemCard cpu={cpu} mem={mem} disk={disk} cores={cores} tempC={health.tempC ?? null} onNavigate={onNavigate} />
      </div>

      {/* ── Analytics: every trend/breakdown a static status card can't
          show. Four real charts, each backed by data already flowing into
          the cards above (system telemetry, LLM per-backend usage, fleet
          task volume by domain, trading P/L) -- a genuine time series or
          comparison the card grammar deliberately keeps out of its own
          summary line. ── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <HudPanel title="Live Telemetry" right={<span className="text-primary text-[0.5rem]">Δ {tick}</span>}>
          <SystemTelemetryChart history={telemetryHistory} height={160} />
          <div className="mt-3 flex items-center gap-3 text-[0.5rem] text-muted-foreground">
            <LegendDot color="var(--hud)" label="cpu" />
            <LegendDot color="var(--accent)" label="memory" />
            <LegendDot color="oklch(0.7 0.16 160)" label="uplink" />
          </div>
        </HudPanel>

        <HudPanel title="LLM Usage by Backend" accent="amber">
          <LlmBackendChart usage={usage} />
        </HudPanel>

        <HudPanel title="Task Volume by Domain" accent="violet">
          <DomainTaskChart agents={agents} />
        </HudPanel>

        <HudPanel title="Trading P/L Trend" accent="magenta">
          <TradingTrendChart />
        </HudPanel>
      </div>

      {/* ── Activity: the real log, deliberately kept separate from the
          status cards above -- a status board and an activity log answer
          different questions and read worse merged into one stream. ── */}
      <div className="rounded-xl border border-border bg-card/60 p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="flex items-center gap-2 font-heading text-[0.72rem] font-medium text-foreground/90">
            <span className="h-1.5 w-1.5 rounded-full bg-primary" /> Activity
          </h2>
          <span className="text-primary text-xs">Live</span>
        </div>
        <RealActivityFeed />
      </div>
    </div>
  )
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="h-2 w-2 rounded-sm" style={{ background: color, boxShadow: `0 0 4px ${color}` }} />
      {label}
    </span>
  )
}

/* ─── Real CPU/memory/uplink history (client-side rolling buffer of
   actual psutil-backed samples — see useMetricHistory) ─── */
function SystemTelemetryChart({ history, height = 160 }: { history: Array<{ t: number } & Record<string, number>>; height?: number }) {
  if (history.length < 2) {
    return (
      <div className="flex items-center justify-center text-[0.6rem] text-muted-foreground" style={{ height }}>
        Gathering telemetry…
      </div>
    )
  }
  return (
    <div className="w-full" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={history} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
          <defs>
            <linearGradient id="fillCpu" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--hud)" stopOpacity={0.4} />
              <stop offset="100%" stopColor="var(--hud)" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="fillMem" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.35} />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="t" hide />
          <YAxis domain={[0, 100]} width={28} tick={{ fontSize: 9, fill: 'var(--muted-foreground)' }} />
          <Tooltip content={<HudTooltip unit="%" />} />
          <Area type="monotone" dataKey="cpu" name="cpu" stroke="var(--hud)" fill="url(#fillCpu)" strokeWidth={1.5} isAnimationActive={false} />
          <Area type="monotone" dataKey="mem" name="memory" stroke="var(--accent)" fill="url(#fillMem)" strokeWidth={1.5} isAnimationActive={false} />
          <Area type="monotone" dataKey="net" name="uplink" stroke="oklch(0.7 0.16 160)" fill="transparent" strokeWidth={1.2} isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Real per-backend LLM usage (calls + tokens), grouped from
 * usage_analytics.py's per-backend rollup -- the fallback chain's actual
 * distribution of work, not just the single top backend's name. */
function LlmBackendChart({ usage }: { usage: ReturnType<typeof useLlmUsageBrief> }) {
  const data = useMemo(() => {
    return (usage?.per_backend ?? []).map((b) => ({
      name: String(b.backend).replace(/LLM$/, ''),
      tokens: Number(b.total_tokens ?? 0),
      calls: Number(b.call_count ?? 0),
      tokPerSec: b.tokens_per_sec != null ? Number(b.tokens_per_sec) : null,
    }))
  }, [usage])

  if (data.length === 0) {
    return <div className="flex h-40 items-center justify-center text-[0.6rem] text-muted-foreground">No LLM calls recorded yet this run.</div>
  }
  return (
    <div className="flex flex-col gap-2">
      <div className="h-32 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
            <XAxis dataKey="name" tick={{ fontSize: 9, fill: 'var(--muted-foreground)' }} interval={0} />
            <YAxis width={32} tick={{ fontSize: 9, fill: 'var(--muted-foreground)' }} />
            <Tooltip content={<HudTooltip unit=" tok" />} />
            <Bar dataKey="tokens" name="tokens" radius={[3, 3, 0, 0]} isAnimationActive={false}>
              {data.map((_, i) => (
                <Cell key={i} fill={DOMAIN_COLORS[i % DOMAIN_COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ul className="flex flex-wrap gap-x-3 gap-y-1 text-[0.55rem] text-muted-foreground">
        {data.map((b, i) => (
          <li key={b.name} className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: DOMAIN_COLORS[i % DOMAIN_COLORS.length] }} />
            {b.name}: {b.calls} call{b.calls === 1 ? '' : 's'}{b.tokPerSec != null ? ` · ${b.tokPerSec} tok/s` : ''}
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Real task volume grouped by agent domain (sum of each agent's real
 * total_tasks) -- a richer breakdown than a bare agent-count split, since
 * it reflects actual work done, not just roster size. */
function DomainTaskChart({ agents }: { agents: AgentInfo[] }) {
  const data = useMemo(() => {
    const counts = new Map<string, number>()
    for (const a of agents) counts.set(a.domain, (counts.get(a.domain) ?? 0) + (a.total_tasks ?? 0))
    return Array.from(counts, ([domain, tasks]) => ({ domain, tasks }))
      .sort((a, b) => b.tasks - a.tasks)
      .slice(0, 8)
  }, [agents])

  if (data.length === 0) {
    return <div className="flex h-40 items-center justify-center text-[0.6rem] text-muted-foreground">Awaiting fleet roster…</div>
  }
  return (
    <div className="h-40 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 12, bottom: 0, left: 4 }}>
          <XAxis type="number" tick={{ fontSize: 9, fill: 'var(--muted-foreground)' }} allowDecimals={false} />
          <YAxis type="category" dataKey="domain" width={92} tick={{ fontSize: 9, fill: 'var(--muted-foreground)' }} />
          <Tooltip content={<HudTooltip unit=" tasks" />} />
          <Bar dataKey="tasks" name="tasks" radius={[0, 3, 3, 0]} isAnimationActive={false}>
            {data.map((_, i) => (
              <Cell key={i} fill={DOMAIN_COLORS[i % DOMAIN_COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Real cumulative trade P/L over the recent trade history
 * (useTradeHistory) -- the trend that the Trading status card's single
 * "latest" figure can't show on its own. */
function TradingTrendChart() {
  const { data: trades, loading } = useTradeHistory(20)
  const data = useMemo(() => {
    let cumulative = 0
    return trades
      .filter((t) => typeof t.profit_loss === 'number')
      .map((t, i) => {
        cumulative += t.profit_loss as number
        return { seq: i, pair: t.pair ?? `#${i}`, cumulative }
      })
  }, [trades])

  if (loading && data.length === 0) {
    return <div className="flex h-40 items-center justify-center text-[0.6rem] text-muted-foreground">Loading trade history…</div>
  }
  if (data.length === 0) {
    return <div className="flex h-40 items-center justify-center text-[0.6rem] text-muted-foreground">No closed trades yet.</div>
  }
  return (
    <div className="h-40 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
          <defs>
            <linearGradient id="fillPl" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--hud)" stopOpacity={0.4} />
              <stop offset="100%" stopColor="var(--hud)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="seq" hide />
          <YAxis width={32} tick={{ fontSize: 9, fill: 'var(--muted-foreground)' }} />
          <Tooltip content={<HudTooltip unit=" pips" />} />
          <Area type="monotone" dataKey="cumulative" name="cumulative P/L" stroke="var(--hud)" fill="url(#fillPl)" strokeWidth={1.5} isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

/* ─── Live activity timeline -- real derived events, not scripted flavor
   text. Appends a real line whenever the actual polled system/fleet values
   change, instead of cycling through fabricated "SIGINT"/"orbital satellite"
   copy that never corresponded to anything the backend does. Rendered as a
   connecting-rail timeline instead of a bordered list, distinct from the
   panel/box vocabulary used everywhere else on the page. ─── */
/* ─── Real activity feed -- terminal commands, file writes, skill/memory
   events, actually recorded by evidence_ledger.py + journey.py. Replaces
   the old client-synthesized timeline that just re-described numbers
   already visible elsewhere on this page. ─── */
function RealActivityFeed() {
  const rows = useRecentActivity()

  if (rows.length === 0) {
    return <p className="text-xs text-muted-foreground">No real activity recorded yet this run — terminal commands, file writes, and skill usage will appear here as they happen.</p>
  }

  return (
    <ol className="relative flex flex-col gap-4 pl-4">
      <div className="absolute bottom-1 left-[3px] top-1 w-px bg-border" aria-hidden />
      {rows.map((row, i) => (
        <li key={row.id} className="relative flex items-start gap-3" style={{ opacity: 1 - i * 0.08 }}>
          <span
            className={cn(
              'absolute -left-4 top-1 h-2 w-2 shrink-0 rounded-full ring-4 ring-card',
              row.tone === 'warn' ? 'bg-destructive' : 'bg-primary',
            )}
          />
          <div className="flex min-w-0 flex-1 items-center justify-between gap-3">
            <div className="min-w-0">
              <span className="mr-2 font-mono text-[0.55rem] text-muted-foreground">{row.tag}</span>
              <span className="truncate text-xs text-foreground">{row.text}</span>
            </div>
            <span className="shrink-0 font-mono text-[0.6rem] text-muted-foreground">
              {new Date(row.at).toLocaleTimeString('en-GB').slice(0, 8)}
            </span>
          </div>
        </li>
      ))}
    </ol>
  )
}

/* ═══════════════════════════════════════════════════════════════
   STATUS CARDS — one consistent card grammar for every real subsystem,
   replacing the previous mix of donut/globe/gauge/bar widgets that each
   looked different for no reason tied to the data itself. Every card is
   simultaneously the summary AND, where a dedicated page exists, the
   navigation into it -- action lives with the data it describes instead
   of a separate read-only tile plus an unrelated "quick actions" grid.
   ═══════════════════════════════════════════════════════════════ */
function StatusCard({
  icon: Icon,
  title,
  value,
  sub,
  tone = 'ok',
  onClick,
  children,
}: {
  icon: ElementType
  title: string
  value: string
  sub?: string
  tone?: 'ok' | 'warn'
  onClick?: () => void
  children?: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!onClick}
      className={cn(
        'group flex flex-col gap-2 rounded-xl border border-border bg-card/60 p-4 text-left transition-all',
        onClick ? 'cursor-pointer hover:border-primary/50 hover:bg-card' : 'cursor-default',
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-[0.62rem] text-muted-foreground">
          <Icon className="h-3.5 w-3.5 text-primary" /> {title}
        </span>
        <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', tone === 'warn' ? 'bg-gold' : 'bg-primary')} />
      </div>
      <div className="truncate font-display text-lg text-foreground">{value}</div>
      {sub && <div className="truncate text-[0.58rem] text-muted-foreground">{sub}</div>}
      {children}
      {onClick && (
        <span className="mt-0.5 flex items-center gap-1 text-[0.55rem] text-primary opacity-0 transition-opacity group-hover:opacity-100">
          View <ArrowRight className="h-2.5 w-2.5" />
        </span>
      )}
    </button>
  )
}

const DOMAIN_COLORS = ['var(--hud)', 'var(--accent)', 'var(--gold)', 'var(--tertiary)', 'oklch(0.7 0.16 160)', 'oklch(0.65 0.18 25)']

function FleetCard({
  stats,
  onNavigate,
}: {
  stats: AgentListResponse['stats'] | null
  onNavigate?: (key: PanelKey) => void
}) {
  const total = stats ? stats.agents_online + stats.agents_offline : 0
  return (
    <StatusCard
      icon={Bot}
      title="Fleet"
      value={stats ? `${stats.agents_online}/${total} online` : '…'}
      sub={stats ? `${Math.round(stats.success_rate * 100)}% success · ${stats.total_tasks} tasks run` : undefined}
      onClick={onNavigate ? () => onNavigate('agents') : undefined}
    />
  )
}

function ReasoningCard({
  usage,
  llm,
  llmLoading,
  onNavigate,
}: {
  usage: ReturnType<typeof useLlmUsageBrief>
  llm: ReturnType<typeof useLlmStatus>['data']
  llmLoading: boolean
  onNavigate?: (key: PanelKey) => void
}) {
  const topBackend = usage?.per_backend?.[0] as Record<string, unknown> | undefined
  return (
    <StatusCard
      icon={Zap}
      title="Reasoning"
      value={llm?.primary_model ?? (topBackend ? String(topBackend.backend) : 'No calls yet')}
      sub={usage ? `${usage.overall_calls} call${usage.overall_calls === 1 ? '' : 's'}${topBackend?.tokens_per_sec != null ? ` · ${topBackend.tokens_per_sec} tok/s` : ''}` : undefined}
      tone={!llmLoading && !llm ? 'warn' : 'ok'}
      onClick={onNavigate ? () => onNavigate('core') : undefined}
    />
  )
}

function AutomationsCard({ onNavigate }: { onNavigate?: (key: PanelKey) => void }) {
  const { data: cronData } = useCronStatus()
  const jobs = cronData?.jobs ?? []
  const job = jobs[0]
  return (
    <StatusCard
      icon={FileClock}
      title="Automations"
      value={job ? job.name : 'None scheduled'}
      sub={job ? `Next run ${formatRelative(job.next_run)} · ${jobs.length} job${jobs.length === 1 ? '' : 's'}` : undefined}
      onClick={onNavigate ? () => onNavigate('cron') : undefined}
    />
  )
}

function SafetyCard({ armed, proxyRunning }: { armed: boolean | null; proxyRunning: boolean | null }) {
  return (
    <StatusCard
      icon={ShieldCheck}
      title="Safety"
      value={armed == null ? '…' : armed ? 'Armed' : 'Disarmed'}
      sub={proxyRunning == null ? undefined : `Egress proxy ${proxyRunning ? 'running' : 'stopped'}`}
      tone={armed ? 'warn' : 'ok'}
    />
  )
}

function ChannelsCard({ onNavigate }: { onNavigate?: (key: PanelKey) => void }) {
  const { data: telegramData } = useTelegramStatus()
  return (
    <StatusCard
      icon={Send}
      title="Channels"
      value={telegramData?.available ? 'Telegram connected' : 'Telegram not configured'}
      sub={telegramData?.polling ? 'Polling for commands' : undefined}
      onClick={onNavigate ? () => onNavigate('channels') : undefined}
    />
  )
}

function MemoryCard({
  activity,
  onNavigate,
}: {
  activity: AchievementsBrief['activity']
  onNavigate?: (key: PanelKey) => void
}) {
  return (
    <StatusCard
      icon={Brain}
      title="Memory & Growth"
      value={activity ? `${activity.total_memories} memories` : '…'}
      sub={activity ? `${activity.distinct_skills_used}/${activity.total_skills} skills used · ${activity.terminal_commands} commands run` : undefined}
      onClick={onNavigate ? () => onNavigate('memory-insights') : undefined}
    />
  )
}

function AchievementsCard({
  achievements,
  onNavigate,
}: {
  achievements: AchievementsBrief | null
  onNavigate?: (key: PanelKey) => void
}) {
  const pct = achievements ? (achievements.unlocked / Math.max(1, achievements.total)) * 100 : 0
  return (
    <StatusCard
      icon={Award}
      title="Achievements"
      value={achievements ? `${achievements.unlocked}/${achievements.total} unlocked` : '…'}
      onClick={onNavigate ? () => onNavigate('achievements') : undefined}
    >
      <div className="h-1.5 overflow-hidden rounded-full bg-secondary/40">
        <div className="h-full rounded-full bg-gold transition-all duration-700" style={{ width: `${pct}%` }} />
      </div>
    </StatusCard>
  )
}

/** Real recent trade P/L summary -- the full trend lives in the Trading
 * P/L Trend chart below (Analytics section); this card stays a plain
 * glanceable status line, not a duplicate of that chart. */
function TradingCard() {
  const { data: trades, loading } = useTradeHistory(10)
  const closed = useMemo(() => trades.filter((t) => typeof t.profit_loss === 'number'), [trades])
  const latest = closed[closed.length - 1]

  return (
    <StatusCard
      icon={TrendingUp}
      title="Trading"
      value={loading && closed.length === 0 ? '…' : !latest ? 'No closed trades' : `${latest.profit_loss >= 0 ? '+' : ''}${Number(latest.profit_loss).toFixed(1)} pips latest`}
      sub={closed.length > 0 ? `${closed.length} recent trade${closed.length === 1 ? '' : 's'}` : undefined}
    />
  )
}

function SystemCard({
  cpu,
  mem,
  disk,
  cores,
  tempC,
  onNavigate,
}: {
  cpu: number
  mem: number
  disk: number
  cores: number | null
  tempC: number | null
  onNavigate?: (key: PanelKey) => void
}) {
  return (
    <StatusCard
      icon={Cpu}
      title="System"
      value={`${cpu.toFixed(0)}% CPU`}
      sub={`${mem.toFixed(0)}% mem · ${disk.toFixed(0)}% disk${tempC != null ? ` · ${tempC.toFixed(0)}°C` : ''}${cores != null ? ` · ${cores} cores` : ''}`}
      onClick={onNavigate ? () => onNavigate('system') : undefined}
    />
  )
}

/* ═══════════════════════════════════════════════════════════════
   NEURAL CORE — Cognition dashboard
   ═══════════════════════════════════════════════════════════════ */
export function CorePanel() {
  const health = useSystemHealth()
  const { stats } = useAgentsBrief()
  const { data: llm, loading: llmLoading } = useLlmStatus()
  const fleetOnlinePct = stats && stats.agents_online + stats.agents_offline > 0
    ? (stats.agents_online / (stats.agents_online + stats.agents_offline)) * 100
    : 0

  return (
    <div className="mx-auto flex max-w-[1680px] flex-col gap-4">
      {/* ── Hero: reactor as the visual anchor, vitals wrapped as a ring of
          gauges beneath it rather than a boxed grid beside it -- a
          genuinely different composition from Overview's briefing-strip
          layout. ── */}
      <div className="relative overflow-hidden rounded-2xl border border-primary/25 bg-gradient-to-br from-card via-card to-primary/5 p-6">
        <div className="pointer-events-none absolute -left-20 -bottom-20 h-56 w-56 rounded-full bg-primary/10 blur-3xl" aria-hidden />
        <div className="relative flex flex-col items-center gap-5">
          <div className="flex items-center gap-2 text-[0.6rem] text-muted-foreground">
            <span className="h-1.5 w-1.5 rounded-full bg-primary animate-hud-pulse" /> Neural Substrate · <span className="text-primary">STABLE</span>
          </div>
          <ArcReactor size={220} />
          <div className="grid w-full max-w-2xl grid-cols-2 gap-3 sm:grid-cols-4">
            <RadialGauge value={health.cpu ?? 0} label="CPU Load" color="var(--hud)" size={84} />
            <RadialGauge value={health.memory ?? 0} label="Memory" color="var(--accent)" size={84} />
            <RadialGauge value={fleetOnlinePct} label="Fleet Online" color="var(--hud)" size={84} />
            <RadialGauge value={(stats?.success_rate ?? 0) * 100} label="Success Rate" color="var(--tertiary)" size={84} />
          </div>
        </div>
      </div>

      {/* ── Real reasoning pipeline: the actual STT -> LLM fallback chain ->
          TTS flow this system runs, sourced from /llm/status. Replaces a
          previous fully-fabricated "thought trace" animation that looped a
          hardcoded, unrelated script regardless of what was really
          happening -- this shows the real chain instead. ── */}
      <HudPanel title="Reasoning Pipeline · Live Chain" accent="violet" right={<span className="text-primary text-[0.5rem]">{llm ? 'synced' : '…'}</span>}>
        <ReasoningPipeline llm={llm} loading={llmLoading} />
      </HudPanel>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_320px]">
        <HudPanel title="Model Stack" accent="amber">
          {llmLoading && !llm ? (
            <div className="flex items-center justify-center py-6 text-[0.6rem] text-muted-foreground">
              <RefreshCw className="mr-2 h-3.5 w-3.5 animate-spin" /> Reading live backend chain…
            </div>
          ) : (
            <ul className="grid grid-cols-1 gap-1.5 md:grid-cols-2">
              {(llm?.backends ?? []).map((b, i) => (
                <li key={`${b.name}-${i}`} className="flex items-center justify-between gap-2 rounded border border-border/50 bg-secondary/20 px-2 py-1.5">
                  <span className="flex items-center gap-2 text-[0.6rem] text-muted-foreground">
                    <Zap className="h-3 w-3 text-primary" /> {b.name}
                  </span>
                  <span className="truncate text-[0.6rem] text-primary">{b.model ?? (i === 0 ? 'primary' : 'fallback')}</span>
                </li>
              ))}
              {llm?.stt && (
                <li className="flex items-center justify-between gap-2 rounded border border-border/50 bg-secondary/20 px-2 py-1.5">
                  <span className="flex items-center gap-2 text-[0.6rem] text-muted-foreground">
                    <Waves className="h-3 w-3 text-primary" /> Speech-to-text
                  </span>
                  <span className="truncate text-[0.6rem] text-primary">{llm.stt.backend}{llm.stt.model ? ` · ${llm.stt.model}` : ''}</span>
                </li>
              )}
              {llm?.tts && (
                <li className="flex items-center justify-between gap-2 rounded border border-border/50 bg-secondary/20 px-2 py-1.5">
                  <span className="flex items-center gap-2 text-[0.6rem] text-muted-foreground">
                    <Eye className="h-3 w-3 text-primary" /> Voice synthesis
                  </span>
                  <span className="truncate text-[0.6rem] text-primary">{llm.tts.backend}</span>
                </li>
              )}
            </ul>
          )}
        </HudPanel>

        <HudPanel title="Agent Fleet" accent="violet">
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between rounded border border-border/50 bg-secondary/20 px-2.5 py-2">
              <span className="flex items-center gap-2 text-[0.6rem] text-muted-foreground"><Bot className="h-3.5 w-3.5 text-primary" /> Online</span>
              <span className="font-heading text-sm text-primary"><AnimatedNumber value={stats?.agents_online ?? 0} /></span>
            </div>
            <div className="flex items-center justify-between rounded border border-border/50 bg-secondary/20 px-2.5 py-2">
              <span className="flex items-center gap-2 text-[0.6rem] text-muted-foreground"><Zap className="h-3.5 w-3.5 text-primary" /> Tasks Run</span>
              <span className="font-heading text-sm text-foreground"><AnimatedNumber value={stats?.total_tasks ?? 0} /></span>
            </div>
            <div className="flex items-center justify-between rounded border border-border/50 bg-secondary/20 px-2.5 py-2">
              <span className="flex items-center gap-2 text-[0.6rem] text-muted-foreground"><Shield className="h-3.5 w-3.5 text-primary" /> Failures</span>
              <span className="font-heading text-sm text-foreground"><AnimatedNumber value={stats?.failed_tasks ?? 0} /></span>
            </div>
          </div>
        </HudPanel>
      </div>
    </div>
  )
}

/** The real reasoning chain -- STT -> each LLM backend in real fallback
 * order -> TTS -- rendered as a flow instead of a fabricated scripted trace. */
function ReasoningPipeline({ llm, loading }: { llm: ReturnType<typeof useLlmStatus>['data']; loading: boolean }) {
  if (loading && !llm) {
    return (
      <div className="flex items-center justify-center py-6 text-[0.6rem] text-muted-foreground">
        <RefreshCw className="mr-2 h-3.5 w-3.5 animate-spin" /> Reading live chain…
      </div>
    )
  }
  if (!llm) {
    return <p className="py-4 text-center text-[0.6rem] text-muted-foreground">Backend chain unavailable.</p>
  }
  const stages: { label: string; detail: string; icon: typeof Waves }[] = [
    { label: 'Speech-to-Text', detail: llm.stt.backend + (llm.stt.model ? ` · ${llm.stt.model}` : ''), icon: Waves },
    ...llm.backends.map((b, i) => ({
      label: i === 0 ? 'Primary Reasoning' : `Fallback ${i}`,
      detail: b.model ?? b.name,
      icon: Zap,
    })),
    { label: 'Voice Synthesis', detail: llm.tts.backend, icon: Eye },
  ]
  return (
    <div className="flex flex-wrap items-stretch gap-1.5">
      {stages.map((s, i) => (
        <div key={`${s.label}-${i}`} className="flex items-stretch gap-1.5">
          <div className="flex min-w-[130px] flex-1 flex-col items-center gap-1.5 rounded border border-border/50 bg-secondary/20 px-3 py-3 text-center">
            <s.icon className="h-4 w-4 text-primary" />
            <span className="font-heading text-[0.58rem] text-foreground">{s.label}</span>
            <span className="truncate text-[0.52rem] text-muted-foreground">{s.detail}</span>
          </div>
          {i < stages.length - 1 && (
            <span className="flex items-center text-primary/50" aria-hidden>→</span>
          )}
        </div>
      ))}
    </div>
  )
}

/* ═══════════════════════════════════════════════════════════════
   SYSTEM — Command layer with app launcher + live terminal + diagnostics
   ═══════════════════════════════════════════════════════════════ */
const APPS = [
  { icon: Terminal, label: 'Terminal', key: 'terminal' },
  { icon: Globe2, label: 'Browser', key: 'browser' },
  { icon: Folder, label: 'Files', key: 'files' },
  { icon: Code2, label: 'Editor', key: 'editor' },
  { icon: Music, label: 'Music', key: 'music' },
  { icon: Mail, label: 'Mail', key: 'mail' },
  { icon: Camera, label: 'Camera', key: 'camera' },
  { icon: Calculator, label: 'Calc', key: 'calculator' },
]

export function SystemPanel({ onLaunch, launched }: { onLaunch: (key: string) => void; launched: string | null }) {
  const tick = useTick(700)
  const health = useSystemHealth()
  const cpu = health.cpu ?? 0
  const mem = health.memory ?? 0
  const disk = health.disk ?? 0
  const net = health.networkPercent ?? 0
  const { stats: agentStats } = useAgentsBrief()
  const { data: llm } = useLlmStatus()
  const uptime = useSessionUptime()

  // Real derived log -- each line reflects the actual currently-polled
  // system values (see useSystemHealth), not a canned random-phrase pool.
  const [logs, setLogs] = useState<string[]>([])
  useEffect(() => {
    if (health.cpu == null) return
    const line =
      `[sys] cpu ${health.cpu.toFixed(0)}% · mem ${(health.memory ?? 0).toFixed(0)}% · ` +
      `disk ${(health.disk ?? 0).toFixed(0)}% · net ${(health.networkPercent ?? 0).toFixed(0)}%` +
      `  ·  ${new Date().toLocaleTimeString('en-GB')}`
    setLogs((l) => [...l.slice(-40), line])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [health.cpu, health.memory, health.disk, health.networkPercent])

  return (
    <div className="mx-auto grid max-w-[1680px] grid-cols-12 gap-4">
      {/* ── Hero: the app launcher leads (it's the one thing on this page
          you actually click), full-width, instead of being squeezed
          beside a column of gauges. ── */}
      <HudPanel hero title="Command Layer · Apps" className="col-span-12">
        <p className="mb-3 text-[0.6rem] leading-relaxed text-muted-foreground">
          Simulated OS bridge. Say <span className="text-primary">&ldquo;Nancy, open terminal&rdquo;</span> or tap an app.
        </p>
        <div className="grid grid-cols-4 gap-2 md:grid-cols-8">
          {APPS.map(({ icon: Icon, label, key }) => (
            <button key={key} type="button" onClick={() => onLaunch(key)}
              className={cn(
                'group flex flex-col items-center gap-1.5 rounded border p-3 transition-all',
                launched === key
                  ? 'border-primary bg-primary/15 shadow-[0_0_16px_var(--hud)]'
                  : 'border-border bg-secondary/20 hover:border-primary/60 hover:bg-secondary/40',
              )}>
              <Icon className={cn('h-6 w-6 transition-transform group-hover:scale-110',
                launched === key ? 'text-primary' : 'text-foreground')} />
              <span className="text-[0.5rem] text-muted-foreground">{label}</span>
            </button>
          ))}
        </div>
        {launched && (
          <div className="mt-3 rounded border border-primary/40 bg-background/60 p-2 font-mono text-[0.6rem] text-primary">
            {'>'} launching <span className="uppercase">{launched}</span>… process spawned [pid {Math.floor(1000 + Math.random() * 8000)}]
          </div>
        )}
      </HudPanel>

      {/* ── One console board instead of three separate boxed-stat panels:
          live metrics on the left, real service health as a status ladder
          on the right -- a single cohesive read instead of three
          disconnected tiles repeating the same "grid of boxes" pattern
          used everywhere else. ── */}
      <HudPanel title="Systems Board" className="col-span-12 lg:col-span-8">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-[1fr_auto]">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {[
              { icon: Cpu, label: 'CPU', v: `${cpu.toFixed(0)}%` },
              { icon: Database, label: 'MEM', v: `${mem.toFixed(0)}%` },
              { icon: Folder, label: 'DISK', v: `${disk.toFixed(0)}%` },
              { icon: Signal, label: 'NET', v: `${net.toFixed(0)}%` },
              { icon: Thermometer, label: 'TEMP', v: health.tempC != null ? `${health.tempC.toFixed(0)}° C` : 'N/A' },
              { icon: Activity, label: 'UPTIME', v: uptime },
            ].map(({ icon: Icon, label, v }) => (
              <div key={label} className="flex items-center gap-2 rounded border border-border/50 bg-secondary/20 p-2">
                <Icon className="h-4 w-4 text-primary" />
                <div>
                  <div className="font-heading text-[0.75rem] text-foreground">{v}</div>
                  <div className="text-[0.45rem] text-muted-foreground">{label}</div>
                </div>
              </div>
            ))}
          </div>
          <div className="flex flex-col items-center justify-center gap-1 border-t border-border/40 pt-3 sm:w-28 sm:border-l sm:border-t-0 sm:pl-4 sm:pt-0">
            <Bot className="h-5 w-5 text-primary" />
            <span className="font-heading text-lg text-foreground">{agentStats ? agentStats.agents_online : '…'}</span>
            <span className="text-[0.45rem] text-muted-foreground">agents online</span>
            <span className="mt-1 text-[0.5rem] text-muted-foreground">{agentStats ? `${agentStats.total_tasks} tasks run` : ''}</span>
          </div>
        </div>
      </HudPanel>

      <HudPanel title="Backend Health" accent="amber" className="col-span-12 lg:col-span-4">
        <ul className="space-y-1.5 text-[0.6rem]">
          {[
            ['Agent Service', agentStats ? `${agentStats.agents_online} online` : 'initialising', ShieldCheck, agentStats ? 'ok' : 'warn'],
            ['LLM Chain', llm ? `${llm.backends.length} backend${llm.backends.length !== 1 ? 's' : ''}` : '…', Zap, llm ? 'ok' : 'warn'],
            ['Speech-to-Text', llm?.stt.backend ?? '…', Waves, llm ? 'ok' : 'warn'],
            ['Voice Synthesis', llm?.tts.backend ?? '…', Eye, llm ? 'ok' : 'warn'],
          ].map(([k, v, Icon, tone]) => {
            const IconComp = Icon as React.ElementType
            return (
              <li key={k as string} className="flex items-center justify-between rounded border border-border/40 bg-secondary/10 px-2 py-1.5">
                <span className="flex items-center gap-2 text-muted-foreground">
                  <IconComp className={cn('h-3.5 w-3.5', tone === 'warn' ? 'text-accent' : 'text-primary')} />
                  {k as string}
                </span>
                <span className={cn(tone === 'warn' ? 'text-accent' : 'text-primary')}>{v as string}</span>
              </li>
            )
          })}
        </ul>
      </HudPanel>

      <HudPanel title="Live Kernel Log" className="col-span-12" right={<span className="text-primary text-[0.5rem]">tick {tick}</span>}>
        <div className="max-h-64 overflow-y-auto rounded border border-border/40 bg-background/50 p-2 font-mono text-[0.6rem] leading-relaxed">
          {logs.map((l, i) => (
            <div key={i} className="flex items-start gap-2 border-b border-border/20 py-0.5 text-muted-foreground last:border-none">
              <span className="text-primary/60">›</span>
              <span className="flex-1">{l}</span>
            </div>
          ))}
        </div>
      </HudPanel>
    </div>
  )
}
