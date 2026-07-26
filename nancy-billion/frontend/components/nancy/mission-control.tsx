'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'
import { AgentTaskModal } from './agent-task-modal'
import { listAgents, autoRouteAgent, summarizeResult, type AgentListResponse } from '@/lib/nancy/agent-client'
import { onDomainEvent } from '@/lib/nancy/ws-client'
import type { AgentInfo } from '@/lib/nancy/types'
import { AGENT_CATEGORIES, categoryFor, iconFor } from '@/lib/nancy/agent-taxonomy'
import { Search, RefreshCw, Zap } from 'lucide-react'

/* ═══════════════════════════════════════════════════════════════════════
   AGENTS — premium glass "mission-control module" cards: dark frosted
   glass, monochrome icons, no colourful gradients, no oversized icons, no
   gaming HUD. Real agent data throughout (/agents/list, live over the
   WebSocket domain-event bridge) — only the visual system is bespoke.
   Accent color is the app's own theme (--primary/--gold), not a one-off
   palette, so this page reads as part of Nancy rather than a skin.
   ═══════════════════════════════════════════════════════════════════════ */

const ACCENT = 'var(--primary)'
const ACCENT2 = 'var(--gold)'
const PAGE_BG = 'var(--background)'
const GLASS_BG = 'color-mix(in oklch, var(--card) 78%, transparent)'
const BORDER_IDLE = 'color-mix(in oklch, var(--primary) 20%, transparent)'
const BORDER_HOVER = 'color-mix(in oklch, var(--primary) 65%, transparent)'
const GLOW_SOFT = 'color-mix(in oklch, var(--primary) 16%, transparent)'
const GLOW_STRONG = 'color-mix(in oklch, var(--primary) 55%, transparent)'

const STATUS_TEXT: Record<string, string> = {
  online: 'ACTIVE', executing: 'RUNNING', idle: 'IDLE', training: 'LEARNING', offline: 'OFFLINE', error: 'OFFLINE',
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
  const total = data?.total ?? 0

  return (
    <div className="mx-auto flex max-w-[1680px] flex-col gap-5 rounded-[20px] p-6" style={{ background: PAGE_BG }}>
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="text-[11px] uppercase tracking-[2px] text-white/40">Fleet Registry</div>
          <h1 className="text-2xl font-semibold text-white">
            Agents <span style={{ color: ACCENT }}>{stats?.agents_online ?? '—'}</span><span className="text-white/30">/{total || '—'}</span>
          </h1>
        </div>
        <div className="flex items-center gap-2.5">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-white/40" />
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Search agents…"
              className="w-56 rounded-full py-2 pl-9 pr-3 text-[0.7rem] text-white outline-none transition-colors"
              style={{ background: GLASS_BG, border: `1px solid ${BORDER_IDLE}` }}
            />
          </div>
          <button
            type="button"
            onClick={fetchAgents}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-full px-3 py-2 text-[0.6rem] uppercase tracking-wide text-white/60 transition-colors hover:text-white"
            style={{ background: GLASS_BG, border: `1px solid ${BORDER_IDLE}` }}
          >
            <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} /> Refresh
          </button>
        </div>
      </div>

      {/* Auto-route bar */}
      <div className="flex flex-wrap items-center gap-2.5 rounded-[14px] px-4 py-3" style={{ background: GLASS_BG, border: `1px solid ${BORDER_IDLE}` }}>
        <Zap className="h-4 w-4 shrink-0" style={{ color: ACCENT }} />
        <input
          value={autoQuery}
          onChange={(e) => setAutoQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleAutoRun()}
          placeholder="Ask anything — Nancy dispatches the right module…"
          className="min-w-[180px] flex-1 bg-transparent text-[0.68rem] text-white outline-none placeholder:text-white/35"
        />
        <button
          type="button"
          onClick={handleAutoRun}
          disabled={autoRunning || !autoQuery.trim()}
          className="rounded-full px-3 py-1.5 text-[0.6rem] uppercase tracking-wide transition-colors disabled:cursor-not-allowed disabled:opacity-30"
          style={{ background: GLOW_SOFT, border: `1px solid ${BORDER_HOVER}`, color: ACCENT }}
        >
          {autoRunning ? 'Dispatching…' : 'Dispatch'}
        </button>
        {autoResult && <p className="w-full text-[0.6rem] leading-relaxed text-white/55">{autoResult}</p>}
      </div>

      {/* Category pills */}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => setActiveCategory(null)}
          className="rounded-full px-3 py-1.5 text-[0.6rem] uppercase tracking-wide transition-colors"
          style={activeCategory === null
            ? { background: GLOW_SOFT, border: `1px solid ${BORDER_HOVER}`, color: ACCENT }
            : { background: GLASS_BG, border: `1px solid ${BORDER_IDLE}`, color: 'rgba(255,255,255,.5)' }}
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
              className="rounded-full px-3 py-1.5 text-[0.6rem] uppercase tracking-wide transition-colors"
              style={active
                ? { background: GLOW_SOFT, border: `1px solid ${BORDER_HOVER}`, color: ACCENT }
                : { background: GLASS_BG, border: `1px solid ${BORDER_IDLE}`, color: 'rgba(255,255,255,.5)' }}
            >
              {cat.label} · {count}
            </button>
          )
        })}
      </div>

      {/* Card row */}
      {loading && !data ? (
        <div className="flex items-center justify-center rounded-[16px] py-16 text-[0.65rem] text-white/40" style={{ background: GLASS_BG, border: `1px solid ${BORDER_IDLE}` }}>
          <RefreshCw className="mr-2 h-4 w-4 animate-spin" /> Establishing uplink to the fleet…
        </div>
      ) : error && !data ? (
        <div className="flex flex-col items-center gap-2 rounded-[16px] py-12 text-center text-[0.65rem]" style={{ background: GLASS_BG, border: '1px solid rgba(255,100,100,.3)', color: '#ff8080' }}>
          <span>{error}</span>
          <button onClick={fetchAgents} className="underline underline-offset-2">retry</button>
        </div>
      ) : filteredAgents.length === 0 ? (
        <div className="flex items-center justify-center rounded-[16px] py-16 text-[0.65rem] text-white/40" style={{ background: GLASS_BG, border: `1px solid ${BORDER_IDLE}` }}>No agents match.</div>
      ) : (
        <div className="flex flex-wrap justify-center gap-4">
          {filteredAgents.map((agent) => (
            <AgentGlassCard key={agent.key} agent={agent} onOpen={() => setTaskAgent(agent)} />
          ))}
        </div>
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

/* ─── Glass module card — exact spec: 260-290px × 170-190px, 16px radius,
   frosted glass, cyan accent bar, monochrome icon, status chip, hover
   lift+bloom, and a real "energized" pulse for genuinely executing agents
   (a real live signal, not decoration tied to a fake "selected" state). ── */
function AgentGlassCard({ agent, onOpen }: { agent: AgentInfo; onOpen: () => void }) {
  const Icon = iconFor(agent.domain)
  const [hovered, setHovered] = useState(false)
  const isExecuting = agent.status === 'executing'
  const isOffline = agent.status === 'offline'

  return (
    <motion.button
      type="button"
      onClick={onOpen}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      whileHover={{ y: -4, scale: 1.02 }}
      whileTap={{ scale: 0.99 }}
      transition={{ type: 'spring', stiffness: 320, damping: 24 }}
      className={cn('relative flex h-[230px] w-[270px] shrink-0 flex-col overflow-hidden p-[18px] text-left', isOffline && 'opacity-50')}
      style={{
        borderRadius: 16,
        background: GLASS_BG,
        backdropFilter: 'blur(22px)',
        WebkitBackdropFilter: 'blur(22px)',
        border: `1px solid ${hovered || isExecuting ? BORDER_HOVER : BORDER_IDLE}`,
        boxShadow: hovered ? `0 0 30px ${GLOW_SOFT}` : isExecuting ? `0 0 18px ${GLOW_SOFT}` : 'none',
        transition: 'border-color 0.25s ease, box-shadow 0.25s ease',
      }}
    >
      {/* left accent bar — breathes for a genuinely executing agent */}
      <motion.span
        className="absolute inset-y-0 left-0 w-[2px]"
        style={{ background: ACCENT }}
        animate={isExecuting
          ? { opacity: [0.45, 1, 0.45], boxShadow: [`0 0 4px ${GLOW_SOFT}`, `0 0 14px ${GLOW_STRONG}`, `0 0 4px ${GLOW_SOFT}`] }
          : { opacity: hovered ? 0.85 : 0.35, boxShadow: `0 0 6px ${GLOW_SOFT}` }}
        transition={isExecuting ? { duration: 2.5, repeat: Infinity, ease: 'easeInOut' } : { duration: 0.2 }}
      />

      <div className="flex items-start justify-between">
        <Icon className="h-[20px] w-[20px] text-white/80" strokeWidth={1.5} />
        <StatusChip status={agent.status} />
      </div>

      <h3 className="mt-3 truncate text-[18px] font-semibold uppercase tracking-wide text-white">{agent.name}</h3>
      <p className="mt-1.5 line-clamp-2 text-[12px] leading-relaxed text-white/65">
        {agent.status === 'executing' && agent.current_task_type ? `Currently running ${agent.current_task_type}.` : (agent.description || agent.role || `Handles ${agent.domain.replace(/-/g, ' ')} tasks.`)}
      </p>

      <div className="mt-auto flex items-center justify-between pt-2">
        <div>
          <div className="text-[9px] uppercase tracking-[1.5px] text-white/40">Tasks</div>
          <div className="text-[13px] text-white">{agent.total_tasks}</div>
        </div>
        <div className="text-right">
          <div className="text-[9px] uppercase tracking-[1.5px] text-white/40">Accuracy</div>
          <div className="text-[13px]" style={{ color: ACCENT2 }}>{Math.round(agent.confidence * 100)}%</div>
        </div>
      </div>
    </motion.button>
  )
}

function StatusChip({ status }: { status: string }) {
  const label = STATUS_TEXT[status] ?? status.toUpperCase()
  return (
    <span
      className="flex h-5 items-center gap-1 rounded-full px-2 text-[10px] uppercase tracking-[1.5px]"
      style={{ border: `1px solid ${BORDER_HOVER}`, color: ACCENT }}
    >
      <span className="h-1 w-1 rounded-full" style={{ background: ACCENT }} />
      {label}
    </span>
  )
}
