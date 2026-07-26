'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { cn } from '@/lib/utils'
import { AgentTaskModal } from './agent-task-modal'
import { SnakeBorder, snakeStateForAgent } from './snake-border'
import { listAgents, autoRouteAgent, summarizeResult, type AgentListResponse } from '@/lib/nancy/agent-client'
import { onDomainEvent } from '@/lib/nancy/ws-client'
import type { AgentInfo } from '@/lib/nancy/types'
import { AGENT_CATEGORIES, STATUS_DOT, categoryFor, colorFor, iconFor } from '@/lib/nancy/agent-taxonomy'
import { Search, RefreshCw, Play, Zap, Bot, ChevronRight } from 'lucide-react'

/* ═══════════════════════════════════════════════════════════════════════
   AGENTS — a real ID-card grid of the actual fleet (/agents/list), rebuilt
   as a flat card wall instead of the previous grouped-cluster/graph/
   inspector layout. Every card is one real, currently-initialised agent;
   status/load/task counts come straight from the backend and update live
   over the same WebSocket domain-event bridge the rest of the app uses.
   Click a card to run a real task on it (AgentTaskModal) — the one real
   action this page needs, kept, just no longer living in a permanent
   sidebar.
   ═══════════════════════════════════════════════════════════════════════ */

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
      setAutoResult(res.success ? `Routed to ${route} — ${summarizeResult(res)}` : `Error (${route}): ${res.error}`)
    } finally { setAutoRunning(false); fetchAgents() }
  }, [autoQuery, fetchAgents])

  const filteredAgents = useMemo(() => (data?.agents ?? []).filter((a) => {
    if (activeCategory && categoryFor(a.domain) !== activeCategory) return false
    if (!filter) return true
    const q = filter.toLowerCase()
    return a.name.toLowerCase().includes(q) || a.domain.toLowerCase().includes(q) || a.specializations.some((s) => s.toLowerCase().includes(q))
  }).sort((a, b) => (a.status === 'offline' ? 1 : 0) - (b.status === 'offline' ? 1 : 0) || b.load - a.load), [data, filter, activeCategory])

  const stats = data?.stats

  return (
    <div className="mx-auto flex max-w-[1680px] flex-col gap-5">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-border bg-card/60 px-5 py-4">
        <Bot className="h-5 w-5 text-primary" />
        <div className="flex flex-col">
          <h1 className="font-display text-lg text-foreground">Agents</h1>
          <p className="text-[0.6rem] text-muted-foreground">
            {error ? 'connection lost' : `${stats?.agents_online ?? '…'} / ${data?.total ?? '…'} online`}
          </p>
        </div>
        <div className="relative ml-auto min-w-[200px] flex-1 sm:flex-none sm:w-64">
          <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Search agents…"
            className="w-full rounded-xl border border-border bg-background/60 py-2 pl-9 pr-3 text-[0.7rem] text-foreground outline-none transition-colors focus:border-primary/50"
          />
        </div>
        <button
          type="button"
          onClick={fetchAgents}
          disabled={loading}
          className="flex items-center gap-1.5 rounded-lg border border-border/60 px-2.5 py-2 text-[0.6rem] text-muted-foreground transition-colors hover:text-primary"
        >
          <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} /> Refresh
        </button>
      </div>

      {/* Auto-route quick bar */}
      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-border bg-card/60 px-4 py-3">
        <Zap className="h-4 w-4 shrink-0 text-primary" />
        <input
          value={autoQuery}
          onChange={(e) => setAutoQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleAutoRun()}
          placeholder="Ask anything — Nancy picks the right specialist…"
          className="min-w-[200px] flex-1 rounded-lg border border-border/60 bg-background/50 px-2.5 py-1.5 text-[0.65rem] text-foreground outline-none focus:border-primary/60"
        />
        <button
          type="button"
          onClick={handleAutoRun}
          disabled={autoRunning || !autoQuery.trim()}
          className="flex items-center gap-1.5 rounded-lg border border-primary/50 bg-primary/10 px-3 py-1.5 text-[0.62rem] text-primary transition-colors hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {autoRunning ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />} Run
        </button>
        {autoResult && (
          <p className="w-full rounded-lg border border-border/50 bg-background/40 px-2.5 py-2 text-[0.55rem] leading-relaxed text-muted-foreground">{autoResult}</p>
        )}
      </div>

      {/* Category filter pills */}
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setActiveCategory(null)}
          className={cn(
            'rounded-full border px-3 py-1.5 text-[0.62rem] transition-all',
            activeCategory === null ? 'border-primary/60 bg-primary/10 text-primary' : 'border-border/50 text-muted-foreground hover:border-primary/30 hover:text-foreground',
          )}
        >
          All · {(data?.agents ?? []).length}
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
              className={cn('flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[0.62rem] transition-all',
                active ? 'text-foreground' : 'border-border/50 text-muted-foreground hover:text-foreground')}
              style={active ? { borderColor: cat.color, background: `color-mix(in oklch, ${cat.color} 14%, transparent)` } : undefined}
            >
              <cat.icon className="h-3 w-3" style={{ color: cat.color }} />
              {cat.label} · {count}
            </button>
          )
        })}
      </div>

      {/* Card grid */}
      {loading && !data ? (
        <div className="flex items-center justify-center rounded-2xl border border-border bg-card/60 py-16 text-[0.65rem] text-muted-foreground">
          <RefreshCw className="mr-2 h-4 w-4 animate-spin" /> Establishing uplink to the fleet…
        </div>
      ) : error && !data ? (
        <div className="flex flex-col items-center gap-2 rounded-2xl border border-border bg-card/60 py-12 text-center text-[0.65rem] text-destructive">
          <span>{error}</span>
          <button onClick={fetchAgents} className="text-primary underline underline-offset-2">retry</button>
        </div>
      ) : filteredAgents.length === 0 ? (
        <div className="flex items-center justify-center rounded-2xl border border-border bg-card/60 py-16 text-[0.65rem] text-muted-foreground">No agents match.</div>
      ) : (
        <motion.div layout className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          <AnimatePresence initial={false}>
            {filteredAgents.map((agent) => (
              <AgentIdCard key={agent.key} agent={agent} onOpen={() => setTaskAgent(agent)} />
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

/* ─── Agent ID card — icon, status badge, name, blurb, footer stat ──────
   Deliberately flat and minimal (no load bar, no mission indicator, no
   specialization tag cloud) -- those live in the task modal now. This is
   an ID badge, not a dashboard tile. ─────────────────────────────────── */
function AgentIdCard({ agent, onOpen }: { agent: AgentInfo; onOpen: () => void }) {
  const Icon = iconFor(agent.domain)
  const color = colorFor(agent.domain)
  const isOffline = agent.status === 'offline'
  const isActive = agent.status === 'online' || agent.status === 'executing'

  return (
    <motion.div layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.2 }}>
      <SnakeBorder state={snakeStateForAgent(agent.status)} radiusClassName="rounded-2xl">
        <button
          type="button"
          onClick={onOpen}
          className={cn(
            'group flex w-full flex-col gap-3 rounded-2xl border border-border bg-card/60 p-3.5 text-left transition-all hover:border-primary/40 hover:bg-card/80',
            isOffline && 'opacity-50',
          )}
        >
          <div className="flex items-start justify-between gap-2">
            <span
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full"
              style={{ background: `color-mix(in oklch, ${color} 20%, var(--background))` }}
            >
              <Icon className="h-4.5 w-4.5" style={{ color }} />
            </span>
            <span className={cn(
              'flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[0.46rem] uppercase tracking-wide',
              isActive ? 'border-primary/40 bg-primary/10 text-primary' : 'border-border/50 text-muted-foreground',
            )}>
              <span className={cn('h-1.5 w-1.5 rounded-full', (agent.status === 'online' || agent.status === 'executing') && 'animate-hud-pulse', STATUS_DOT[agent.status])} />
              {agent.status}
            </span>
          </div>

          <div className="min-w-0">
            <div className="truncate text-[0.75rem] font-medium text-foreground">{agent.name}</div>
            <div className="mt-0.5 line-clamp-2 text-[0.56rem] leading-snug text-muted-foreground">
              {agent.status === 'executing' && agent.current_task_type ? `running ${agent.current_task_type}…` : (agent.description || agent.role || agent.domain.replace(/-/g, ' '))}
            </div>
          </div>

          <div className="flex items-center justify-between border-t border-border/30 pt-2 text-[0.5rem] text-muted-foreground">
            <span>{agent.total_tasks} tasks</span>
            <ChevronRight className="h-3 w-3 shrink-0 opacity-0 transition-opacity group-hover:opacity-100" />
          </div>
        </button>
      </SnakeBorder>
    </motion.div>
  )
}
