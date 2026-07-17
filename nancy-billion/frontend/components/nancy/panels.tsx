'use client'

import { useEffect, useCallback, useMemo, useState } from 'react'
import { ArcReactor, HudPanel, RadialGauge, StatBar } from './hud-bits'
import type { AgentInfo } from '@/lib/nancy/types'
import { listAgents, autoRouteAgent, type AgentListResponse } from '@/lib/nancy/agent-client'
import { AgentTaskModal } from './agent-task-modal'
import { useSystemHealth, useTradeHistory } from '@/hooks/useSystemData'
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
  Radar,
  Satellite,
  Waves,
  Radio,
  Fingerprint,
  Sparkles,
  Signal,
  Lock,
  ShieldCheck,
  AlertTriangle,
  Eye,
  Thermometer,
  Flame,
} from 'lucide-react'
import { cn } from '@/lib/utils'

/* ─── Jitter hook for live gauges ─────────────────────────────── */
function useJitter(base: number, amp = 6) {
  const [v, setV] = useState(base)
  useEffect(() => {
    const t = setInterval(() => {
      setV(Math.max(2, Math.min(100, base + (Math.random() - 0.5) * amp * 2)))
    }, 1600)
    return () => clearInterval(t)
  }, [base, amp])
  return v
}

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
  const telemetryHistory = useMetricHistory({ cpu: health.cpu, mem: health.memory, net: health.networkPercent })

  return (
    <div className="mx-auto grid max-w-[1680px] grid-cols-12 gap-4">
      {/* ── HERO: Reactor + status stripe ── */}
      <div className="col-span-12 grid grid-cols-12 gap-4 xl:col-span-8">
        <HudPanel
          title="Central Reactor · Nancy Core"
          right={<span className="text-primary">ONLINE</span>}
          className="col-span-12 md:col-span-7 xl:col-span-7"
        >
          <div className="flex items-center gap-4">
            <div className="shrink-0">
              <ArcReactor size={220} />
            </div>
            <div className="flex-1 min-w-0 space-y-3">
              <div>
                <div className="font-heading text-3xl tracking-tight text-primary hud-glow">
                  100.00 <span className="text-base text-muted-foreground">%</span>
                </div>
                <div className="text-[0.55rem] uppercase tracking-[0.28em] text-muted-foreground">
                  Reactor Output · Stable
                </div>
              </div>
              <StatBar label="Neural CPU" value={cpu.toFixed(0)} unit="%" pct={cpu} />
              <StatBar label="Memory" value={mem.toFixed(0)} unit="%" pct={mem} amber />
              <StatBar label="GPU Cortex" value="N/A" unit="" pct={0} />
              <StatBar label="Uplink" value={net.toFixed(0)} unit="%" pct={net} />
            </div>
          </div>
        </HudPanel>

        {/* Big number cards */}
        <div className="col-span-12 md:col-span-5 xl:col-span-5 grid grid-cols-2 gap-3">
          {[
            { label: 'Tasks Run',  v: `${stats?.total_tasks ?? 0}`, delta: stats ? `${stats.agents_online} online` : '…', icon: Zap, tone: 'primary' as const },
            { label: 'Agents',     v: `${stats?.agents_online ?? 0}`, delta: stats ? `${stats.agents_offline} offline` : '…', icon: Radio, tone: 'accent' as const },
            { label: 'Failures',   v: `${stats?.failed_tasks ?? 0}`, delta: stats ? `${(stats.success_rate * 100).toFixed(0)}% success` : '…', icon: Shield, tone: 'ok' as const },
            { label: 'Session',    v: uptime, delta: 'this tab', icon: Activity, tone: 'primary' as const },
          ].map((s) => (
            <div key={s.label} className="hud-panel flex flex-col justify-between rounded-md p-3 transition-transform hover:-translate-y-0.5">
              <div className="flex items-center gap-2">
                <span className={cn(
                  'flex h-8 w-8 items-center justify-center rounded-md',
                  s.tone === 'primary' && 'bg-primary/15 text-primary',
                  s.tone === 'accent'  && 'bg-accent/15 text-accent',
                  s.tone === 'ok'      && 'bg-primary/15 text-primary',
                )}>
                  <s.icon className="h-4 w-4" />
                </span>
                <span className="text-[0.5rem] uppercase tracking-[0.22em] text-muted-foreground">{s.label}</span>
              </div>
              <div>
                <div className="font-heading text-2xl tracking-tight text-foreground hud-glow">{s.v}</div>
                <div className="text-[0.55rem] text-primary/80">{s.delta}</div>
              </div>
            </div>
          ))}
        </div>

        {/* Ops timeline */}
        <HudPanel
          title="Operations Feed · Live"
          right={<span className="text-accent text-[0.5rem] animate-hud-pulse">● LIVE</span>}
          className="col-span-12"
        >
          <CommsFeed />
        </HudPanel>

        {/* System telemetry + agent domains */}
        <HudPanel title="System Telemetry · Live" right={<span className="text-primary text-[0.5rem]">Δ {tick}</span>} className="col-span-12 md:col-span-7">
          <SystemTelemetryChart history={telemetryHistory} />
          <div className="mt-3 flex items-center gap-3 text-[0.5rem] uppercase tracking-widest text-muted-foreground">
            <LegendDot color="var(--hud)" label="cpu" />
            <LegendDot color="var(--accent)" label="memory" />
            <LegendDot color="oklch(0.7 0.16 160)" label="uplink" />
          </div>
        </HudPanel>

        <HudPanel title="Agent Domains" className="col-span-12 md:col-span-5">
          <AgentDomainChart agents={agents} />
        </HudPanel>
      </div>

      {/* ── RIGHT COLUMN: Global recon ── */}
      <div className="col-span-12 xl:col-span-4 grid grid-cols-1 gap-4">
        <HudPanel title="Deep Space Uplink" right={<span className="text-primary">ACTIVE</span>}>
          <div className="flex flex-wrap items-center justify-around gap-2 py-1">
            <RadialGauge value={cpu} label="Cognition" color="var(--hud)" size={92} />
            <RadialGauge value={0} sub="N/A" label="Inference" color="var(--accent)" size={92} />
            <RadialGauge
              value={stats && stats.agents_online + stats.agents_offline > 0
                ? (stats.agents_online / (stats.agents_online + stats.agents_offline)) * 100
                : 0}
              label="Fleet Online"
              color="var(--hud)"
              size={92}
            />
          </div>
        </HudPanel>

        <HudPanel title="Global Track Sys">
          <WorldTracker />
        </HudPanel>

        <HudPanel title="Trading P/L · Recent">
          <TradePLChart />
        </HudPanel>

        <HudPanel title="Quick Stats">
          <div className="grid grid-cols-3 gap-2 text-center">
            {[
              { icon: Cpu, label: 'CORES', v: '128' },
              { icon: Database, label: 'STORAGE', v: '4.2 PB' },
              { icon: ShieldCheck, label: 'PERIMETER', v: 'GREEN' },
            ].map(({ icon: Icon, label, v }) => (
              <div key={label} className="flex flex-col items-center gap-1 rounded border border-border/60 bg-secondary/30 py-2">
                <Icon className="h-4 w-4 text-primary" />
                <span className="font-heading text-xs text-foreground">{v}</span>
                <span className="text-[0.45rem] uppercase tracking-widest text-muted-foreground">{label}</span>
              </div>
            ))}
          </div>
        </HudPanel>
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
function SystemTelemetryChart({ history }: { history: Array<{ t: number } & Record<string, number>> }) {
  if (history.length < 2) {
    return (
      <div className="flex h-40 items-center justify-center text-[0.6rem] text-muted-foreground">
        Gathering telemetry…
      </div>
    )
  }
  return (
    <div className="h-40 w-full">
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

/* ─── Live ops feed ─── */
const FEED_TEMPLATES = [
  ['SIGINT', 'Uplink stable · pkt loss 0.02%', 'ok'],
  ['ORBIT',  'Sat KH-11 · frame lock acquired', 'ok'],
  ['GRID',   'Neural mesh sync · 97.4%', 'ok'],
  ['SEC',    'Zero intrusions · perimeter green', 'ok'],
  ['AI',     'Model warm · 671B weights cached', 'ok'],
  ['GEO',    'Aurora ping · Reykjavík', 'info'],
  ['NET',    'Backbone latency 12ms', 'ok'],
  ['OPS',    'Task queue drained · 0 pending', 'ok'],
  ['ALERT',  'Anomalous packet · Kiev · resolved', 'warn'],
  ['SAT',    'GOES-17 imagery refreshed', 'info'],
] as const
function CommsFeed() {
  const [idx, setIdx] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setIdx((n) => (n + 1) % FEED_TEMPLATES.length), 1600)
    return () => clearInterval(t)
  }, [])
  const rows = Array.from({ length: 6 }).map((_, i) => FEED_TEMPLATES[(idx + i) % FEED_TEMPLATES.length])
  return (
    <ul className="flex flex-col gap-1 font-mono text-[0.6rem]">
      {rows.map(([tag, msg, level], i) => (
        <li
          key={`${tag}-${idx}-${i}`}
          className="flex items-center gap-3 border-b border-border/40 pb-1 last:border-none"
          style={{ opacity: 1 - i * 0.13 }}
        >
          <span className="w-14 shrink-0 text-primary hud-glow">{tag}</span>
          <span className="flex-1 truncate text-muted-foreground">{msg}</span>
          <span className={cn(
            'text-xs',
            level === 'warn' ? 'text-accent' : level === 'info' ? 'text-primary/70' : 'text-primary',
          )}>●</span>
          <span className="w-16 shrink-0 text-right text-[0.5rem] text-muted-foreground">
            {new Date(Date.now() - i * 3400).toLocaleTimeString('en-GB').slice(0, 8)}
          </span>
        </li>
      ))}
    </ul>
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
                <span className="truncate font-heading tracking-widest text-muted-foreground">{d.domain}</span>
              </span>
              <span className="shrink-0 text-foreground">{d.count}</span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

/* ─── Simple world tracker (SVG blips over a globe silhouette) ─── */
function WorldTracker() {
  const tick = useTick(1600)
  const blips = Array.from({ length: 8 }).map((_, i) => ({
    x: 15 + ((i * 37 + tick * 3) % 130),
    y: 30 + ((i * 19 + tick * 2) % 60),
    hot: i % 3 === 0,
  }))
  return (
    <div className="relative aspect-[3/2] w-full overflow-hidden rounded border border-border/50 bg-background/40">
      <svg viewBox="0 0 160 100" className="h-full w-full">
        <defs>
          <radialGradient id="g" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="oklch(0.32 0.09 215)" />
            <stop offset="100%" stopColor="transparent" />
          </radialGradient>
        </defs>
        {/* latitude/longitude grid */}
        {Array.from({ length: 7 }).map((_, i) => (
          <line key={`h${i}`} x1="0" x2="160" y1={(i + 1) * 12.5} y2={(i + 1) * 12.5} stroke="var(--hud)" strokeOpacity="0.12" />
        ))}
        {Array.from({ length: 12 }).map((_, i) => (
          <line key={`v${i}`} y1="0" y2="100" x1={(i + 1) * 13.3} x2={(i + 1) * 13.3} stroke="var(--hud)" strokeOpacity="0.12" />
        ))}
        <ellipse cx="80" cy="50" rx="70" ry="42" fill="url(#g)" stroke="var(--hud)" strokeOpacity="0.35" />
        {blips.map((b, i) => (
          <g key={i}>
            <circle cx={b.x} cy={b.y} r={b.hot ? 2.4 : 1.6} fill={b.hot ? 'var(--accent)' : 'var(--hud)'}
              style={{ filter: `drop-shadow(0 0 4px ${b.hot ? 'var(--accent)' : 'var(--hud)'})` }} />
            <circle cx={b.x} cy={b.y} r={b.hot ? 6 : 4} fill="none" stroke={b.hot ? 'var(--accent)' : 'var(--hud)'} strokeOpacity="0.4">
              <animate attributeName="r" from={b.hot ? 3 : 2} to={b.hot ? 10 : 8} dur="2s" repeatCount="indefinite" />
              <animate attributeName="opacity" from="0.6" to="0" dur="2s" repeatCount="indefinite" />
            </circle>
          </g>
        ))}
      </svg>
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
  const a = useJitter(72, 8)
  const b = useJitter(55, 8)
  const c = useJitter(88, 5)
  const d = useJitter(64, 10)

  return (
    <div className="mx-auto grid max-w-[1680px] grid-cols-12 gap-4">
      {/* Big reactor / neural sphere */}
      <HudPanel title="Neural Substrate" right={<span className="text-primary">STABLE</span>} className="col-span-12 lg:col-span-5">
        <div className="flex flex-col items-center gap-4 py-2">
          <ArcReactor size={280} />
          <div className="grid w-full grid-cols-2 gap-2">
            <div className="rounded border border-border/50 bg-secondary/20 p-2 text-center">
              <div className="font-heading text-xl text-primary hud-glow">671B</div>
              <div className="text-[0.5rem] uppercase tracking-widest text-muted-foreground">Parameters</div>
            </div>
            <div className="rounded border border-border/50 bg-secondary/20 p-2 text-center">
              <div className="font-heading text-xl text-accent hud-glow-amber">2.4M</div>
              <div className="text-[0.5rem] uppercase tracking-widest text-muted-foreground">Vectors</div>
            </div>
          </div>
        </div>
      </HudPanel>

      {/* Gauges & modules */}
      <div className="col-span-12 grid grid-cols-1 gap-4 lg:col-span-7">
        <HudPanel title="Cognitive Load">
          <div className="flex flex-wrap items-center justify-around gap-3 py-2">
            <RadialGauge value={a} label="Reasoning" color="var(--hud)" size={110} />
            <RadialGauge value={b} label="Perception" color="var(--accent)" size={110} />
            <RadialGauge value={c} label="Sync" color="var(--hud)" size={110} />
            <RadialGauge value={d} label="Attention" color="oklch(0.7 0.16 160)" size={110} />
          </div>
        </HudPanel>

        <HudPanel title="Model Stack">
          <ul className="grid grid-cols-1 gap-1.5 md:grid-cols-2">
            {[
              ['Reasoning Engine', 'gpt-class · 671B', Zap],
              ['Vision Cortex',    'multimodal · online', Eye],
              ['Voice Synthesis',  'neural TTS · ready', Waves],
              ['Memory Index',     '2.4M vectors', Database],
              ['Router / Planner', 'DAG · v3.2', Radar],
              ['Ethics Filter',    'active · pass 100%', ShieldCheck],
            ].map(([k, v, Icon]) => {
              const IconComp = Icon as React.ElementType
              return (
                <li key={k as string} className="flex items-center justify-between gap-2 rounded border border-border/50 bg-secondary/20 px-2 py-1.5">
                  <span className="flex items-center gap-2 text-[0.6rem] text-muted-foreground">
                    <IconComp className="h-3 w-3 text-primary" /> {k as string}
                  </span>
                  <span className="text-[0.6rem] text-primary">{v as string}</span>
                </li>
              )
            })}
          </ul>
        </HudPanel>

        <HudPanel title="Reasoning Trace · Live">
          <ThoughtTrace />
        </HudPanel>
      </div>
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
   AGENTS — largely unchanged behaviour, but a richer 2-col layout
   ═══════════════════════════════════════════════════════════════ */
const STATUS_COLOR: Record<string, string> = {
  online: 'text-primary',
  idle: 'text-muted-foreground',
  offline: 'text-destructive',
  training: 'text-accent',
  error: 'text-destructive',
}
const DOMAIN_ICON: Record<string, React.ElementType> = {
  'quantum-reasoning': Zap,
  'consciousness': Activity,
  'ethics': Shield,
  'temporal-prediction': BarChart3,
  'swarm-coordination': Rss,
  'self-improvement': RefreshCw,
  'embodied-cognition': Bot,
  'data-science': Database,
  'crypto-trading': BarChart3,
  'security': Shield,
  'devops': Terminal,
  'research': Search,
}

function AgentCard({ agent, onClick }: { agent: AgentInfo; onClick: () => void }) {
  const Icon = DOMAIN_ICON[agent.domain] ?? Bot
  const isOnline = agent.status === 'online'
  const loadPct = Math.min(100, agent.load)
  return (
    <li
      onClick={agent.status !== 'offline' ? onClick : undefined}
      className={cn(
        'group flex cursor-pointer flex-col gap-2 rounded border p-2.5 transition-all duration-200',
        isOnline
          ? 'border-primary/40 bg-primary/5 hover:border-primary hover:bg-primary/10 hover:shadow-[0_0_18px_rgba(56,211,235,0.2)]'
          : agent.status === 'offline'
          ? 'cursor-default border-border/30 bg-background/20 opacity-50'
          : 'border-border bg-secondary/30 hover:border-primary/50 hover:bg-secondary/40',
      )}
    >
      <div className="flex items-center justify-between gap-1">
        <span className="flex items-center gap-1.5 font-heading text-[0.7rem] tracking-widest text-foreground">
          <Icon className="h-3.5 w-3.5 text-primary shrink-0" />
          <span className="truncate">{agent.name}</span>
        </span>
        <span className={cn('shrink-0 text-[0.45rem] uppercase tracking-widest', STATUS_COLOR[agent.status] ?? 'text-muted-foreground')}>
          {agent.status}
        </span>
      </div>
      <p className="text-[0.5rem] text-muted-foreground truncate">{agent.domain}</p>
      {(agent.mode && agent.mode !== 'production') || agent.hardware_connected === false ? (
        <div className="flex flex-wrap gap-1">
          {agent.mode && agent.mode !== 'production' && (
            <span className="rounded border border-accent/40 bg-accent/10 px-1 py-px text-[0.4rem] uppercase tracking-widest text-accent">
              {agent.mode.replace(/_/g, ' ')}
            </span>
          )}
          {agent.hardware_connected === false && (
            <span className="rounded border border-accent/40 bg-accent/10 px-1 py-px text-[0.4rem] uppercase tracking-widest text-accent">
              no hardware
            </span>
          )}
        </div>
      ) : null}
      <div className="flex items-center gap-2">
        <div className="h-1 flex-1 overflow-hidden rounded-full bg-background/60">
          <div className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${loadPct}%`,
              background: agent.status === 'training' ? 'var(--accent)' : isOnline ? 'var(--hud)' : '#555',
              boxShadow: isOnline ? '0 0 4px var(--hud)' : 'none',
            }} />
        </div>
        <span className="shrink-0 text-[0.45rem] text-muted-foreground">{loadPct}%</span>
      </div>
      {agent.specializations.length > 0 && (
        <div className="flex flex-wrap gap-0.5">
          {agent.specializations.slice(0, 3).map((s) => (
            <span key={s} className="rounded bg-secondary/40 px-1 py-px text-[0.4rem] text-muted-foreground">{s}</span>
          ))}
          {agent.specializations.length > 3 && (
            <span className="text-[0.4rem] text-muted-foreground self-center">+{agent.specializations.length - 3}</span>
          )}
        </div>
      )}
    </li>
  )
}

export function AgentsPanel({ onAgentSelect }: { onAgentSelect?: (agentId: string) => void } = {}) {
  const [data, setData] = useState<AgentListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedAgent, setSelectedAgent] = useState<AgentInfo | null>(null)
  const [filter, setFilter] = useState('')
  const [autoQuery, setAutoQuery] = useState('')
  const [autoRunning, setAutoRunning] = useState(false)
  const [autoResult, setAutoResult] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date())

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

  return (
    <div className="mx-auto grid max-w-[1680px] grid-cols-12 gap-4">
      {/* Left: hero stats + auto-router */}
      <div className="col-span-12 grid grid-cols-1 gap-4 lg:col-span-4">
        <HudPanel title="Agent Fleet · Overview" right={
          <button type="button" onClick={fetchAgents} disabled={loading} className="text-muted-foreground hover:text-primary">
            <RefreshCw className={cn('h-3 w-3', loading && 'animate-spin')} />
          </button>
        }>
          <div className="mb-3 flex items-center gap-1.5 text-[0.55rem]">
            {error ? (<><WifiOff className="h-3 w-3 text-destructive" /><span className="text-destructive">Backend offline</span></>)
              : (<><Wifi className="h-3 w-3 text-primary" /><span className="text-muted-foreground">Connected · {data?.total ?? '?'} · {lastRefresh.toLocaleTimeString('en-GB')}</span></>)}
          </div>
          {data && (
            <div className="grid grid-cols-3 gap-2 text-center">
              {[
                { label: 'Online',  v: data.stats.agents_online, tone: 'text-primary' },
                { label: 'Tasks',   v: data.stats.total_tasks, tone: 'text-foreground' },
                { label: 'Success', v: `${(data.stats.success_rate * 100).toFixed(0)}%`, tone: 'text-accent' },
              ].map(({ label, v, tone }) => (
                <div key={label} className="rounded border border-border/60 bg-secondary/20 py-2">
                  <div className={cn('font-heading text-lg hud-glow', tone)}>{v}</div>
                  <div className="text-[0.5rem] uppercase tracking-widest text-muted-foreground">{label}</div>
                </div>
              ))}
            </div>
          )}
        </HudPanel>

        <HudPanel title="Auto-Route Query" right={<Sparkles className="h-3 w-3 text-primary" />}>
          <p className="mb-2 text-[0.55rem] text-muted-foreground">
            Ask anything — Nancy picks the right specialist agent.
          </p>
          <div className="flex gap-1.5">
            <input
              value={autoQuery}
              onChange={(e) => setAutoQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAutoRun()}
              placeholder="e.g. analyse the current BTC volatility profile…"
              className="flex-1 rounded border border-border bg-background/60 px-2 py-1.5 text-[0.65rem] text-foreground outline-none focus:border-primary/60"
            />
            <button type="button" onClick={handleAutoRun} disabled={autoRunning}
              className="rounded border border-primary bg-primary/15 px-2.5 py-1.5 text-primary hover:bg-primary/25 disabled:opacity-50">
              {autoRunning ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Zap className="h-3 w-3" />}
            </button>
          </div>
          {autoResult && (
            <p className="mt-2 rounded border border-border bg-background/40 px-2 py-1.5 text-[0.55rem] text-muted-foreground">
              {autoResult}
            </p>
          )}
        </HudPanel>

        <HudPanel title="Fleet Activity">
          <AgentLoadChart agents={data?.agents ?? []} />
        </HudPanel>
      </div>

      {/* Right: agent grid */}
      <div className="col-span-12 lg:col-span-8">
        <HudPanel title="Autonomous Agents · Fleet"
          right={data && <span className="text-primary text-[0.55rem]">{data.stats.agents_online} ONLINE</span>}>
          <div className="relative mb-2">
            <Search className="absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
            <input value={filter} onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter by name, domain, or specialisation…"
              className="w-full rounded border border-border bg-background/60 py-1.5 pl-7 pr-2 text-[0.65rem] text-foreground outline-none focus:border-primary/60" />
          </div>

          {loading && !data ? (
            <div className="flex items-center justify-center py-8 text-[0.6rem] text-muted-foreground">
              <RefreshCw className="mr-2 h-3.5 w-3.5 animate-spin" /> Loading agents…
            </div>
          ) : error && !data ? (
            <div className="py-6 text-center text-[0.6rem] text-destructive">
              {error}<br />
              <button onClick={fetchAgents} className="mt-2 text-primary underline">Retry</button>
            </div>
          ) : (
            <ul className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
              {filteredAgents.length === 0 ? (
                <li className="col-span-full py-4 text-center text-[0.6rem] text-muted-foreground">No agents match filter.</li>
              ) : (
                filteredAgents.map((agent) => (
                  <AgentCard key={agent.key} agent={agent}
                    onClick={() => { setSelectedAgent(agent); onAgentSelect?.(agent.key) }} />
                ))
              )}
            </ul>
          )}
        </HudPanel>
      </div>

      {selectedAgent && <AgentTaskModal agent={selectedAgent} onClose={() => setSelectedAgent(null)} />}
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
  const [logs, setLogs] = useState<string[]>([
    '[boot] jarvis-core online · 0.03s',
    '[net]  uplink up · 12ms · pkt loss 0.02%',
    '[sec]  perimeter green · 0 intrusions',
    '[mem]  vector cache warm · 2.4M',
    '[ai]   671B weights loaded · fp16',
  ])
  useEffect(() => {
    const lines = [
      '[net]  packet burst · Prague relay',
      '[gpu]  cortex idle · 74% headroom',
      '[sat]  KH-11 frame lock',
      '[ai]   inference · 42ms',
      '[ops]  task queue drained',
    ]
    const t = setInterval(() => {
      setLogs((l) => [...l.slice(-40), lines[Math.floor(Math.random() * lines.length)] + '  ·  ' + new Date().toLocaleTimeString('en-GB')])
    }, 900)
    return () => clearInterval(t)
  }, [])

  const health = useSystemHealth()
  const cpu = health.cpu ?? 0
  const mem = health.memory ?? 0
  const disk = health.disk ?? 0
  const net = health.networkPercent ?? 0

  return (
    <div className="mx-auto grid max-w-[1680px] grid-cols-12 gap-4">
      {/* Diagnostics column */}
      <div className="col-span-12 grid grid-cols-1 gap-4 xl:col-span-4">
        <HudPanel title="System Diagnostics">
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
                  <div className="text-[0.45rem] uppercase tracking-widest text-muted-foreground">{label}</div>
                </div>
              </div>
            ))}
          </div>
        </HudPanel>

        <HudPanel title="Perimeter · Security">
          <ul className="space-y-1.5 text-[0.6rem]">
            {[
              ['Firewall', 'active', ShieldCheck, 'ok'],
              ['Intrusion', '0 detected', Lock, 'ok'],
              ['Certs',    'valid · 89d', Fingerprint, 'ok'],
              ['Alerts',   '2 low priority', AlertTriangle, 'warn'],
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

        <HudPanel title="Reactor Load">
          <div className="flex items-center justify-around">
            <RadialGauge value={cpu} label="Core A" color="var(--hud)" size={92} />
            <RadialGauge value={mem} label="Core B" color="var(--accent)" size={92} />
          </div>
        </HudPanel>
      </div>

      {/* Terminal + apps */}
      <div className="col-span-12 grid grid-cols-1 gap-4 xl:col-span-8">
        <HudPanel title="Command Layer · Apps">
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
                  launched === key ? 'text-primary hud-glow' : 'text-foreground')} />
                <span className="text-[0.5rem] uppercase tracking-widest text-muted-foreground">{label}</span>
              </button>
            ))}
          </div>
          {launched && (
            <div className="mt-3 rounded border border-primary/40 bg-background/60 p-2 font-mono text-[0.6rem] text-primary">
              {'>'} launching <span className="uppercase">{launched}</span>… process spawned [pid {Math.floor(1000 + Math.random() * 8000)}]
            </div>
          )}
        </HudPanel>

        <HudPanel title="Live Kernel Log" right={<span className="text-primary text-[0.5rem]">tick {tick}</span>}>
          <div className="max-h-64 overflow-y-auto rounded border border-border/40 bg-background/50 p-2 font-mono text-[0.6rem] leading-relaxed">
            {logs.map((l, i) => (
              <div key={i} className={cn(
                'flex items-start gap-2 border-b border-border/20 py-0.5 last:border-none',
                l.includes('[sec]') && 'text-primary',
                l.includes('[ai]') && 'text-accent',
                !l.includes('[sec]') && !l.includes('[ai]') && 'text-muted-foreground',
              )}>
                <span className="text-primary/60">›</span>
                <span className="flex-1">{l}</span>
              </div>
            ))}
          </div>
        </HudPanel>

        <HudPanel title="Fleet Uplink">
          <div className="grid grid-cols-3 gap-2 text-center">
            {[
              { icon: Satellite, label: 'SATCOM', v: '12 birds' },
              { icon: Radar,     label: 'RADAR',  v: '8 sweeps/s' },
              { icon: Flame,     label: 'REACTOR',v: 'nominal' },
            ].map(({ icon: Icon, label, v }) => (
              <div key={label} className="flex flex-col items-center gap-1 rounded border border-border/50 bg-secondary/20 py-3">
                <Icon className="h-5 w-5 text-primary" />
                <span className="font-heading text-sm text-foreground">{v}</span>
                <span className="text-[0.5rem] uppercase tracking-widest text-muted-foreground">{label}</span>
              </div>
            ))}
          </div>
        </HudPanel>
      </div>
    </div>
  )
}
