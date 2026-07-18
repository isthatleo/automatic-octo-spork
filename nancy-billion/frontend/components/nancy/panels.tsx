'use client'

import { useEffect, useCallback, useMemo, useRef, useState } from 'react'
import { ArcReactor, HudPanel, RadialGauge, StatBar, AnimatedNumber } from './hud-bits'
import { GlobeView } from './globe-view'
import type { AgentInfo } from '@/lib/nancy/types'
import { listAgents, autoRouteAgent, type AgentListResponse } from '@/lib/nancy/agent-client'
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
  ChevronDown,
  ChevronRight,
  X,
  Play,
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
      {/* slim briefing strip -- same language as the Fleet Console header,
          so pages read as one product instead of one-off box grids */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card/60 px-4 py-3">
        <div className="flex items-center gap-3">
          <span className="font-display text-xl text-foreground">Mission Briefing</span>
          <span className="flex items-center gap-1.5 text-[0.62rem] text-muted-foreground">
            <Activity className="h-3 w-3 text-primary animate-hud-breathe" /> Session {uptime}
          </span>
        </div>
        <div className="flex items-center gap-4 text-[0.68rem]">
          {bigStats.map((s) => (
            <span key={s.label} className="flex items-center gap-1.5">
              <s.icon className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="font-display text-base text-foreground"><AnimatedNumber value={s.v} /></span>
              <span className="text-muted-foreground">{s.label.toLowerCase()}</span>
            </span>
          ))}
        </div>
      </div>

      {/* spotlight core -- a deliberately distinct card (gradient ring
          border, asymmetric split), not another hairline HudPanel box */}
      <div className="relative overflow-hidden rounded-2xl border border-primary/25 bg-gradient-to-br from-card via-card to-primary/5 p-5">
        <div className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-primary/10 blur-3xl" aria-hidden />
        <div className="relative grid grid-cols-1 gap-6 md:grid-cols-[auto_1fr]">
          <div className="flex flex-col items-center justify-center gap-2">
            <ArcReactor size={168} />
            <div className="text-center">
              <div className="font-display text-2xl tracking-tight text-primary">
                <AnimatedNumber value={successPct} decimals={1} /> <span className="text-sm text-muted-foreground">%</span>
              </div>
              <div className="text-[0.55rem] text-muted-foreground">fleet success</div>
            </div>
          </div>
          <div className="flex flex-col justify-center gap-3">
            <StatBar label="Neural CPU" value={cpu.toFixed(0)} unit="%" pct={cpu} />
            <StatBar label="Memory" value={mem.toFixed(0)} unit="%" pct={mem} amber />
            <StatBar label="Uplink" value={net.toFixed(0)} unit="%" pct={net} />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        {/* LEFT column */}
        <div className="flex flex-col gap-4">
          <HudPanel title="System Telemetry · Live" right={<span className="text-primary text-[0.5rem]">Δ {tick}</span>}>
            <SystemTelemetryChart history={telemetryHistory} height={208} />
            <div className="mt-3 flex items-center gap-3 text-[0.5rem] text-muted-foreground">
              <LegendDot color="var(--hud)" label="cpu" />
              <LegendDot color="var(--accent)" label="memory" />
              <LegendDot color="oklch(0.7 0.16 160)" label="uplink" />
            </div>
          </HudPanel>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <HudPanel title="Agent Domains" accent="violet">
              <AgentDomainChart agents={agents} />
            </HudPanel>
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

          {/* Activity as a real timeline (connecting rail + dots), not a
              bordered box of list rows -- visually distinct from every
              other panel on this page. */}
          <div className="rounded-xl border border-border bg-card/60 p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="flex items-center gap-2 font-heading text-[0.72rem] font-medium text-foreground/90">
                <span className="h-1.5 w-1.5 rounded-full bg-primary" /> Activity
              </h2>
              <span className="text-primary text-xs">Live</span>
            </div>
            <ActivityTimeline cpu={cpu} mem={mem} net={net} stats={stats} />
          </div>
        </div>

        {/* RIGHT rail -- one continuous card with internal dividers instead
            of three stacked, identical boxes. */}
        <div className="flex flex-col gap-4 rounded-xl border border-border bg-card/60 p-4 xl:sticky xl:top-4 xl:self-start">
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
    <div className="mx-auto grid max-w-[1680px] grid-cols-12 gap-4">
      {/* ── Hero row: reactor and vitals sit as a matched pair, not a lone
          reactor beside a stacked column of unrelated cards. ── */}
      <HudPanel hero title="Neural Substrate" right={<span className="text-primary">STABLE</span>} className="col-span-12 lg:col-span-5">
        <div className="flex flex-col items-center gap-4 py-2">
          <ArcReactor size={240} />
          <div className="grid w-full grid-cols-2 gap-2">
            <div className="rounded border border-border/50 bg-secondary/20 p-2 text-center">
              <div className="font-display text-xl text-primary">{llm?.backends.length ?? '–'}</div>
              <div className="text-[0.5rem] text-muted-foreground">LLM Backends</div>
            </div>
            <div className="rounded border border-border/50 bg-secondary/20 p-2 text-center">
              <div className="font-display text-xl text-accent">
                <AnimatedNumber value={stats?.agents_online ?? 0} />
              </div>
              <div className="text-[0.5rem] text-muted-foreground">Agents Online</div>
            </div>
          </div>
        </div>
      </HudPanel>

      <HudPanel title="System Vitals" className="col-span-12 lg:col-span-7">
        <div className="grid h-full grid-cols-2 place-items-center gap-3 py-2 sm:grid-cols-4">
          <RadialGauge value={health.cpu ?? 0} label="CPU Load" color="var(--hud)" size={110} />
          <RadialGauge value={health.memory ?? 0} label="Memory" color="var(--accent)" size={110} />
          <RadialGauge value={fleetOnlinePct} label="Fleet Online" color="var(--hud)" size={110} />
          <RadialGauge value={(stats?.success_rate ?? 0) * 100} label="Success Rate" color="var(--tertiary)" size={110} />
        </div>
      </HudPanel>

      {/* ── Second row: model stack and reasoning pipeline sit side by
          side instead of stacked in a single narrow column. ── */}
      <HudPanel title="Model Stack" accent="amber" className="col-span-12 lg:col-span-7">
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

      <HudPanel title="Reasoning Pipeline" accent="violet" className="col-span-12 lg:col-span-5">
        <ThoughtTrace />
      </HudPanel>
    </div>
  )
}

function ThoughtTrace() {
  const items = [
    'Parsed utterance → intent: locate',
    'Geocoded target → coords resolved',
    'Solar altitude computed → -4.2°',
    'Basemap decision → night · tinted satellite',
    'Fly-to camera path plotted → 2.6s',
    'Emit spoken response → cadence primed',
  ]
  const [n, setN] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setN((x) => (x + 1) % (items.length + 1)), 900)
    return () => clearInterval(t)
  }, [items.length])
  return (
    <ol className="flex flex-col gap-1 font-mono text-[0.6rem]">
      {items.map((line, i) => (
        <li key={i} className={cn(
          'flex items-start gap-2 border-l-2 pl-2 transition-colors',
          i < n ? 'border-primary text-foreground' : 'border-border/40 text-muted-foreground',
        )}>
          <span className={cn('mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full', i < n ? 'bg-primary shadow-[0_0_6px_var(--hud)]' : 'bg-muted')} />
          {line}
        </li>
      ))}
    </ol>
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
}
interface AgentCategory { label: string; icon: React.ElementType; domains: string[]; color: string }
const AGENT_CATEGORIES: AgentCategory[] = [
  { label: 'Cognition & Reasoning', icon: Brain, color: 'oklch(0.72 0.15 42)', domains: ['artificial-consciousness', 'quantum-reasoning', 'quantum-computing', 'embodied-cognition', 'neural-interface', 'self-improvement', 'temporal-prediction'] },
  { label: 'Data & Research', icon: FlaskConical, color: 'oklch(0.68 0.13 290)', domains: ['data-science', 'research', 'market-research', 'business-intelligence', 'bioinformatics', 'astrophysics', 'healthcare-analytics', 'operations-research'] },
  { label: 'Security & Governance', icon: Scale, color: 'oklch(0.78 0.13 88)', domains: ['security', 'ethics', 'legal-compliance', 'qa-testing'] },
  { label: 'Infrastructure & Ops', icon: Server, color: 'oklch(0.72 0.14 200)', domains: ['devops', 'system-monitoring', 'file-management', 'swarm-coordinator', 'communication'] },
  { label: 'Physical & Interface', icon: Cpu, color: 'oklch(0.7 0.14 150)', domains: ['environmental-control', 'holographic-display', 'nanotechnology'] },
  { label: 'Business & Creative', icon: Palette, color: 'oklch(0.68 0.15 20)', domains: ['crypto-trading', 'creative-design'] },
]
function categoryFor(domain: string): string {
  return AGENT_CATEGORIES.find((c) => c.domains.includes(domain))?.label ?? 'Other'
}
function colorFor(domain: string): string {
  return AGENT_CATEGORIES.find((c) => c.domains.includes(domain))?.color ?? 'var(--hud)'
}

function AgentCard({ agent, selected, onClick }: { agent: AgentInfo; selected: boolean; onClick: () => void }) {
  const Icon = DOMAIN_ICON[agent.domain] ?? Bot
  const isOnline = agent.status === 'online'
  const loadPct = Math.min(100, agent.load)
  const color = colorFor(agent.domain)
  return (
    <li
      onClick={agent.status !== 'offline' ? onClick : undefined}
      className={cn(
        'group relative flex flex-col gap-2.5 overflow-hidden rounded-xl border p-3 transition-all duration-200',
        agent.status === 'offline'
          ? 'cursor-default border-border/20 bg-background/10 opacity-45'
          : 'cursor-pointer hover:-translate-y-0.5',
        selected ? 'border-primary bg-primary/10' : 'border-border/60 bg-secondary/30 hover:bg-secondary/50',
      )}
      style={selected ? undefined : { borderTopColor: isOnline ? color : undefined, borderTopWidth: isOnline ? 2 : undefined }}
    >
      {/* live agents get a slow-breathing colour wash anchored top-left,
          not a spinning border -- reads as "active", not as decoration */}
      {isOnline && (
        <div
          className="pointer-events-none absolute -left-8 -top-8 h-28 w-28 rounded-full opacity-25 blur-2xl animate-hud-breathe"
          style={{ background: color }}
          aria-hidden
        />
      )}

      <div className="relative flex items-center gap-2.5">
        <span
          className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-full"
          style={{ background: `color-mix(in oklch, ${color} 18%, var(--background))`, boxShadow: isOnline ? `0 0 0 1px color-mix(in oklch, ${color} 40%, transparent)` : undefined }}
        >
          <Icon className="h-5 w-5" style={{ color }} />
          <span
            className={cn('absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-card', isOnline && 'animate-hud-pulse', STATUS_DOT[agent.status] ?? 'bg-muted-foreground')}
          />
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate font-heading text-[0.78rem] text-foreground">{agent.name}</div>
          <div className="truncate text-[0.55rem] text-muted-foreground">{agent.domain}</div>
        </div>
        <span className={cn('shrink-0 text-[0.5rem]', STATUS_COLOR[agent.status] ?? 'text-muted-foreground')}>{agent.status}</span>
      </div>

      <div className="relative flex items-center gap-2">
        <div className="h-1 flex-1 overflow-hidden rounded-full bg-background/60">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{ width: `${loadPct}%`, background: isOnline ? color : '#555' }}
          />
        </div>
        <span className="shrink-0 text-[0.5rem] text-muted-foreground">{loadPct}%</span>
      </div>

      {agent.specializations.length > 0 && (
        <div className="relative flex flex-wrap gap-1">
          {agent.specializations.slice(0, 3).map((s) => (
            <span key={s} className="rounded-full bg-secondary/50 px-1.5 py-0.5 text-[0.45rem] text-muted-foreground">{s}</span>
          ))}
          {agent.specializations.length > 3 && (
            <span className="self-center text-[0.45rem] text-muted-foreground">+{agent.specializations.length - 3}</span>
          )}
        </div>
      )}
    </li>
  )
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
      <div className="flex flex-col gap-3">
        <div className="rounded-xl border border-border bg-card/60 p-4">
          <h3 className="mb-1 font-heading text-xs text-foreground">Auto-route</h3>
          <p className="mb-2 text-[0.6rem] text-muted-foreground">Ask anything — Nancy picks the right specialist.</p>
          <div className="flex gap-1.5">
            <input
              value={autoQuery}
              onChange={(e) => setAutoQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAutoRun()}
              placeholder="e.g. analyse BTC volatility…"
              className="flex-1 rounded border border-border bg-background/60 px-2 py-1.5 text-[0.65rem] text-foreground outline-none focus:border-primary/60"
            />
            <button type="button" onClick={handleAutoRun} disabled={autoRunning}
              className="rounded border border-tertiary bg-tertiary/15 px-2.5 py-1.5 text-tertiary hover:bg-tertiary/25 disabled:opacity-50">
              {autoRunning ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Zap className="h-3 w-3" />}
            </button>
          </div>
          {autoResult && (
            <p className="mt-2 rounded border border-border bg-background/40 px-2 py-1.5 text-[0.55rem] text-muted-foreground">{autoResult}</p>
          )}
        </div>
        <div className="rounded-xl border border-border bg-card/60 p-4">
          <h3 className="mb-2 font-heading text-xs text-foreground">Fleet load</h3>
          <AgentLoadChart agents={fallbackAgents} />
        </div>
        <p className="px-1 text-[0.6rem] text-muted-foreground">Select an agent from the roster for full detail and to run a task.</p>
      </div>
    )
  }
  const Icon = DOMAIN_ICON[agent.domain] ?? Bot
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-primary/40 bg-card/70 p-4">
      <div className="flex items-center gap-3">
        <span className="glow-ring flex h-11 w-11 shrink-0 items-center justify-center rounded-full border-transparent bg-secondary/60">
          <Icon className="h-5 w-5 text-primary" />
        </span>
        <div className="min-w-0">
          <div className="truncate font-display text-lg text-foreground">{agent.name}</div>
          <div className="truncate text-[0.6rem] text-muted-foreground">{agent.domain} · {categoryFor(agent.domain)}</div>
        </div>
      </div>
      <p className="text-[0.65rem] leading-relaxed text-muted-foreground">
        {agent.description || `${agent.role || 'Specialist agent'} handling ${agent.domain.replace(/-/g, ' ')} tasks.`}
      </p>
      <div className="grid grid-cols-2 gap-2 text-center">
        <div className="rounded-lg border border-border/60 bg-secondary/20 py-2">
          <div className="font-display text-base text-foreground">{agent.total_tasks}</div>
          <div className="text-[0.5rem] text-muted-foreground">tasks run</div>
        </div>
        <div className="rounded-lg border border-border/60 bg-secondary/20 py-2">
          <div className="font-display text-base text-accent">{(agent.confidence * 100).toFixed(0)}%</div>
          <div className="text-[0.5rem] text-muted-foreground">confidence</div>
        </div>
      </div>
      {(agent.mode && agent.mode !== 'production') || agent.hardware_connected === false ? (
        <div className="flex flex-wrap gap-1">
          {agent.mode && agent.mode !== 'production' && (
            <span className="rounded border border-accent/40 bg-accent/10 px-1.5 py-0.5 text-[0.5rem] text-accent">{agent.mode.replace(/_/g, ' ')}</span>
          )}
          {agent.hardware_connected === false && (
            <span className="rounded border border-accent/40 bg-accent/10 px-1.5 py-0.5 text-[0.5rem] text-accent">no hardware attached</span>
          )}
        </div>
      ) : null}
      {agent.specializations.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {agent.specializations.map((s) => (
            <span key={s} className="rounded-full bg-secondary/50 px-2 py-0.5 text-[0.5rem] text-muted-foreground">{s}</span>
          ))}
        </div>
      )}
      <button
        type="button"
        onClick={() => onRunTask(agent)}
        disabled={agent.status === 'offline'}
        className="mt-1 flex items-center justify-center gap-1.5 rounded-lg border border-primary bg-primary/15 py-2 text-xs text-primary transition-colors hover:bg-primary/25 disabled:cursor-not-allowed disabled:opacity-40"
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
  const [selectedAgent, setSelectedAgent] = useState<AgentInfo | null>(null)
  const [taskAgent, setTaskAgent] = useState<AgentInfo | null>(null)
  const [filter, setFilter] = useState('')
  const [autoQuery, setAutoQuery] = useState('')
  const [autoRunning, setAutoRunning] = useState(false)
  const [autoResult, setAutoResult] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date())
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())

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
        ? `Routed to ${route} · ${JSON.stringify(res).slice(0, 160)}…`
        : `Error (${route}): ${res.error}`
      setAutoResult(msg)
    } finally { setAutoRunning(false) }
  }, [autoQuery])

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

  const toggleCategory = (label: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(label)) next.delete(label); else next.add(label)
      return next
    })
  }

  const selectAgent = (agent: AgentInfo) => {
    setSelectedAgent((prev) => (prev?.key === agent.key ? null : agent))
    onAgentSelect?.(agent.key)
  }

  return (
    <div className="mx-auto flex max-w-[1680px] flex-col gap-4">
      {/* slim title strip, not a boxed hero panel -- fleet vitals at a glance */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card/60 px-4 py-3">
        <div className="flex items-center gap-3">
          <span className="font-display text-xl text-foreground">Fleet Console</span>
          <span className={cn('flex items-center gap-1.5 text-[0.62rem]', error ? 'text-destructive' : 'text-muted-foreground')}>
            {error ? <WifiOff className="h-3 w-3" /> : <Wifi className="h-3 w-3 text-primary animate-hud-breathe" />}
            {error ? 'Backend offline' : `${data?.total ?? '…'} agents · updated ${lastRefresh.toLocaleTimeString('en-GB')}`}
          </span>
        </div>
        <div className="flex items-center gap-4 text-[0.68rem]">
          <span><span className="font-display text-base text-primary">{data?.stats.agents_online ?? '…'}</span> <span className="text-muted-foreground">online</span></span>
          <span><span className="font-display text-base text-foreground">{data?.stats.total_tasks ?? '…'}</span> <span className="text-muted-foreground">tasks</span></span>
          <span><span className="font-display text-base text-accent">{data ? `${(data.stats.success_rate * 100).toFixed(0)}%` : '…'}</span> <span className="text-muted-foreground">success</span></span>
          <button type="button" onClick={fetchAgents} disabled={loading} className="text-muted-foreground hover:text-primary">
            <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        {/* LEFT: grouped roster, browsable by category */}
        <div className="flex flex-col gap-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter by name, domain, or specialisation…"
              className="w-full rounded-lg border border-border bg-background/60 py-2 pl-8 pr-3 text-[0.68rem] text-foreground outline-none focus:border-primary/60"
            />
          </div>

          {loading && !data ? (
            <div className="flex items-center justify-center rounded-xl border border-border bg-card/40 py-10 text-[0.62rem] text-muted-foreground">
              <RefreshCw className="mr-2 h-3.5 w-3.5 animate-spin" /> Loading agents…
            </div>
          ) : error && !data ? (
            <div className="rounded-xl border border-border bg-card/40 py-6 text-center text-[0.62rem] text-destructive">
              {error}<br />
              <button onClick={fetchAgents} className="mt-2 text-primary underline">Retry</button>
            </div>
          ) : filteredAgents.length === 0 ? (
            <div className="rounded-xl border border-border bg-card/40 py-6 text-center text-[0.62rem] text-muted-foreground">No agents match filter.</div>
          ) : (
            AGENT_CATEGORIES.map((cat) => {
              const items = grouped.get(cat.label) ?? []
              if (items.length === 0) return null
              const isCollapsed = collapsed.has(cat.label)
              const onlineCount = items.filter((a) => a.status === 'online').length
              return (
                <div key={cat.label} className="overflow-hidden rounded-xl border border-border bg-card/40">
                  <button
                    type="button"
                    onClick={() => toggleCategory(cat.label)}
                    className="flex w-full items-center justify-between gap-2 px-3 py-2.5 hover:bg-secondary/20"
                  >
                    <span className="flex items-center gap-2 text-xs font-medium text-foreground">
                      <cat.icon className="h-3.5 w-3.5" style={{ color: cat.color }} />
                      {cat.label}
                      <span className="text-muted-foreground">({onlineCount}/{items.length} online)</span>
                    </span>
                    {isCollapsed ? <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" /> : <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />}
                  </button>
                  {!isCollapsed && (
                    <ul className="grid grid-cols-1 gap-2 border-t border-border/60 p-2 sm:grid-cols-2 xl:grid-cols-3">
                      {items.map((agent) => (
                        <AgentCard key={agent.key} agent={agent} selected={selectedAgent?.key === agent.key} onClick={() => selectAgent(agent)} />
                      ))}
                    </ul>
                  )}
                </div>
              )
            })
          )}
        </div>

        {/* RIGHT: persistent detail rail -- selection updates it in place,
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

      {taskAgent && <AgentTaskModal agent={taskAgent} onClose={() => setTaskAgent(null)} />}
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

      {/* ── Three-up status row ── */}
      <HudPanel title="System Diagnostics" className="col-span-12 md:col-span-4">
        <div className="grid grid-cols-2 gap-2">
          {[
            { icon: Cpu, label: 'CPU', v: `${cpu.toFixed(0)}%` },
            { icon: Database, label: 'MEM', v: `${mem.toFixed(0)}%` },
            { icon: Folder, label: 'DISK', v: `${disk.toFixed(0)}%` },
            { icon: Signal, label: 'NET', v: `${net.toFixed(0)}%` },
            { icon: Thermometer, label: 'TEMP', v: health.tempC != null ? `${health.tempC.toFixed(0)}° C` : 'N/A' },
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
      </HudPanel>

      <HudPanel title="Backend Health" accent="amber" className="col-span-12 md:col-span-4">
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

      <HudPanel title="Fleet Snapshot" accent="violet" className="col-span-12 md:col-span-4">
        <div className="grid grid-cols-3 gap-2 text-center">
          {[
            { icon: Bot, label: 'Agents', v: agentStats ? `${agentStats.agents_online}` : '…' },
            { icon: Zap, label: 'Tasks', v: agentStats ? `${agentStats.total_tasks}` : '…' },
            { icon: Activity, label: 'Uptime', v: uptime },
          ].map(({ icon: Icon, label, v }) => (
            <div key={label} className="flex flex-col items-center gap-1 rounded border border-border/50 bg-secondary/20 py-3">
              <Icon className="h-5 w-5 text-primary" />
              <span className="font-heading text-sm text-foreground">{v}</span>
              <span className="text-[0.5rem] text-muted-foreground">{label}</span>
            </div>
          ))}
        </div>
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
