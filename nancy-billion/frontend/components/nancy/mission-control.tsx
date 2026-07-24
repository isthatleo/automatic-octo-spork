'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { cn } from '@/lib/utils'
import { AmbientField } from './ambient-field'
import { AgentTaskModal } from './agent-task-modal'
import { SnakeBorder, snakeStateForAgent } from './snake-border'
import {
  listAgents, autoRouteAgent, summarizeResult, type AgentListResponse,
} from '@/lib/nancy/agent-client'
import { listMissions } from '@/lib/nancy/mission-client'
import { onDomainEvent } from '@/lib/nancy/ws-client'
import { describeDomainEvent, STAGE_LABELS } from '@/lib/nancy/event-descriptions'
import { useSystemHealth, useLlmStatus } from '@/hooks/useSystemData'
import type { AgentInfo, AgentResult, Mission } from '@/lib/nancy/types'
import {
  AGENT_CATEGORIES, STATUS_DOT, STATUS_COLOR, categoryFor, colorFor, iconFor,
} from '@/lib/nancy/agent-taxonomy'
import {
  Search, RefreshCw, Play, X, Zap, CheckCircle2, XCircle, Gauge, Activity,
  ChevronRight, Sparkles, Rocket, HeartPulse, Cpu, HardDrive, Wifi, Waypoints,
  Radio, Link2,
} from 'lucide-react'
import { BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip } from 'recharts'

/* ═══════════════════════════════════════════════════════════════════════
   MISSION CONTROL — a spatial narrative, not a table: Mission Overview →
   Operational Health → AI Fleet → Relationship Graph → Live Activity →
   Inspector. Every number comes from real backend state (agents.list,
   missions.list, /system/health, /llm/status), kept live by the real
   domain events the backend broadcasts (event_bus.py) rather than by
   polling. The Relationship Graph is the one section that genuinely
   couldn't exist honestly before the missions backend: an edge only
   appears when a real mission dependency links two agents' work, and the
   traveling particle only animates while that dependency mission is
   actually executing — never a fabricated "these agents are talking"
   claim. Each card's rotating snake border is likewise a real signal, not
   decoration: its speed/color is a direct function of agent.status.
   ═══════════════════════════════════════════════════════════════════════ */

interface FeedItem { id: string; text: string; at: number; tone: 'ok' | 'error' | 'info' }
let feedSeq = 0
function newFeedId() { feedSeq += 1; return `mc_feed_${Date.now()}_${feedSeq}` }

export function MissionControlPanel() {
  const [data, setData] = useState<AgentListResponse | null>(null)
  const [missions, setMissions] = useState<Mission[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState('')
  const [activeCategory, setActiveCategory] = useState<string | null>(null)
  const [selectedAgentKey, setSelectedAgentKey] = useState<string | null>(null)
  const [taskAgent, setTaskAgent] = useState<AgentInfo | null>(null)
  const [autoQuery, setAutoQuery] = useState('')
  const [autoRunning, setAutoRunning] = useState(false)
  const [autoResult, setAutoResult] = useState<string | null>(null)
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date())
  const [sessionRuns, setSessionRuns] = useState<{ agentKey: string; text: string; success: boolean; at: number }[]>([])
  const [feed, setFeed] = useState<FeedItem[]>([])

  const health = useSystemHealth()
  const { data: llm } = useLlmStatus()

  const fetchAgents = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const res = await listAgents()
      setData(res); setLastRefresh(new Date())
    } catch (e) { setError(String(e)) } finally { setLoading(false) }
  }, [])

  const fetchMissions = useCallback(async () => {
    const res = await listMissions()
    if (res.success) setMissions(res.missions)
  }, [])

  useEffect(() => {
    fetchAgents()
    fetchMissions()
    // Safety-net poll -- real-time updates come from the WS subscription
    // below; this only covers a missed frame after a reconnect.
    const t = setInterval(() => { fetchAgents(); fetchMissions() }, 60_000)
    return () => clearInterval(t)
  }, [fetchAgents, fetchMissions])

  // Live projection of real backend events -- agent lifecycle refreshes the
  // fleet (debounced), mission events patch mission state directly, and
  // every real event narrates into the Live Activity feed.
  const refetchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    const unsubscribe = onDomainEvent((evt) => {
      if (evt.type.startsWith('AGENT_')) {
        if (refetchTimer.current) clearTimeout(refetchTimer.current)
        refetchTimer.current = setTimeout(fetchAgents, 150)
      }
      if (evt.type === 'MISSION_DELETED' && evt.mission_id) {
        setMissions((prev) => prev.filter((m) => m.id !== evt.mission_id))
      } else if (evt.mission) {
        setMissions((prev) => {
          const idx = prev.findIndex((m) => m.id === evt.mission!.id)
          if (idx === -1) return [...prev, evt.mission!]
          const next = [...prev]; next[idx] = evt.mission!
          return next
        })
      }
      const described = describeDomainEvent(evt)
      if (described) setFeed((f) => [{ id: newFeedId(), ...described, at: Date.now() }, ...f].slice(0, 40))
    })
    return () => {
      unsubscribe()
      if (refetchTimer.current) clearTimeout(refetchTimer.current)
    }
  }, [fetchAgents])

  const handleAutoRun = useCallback(async () => {
    if (!autoQuery.trim()) return
    setAutoRunning(true); setAutoResult(null)
    try {
      const res = await autoRouteAgent(autoQuery)
      const route = res.routed_to ?? res.agent_key ?? '?'
      setAutoResult(res.success ? `Routed to ${route} — ${summarizeResult(res)}` : `Error (${route}): ${res.error}`)
    } finally { setAutoRunning(false); fetchAgents() }
  }, [autoQuery, fetchAgents])

  const filteredAgents = useMemo(() => (data?.agents ?? []).filter((a) =>
    !filter ||
    a.name.toLowerCase().includes(filter.toLowerCase()) ||
    a.domain.toLowerCase().includes(filter.toLowerCase()) ||
    a.specializations.some((s) => s.toLowerCase().includes(filter.toLowerCase())),
  ), [data, filter])

  const grouped = useMemo(() => {
    const map = new Map<string, AgentInfo[]>()
    for (const a of filteredAgents) {
      const cat = categoryFor(a.domain)
      if (!map.has(cat)) map.set(cat, [])
      map.get(cat)!.push(a)
    }
    for (const list of map.values()) {
      list.sort((a, b) => (a.status === 'online' ? 0 : 1) - (b.status === 'online' ? 0 : 1) || b.load - a.load)
    }
    return map
  }, [filteredAgents])

  // Real cross-reference: the mission (if any) currently keeping an agent
  // busy -- assigned to it and not yet archived/cancelled, most recent wins.
  const currentMissionByAgent = useMemo(() => {
    const map = new Map<string, Mission>()
    for (const m of missions) {
      if (!m.assigned_agent || m.cancelled || m.stage === 'archive') continue
      const existing = map.get(m.assigned_agent)
      if (!existing || m.updated_at > existing.updated_at) map.set(m.assigned_agent, m)
    }
    return map
  }, [missions])

  const selectedAgent = selectedAgentKey ? (data?.agents.find((a) => a.key === selectedAgentKey) ?? null) : null

  const selectAgent = (agent: AgentInfo) => {
    setSelectedAgentKey((prev) => (prev === agent.key ? null : agent.key))
  }

  const handleTaskResult = useCallback((agentKey: string, res: AgentResult) => {
    setSessionRuns((prev) => [{ agentKey, text: summarizeResult(res), success: res.success, at: Date.now() }, ...prev].slice(0, 40))
  }, [])

  const stats = data?.stats
  const activeMissions = missions.filter((m) => m.stage !== 'archive' && !m.cancelled)

  return (
    <div className="relative mx-auto flex max-w-[1680px] flex-col gap-6">
      <AmbientField />

      <OverviewStrip
        agentsOnline={stats?.agents_online ?? null}
        agentsTotal={data?.total ?? null}
        totalTasks={stats?.total_tasks ?? null}
        successRate={stats?.success_rate ?? null}
        activeMissions={activeMissions.length}
        error={error}
        loading={loading}
        lastRefresh={lastRefresh}
        onRefresh={() => { fetchAgents(); fetchMissions() }}
      />

      <HealthBand health={health} llm={llm} />

      {/* AI Fleet */}
      <section className="flex flex-col gap-4">
        <SectionHeading icon={Sparkles} label="AI Fleet" sub="Grouped by domain — every card is a real, currently-initialised agent" />

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[200px] flex-1">
            <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Search agents, domains, specializations…"
              className="glass-surface w-full rounded-xl py-2 pl-9 pr-3 text-[0.7rem] text-foreground outline-none transition-colors focus:border-primary/50"
            />
          </div>
          <button
            type="button"
            onClick={() => setActiveCategory(null)}
            className={cn(
              'rounded-full border px-3 py-1.5 text-[0.62rem] transition-all',
              activeCategory === null ? 'border-primary/60 bg-primary/10 text-primary' : 'border-border/50 text-muted-foreground hover:border-primary/30 hover:text-foreground',
            )}
          >
            All · {filteredAgents.length}
          </button>
          {AGENT_CATEGORIES.map((cat) => {
            const items = grouped.get(cat.label) ?? []
            if (items.length === 0) return null
            const active = activeCategory === cat.label
            return (
              <button
                key={cat.label}
                type="button"
                onClick={() => setActiveCategory((c) => (c === cat.label ? null : cat.label))}
                className={cn('flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[0.62rem] transition-all',
                  active ? 'text-foreground' : 'border-border/50 text-muted-foreground hover:text-foreground')}
                style={active ? { borderColor: `${cat.color}`, background: `color-mix(in oklch, ${cat.color} 14%, transparent)` } : undefined}
              >
                <cat.icon className="h-3 w-3" style={{ color: cat.color }} />
                {cat.label} · {items.length}
              </button>
            )
          })}
        </div>

        <div className="flex flex-col gap-5 xl:flex-row xl:items-start">
          <div className="flex min-w-0 flex-1 flex-col gap-5">
            {loading && !data ? (
              <div className="glass-surface flex items-center justify-center rounded-2xl py-16 text-[0.65rem] text-muted-foreground">
                <RefreshCw className="mr-2 h-4 w-4 animate-spin" /> Establishing uplink to the fleet…
              </div>
            ) : error && !data ? (
              <div className="glass-surface flex flex-col items-center gap-2 rounded-2xl py-12 text-center text-[0.65rem] text-destructive">
                <span>{error}</span>
                <button onClick={fetchAgents} className="text-primary underline underline-offset-2">retry</button>
              </div>
            ) : filteredAgents.length === 0 ? (
              <div className="glass-surface flex items-center justify-center rounded-2xl py-16 text-[0.65rem] text-muted-foreground">No agents match.</div>
            ) : (
              AGENT_CATEGORIES.filter((cat) => (activeCategory === null || activeCategory === cat.label) && (grouped.get(cat.label)?.length ?? 0) > 0).map((cat) => (
                <CategoryCluster
                  key={cat.label}
                  category={cat}
                  agents={grouped.get(cat.label) ?? []}
                  selectedKey={selectedAgentKey}
                  currentMissionByAgent={currentMissionByAgent}
                  onSelect={selectAgent}
                />
              ))
            )}

            {/* Relationship Graph */}
            <RelationshipGraph agents={data?.agents ?? []} missions={missions} onSelectAgentKey={setSelectedAgentKey} />

            {/* Live Activity */}
            <LiveActivity feed={feed} />
          </div>

          {/* Inspector — persistent right rail alongside Fleet/Graph/Activity */}
          <div className="xl:sticky xl:top-4 xl:w-[360px] xl:shrink-0" style={{ perspective: 1000 }}>
            <AnimatePresence mode="wait">
              {selectedAgent ? (
                <InspectorPanel
                  key={selectedAgent.key}
                  agent={selectedAgent}
                  mission={currentMissionByAgent.get(selectedAgent.key)}
                  runs={sessionRuns.filter((r) => r.agentKey === selectedAgent.key)}
                  onRunTask={() => setTaskAgent(selectedAgent)}
                  onClose={() => setSelectedAgentKey(null)}
                />
              ) : (
                <motion.div
                  key="empty"
                  initial={{ opacity: 0, x: 24 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 24 }}
                  transition={{ duration: 0.25, ease: 'easeOut' }}
                  className="flex flex-col gap-3"
                >
                  <div className="glass-surface rounded-2xl p-4">
                    <h3 className="mb-1 flex items-center gap-1.5 font-heading text-[0.68rem] text-foreground">
                      <Zap className="h-3.5 w-3.5 text-primary" /> Auto-route
                    </h3>
                    <p className="mb-2.5 text-[0.58rem] text-muted-foreground">Ask anything — Nancy picks the right specialist.</p>
                    <div className="flex gap-1.5">
                      <input
                        value={autoQuery}
                        onChange={(e) => setAutoQuery(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleAutoRun()}
                        placeholder="e.g. analyse BTC volatility…"
                        className="flex-1 rounded-lg border border-border/60 bg-background/50 px-2.5 py-1.5 text-[0.65rem] text-foreground outline-none focus:border-primary/60"
                      />
                      <button type="button" onClick={handleAutoRun} disabled={autoRunning}
                        className="rounded-lg border border-primary/50 bg-primary/10 px-2.5 py-1.5 text-primary transition-colors hover:bg-primary/20 disabled:opacity-50">
                        {autoRunning ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Zap className="h-3.5 w-3.5" />}
                      </button>
                    </div>
                    {autoResult && (
                      <p className="mt-2 rounded-lg border border-border/50 bg-background/40 px-2.5 py-2 text-[0.55rem] leading-relaxed text-muted-foreground">{autoResult}</p>
                    )}
                  </div>
                  <div className="glass-surface rounded-2xl p-4">
                    <h3 className="mb-2 flex items-center gap-1.5 font-heading text-[0.68rem] text-foreground">
                      <Gauge className="h-3.5 w-3.5 text-primary" /> Fleet load
                    </h3>
                    <FleetLoadChart agents={data?.agents ?? []} />
                  </div>
                  <p className="px-1 text-[0.58rem] text-muted-foreground">Select an agent to see full telemetry and run a task.</p>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </section>

      {taskAgent && (
        <AgentTaskModal
          agent={taskAgent}
          onClose={() => { setTaskAgent(null); fetchAgents() }}
          onResult={(res) => handleTaskResult(taskAgent.key, res)}
        />
      )}
    </div>
  )
}

/* ─── Shared section heading ─────────────────────────────────────────── */
function SectionHeading({ icon: Icon, label, sub }: { icon: typeof Sparkles; label: string; sub?: string }) {
  return (
    <div className="flex items-center gap-2.5 px-1">
      <Icon className="h-4 w-4 text-primary" />
      <h2 className="font-heading text-[0.8rem] text-foreground">{label}</h2>
      {sub && <span className="hidden text-[0.58rem] text-muted-foreground sm:inline">— {sub}</span>}
    </div>
  )
}

/* ─── Mission Overview — hero strip ──────────────────────────────────── */
function OverviewStrip({
  agentsOnline, agentsTotal, totalTasks, successRate, activeMissions, error, loading, lastRefresh, onRefresh,
}: {
  agentsOnline: number | null
  agentsTotal: number | null
  totalTasks: number | null
  successRate: number | null
  activeMissions: number
  error: string | null
  loading: boolean
  lastRefresh: Date
  onRefresh: () => void
}) {
  return (
    <section className="glass-surface relative overflow-hidden rounded-2xl px-6 py-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className={cn('flex h-10 w-10 items-center justify-center rounded-full', error ? 'bg-destructive/15' : 'bg-primary/15')}>
            <Rocket className={cn('h-4.5 w-4.5', error ? 'text-destructive' : 'text-primary animate-hud-pulse')} />
          </span>
          <div>
            <h1 className="font-display text-xl text-foreground">Mission Control</h1>
            <p className="text-[0.62rem] text-muted-foreground">
              {error ? 'connection lost' : `Supervising the fleet · synced ${lastRefresh.toLocaleTimeString('en-GB')}`}
            </p>
          </div>
        </div>
        <button type="button" onClick={onRefresh} disabled={loading} className="flex items-center gap-1.5 rounded-lg border border-border/50 px-2.5 py-1.5 text-[0.6rem] text-muted-foreground transition-colors hover:text-primary">
          <RefreshCw className={cn('h-3 w-3', loading && 'animate-spin')} /> Refresh
        </button>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <OverviewStat label="Agents online" value={agentsOnline} suffix={agentsTotal != null ? `/${agentsTotal}` : undefined} tone="primary" />
        <OverviewStat label="Missions in flight" value={activeMissions} tone="gold" />
        <OverviewStat label="Tasks executed" value={totalTasks} tone="foreground" />
        <OverviewStat label="Success rate" value={successRate != null ? Math.round(successRate * 100) : null} suffix="%" tone="accent" />
      </div>
    </section>
  )
}

function OverviewStat({ label, value, suffix, tone }: { label: string; value: number | null; suffix?: string; tone: 'primary' | 'gold' | 'foreground' | 'accent' }) {
  const toneClass = { primary: 'text-primary', gold: 'text-gold', foreground: 'text-foreground', accent: 'text-accent' }[tone]
  return (
    <div className="rounded-xl border border-border/40 bg-secondary/10 px-3.5 py-3">
      <div className={cn('font-display text-2xl', toneClass)}>{value ?? '—'}{value != null && suffix}</div>
      <div className="mt-0.5 text-[0.55rem] uppercase tracking-wide text-muted-foreground">{label}</div>
    </div>
  )
}

/* ─── Operational Health ─────────────────────────────────────────────── */
function HealthBand({
  health, llm,
}: {
  health: { cpu: number | null; memory: number | null; disk: number | null; networkPercent: number | null; tempC: number | null }
  llm: { backends: { name: string; model?: string }[]; primary_model: string | null } | null | undefined
}) {
  const tiles = [
    { icon: Cpu, label: 'CPU', value: health.cpu },
    { icon: HeartPulse, label: 'Memory', value: health.memory },
    { icon: HardDrive, label: 'Disk', value: health.disk },
    { icon: Wifi, label: 'Network', value: health.networkPercent },
  ]
  return (
    <section className="flex flex-col gap-3">
      <SectionHeading icon={HeartPulse} label="Operational Health" sub="Real psutil-backed system telemetry + reasoning chain" />
      <div className="glass-surface grid grid-cols-2 gap-3 rounded-2xl p-4 sm:grid-cols-4 lg:grid-cols-5">
        {tiles.map(({ icon: Icon, label, value }) => (
          <div key={label} className="flex items-center gap-2.5">
            <Icon className="h-4 w-4 shrink-0 text-primary" />
            <div className="min-w-0 flex-1">
              <div className="text-[0.8rem] text-foreground">{value != null ? `${value.toFixed(0)}%` : '…'}</div>
              <div className="h-1 overflow-hidden rounded-full bg-secondary/50">
                <div className="h-full rounded-full bg-primary transition-all duration-700" style={{ width: `${Math.min(100, value ?? 0)}%` }} />
              </div>
              <div className="mt-0.5 text-[0.46rem] text-muted-foreground">{label}</div>
            </div>
          </div>
        ))}
        <div className="col-span-2 flex items-center gap-2.5 border-t border-border/30 pt-3 sm:col-span-4 sm:border-t-0 sm:border-l sm:pl-4 sm:pt-0 lg:col-span-1">
          <Zap className="h-4 w-4 shrink-0 text-tertiary" />
          <div className="min-w-0 flex-1">
            <div className="truncate text-[0.68rem] text-foreground">{llm?.primary_model ?? '…'}</div>
            <div className="text-[0.46rem] text-muted-foreground">{llm ? `${llm.backends.length} reasoning backend${llm.backends.length !== 1 ? 's' : ''} live` : 'reading chain…'}</div>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ─── Category cluster: glass container + hub-and-spoke connector rail ── */
function CategoryCluster({
  category, agents, selectedKey, currentMissionByAgent, onSelect,
}: {
  category: (typeof AGENT_CATEGORIES)[number]
  agents: AgentInfo[]
  selectedKey: string | null
  currentMissionByAgent: Map<string, Mission>
  onSelect: (a: AgentInfo) => void
}) {
  const avgLoad = agents.length ? Math.round(agents.reduce((s, a) => s + a.load, 0) / agents.length) : 0
  const onlineCount = agents.filter((a) => a.status === 'online' || a.status === 'executing').length

  return (
    <motion.section
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: 'easeOut' }}
      className="glass-surface rounded-2xl p-4"
    >
      <header className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <span
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
            style={{ background: `color-mix(in oklch, ${category.color} 18%, var(--background))`, boxShadow: `0 0 0 1px color-mix(in oklch, ${category.color} 35%, transparent)` }}
          >
            <category.icon className="h-4 w-4" style={{ color: category.color }} />
          </span>
          <div>
            <h3 className="font-heading text-[0.72rem] text-foreground">{category.label}</h3>
            <p className="text-[0.55rem] text-muted-foreground">{onlineCount}/{agents.length} online · avg load {avgLoad}%</p>
          </div>
        </div>
        <div className="h-1 w-24 overflow-hidden rounded-full bg-secondary/50">
          <div className="h-full rounded-full transition-all duration-700" style={{ width: `${avgLoad}%`, background: category.color }} />
        </div>
      </header>

      {/* hub rail — the visible "this is a group" line, not a live-collab claim */}
      <div className="relative mb-1 h-px w-full" style={{ background: `linear-gradient(90deg, transparent, color-mix(in oklch, ${category.color} 45%, transparent), transparent)` }} />

      <div className="grid grid-cols-1 gap-3 pt-3 sm:grid-cols-2 xl:grid-cols-3" style={{ perspective: 900 }}>
        {agents.map((agent) => (
          <div key={agent.key} className="relative">
            <span
              aria-hidden
              className="absolute -top-3 left-1/2 h-3 w-px -translate-x-1/2 animate-flow-dash-vertical"
              style={{ background: `repeating-linear-gradient(to bottom, color-mix(in oklch, ${category.color} 70%, transparent) 0 3px, transparent 3px 6px)` }}
            />
            <AgentCard
              agent={agent}
              color={category.color}
              selected={selectedKey === agent.key}
              currentMission={currentMissionByAgent.get(agent.key)}
              onSelect={() => onSelect(agent)}
            />
          </div>
        ))}
      </div>
    </motion.section>
  )
}

/* ─── Agent card — an entity, not a row: no inline action button, click
   anywhere to open the Inspector, where "Run task" lives as the one real
   primary action ─────────────────────────────────────────────────────── */
function AgentCard({
  agent, color, selected, currentMission, onSelect,
}: {
  agent: AgentInfo
  color: string
  selected: boolean
  currentMission?: Mission
  onSelect: () => void
}) {
  const Icon = iconFor(agent.domain)
  const isOnline = agent.status === 'online'
  const isOffline = agent.status === 'offline'
  const isExecuting = agent.status === 'executing'

  return (
    <SnakeBorder state={snakeStateForAgent(agent.status)} radiusClassName="rounded-[18px]">
      <motion.button
        type="button"
        layout
        onClick={onSelect}
        whileHover={isOffline ? undefined : { y: -4, rotateX: 3, rotateY: -3, scale: 1.01 }}
        whileTap={isOffline ? undefined : { scale: 0.99 }}
        transition={{ type: 'spring', stiffness: 300, damping: 22 }}
        className={cn(
          'group relative flex w-full flex-col gap-2.5 rounded-[18px] p-3.5 text-left transition-colors duration-200',
          'glass-surface',
          isOffline && 'opacity-45',
          selected ? 'animate-card-border-breathe' : 'hover:border-primary/25',
        )}
        style={selected ? { borderColor: 'color-mix(in oklch, var(--hud) 40%, transparent)' } : undefined}
      >
        <div className="flex items-center gap-2.5">
          <span className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-full" style={{ background: `color-mix(in oklch, ${color} 22%, var(--background))` }}>
            {isOnline && (
              <span className="absolute inset-0 rounded-full animate-hud-pulse" style={{ boxShadow: `0 0 0 1px color-mix(in oklch, ${color} 55%, transparent)` }} />
            )}
            <Icon className="h-4.5 w-4.5" style={{ color }} />
          </span>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[0.72rem] font-medium text-foreground">{agent.name}</div>
            <div className="truncate text-[0.55rem] text-muted-foreground">
              {isExecuting && agent.current_task_type ? `running ${agent.current_task_type}…` : (agent.role || agent.domain)}
            </div>
          </div>
          <span className={cn('flex shrink-0 items-center gap-1 text-[0.5rem]', STATUS_COLOR[agent.status])}>
            <span className={cn('h-1.5 w-1.5 rounded-full', (isOnline || isExecuting) && 'animate-hud-pulse', STATUS_DOT[agent.status])} />
            {agent.status}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <div className="h-1 flex-1 overflow-hidden rounded-full bg-secondary/50">
            <div className="h-full rounded-full transition-all duration-700" style={{ width: `${Math.min(100, agent.load)}%`, background: isOnline ? color : 'var(--muted-foreground)' }} />
          </div>
          <span className="shrink-0 text-[0.5rem] text-muted-foreground">{agent.load}%</span>
        </div>

        {currentMission && (
          <div className="flex items-center gap-1.5 rounded-lg border border-border/40 bg-secondary/20 px-2 py-1">
            <Waypoints className="h-3 w-3 shrink-0 text-primary" />
            <span className="truncate text-[0.5rem] text-foreground">{currentMission.title}</span>
            <span className="ml-auto shrink-0 text-[0.44rem] text-muted-foreground">{STAGE_LABELS[currentMission.stage]}</span>
          </div>
        )}

        {agent.specializations.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {agent.specializations.slice(0, 3).map((s) => (
              <span key={s} className="rounded-md border border-border/40 bg-secondary/40 px-1.5 py-0.5 text-[0.46rem] text-muted-foreground">{s}</span>
            ))}
            {agent.specializations.length > 3 && (
              <span className="text-[0.46rem] text-muted-foreground/70">+{agent.specializations.length - 3}</span>
            )}
          </div>
        )}

        <div className="flex items-center justify-between border-t border-border/30 pt-2 text-[0.5rem] text-muted-foreground">
          <span>{agent.total_tasks} tasks · {(agent.confidence * 100).toFixed(0)}% conf</span>
          <ChevronRight className={cn('h-3 w-3 shrink-0 transition-transform', selected && 'rotate-90')} />
        </div>
      </motion.button>
    </SnakeBorder>
  )
}

/* ─── Relationship Graph — real edges derived from mission dependencies
   that span two different agents. No edge without a real dependency; no
   claim of live collaboration without a real in-flight execution. ──────── */
function RelationshipGraph({
  agents, missions, onSelectAgentKey,
}: {
  agents: AgentInfo[]
  missions: Mission[]
  onSelectAgentKey: (key: string) => void
}) {
  const { nodes, edges } = useMemo(() => {
    const missionById = new Map(missions.map((m) => [m.id, m]))
    const edgeMap = new Map<string, { from: string; to: string; active: boolean }>()
    for (const m of missions) {
      if (!m.assigned_agent) continue
      for (const depId of m.dependencies) {
        const dep = missionById.get(depId)
        if (!dep || !dep.assigned_agent || dep.assigned_agent === m.assigned_agent) continue
        const key = `${dep.assigned_agent}→${m.assigned_agent}`
        const active = dep.stage === 'execution' || m.stage === 'execution'
        const existing = edgeMap.get(key)
        if (!existing || (active && !existing.active)) edgeMap.set(key, { from: dep.assigned_agent, to: m.assigned_agent, active })
      }
    }
    const edgeList = Array.from(edgeMap.values())
    const nodeKeys = Array.from(new Set(edgeList.flatMap((e) => [e.from, e.to])))
    const nodeList = nodeKeys
      .map((key) => agents.find((a) => a.key === key))
      .filter((a): a is AgentInfo => !!a)
    return { nodes: nodeList, edges: edgeList }
  }, [agents, missions])

  const size = 460
  const cx = size / 2
  const cy = size / 2
  const r = size / 2 - 64
  const positions = useMemo(() => {
    const map = new Map<string, { x: number; y: number }>()
    nodes.forEach((n, i) => {
      const angle = (i / Math.max(1, nodes.length)) * Math.PI * 2 - Math.PI / 2
      map.set(n.key, { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) })
    })
    return map
  }, [nodes, cx, cy, r])

  return (
    <section className="glass-surface flex flex-col gap-3 rounded-2xl p-4">
      <SectionHeading icon={Waypoints} label="Relationship Graph" sub="Real agent-to-agent links, derived from mission dependencies" />

      {nodes.length === 0 ? (
        <div className="flex flex-col items-center gap-1.5 rounded-xl border border-dashed border-border/50 py-10 text-center">
          <Link2 className="h-5 w-5 text-muted-foreground" />
          <p className="text-[0.62rem] text-muted-foreground">No active agent dependencies right now.</p>
          <p className="max-w-xs text-[0.52rem] text-muted-foreground/70">Link missions with dependencies in the Workflow Orchestrator to see the agents behind them connect here.</p>
        </div>
      ) : (
        <div className="mx-auto w-full max-w-[460px]">
          <svg viewBox={`0 0 ${size} ${size}`} className="w-full">
            {edges.map((e, i) => {
              const from = positions.get(e.from); const to = positions.get(e.to)
              if (!from || !to) return null
              const pathId = `mc-edge-${i}`
              return (
                <g key={pathId}>
                  <path
                    id={pathId}
                    d={`M ${from.x} ${from.y} L ${to.x} ${to.y}`}
                    stroke={e.active ? 'var(--hud)' : 'var(--border)'}
                    strokeWidth={e.active ? 1.5 : 1}
                    fill="none"
                    opacity={e.active ? 0.8 : 0.4}
                  />
                  {e.active && (
                    <circle r={3} fill="var(--gold)">
                      <animateMotion dur="1.8s" repeatCount="indefinite">
                        <mpath href={`#${pathId}`} />
                      </animateMotion>
                    </circle>
                  )}
                </g>
              )
            })}
            {nodes.map((n) => {
              const pos = positions.get(n.key)
              if (!pos) return null
              const color = colorFor(n.domain)
              const Icon = iconFor(n.domain)
              return (
                <foreignObject key={n.key} x={pos.x - 26} y={pos.y - 26} width={52} height={52}>
                  <button
                    type="button"
                    onClick={() => onSelectAgentKey(n.key)}
                    title={n.name}
                    className="flex h-[52px] w-[52px] items-center justify-center rounded-full border transition-transform hover:scale-110"
                    style={{ background: `color-mix(in oklch, ${color} 20%, var(--surface-2))`, borderColor: `color-mix(in oklch, ${color} 45%, transparent)` }}
                  >
                    <Icon className="h-5 w-5" style={{ color }} />
                  </button>
                </foreignObject>
              )
            })}
          </svg>
        </div>
      )}
    </section>
  )
}

/* ─── Live Activity — real event stream, agent-focused ───────────────── */
function LiveActivity({ feed }: { feed: FeedItem[] }) {
  return (
    <section className="glass-surface flex flex-col gap-3 rounded-2xl p-4">
      <div className="flex items-center justify-between">
        <SectionHeading icon={Radio} label="Live Activity" />
        <span className="flex items-center gap-1 text-[0.5rem] text-primary"><span className="h-1.5 w-1.5 animate-hud-pulse rounded-full bg-primary" /> LIVE</span>
      </div>
      {feed.length === 0 ? (
        <p className="py-6 text-center text-[0.55rem] text-muted-foreground">No activity yet — real fleet events will stream in here.</p>
      ) : (
        <div className="flex max-h-64 flex-col gap-1.5 overflow-y-auto">
          {feed.map((e) => (
            <div key={e.id} className={cn(
              'flex items-center justify-between gap-2 rounded-lg border px-2.5 py-1.5 text-[0.55rem]',
              e.tone === 'ok' ? 'border-primary/25 bg-primary/5' : e.tone === 'error' ? 'border-destructive/25 bg-destructive/5' : 'border-border/40 bg-secondary/20',
            )}>
              <span className="text-foreground">{e.text}</span>
              <span className="shrink-0 text-[0.45rem] text-muted-foreground">{new Date(e.at).toLocaleTimeString('en-GB')}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

/* ─── Right inspector drawer ─────────────────────────────────────────── */
function InspectorPanel({
  agent, mission, runs, onRunTask, onClose,
}: {
  agent: AgentInfo
  mission?: Mission
  runs: { text: string; success: boolean; at: number }[]
  onRunTask: () => void
  onClose: () => void
}) {
  const Icon = iconFor(agent.domain)
  const color = colorFor(agent.domain)

  return (
    <motion.div
      initial={{ opacity: 0, x: 24 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 24 }}
      transition={{ duration: 0.25, ease: 'easeOut' }}
      className="glass-surface flex flex-col gap-3.5 rounded-2xl p-4"
    >
      <div className="flex items-start gap-3">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full" style={{ background: `color-mix(in oklch, ${color} 20%, var(--background))` }}>
          <Icon className="h-5 w-5" style={{ color }} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm text-foreground">{agent.name}</div>
          <div className="truncate text-[0.58rem] text-muted-foreground">{agent.domain} · {categoryFor(agent.domain)}</div>
        </div>
        <button type="button" onClick={onClose} className="shrink-0 text-muted-foreground hover:text-foreground" aria-label="Close inspector">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      <p className="text-[0.62rem] leading-relaxed text-muted-foreground">
        {agent.description || `${agent.role || 'Specialist agent'} handling ${agent.domain.replace(/-/g, ' ')} tasks.`}
      </p>

      {agent.status === 'executing' && agent.current_task_type && (
        <div className="flex items-center gap-1.5 rounded-lg border border-gold/30 bg-gold/5 px-2.5 py-1.5 text-[0.58rem] text-gold">
          <Activity className="h-3 w-3 animate-hud-pulse" /> live — running <span className="font-medium">{agent.current_task_type}</span>
        </div>
      )}

      {mission && (
        <div className="rounded-xl border border-primary/25 bg-primary/5 p-3">
          <div className="mb-1 flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5 text-[0.6rem] font-medium text-foreground"><Waypoints className="h-3 w-3 text-primary" /> {mission.title}</span>
            <span className="shrink-0 rounded-full border border-primary/40 px-1.5 py-0.5 text-[0.46rem] text-primary">{STAGE_LABELS[mission.stage]}</span>
          </div>
          {mission.dependencies.length > 0 && (
            <p className="text-[0.5rem] text-muted-foreground">{mission.dependencies.length} dependenc{mission.dependencies.length === 1 ? 'y' : 'ies'}</p>
          )}
        </div>
      )}

      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="rounded-xl border border-border/40 bg-secondary/20 py-2">
          <div className="text-sm text-foreground">{agent.total_tasks}</div>
          <div className="text-[0.46rem] text-muted-foreground">tasks</div>
        </div>
        <div className="rounded-xl border border-border/40 bg-secondary/20 py-2">
          <div className="text-sm text-accent">{(agent.confidence * 100).toFixed(0)}%</div>
          <div className="text-[0.46rem] text-muted-foreground">confidence</div>
        </div>
        <div className="rounded-xl border border-border/40 bg-secondary/20 py-2">
          <div className="text-sm" style={{ color }}>{agent.load}%</div>
          <div className="text-[0.46rem] text-muted-foreground">load</div>
        </div>
      </div>

      {((agent.mode && agent.mode !== 'production') || agent.hardware_connected === false) && (
        <div className="flex flex-wrap gap-1">
          {agent.mode && agent.mode !== 'production' && (
            <span className="rounded-md border border-accent/40 bg-accent/10 px-1.5 py-0.5 text-[0.48rem] text-accent">{agent.mode.replace(/_/g, ' ')}</span>
          )}
          {agent.hardware_connected === false && (
            <span className="rounded-md border border-accent/40 bg-accent/10 px-1.5 py-0.5 text-[0.48rem] text-accent">no hardware attached</span>
          )}
        </div>
      )}

      {agent.specializations.length > 0 && (
        <div>
          <h4 className="mb-1.5 text-[0.55rem] uppercase tracking-wide text-muted-foreground">Capabilities</h4>
          <div className="flex flex-wrap gap-1">
            {agent.specializations.map((s) => (
              <span key={s} className="rounded-md border border-border/40 bg-secondary/40 px-1.5 py-0.5 text-[0.48rem] text-muted-foreground">{s}</span>
            ))}
          </div>
        </div>
      )}

      <button
        type="button"
        onClick={onRunTask}
        disabled={agent.status === 'offline'}
        className="flex items-center justify-center gap-1.5 rounded-xl border border-primary bg-primary/15 py-2.5 text-xs text-primary transition-colors hover:bg-primary/25 disabled:cursor-not-allowed disabled:opacity-40"
      >
        <Play className="h-3.5 w-3.5" /> Run task
      </button>

      <div>
        <h4 className="mb-1.5 flex items-center gap-1.5 text-[0.55rem] uppercase tracking-wide text-muted-foreground">
          <Activity className="h-3 w-3" /> This session
        </h4>
        {runs.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border/50 px-2.5 py-3 text-center text-[0.55rem] text-muted-foreground">No runs yet this session.</p>
        ) : (
          <div className="flex max-h-48 flex-col gap-1.5 overflow-y-auto">
            {runs.map((r, i) => (
              <div key={i} className={cn('flex items-start gap-1.5 rounded-lg border px-2 py-1.5 text-[0.55rem]', r.success ? 'border-primary/25 bg-primary/5 text-foreground' : 'border-destructive/25 bg-destructive/5 text-destructive')}>
                {r.success ? <CheckCircle2 className="mt-px h-3 w-3 shrink-0 text-primary" /> : <XCircle className="mt-px h-3 w-3 shrink-0" />}
                <span className="line-clamp-2 flex-1">{r.text}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  )
}

/* ─── Fleet load chart — shown in the inspector's empty state ──────────── */
function FleetLoadChart({ agents }: { agents: AgentInfo[] }) {
  const bars = useMemo(
    () => agents
      .filter((a) => a.status !== 'offline')
      .sort((a, b) => b.load - a.load)
      .slice(0, 10)
      .map((a) => ({ label: a.name, load: Math.min(100, a.load) })),
    [agents],
  )
  if (bars.length === 0) {
    return <div className="flex h-24 items-center justify-center text-[0.58rem] text-muted-foreground"><Sparkles className="mr-1.5 h-3.5 w-3.5" /> No agents online.</div>
  }
  return (
    <div className="h-24 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={bars} margin={{ top: 4, right: 4, bottom: 0, left: -28 }}>
          <XAxis dataKey="label" hide />
          <YAxis domain={[0, 100]} width={28} tick={{ fontSize: 9, fill: 'var(--muted-foreground)' }} />
          <Tooltip
            contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8, fontSize: '0.6rem' }}
            labelStyle={{ color: 'var(--foreground)' }}
          />
          <Bar dataKey="load" name="load" radius={[3, 3, 0, 0]} fill="var(--hud)" isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
