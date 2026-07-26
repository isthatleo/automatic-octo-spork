'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { cn } from '@/lib/utils'
import { AgentTaskModal } from './agent-task-modal'
import { listAgents, autoRouteAgent, summarizeResult, type AgentListResponse } from '@/lib/nancy/agent-client'
import { onDomainEvent } from '@/lib/nancy/ws-client'
import type { AgentInfo } from '@/lib/nancy/types'
import { AGENT_CATEGORIES, categoryFor, colorFor, iconFor } from '@/lib/nancy/agent-taxonomy'
import { ArrowRight, RotateCw } from 'lucide-react'

/* ═══════════════════════════════════════════════════════════════════════
   AGENTS — a real fleet registry, deliberately built as its own visual
   system instead of reusing the app's shared glass/rounded-card language:
   square-cut monospace ID tiles, a top color strip instead of a glowing
   border, hard-edged corner brackets on hover instead of a pulse. Every
   number is real (/agents/list, live over the WebSocket domain-event
   bridge); nothing here is decorative data.
   ═══════════════════════════════════════════════════════════════════════ */

const STATUS_LABEL: Record<string, string> = {
  online: 'ONLINE', executing: 'ACTIVE', idle: 'IDLE', training: 'TRAINING', offline: 'OFFLINE', error: 'ERROR',
}
const STATUS_HEX: Record<string, string> = {
  online: 'var(--success)', executing: 'var(--gold)', idle: 'var(--muted-foreground)',
  training: 'var(--accent)', offline: 'var(--destructive)', error: 'var(--destructive)',
}

export function MissionControlPanel() {
  const [data, setData] = useState<AgentListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState('')
  const [activeCategory, setActiveCategory] = useState<string | null>(null)
  const [taskAgent, setTaskAgent] = useState<AgentInfo | null>(null)
  const [autoQuery, setAutoQuery] = useState('')
  const [autoRunning, setAutoRunning] = useState(false)
  const [autoResult, setAutoResult] = useState<string | null>(null)

  const fetchAgents = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const res = await listAgents()
      setData(res)
    } catch (e) { setError(String(e)) } finally { setLoading(false) }
  }, [])

  useEffect(() => {
    fetchAgents()
    const t = setInterval(fetchAgents, 60_000)
    return () => clearInterval(t)
  }, [fetchAgents])

  useEffect(() => onDomainEvent((evt) => {
    if (evt.type.startsWith('AGENT_')) fetchAgents()
  }), [fetchAgents])

  const handleAutoRun = useCallback(async () => {
    if (!autoQuery.trim()) return
    setAutoRunning(true); setAutoResult(null)
    try {
      const res = await autoRouteAgent(autoQuery)
      const route = res.routed_to ?? res.agent_key ?? '?'
      setAutoResult(res.success ? `→ ${route} :: ${summarizeResult(res)}` : `✕ ${route} :: ${res.error}`)
    } finally { setAutoRunning(false); fetchAgents() }
  }, [autoQuery, fetchAgents])

  const filteredAgents = useMemo(() => (data?.agents ?? []).filter((a) => {
    if (activeCategory && categoryFor(a.domain) !== activeCategory) return false
    if (!filter) return true
    const q = filter.toLowerCase()
    return a.name.toLowerCase().includes(q) || a.domain.toLowerCase().includes(q) || a.specializations.some((s) => s.toLowerCase().includes(q))
  }).sort((a, b) => (a.status === 'offline' ? 1 : 0) - (b.status === 'offline' ? 1 : 0) || b.load - a.load), [data, filter, activeCategory])

  const stats = data?.stats
  const total = data?.total ?? 0

  return (
    <div className="mx-auto flex max-w-[1680px] flex-col gap-5 font-mono">
      {/* ── Registry header ─────────────────────────────────────────── */}
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-foreground/10 pb-4">
        <div>
          <div className="text-[0.55rem] tracking-[0.35em] text-foreground/35">FLEET REGISTRY</div>
          <h1 className="text-xl font-semibold uppercase tracking-wide text-foreground">Agents</h1>
        </div>
        <div className="text-right">
          <div className="text-3xl font-semibold tabular-nums leading-none text-primary">
            {stats?.agents_online ?? '–'}<span className="text-foreground/25">/{total || '–'}</span>
          </div>
          <div className="mt-1 text-[0.5rem] tracking-[0.25em] text-foreground/35">{error ? 'LINK LOST' : 'ONLINE'}</div>
        </div>
      </div>

      {/* ── Console bar: search + auto-route + refresh ──────────────── */}
      <div className="flex flex-col gap-2.5 border-b border-foreground/10 pb-4">
        <div className="flex flex-wrap items-center gap-3 text-[0.68rem]">
          <span className="shrink-0 text-primary">{'>'}</span>
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="search fleet_"
            className="min-w-[160px] flex-1 border-none bg-transparent text-foreground outline-none placeholder:text-foreground/30"
          />
          <button
            type="button"
            onClick={fetchAgents}
            disabled={loading}
            className="flex shrink-0 items-center gap-1.5 border border-foreground/15 px-2.5 py-1 text-[0.58rem] tracking-wide text-foreground/60 transition-colors hover:border-primary/50 hover:text-primary"
          >
            <RotateCw className={cn('h-3 w-3', loading && 'animate-spin')} /> REFRESH
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-[0.68rem]">
          <span className="shrink-0 text-foreground/40">{'route>'}</span>
          <input
            value={autoQuery}
            onChange={(e) => setAutoQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAutoRun()}
            placeholder="ask anything — auto-dispatch to the right specialist_"
            className="min-w-[160px] flex-1 border-none bg-transparent text-foreground outline-none placeholder:text-foreground/30"
          />
          <button
            type="button"
            onClick={handleAutoRun}
            disabled={autoRunning || !autoQuery.trim()}
            className="flex shrink-0 items-center gap-1.5 border border-primary/40 bg-primary/10 px-2.5 py-1 text-[0.58rem] tracking-wide text-primary transition-colors hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-30"
          >
            {autoRunning ? <RotateCw className="h-3 w-3 animate-spin" /> : <ArrowRight className="h-3 w-3" />} DISPATCH
          </button>
        </div>
        {autoResult && <p className="border-l-2 border-primary/40 pl-2.5 text-[0.6rem] leading-relaxed text-foreground/60">{autoResult}</p>}
      </div>

      {/* ── Category tabs ────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-x-5 gap-y-2 text-[0.6rem] uppercase tracking-wide">
        <button
          type="button"
          onClick={() => setActiveCategory(null)}
          className={cn(
            'border-b-2 pb-1.5 transition-colors',
            activeCategory === null ? 'border-primary text-foreground' : 'border-transparent text-foreground/40 hover:text-foreground/70',
          )}
        >
          All // {(data?.agents ?? []).length}
        </button>
        {AGENT_CATEGORIES.map((cat) => {
          const count = (data?.agents ?? []).filter((a) => categoryFor(a.domain) === cat.label).length
          if (count === 0) return null
          const active = activeCategory === cat.label
          return (
            <button
              key={cat.label}
              type="button"
              onClick={() => setActiveCategory((c) => (c === cat.label ? null : cat.label))}
              className={cn('border-b-2 pb-1.5 transition-colors', active ? 'text-foreground' : 'border-transparent text-foreground/40 hover:text-foreground/70')}
              style={{ borderColor: active ? cat.color : 'transparent' }}
            >
              {cat.label} // {count}
            </button>
          )
        })}
      </div>

      {/* ── Fleet grid ───────────────────────────────────────────────── */}
      {loading && !data ? (
        <div className="flex items-center justify-center border border-dashed border-foreground/15 py-16 text-[0.65rem] text-foreground/40">
          <RotateCw className="mr-2 h-4 w-4 animate-spin" /> establishing uplink…
        </div>
      ) : error && !data ? (
        <div className="flex flex-col items-center gap-2 border border-dashed border-destructive/30 py-12 text-center text-[0.65rem] text-destructive">
          <span>{error}</span>
          <button onClick={fetchAgents} className="underline underline-offset-2">retry</button>
        </div>
      ) : filteredAgents.length === 0 ? (
        <div className="flex items-center justify-center border border-dashed border-foreground/15 py-16 text-[0.65rem] text-foreground/40">no agents match</div>
      ) : (
        <motion.div layout className="grid grid-cols-2 gap-px bg-foreground/10 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          <AnimatePresence initial={false}>
            {filteredAgents.map((agent, i) => (
              <AgentTile key={agent.key} agent={agent} index={i} onOpen={() => setTaskAgent(agent)} />
            ))}
          </AnimatePresence>
        </motion.div>
      )}

      {taskAgent && (
        <AgentTaskModal
          agent={taskAgent}
          onClose={() => { setTaskAgent(null); fetchAgents() }}
          onResult={() => fetchAgents()}
        />
      )}
    </div>
  )
}

/* ─── Fleet tile — square-cut, top color strip, corner brackets on hover
   instead of a glow. Sits flush against its grid neighbors (1px hairline
   gaps via the parent's bg-foreground/10 + this tile's own bg) for a
   panel/console feel rather than floating cards. ─────────────────────── */
function AgentTile({ agent, index, onOpen }: { agent: AgentInfo; index: number; onOpen: () => void }) {
  const Icon = iconFor(agent.domain)
  const color = colorFor(agent.domain)
  const statusColor = STATUS_HEX[agent.status] ?? 'var(--muted-foreground)'
  const isOffline = agent.status === 'offline'
  const idTag = `AGT-${String(index + 1).padStart(2, '0')}`

  return (
    <motion.button
      type="button"
      layout
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.15 }}
      onClick={onOpen}
      className={cn(
        'group relative flex flex-col gap-2.5 bg-background p-3.5 text-left transition-colors hover:bg-secondary/30',
        isOffline && 'opacity-45 hover:opacity-70',
      )}
    >
      {/* top strip */}
      <span className="absolute inset-x-0 top-0 h-[3px]" style={{ background: color }} />

      {/* corner brackets — sharp, not a glow, fade in on hover/focus only */}
      {(['top-0 left-0 border-t border-l', 'top-0 right-0 border-t border-r', 'bottom-0 left-0 border-b border-l', 'bottom-0 right-0 border-b border-r'] as const).map((pos) => (
        <span
          key={pos}
          aria-hidden
          className={cn('pointer-events-none absolute h-2.5 w-2.5 opacity-0 transition-opacity duration-150 group-hover:opacity-100', pos)}
          style={{ borderColor: color }}
        />
      ))}

      <div className="flex items-center justify-between text-[0.5rem] tracking-[0.1em] text-foreground/30">
        <span>{idTag}</span>
        <span className="flex items-center gap-1" style={{ color: statusColor }}>
          <span className="h-1.5 w-1.5" style={{ background: statusColor }} />
          {STATUS_LABEL[agent.status] ?? agent.status.toUpperCase()}
        </span>
      </div>

      <Icon className="h-6 w-6" style={{ color }} strokeWidth={1.4} />

      <div className="min-w-0">
        <div className="truncate text-[0.72rem] font-semibold uppercase tracking-wide text-foreground">{agent.name}</div>
        <p className="mt-1 line-clamp-2 text-[0.58rem] normal-case leading-snug text-foreground/45">
          {agent.status === 'executing' && agent.current_task_type ? `running ${agent.current_task_type}…` : (agent.description || agent.role || agent.domain.replace(/-/g, ' '))}
        </p>
      </div>

      <div className="mt-auto flex items-center justify-between border-t border-foreground/10 pt-2 text-[0.5rem] tracking-wide text-foreground/35">
        <span>TASKS <span className="text-foreground/70">{agent.total_tasks}</span></span>
        <span>CONF <span className="text-foreground/70">{Math.round(agent.confidence * 100)}%</span></span>
      </div>
    </motion.button>
  )
}
