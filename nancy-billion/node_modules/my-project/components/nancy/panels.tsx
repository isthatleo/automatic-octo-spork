'use client'

import { useEffect, useCallback, useMemo, useRef, useState } from 'react'
import { ArcReactor, HudPanel, RadialGauge, StatBar, AnimatedNumber } from './hud-bits'
import { GlobeView } from './globe-view'
import type { AgentInfo } from '@/lib/nancy/types'
import { listAgents, autoRouteAgent, summarizeResult, type AgentListResponse } from '@/lib/nancy/agent-client'
import { AgentTaskModal } from './agent-task-modal'
import { useSystemHealth, useTradeHistory, useLlmStatus } from '@/hooks/useSystemData'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
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
  Wifi,
  WifiOff,
  Zap,
  BarChart3,
  Search,
  Rss,
  Waves,
  Radio,
  Sparkles,
  Signal,
  ShieldCheck,
  Eye,
  Thermometer,
  Brain,
  FlaskConical,
  Scale,
  Server,
  Palette,
  X,
  Play,
  ClipboardList,
  GitBranch,
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
export function OverviewPanel() {
  const health = useSystemHealth()
  const cpu = health.cpu ?? 0
  const mem = health.memory ?? 0
  const net = health.networkPercent ?? 0
  const tick = useTick(1200)
  const { agents, stats } = useAgentsBrief()
  const uptime = useSessionUptime()
  const cores = useCpuCoreCount()
  const telemetryHistory = useMetricHistory({ cpu: health.cpu, mem: health.memory, net: health.networkPercent })
  const successPct = stats ? stats.success_rate * 100 : 100

  const fleetOnlinePct = stats && stats.agents_online + stats.agents_offline > 0
    ? (stats.agents_online / (stats.agents_online + stats.agents_offline)) * 100
    : 0

  const bigStats = [
    { label: 'Tasks Run', v: stats?.total_tasks ?? 0, icon: Zap, tone: 'primary' as const },
    { label: 'Agents',    v: stats?.agents_online ?? 0, icon: Radio, tone: 'accent' as const },
    { label: 'Failures',  v: stats?.failed_tasks ?? 0, icon: Shield, tone: 'ok' as const },
  ]

  return (
    <div className="mx-auto flex max-w-[1680px] flex-col gap-4">
      {/* ── One compact hero band (reactor + headline stats + vitals all in
          a single row) instead of two stacked hero blocks -- a genuine
          bento grid follows instead of a fixed two-column [content|rail]
          split, so this reads as its own composition rather than the same
          "column of cards" shape repeated with different content. ── */}
      <div className="relative overflow-hidden rounded-2xl border border-primary/25 bg-gradient-to-br from-card via-card to-primary/5 p-5">
        <div className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-primary/10 blur-3xl" aria-hidden />
        <div className="relative flex flex-wrap items-center gap-6">
          <div className="flex items-center gap-3">
            <ArcReactor size={100} />
            <div>
              <div className="font-display text-2xl tracking-tight text-primary">
                <AnimatedNumber value={successPct} decimals={1} /> <span className="text-sm text-muted-foreground">%</span>
              </div>
              <div className="text-[0.55rem] text-muted-foreground">fleet success</div>
            </div>
          </div>
          <div className="h-10 w-px bg-border/50" />
          <div className="flex items-center gap-1.5 text-[0.62rem] text-muted-foreground">
            <Activity className="h-3 w-3 text-primary animate-hud-breathe" /> Session {uptime}
          </div>
          <div className="ml-auto flex flex-wrap items-center gap-4 text-[0.68rem]">
            {bigStats.map((s) => (
              <span key={s.label} className="flex items-center gap-1.5">
                <s.icon className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="font-display text-base text-foreground"><AnimatedNumber value={s.v} /></span>
                <span className="text-muted-foreground">{s.label.toLowerCase()}</span>
              </span>
            ))}
          </div>
          <div className="flex w-full flex-col gap-2 sm:w-auto sm:min-w-[260px] sm:flex-1">
            <StatBar label="Neural CPU" value={cpu.toFixed(0)} unit="%" pct={cpu} />
            <StatBar label="Memory" value={mem.toFixed(0)} unit="%" pct={mem} amber />
          </div>
        </div>
      </div>

      {/* ── Bento grid: varied tile sizes instead of a uniform two-up or
          three-up repeat. Global Track spans two rows on the right; the
          telemetry chart leads wide on the left; activity closes full
          width at the bottom. ── */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-12">
        <div className="md:col-span-8">
          <HudPanel title="System Telemetry · Live" right={<span className="text-primary text-[0.5rem]">Δ {tick}</span>}>
            <SystemTelemetryChart history={telemetryHistory} height={208} />
            <div className="mt-3 flex items-center gap-3 text-[0.5rem] text-muted-foreground">
              <LegendDot color="var(--hud)" label="cpu" />
              <LegendDot color="var(--accent)" label="memory" />
              <LegendDot color="oklch(0.7 0.16 160)" label="uplink" />
            </div>
          </HudPanel>
        </div>

        <div className="flex flex-col gap-4 rounded-xl border border-border bg-card/60 p-4 md:col-span-4 md:row-span-2">
          <div>
            <div className="mb-2 flex items-center justify-between">
              <h2 className="font-heading text-[0.72rem] font-medium text-foreground/90">Global Track</h2>
              <span className="text-primary text-[0.6rem]">Active</span>
            </div>
            <WorldTracker tall />
          </div>
          <div className="h-px bg-border/60" />
          <div>
            <h2 className="mb-2 font-heading text-[0.72rem] font-medium text-foreground/90">Trading P/L · Recent</h2>
            <TradePLChart />
          </div>
        </div>

        <div className="md:col-span-4">
          <HudPanel title="Agent Domains" accent="violet">
            <AgentDomainChart agents={agents} />
          </HudPanel>
        </div>
        <div className="md:col-span-4">
          <HudPanel title="Fleet & System Vitals">
            <div className="flex flex-wrap items-center justify-around gap-2 py-1">
              <RadialGauge value={cpu} label="CPU" color="var(--hud)" size={72} />
              <RadialGauge value={fleetOnlinePct} label="Fleet" color="var(--accent)" size={72} />
              <RadialGauge value={health.disk ?? 0} label="Disk" color="var(--tertiary)" size={72} />
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2 text-center">
              {[
                { icon: Cpu, label: 'Cores', v: cores != null ? `${cores}` : '…' },
                { icon: Database, label: 'Mem', v: `${mem.toFixed(0)}%` },
                { icon: Thermometer, label: 'Temp', v: health.tempC != null ? `${health.tempC.toFixed(0)}°C` : 'N/A' },
              ].map(({ icon: Icon, label, v }) => (
                <div key={label} className="flex flex-col items-center gap-1 rounded border border-border/60 bg-secondary/30 py-2">
                  <Icon className="h-4 w-4 text-primary" />
                  <span className="font-heading text-xs text-foreground">{v}</span>
                  <span className="text-[0.45rem] text-muted-foreground">{label}</span>
                </div>
              ))}
            </div>
          </HudPanel>
        </div>

        {/* Activity as a real timeline (connecting rail + dots), full width
            across the bottom of the grid instead of tucked in a column. */}
        <div className="rounded-xl border border-border bg-card/60 p-4 md:col-span-12">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="flex items-center gap-2 font-heading text-[0.72rem] font-medium text-foreground/90">
              <span className="h-1.5 w-1.5 rounded-full bg-primary" /> Activity
            </h2>
            <span className="text-primary text-xs">Live</span>
          </div>
          <ActivityTimeline cpu={cpu} mem={mem} net={net} stats={stats} />
        </div>
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

/* ─── Live activity timeline -- real derived events, not scripted flavor
   text. Appends a real line whenever the actual polled system/fleet values
   change, instead of cycling through fabricated "SIGINT"/"orbital satellite"
   copy that never corresponded to anything the backend does. Rendered as a
   connecting-rail timeline instead of a bordered list, distinct from the
   panel/box vocabulary used everywhere else on the page. ─── */
function ActivityTimeline({
  cpu, mem, net, stats,
}: {
  cpu: number
  mem: number
  net: number
  stats: AgentListResponse['stats'] | null
}) {
  const [rows, setRows] = useState<{ id: number; tag: string; text: string; tone: 'ok' | 'warn'; at: number }[]>([])
  const seq = useRef(0)
  const prevTasks = useRef<number | null>(null)

  useEffect(() => {
    const id = seq.current++
    setRows((r) => [
      { id, tag: 'sys', text: `cpu ${cpu.toFixed(0)}% · mem ${mem.toFixed(0)}% · net ${net.toFixed(0)}%`, tone: 'ok' as const, at: Date.now() },
      ...r,
    ].slice(0, 6))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [Math.round(cpu / 3), Math.round(mem / 3), Math.round(net / 5)])

  useEffect(() => {
    if (!stats) return
    if (prevTasks.current !== null && stats.total_tasks === prevTasks.current) return
    prevTasks.current = stats.total_tasks
    const id = seq.current++
    setRows((r) => [
      { id, tag: 'fleet', text: `${stats.agents_online} agents online · ${stats.total_tasks} tasks · ${(stats.success_rate * 100).toFixed(0)}% success`, tone: stats.failed_tasks > 0 ? ('warn' as const) : ('ok' as const), at: Date.now() },
      ...r,
    ].slice(0, 6))
  }, [stats])

  if (rows.length === 0) {
    return <p className="text-xs text-muted-foreground">Waiting for the first real reading…</p>
  }

  return (
    <ol className="relative flex flex-col gap-4 pl-4">
      <div className="absolute bottom-1 left-[3px] top-1 w-px bg-border" aria-hidden />
      {rows.map((row, i) => (
        <li key={row.id} className="relative flex items-start gap-3" style={{ opacity: 1 - i * 0.12 }}>
          <span
            className={cn(
              'absolute -left-4 top-1 h-2 w-2 shrink-0 rounded-full ring-4 ring-card',
              row.tone === 'warn' ? 'bg-destructive' : 'bg-primary',
            )}
          />
          <div className="flex min-w-0 flex-1 items-center justify-between gap-3">
            <div className="min-w-0">
              <span className="mr-2 font-mono text-[0.55rem] text-muted-foreground">{row.tag}</span>
              <span className="text-xs text-foreground">{row.text}</span>
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

/* ─── Real per-domain agent distribution donut (grouped from the live
   fleet roster — replaces the previous hardcoded NAM/EMEA/APAC/LATAM split
   that had no backing data at all) ─── */
const DOMAIN_CHART_COLORS = [
  'var(--hud)', 'var(--accent)', 'oklch(0.7 0.16 160)', 'oklch(0.65 0.18 25)',
  'oklch(0.75 0.14 90)', 'oklch(0.6 0.15 290)', 'oklch(0.7 0.12 340)', 'oklch(0.55 0.1 220)',
]
function AgentDomainChart({ agents }: { agents: AgentInfo[] }) {
  const data = useMemo(() => {
    const counts = new Map<string, number>()
    for (const a of agents) counts.set(a.domain, (counts.get(a.domain) ?? 0) + 1)
    return Array.from(counts, ([domain, count]) => ({ domain, count }))
      .sort((a, b) => b.count - a.count)
  }, [agents])

  if (data.length === 0) {
    return (
      <div className="flex h-32 items-center justify-center text-[0.6rem] text-muted-foreground">
        Awaiting fleet roster…
      </div>
    )
  }

  return (
    <div className="flex items-center gap-4">
      <div className="h-32 w-32 shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey="count" nameKey="domain" innerRadius={38} outerRadius={58} paddingAngle={2} isAnimationActive={false}>
              {data.map((d, i) => (
                <Cell key={d.domain} fill={DOMAIN_CHART_COLORS[i % DOMAIN_CHART_COLORS.length]} stroke="none" />
              ))}
            </Pie>
            <Tooltip content={<HudTooltip />} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <ul className="flex-1 flex flex-col gap-1.5 text-[0.6rem]">
        {data.slice(0, 6).map((d, i) => {
          const color = DOMAIN_CHART_COLORS[i % DOMAIN_CHART_COLORS.length]
          return (
            <li key={d.domain} className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 min-w-0">
                <span className="h-2 w-2 shrink-0 rounded-sm" style={{ background: color, boxShadow: `0 0 4px ${color}` }} />
                <span className="truncate font-heading text-muted-foreground">{d.domain}</span>
              </span>
              <span className="shrink-0 text-foreground">{d.count}</span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

/* ─── Mini live globe (reuses the real three.js/globe.gl instance from
   globe-view.tsx instead of a flat SVG placeholder — same asset the Recon
   map uses, just ambient-rotating with no active target). Only mounts
   while the Overview tab is actually visible, since OverviewPanel itself
   is conditionally rendered by page.tsx. ─── */
function WorldTracker({ tall = false }: { tall?: boolean }) {
  return (
    <div className={cn(
      'relative w-full overflow-hidden rounded border border-border/50 bg-background/40',
      tall ? 'aspect-[5/4]' : 'aspect-[3/2]',
    )}>
      <GlobeView place={null} active={false} />
    </div>
  )
}

/* ─── Real recent trade P/L (replaces the fake audio-spectrum bars —
   no mic/audio signal was ever actually measured here) ─── */
function TradePLChart() {
  const { data: trades, loading } = useTradeHistory(12)
  const bars = useMemo(
    () => trades
      .filter((t) => typeof t.profit_loss === 'number')
      .map((t, i) => ({ label: t.pair ?? `#${i}`, pl: t.profit_loss as number })),
    [trades],
  )

  if (loading && bars.length === 0) {
    return <div className="flex h-24 items-center justify-center text-[0.6rem] text-muted-foreground">Loading trade history…</div>
  }
  if (bars.length === 0) {
    return <div className="flex h-24 items-center justify-center text-[0.6rem] text-muted-foreground">No closed trades yet.</div>
  }
  return (
    <div className="h-24 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={bars} margin={{ top: 4, right: 4, bottom: 0, left: -28 }}>
          <XAxis dataKey="label" hide />
          <YAxis width={32} tick={{ fontSize: 9, fill: 'var(--muted-foreground)' }} />
          <Tooltip content={<HudTooltip unit=" pips" />} />
          <Bar dataKey="pl" name="P/L" isAnimationActive={false}>
            {bars.map((b, i) => (
              <Cell key={i} fill={b.pl >= 0 ? 'var(--hud)' : 'oklch(0.65 0.2 25)'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/* ─── Real per-agent load bars (replaces the fake audio-spectrum bars in
   the Agents tab's "Fleet Activity" card — uses the same agent list the
   fleet grid already fetched, no extra request) ─── */
function AgentLoadChart({ agents }: { agents: AgentInfo[] }) {
  const bars = useMemo(
    () => agents
      .filter((a) => a.status !== 'offline')
      .sort((a, b) => b.load - a.load)
      .slice(0, 10)
      .map((a) => ({ label: a.name, load: Math.min(100, a.load) })),
    [agents],
  )
  if (bars.length === 0) {
    return <div className="flex h-24 items-center justify-center text-[0.6rem] text-muted-foreground">No agents online.</div>
  }
  return (
    <div className="h-24 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={bars} margin={{ top: 4, right: 4, bottom: 0, left: -28 }}>
          <XAxis dataKey="label" hide />
          <YAxis domain={[0, 100]} width={28} tick={{ fontSize: 9, fill: 'var(--muted-foreground)' }} />
          <Tooltip content={<HudTooltip unit="%" />} />
          <Bar dataKey="load" name="load" fill="var(--hud)" isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
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
   AGENTS — Fleet Console: a grouped roster + persistent detail rail,
   not another grid of equal-sized boxes. Categories are a display-only
   grouping decision (the backend has no category field) built from the
   29 real domains actually returned by /agents/list.
   ═══════════════════════════════════════════════════════════════ */
const STATUS_DOT: Record<string, string> = {
  online: 'bg-primary',
  idle: 'bg-muted-foreground',
  training: 'bg-accent',
  offline: 'bg-destructive/60',
  error: 'bg-destructive',
}
const STATUS_COLOR: Record<string, string> = {
  online: 'text-primary',
  idle: 'text-muted-foreground',
  offline: 'text-destructive',
  training: 'text-accent',
  error: 'text-destructive',
}
const DOMAIN_ICON: Record<string, React.ElementType> = {
  'artificial-consciousness': Brain,
  'quantum-reasoning': Zap,
  'quantum-computing': Cpu,
  'embodied-cognition': Bot,
  'neural-interface': Activity,
  'self-improvement': RefreshCw,
  'temporal-prediction': BarChart3,
  'data-science': Database,
  'research': Search,
  'market-research': BarChart3,
  'business-intelligence': BarChart3,
  'bioinformatics': FlaskConical,
  'astrophysics': Globe2,
  'healthcare-analytics': FlaskConical,
  'operations-research': Server,
  'security': Shield,
  'ethics': Scale,
  'legal-compliance': Scale,
  'qa-testing': ShieldCheck,
  'devops': Terminal,
  'system-monitoring': Signal,
  'file-management': Folder,
  'swarm-coordinator': Rss,
  'communication': Radio,
  'environmental-control': Thermometer,
  'holographic-display': Eye,
  'nanotechnology': Sparkles,
  'crypto-trading': BarChart3,
  'creative-design': Palette,
  'planning': ClipboardList,
  'dispatcher': GitBranch,
  'explore': Search,
  'general-purpose': Bot,
  'claude': Sparkles,
  'claude-code-guide': Code2,
  'statusline-setup': Terminal,
}
interface AgentCategory { label: string; icon: React.ElementType; domains: string[]; color: string }
const AGENT_CATEGORIES: AgentCategory[] = [
  { label: 'Cognition & Reasoning', icon: Brain, color: 'oklch(0.72 0.15 42)', domains: ['artificial-consciousness', 'quantum-reasoning', 'quantum-computing', 'embodied-cognition', 'neural-interface', 'self-improvement', 'temporal-prediction'] },
  { label: 'Data & Research', icon: FlaskConical, color: 'oklch(0.68 0.13 290)', domains: ['data-science', 'research', 'market-research', 'business-intelligence', 'bioinformatics', 'astrophysics', 'healthcare-analytics', 'operations-research'] },
  { label: 'Security & Governance', icon: Scale, color: 'oklch(0.78 0.13 88)', domains: ['security', 'ethics', 'legal-compliance', 'qa-testing'] },
  { label: 'Infrastructure & Ops', icon: Server, color: 'oklch(0.72 0.14 200)', domains: ['devops', 'system-monitoring', 'file-management', 'swarm-coordinator', 'communication'] },
  { label: 'Physical & Interface', icon: Cpu, color: 'oklch(0.7 0.14 150)', domains: ['environmental-control', 'holographic-display', 'nanotechnology'] },
  { label: 'Business & Creative', icon: Palette, color: 'oklch(0.68 0.15 20)', domains: ['crypto-trading', 'creative-design'] },
  { label: 'Meta & Orchestration', icon: Sparkles, color: 'oklch(0.7 0.14 250)', domains: ['planning', 'dispatcher', 'explore', 'general-purpose', 'claude', 'claude-code-guide', 'statusline-setup'] },
]
function categoryFor(domain: string): string {
  return AGENT_CATEGORIES.find((c) => c.domains.includes(domain))?.label ?? 'Other'
}
function colorFor(domain: string): string {
  return AGENT_CATEGORIES.find((c) => c.domains.includes(domain))?.color ?? 'var(--hud)'
}

function AgentDetailRail({
  agent, fallbackAgents, autoQuery, setAutoQuery, handleAutoRun, autoRunning, autoResult, onRunTask,
}: {
  agent: AgentInfo | null
  fallbackAgents: AgentInfo[]
  autoQuery: string
  setAutoQuery: (v: string) => void
  handleAutoRun: () => void
  autoRunning: boolean
  autoResult: string | null
  onRunTask: (agent: AgentInfo) => void
}) {
  if (!agent) {
    return (
      <div className="flex flex-col gap-3 font-mono">
        <div className="border border-border/40 bg-background/40 p-4">
          <h3 className="mb-1 text-[0.68rem] text-foreground">$ auto-route</h3>
          <p className="mb-2 text-[0.6rem] text-muted-foreground">Ask anything — Billion picks the right specialist.</p>
          <div className="flex gap-1.5">
            <input
              value={autoQuery}
              onChange={(e) => setAutoQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAutoRun()}
              placeholder="e.g. analyse BTC volatility…"
              className="flex-1 border border-border/60 bg-background/60 px-2 py-1.5 text-[0.65rem] text-foreground outline-none focus:border-primary/60"
            />
            <button type="button" onClick={handleAutoRun} disabled={autoRunning}
              className="border border-tertiary/60 bg-tertiary/15 px-2.5 py-1.5 text-tertiary hover:bg-tertiary/25 disabled:opacity-50">
              {autoRunning ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Zap className="h-3 w-3" />}
            </button>
          </div>
          {autoResult && (
            <p className="mt-2 border border-border/50 bg-background/40 px-2 py-1.5 text-[0.55rem] text-muted-foreground">{autoResult}</p>
          )}
        </div>
        <div className="border border-border/40 bg-background/40 p-4">
          <h3 className="mb-2 text-[0.68rem] text-foreground">$ fleet-load --chart</h3>
          <AgentLoadChart agents={fallbackAgents} />
        </div>
        <p className="px-1 text-[0.6rem] text-muted-foreground">// select a row for full detail and to run a task</p>
      </div>
    )
  }
  const Icon = DOMAIN_ICON[agent.domain] ?? Bot
  const detailColor = colorFor(agent.domain)
  return (
    <div className="flex flex-col gap-3 border-2 bg-background/50 p-4 font-mono" style={{ borderColor: detailColor }}>
      <div className="flex items-center gap-3">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full" style={{ background: `color-mix(in oklch, ${detailColor} 20%, var(--background))` }}>
          <Icon className="h-5 w-5" style={{ color: detailColor }} />
        </span>
        <div className="min-w-0">
          <div className="truncate text-sm text-foreground">{agent.name}</div>
          <div className="truncate text-[0.6rem] text-muted-foreground">{agent.domain} · {categoryFor(agent.domain)}</div>
        </div>
      </div>
      <p className="text-[0.65rem] leading-relaxed text-muted-foreground">
        {agent.description || `${agent.role || 'Specialist agent'} handling ${agent.domain.replace(/-/g, ' ')} tasks.`}
      </p>
      <div className="grid grid-cols-2 gap-2 text-center">
        <div className="border border-border/50 bg-secondary/20 py-2">
          <div className="text-base text-foreground">{agent.total_tasks}</div>
          <div className="text-[0.5rem] text-muted-foreground">tasks run</div>
        </div>
        <div className="border border-border/50 bg-secondary/20 py-2">
          <div className="text-base text-accent">{(agent.confidence * 100).toFixed(0)}%</div>
          <div className="text-[0.5rem] text-muted-foreground">confidence</div>
        </div>
      </div>
      {(agent.mode && agent.mode !== 'production') || agent.hardware_connected === false ? (
        <div className="flex flex-wrap gap-1">
          {agent.mode && agent.mode !== 'production' && (
            <span className="border border-accent/40 bg-accent/10 px-1.5 py-0.5 text-[0.5rem] text-accent">{agent.mode.replace(/_/g, ' ')}</span>
          )}
          {agent.hardware_connected === false && (
            <span className="border border-accent/40 bg-accent/10 px-1.5 py-0.5 text-[0.5rem] text-accent">no hardware attached</span>
          )}
        </div>
      ) : null}
      {agent.specializations.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {agent.specializations.map((s) => (
            <span key={s} className="border border-border/40 bg-secondary/50 px-2 py-0.5 text-[0.5rem] text-muted-foreground">{s}</span>
          ))}
        </div>
      )}
      <button
        type="button"
        onClick={() => onRunTask(agent)}
        disabled={agent.status === 'offline'}
        className="mt-1 flex items-center justify-center gap-1.5 border border-primary bg-primary/15 py-2 text-xs text-primary transition-colors hover:bg-primary/25 disabled:cursor-not-allowed disabled:opacity-40"
      >
        <Play className="h-3.5 w-3.5" /> Run task
      </button>
    </div>
  )
}

export function AgentsPanel({ onAgentSelect }: { onAgentSelect?: (agentId: string) => void } = {}) {
  const [data, setData] = useState<AgentListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedAgentKey, setSelectedAgentKey] = useState<string | null>(null)
  const [taskAgent, setTaskAgent] = useState<AgentInfo | null>(null)
  const [filter, setFilter] = useState('')
  const [autoQuery, setAutoQuery] = useState('')
  const [autoRunning, setAutoRunning] = useState(false)
  const [autoResult, setAutoResult] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date())
  const [activeCategory, setActiveCategory] = useState<string | null>(null)

  const fetchAgents = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const res = await listAgents()
      setData(res); setLastRefresh(new Date())
    } catch (e) { setError(String(e)) } finally { setLoading(false) }
  }, [])

  useEffect(() => {
    fetchAgents()
    const t = setInterval(fetchAgents, 30_000)
    return () => clearInterval(t)
  }, [fetchAgents])

  const handleAutoRun = useCallback(async () => {
    if (!autoQuery.trim()) return
    setAutoRunning(true); setAutoResult(null)
    try {
      const res = await autoRouteAgent(autoQuery)
      const route = res.routed_to ?? res.agent_key ?? '?'
      const msg = res.success
        ? `Routed to ${route} — ${summarizeResult(res)}`
        : `Error (${route}): ${res.error}`
      setAutoResult(msg)
    } finally { setAutoRunning(false); fetchAgents() }
  }, [autoQuery, fetchAgents])

  const filteredAgents = (data?.agents ?? []).filter((a) =>
    !filter ||
    a.name.toLowerCase().includes(filter.toLowerCase()) ||
    a.domain.toLowerCase().includes(filter.toLowerCase()) ||
    a.specializations.some((s) => s.toLowerCase().includes(filter.toLowerCase())),
  )

  const grouped = useMemo(() => {
    const map = new Map<string, AgentInfo[]>()
    for (const a of filteredAgents) {
      const cat = categoryFor(a.domain)
      if (!map.has(cat)) map.set(cat, [])
      map.get(cat)!.push(a)
    }
    return map
  }, [filteredAgents])

  const visibleAgents = activeCategory ? (grouped.get(activeCategory) ?? []) : filteredAgents

  const selectAgent = (agent: AgentInfo) => {
    setSelectedAgentKey((prev) => (prev === agent.key ? null : agent.key))
    onAgentSelect?.(agent.key)
  }

  // Look up the live object by key on every render instead of holding a
  // stale snapshot — so a refresh right after running a task (or the 30s
  // poll) updates the detail rail's stats instead of freezing them at
  // whatever they were when the row was clicked.
  const selectedAgent = selectedAgentKey ? (data?.agents.find((a) => a.key === selectedAgentKey) ?? null) : null

  const sortedAgents = useMemo(
    () => [...visibleAgents].sort((a, b) => {
      if (a.status === 'online' && b.status !== 'online') return -1
      if (b.status === 'online' && a.status !== 'online') return 1
      return b.load - a.load
    }),
    [visibleAgents],
  )

  return (
    <div className="mx-auto flex max-w-[1680px] flex-col gap-3 font-mono">
      {/* terminal-style title bar -- sharp corners, a coloured status strip
          instead of a rounded card, deliberately not the soft-panel idiom
          used everywhere else in this dashboard */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b-2 border-primary/40 bg-background/60 px-4 py-2.5">
        <div className="flex items-center gap-3">
          <span className={cn('h-2 w-2 rounded-full', error ? 'bg-destructive' : 'bg-primary animate-hud-pulse')} aria-hidden />
          <span className="text-sm tracking-tight text-foreground">fleet@billion:~$ status</span>
          <span className="text-[0.62rem] text-muted-foreground">
            {error ? 'connection lost' : `${data?.total ?? '…'} agents · synced ${lastRefresh.toLocaleTimeString('en-GB')}`}
          </span>
        </div>
        <div className="flex items-center gap-4 text-[0.68rem] text-muted-foreground">
          <span className="text-primary">{data?.stats.agents_online ?? '…'}</span> online
          <span className="text-foreground">{data?.stats.total_tasks ?? '…'}</span> tasks
          <span className="text-accent">{data ? `${(data.stats.success_rate * 100).toFixed(0)}%` : '…'}</span> success
          <button type="button" onClick={fetchAgents} disabled={loading} className="text-muted-foreground hover:text-primary">
            <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_340px]">
        {/* LEFT: a real table -- rows and columns, not cards -- with
            category filters as inline tabs above it */}
        <div className="flex flex-col gap-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative flex-1 min-w-[180px]">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <input
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="grep agents…"
                className="w-full border border-border/60 bg-background/60 py-1.5 pl-8 pr-3 text-[0.68rem] text-foreground outline-none focus:border-primary/60"
              />
            </div>
            <button
              type="button"
              onClick={() => setActiveCategory(null)}
              className={cn(
                'border px-2 py-1 text-[0.6rem] transition-colors',
                activeCategory === null ? 'border-primary text-primary' : 'border-border/40 text-muted-foreground hover:border-primary/40',
              )}
            >
              all[{filteredAgents.length}]
            </button>
            {AGENT_CATEGORIES.map((cat) => {
              const items = grouped.get(cat.label) ?? []
              if (items.length === 0) return null
              return (
                <button
                  key={cat.label}
                  type="button"
                  onClick={() => setActiveCategory((c) => (c === cat.label ? null : cat.label))}
                  className={cn(
                    'border px-2 py-1 text-[0.6rem] transition-colors',
                    activeCategory === cat.label ? 'border-primary text-primary' : 'border-border/40 text-muted-foreground hover:border-primary/40',
                  )}
                  style={activeCategory === cat.label ? { borderColor: cat.color, color: cat.color } : undefined}
                >
                  {cat.label.split(' ')[0].toLowerCase()}[{items.length}]
                </button>
              )
            })}
          </div>

          {loading && !data ? (
            <div className="flex items-center justify-center border border-border/40 bg-background/40 py-10 text-[0.62rem] text-muted-foreground">
              <RefreshCw className="mr-2 h-3.5 w-3.5 animate-spin" /> loading fleet…
            </div>
          ) : error && !data ? (
            <div className="border border-border/40 bg-background/40 py-6 text-center text-[0.62rem] text-destructive">
              {error}<br />
              <button onClick={fetchAgents} className="mt-2 text-primary underline">retry</button>
            </div>
          ) : sortedAgents.length === 0 ? (
            <div className="border border-border/40 bg-background/40 py-6 text-center text-[0.62rem] text-muted-foreground">no matches</div>
          ) : (
            <div className="overflow-x-auto border border-border/40 bg-background/40">
              <table className="w-full min-w-[560px] border-collapse text-[0.68rem]">
                <thead>
                  <tr className="border-b border-border/50 text-left text-[0.58rem] text-muted-foreground">
                    <th className="px-3 py-2 font-normal">status</th>
                    <th className="px-3 py-2 font-normal">agent</th>
                    <th className="hidden px-3 py-2 font-normal sm:table-cell">category</th>
                    <th className="px-3 py-2 font-normal">load</th>
                    <th className="hidden px-3 py-2 font-normal md:table-cell">tasks</th>
                    <th className="px-3 py-2 font-normal text-right">action</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedAgents.map((agent) => {
                    const Icon = DOMAIN_ICON[agent.domain] ?? Bot
                    const isOnline = agent.status === 'online'
                    const color = colorFor(agent.domain)
                    const selected = selectedAgentKey === agent.key
                    return (
                      <tr
                        key={agent.key}
                        onClick={() => agent.status !== 'offline' && selectAgent(agent)}
                        className={cn(
                          'border-b border-border/20 transition-colors last:border-none',
                          agent.status === 'offline' ? 'opacity-40' : 'cursor-pointer hover:bg-secondary/30',
                          selected && 'bg-primary/10',
                        )}
                      >
                        <td className="px-3 py-2">
                          <span
                            className={cn('inline-flex items-center gap-1 text-[0.58rem]', STATUS_COLOR[agent.status] ?? 'text-muted-foreground')}
                          >
                            <span className={cn('h-1.5 w-1.5 rounded-full', isOnline && 'animate-hud-pulse', STATUS_DOT[agent.status] ?? 'bg-muted-foreground')} />
                            [{agent.status}]
                          </span>
                        </td>
                        <td className="px-3 py-2">
                          <span className="flex items-center gap-1.5 text-foreground">
                            <Icon className="h-3.5 w-3.5 shrink-0" style={{ color }} />
                            <span className="truncate">{agent.name}</span>
                          </span>
                        </td>
                        <td className="hidden px-3 py-2 text-muted-foreground sm:table-cell">{agent.domain}</td>
                        <td className="px-3 py-2">
                          <div className="flex items-center gap-1.5">
                            <div className="h-1 w-14 overflow-hidden bg-secondary/60">
                              <div className="h-full" style={{ width: `${Math.min(100, agent.load)}%`, background: isOnline ? color : '#555' }} />
                            </div>
                            <span className="text-[0.58rem] text-muted-foreground">{agent.load}%</span>
                          </div>
                        </td>
                        <td className="hidden px-3 py-2 text-muted-foreground md:table-cell">{agent.total_tasks}</td>
                        <td className="px-3 py-2 text-right">
                          <button
                            type="button"
                            onClick={(e) => { e.stopPropagation(); setTaskAgent(agent) }}
                            disabled={agent.status === 'offline'}
                            className="inline-flex items-center gap-1 border border-primary/50 px-2 py-0.5 text-[0.58rem] text-primary transition-colors hover:bg-primary/15 disabled:cursor-not-allowed disabled:opacity-30"
                          >
                            <Play className="h-2.5 w-2.5" /> run
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* RIGHT: persistent detail pane -- selection updates it in place,
            no modal takeover for just looking at an agent. */}
        <div className="lg:sticky lg:top-4 lg:self-start">
          <AgentDetailRail
            agent={selectedAgent}
            fallbackAgents={data?.agents ?? []}
            autoQuery={autoQuery}
            setAutoQuery={setAutoQuery}
            handleAutoRun={handleAutoRun}
            autoRunning={autoRunning}
            autoResult={autoResult}
            onRunTask={setTaskAgent}
          />
        </div>
      </div>

      {taskAgent && <AgentTaskModal agent={taskAgent} onClose={() => { setTaskAgent(null); fetchAgents() }} />}
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
