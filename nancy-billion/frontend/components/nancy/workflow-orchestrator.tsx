'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { cn } from '@/lib/utils'
import { AmbientField } from './ambient-field'
import { listAgents } from '@/lib/nancy/agent-client'
import { categoryFor, colorFor } from '@/lib/nancy/agent-taxonomy'
import { onDomainEvent } from '@/lib/nancy/ws-client'
import { describeDomainEvent, STAGE_LABELS } from '@/lib/nancy/event-descriptions'
import {
  listMissions, createMission, updateMission, assignMission, assignMissionMulti, transitionMission,
  cancelMission, deleteMission, type MissionCreateInput,
} from '@/lib/nancy/mission-client'
import type { AgentInfo, Mission, MissionStage } from '@/lib/nancy/types'
import {
  Plus, X, Trash2, Play, Loader2, Flag, CalendarClock, Tag, Bot, CheckCircle2,
  XCircle, Waypoints, GanttChartSquare, Filter, Search, Users, Link2,
  ListChecks, AlertTriangle, Sparkles, ChevronDown, ChevronsRight, Ban, History,
  GitBranch,
} from 'lucide-react'

/* ═══════════════════════════════════════════════════════════════════════
   WORKFLOW ORCHESTRATOR — a real backend-driven execution pipeline, not a
   Trello board and not a localStorage app. Every card is a real `Mission`
   row (data/missions.json — see backend/missions_store.py), every stage
   move is a real /missions/{id}/transition call the backend validates
   (dependency gating is enforced server-side, not just drawn client-side),
   and every visible update comes from a real MISSION_* event broadcast
   over the same WebSocket Mission Control listens on. Three real views:
   Pipeline (the flow, live drag-to-transition), Timeline (real due dates),
   Dependency Graph (a real DAG built from mission.dependencies, layered by
   topological depth — an agent-assignment overlay stands in for a
   separate "mission network" view rather than duplicating the same edges
   in a second graph).
   ═══════════════════════════════════════════════════════════════════════ */

const STAGE_ORDER: MissionStage[] = [
  'mission_created', 'planning', 'reasoning', 'dependency_resolution', 'agent_assignment',
  'execution', 'validation', 'human_approval', 'deployment', 'archive',
]
const STAGES: { key: MissionStage; label: string }[] = STAGE_ORDER.map((key) => ({ key, label: STAGE_LABELS[key] }))
const STAGE_INDEX: Record<MissionStage, number> = Object.fromEntries(STAGES.map((s, i) => [s.key, i])) as Record<MissionStage, number>

const PRIORITY_COLOR: Record<Mission['priority'], string> = {
  low: 'border-border/60 text-muted-foreground bg-secondary/30',
  medium: 'border-primary/40 text-primary bg-primary/10',
  high: 'border-gold/40 text-gold bg-gold/10',
  critical: 'border-destructive/40 text-destructive bg-destructive/10',
}
const RISK_COLOR: Record<Mission['risk'], string> = {
  low: 'text-muted-foreground',
  medium: 'text-gold',
  high: 'text-destructive',
}

interface FeedEvent { id: string; text: string; at: number; tone: 'ok' | 'error' | 'info' }
let feedSeq = 0
function newFeedId() { feedSeq += 1; return `feed_${Date.now()}_${feedSeq}` }

function missionProgress(m: Mission): number {
  if (m.stage === 'archive') return 100
  if (m.subtasks.length > 0) return Math.round((m.subtasks.filter((s) => s.done).length / m.subtasks.length) * 100)
  return Math.round((STAGE_INDEX[m.stage] / (STAGES.length - 1)) * 100)
}

const APPROVAL_PHRASES = ['waiting for approval', 'needs approval', 'human approval', 'pending approval']
function missionSearchFields(m: Mission, agents: AgentInfo[]): string[] {
  const agent = agents.find((a) => a.key === m.assigned_agent)
  return [m.title, m.description, m.owner, m.assigned_agent ?? '', agent ? categoryFor(agent.domain) : '', m.priority, m.risk, ...m.tags].map((s) => s.toLowerCase())
}
function matchesSearch(m: Mission, agents: AgentInfo[], query: string): boolean {
  const q = query.toLowerCase().trim()
  if (!q) return true
  const phrase = APPROVAL_PHRASES.find((p) => q.includes(p))
  if (phrase) {
    if (m.stage !== 'human_approval') return false
    const rest = q.replace(phrase, '').trim()
    return !rest || missionSearchFields(m, agents).some((f) => f.includes(rest))
  }
  return missionSearchFields(m, agents).some((f) => f.includes(q))
}

export function WorkflowOrchestratorPanel() {
  const [missions, setMissions] = useState<Mission[]>([])
  const [loaded, setLoaded] = useState(false)
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [feed, setFeed] = useState<FeedEvent[]>([])
  const [composerOpen, setComposerOpen] = useState(false)
  const [editingMission, setEditingMission] = useState<Mission | null>(null)
  const [dragOverStage, setDragOverStage] = useState<MissionStage | null>(null)
  const [dropIndex, setDropIndex] = useState<number | null>(null)
  const [view, setView] = useState<'pipeline' | 'timeline' | 'dependency_graph'>('pipeline')
  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState<{ department: string | null; priority: Mission['priority'] | null; agentKey: string | null; owner: string | null; stage: MissionStage | null; automation: 'auto' | 'manual' | null; tag: string | null }>({
    department: null, priority: null, agentKey: null, owner: null, stage: null, automation: null, tag: null,
  })
  const [filtersOpen, setFiltersOpen] = useState(false)
  const dragMissionId = useRef<string | null>(null)

  const logEvent = useCallback((text: string, tone: FeedEvent['tone'] = 'info') => {
    setFeed((f) => [{ id: newFeedId(), text, at: Date.now(), tone }, ...f].slice(0, 40))
  }, [])

  const refreshAgents = useCallback(() => {
    listAgents().then((res) => res.success && setAgents(res.agents))
  }, [])

  const refreshMissions = useCallback(async () => {
    const res = await listMissions()
    if (res.success) setMissions(res.missions)
  }, [])

  useEffect(() => {
    Promise.all([refreshMissions(), refreshAgents()]).finally(() => setLoaded(true))
    // Safety-net poll -- WS events are the real update path, but a missed
    // frame (a reconnect gap) shouldn't leave the board silently stale.
    const t = setInterval(() => { refreshMissions(); refreshAgents() }, 60_000)
    return () => clearInterval(t)
  }, [refreshMissions, refreshAgents])

  // Live projection of real backend events -- this is the actual data path,
  // not a decoration on top of polling.
  useEffect(() => {
    const unsubscribe = onDomainEvent((evt) => {
      if (evt.type === 'MISSION_DELETED' && evt.mission_id) {
        setMissions((prev) => prev.filter((m) => m.id !== evt.mission_id))
      } else if (evt.mission) {
        setMissions((prev) => {
          const idx = prev.findIndex((m) => m.id === evt.mission!.id)
          if (idx === -1) return [...prev, evt.mission!]
          const next = [...prev]
          next[idx] = evt.mission!
          return next
        })
      }
      if (evt.type.startsWith('AGENT_')) refreshAgents()
      const described = describeDomainEvent(evt)
      if (described) logEvent(described.text, described.tone)
    })
    return unsubscribe
  }, [logEvent, refreshAgents])

  const moveMission = useCallback(async (id: string, stage: MissionStage) => {
    const prev = missions.find((m) => m.id === id)
    if (!prev || prev.stage === stage) return
    setMissions((list) => list.map((m) => (m.id === id ? { ...m, stage } : m)))
    const res = await transitionMission(id, stage)
    if (!res.success) {
      setMissions((list) => list.map((m) => (m.id === id ? { ...m, stage: prev.stage } : m)))
      logEvent(`Could not move "${prev.title}" to ${STAGE_LABELS[stage]}: ${res.detail ?? 'blocked'}`, 'error')
    } else if (res.mission) {
      setMissions((list) => list.map((m) => (m.id === id ? res.mission! : m)))
    }
  }, [missions, logEvent])

  const advanceMission = useCallback((m: Mission) => {
    const next = STAGES[Math.min(STAGES.length - 1, STAGE_INDEX[m.stage] + 1)]
    void moveMission(m.id, next.key)
  }, [moveMission])

  const cancelOne = useCallback(async (id: string) => {
    const res = await cancelMission(id)
    if (!res.success) logEvent('Could not cancel mission', 'error')
  }, [logEvent])

  const deleteOne = useCallback(async (id: string) => {
    const m = missions.find((x) => x.id === id)
    const res = await deleteMission(id)
    if (res.success) {
      setMissions((list) => list.filter((x) => x.id !== id))
      logEvent(`Deleted "${m?.title ?? id}"`)
    }
  }, [missions, logEvent])

  const saveMission = useCallback(async (input: MissionCreateInput, existing: Mission | null) => {
    if (!existing) {
      const res = await createMission(input)
      if (!res.success) logEvent(`Could not create mission: ${res.detail ?? 'unknown error'}`, 'error')
      return
    }
    const { assigned_agent, assigned_agents, ...rest } = input
    const res = await updateMission(existing.id, rest)
    if (!res.success) { logEvent(`Could not update mission: ${res.detail ?? 'unknown error'}`, 'error'); return }
    const sameList = (a: string[], b: string[]) => a.length === b.length && [...a].sort().every((v, i) => v === [...b].sort()[i])
    if (assigned_agents && assigned_agents.length > 0) {
      if (!sameList(assigned_agents, existing.assigned_agents ?? [])) {
        const assignRes = await assignMissionMulti(existing.id, assigned_agents)
        if (!assignRes.success) logEvent('Could not update assignment', 'error')
      }
    } else if (assigned_agent !== existing.assigned_agent) {
      const assignRes = await assignMission(existing.id, assigned_agent ?? null)
      if (!assignRes.success) logEvent('Could not update assignment', 'error')
    }
  }, [logEvent])

  const agentByKey = useMemo(() => new Map(agents.map((a) => [a.key, a])), [agents])
  const onlineAgentKeys = useMemo(() => new Set(agents.filter((a) => a.status !== 'offline').map((a) => a.key)), [agents])

  const visibleMissions = useMemo(() => missions.filter((m) => {
    if (!matchesSearch(m, agents, search)) return false
    if (filters.priority && m.priority !== filters.priority) return false
    if (filters.stage && m.stage !== filters.stage) return false
    if (filters.agentKey && m.assigned_agent !== filters.agentKey) return false
    if (filters.owner && m.owner.toLowerCase() !== filters.owner.toLowerCase()) return false
    if (filters.tag && !m.tags.includes(filters.tag)) return false
    if (filters.automation === 'auto' && !m.assigned_agent) return false
    if (filters.automation === 'manual' && m.assigned_agent) return false
    if (filters.department) {
      const agent = agentByKey.get(m.assigned_agent ?? '')
      if (!agent || categoryFor(agent.domain) !== filters.department) return false
    }
    return true
  }), [missions, agents, search, filters, agentByKey])

  const grouped = useMemo(() => {
    const g: Record<MissionStage, Mission[]> = Object.fromEntries(STAGES.map((s) => [s.key, [] as Mission[]])) as Record<MissionStage, Mission[]>
    for (const m of visibleMissions) g[m.stage]?.push(m)
    for (const list of Object.values(g)) list.sort((a, b) => a.order - b.order)
    return g
  }, [visibleMissions])

  const departments = useMemo(() => Array.from(new Set(agents.map((a) => categoryFor(a.domain)))).sort(), [agents])
  const allTags = useMemo(() => Array.from(new Set(missions.flatMap((m) => m.tags))).sort(), [missions])
  const activeFilterCount = Object.values(filters).filter(Boolean).length
  const completedToday = missions.filter((m) => m.stage === 'archive' && new Date(m.updated_at * 1000).toDateString() === new Date().toDateString()).length

  return (
    <div className="relative mx-auto flex max-w-[1680px] flex-col gap-4">
      <AmbientField />

      <div className="glass-surface flex flex-col gap-3 rounded-2xl px-4 py-3.5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2 text-[0.6rem]">
            <span className="rounded-full border border-border/60 bg-secondary/30 px-3 py-1 text-muted-foreground">
              {agents.filter((a) => a.status !== 'offline').length} agents active
            </span>
            <span className="rounded-full border border-border/60 bg-secondary/30 px-3 py-1 text-muted-foreground">
              {missions.filter((m) => m.stage !== 'archive' && !m.cancelled).length} missions in flight
            </span>
            <span className="rounded-full border border-primary/40 bg-primary/10 px-3 py-1 text-primary">
              {completedToday} archived today
            </span>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex rounded-lg border border-border/50 p-0.5">
              <button type="button" onClick={() => setView('pipeline')} className={cn('flex items-center gap-1 rounded-md px-2.5 py-1 text-[0.6rem] transition-colors', view === 'pipeline' ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground')}>
                <Waypoints className="h-3 w-3" /> Pipeline
              </button>
              <button type="button" onClick={() => setView('timeline')} className={cn('flex items-center gap-1 rounded-md px-2.5 py-1 text-[0.6rem] transition-colors', view === 'timeline' ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground')}>
                <GanttChartSquare className="h-3 w-3" /> Timeline
              </button>
              <button type="button" onClick={() => setView('dependency_graph')} className={cn('flex items-center gap-1 rounded-md px-2.5 py-1 text-[0.6rem] transition-colors', view === 'dependency_graph' ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground')}>
                <GitBranch className="h-3 w-3" /> Dependency Graph
              </button>
            </div>
            <button
              type="button"
              onClick={() => { setEditingMission(null); setComposerOpen(true) }}
              className="flex items-center gap-1.5 rounded-lg border border-primary bg-primary/15 px-3 py-1.5 text-[0.6rem] text-primary transition-colors hover:bg-primary/25"
            >
              <Plus className="h-3.5 w-3.5" /> New Mission
            </button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[200px] flex-1">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder='Search — try "waiting for approval"…'
              className="w-full rounded-lg border border-border/50 bg-background/50 py-1.5 pl-8 pr-3 text-[0.65rem] text-foreground outline-none focus:border-primary/60"
            />
          </div>
          <button
            type="button"
            onClick={() => setFiltersOpen((v) => !v)}
            className={cn('flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[0.6rem] transition-colors', activeFilterCount > 0 ? 'border-primary/50 bg-primary/10 text-primary' : 'border-border/50 text-muted-foreground hover:text-foreground')}
          >
            <Filter className="h-3 w-3" /> Filters {activeFilterCount > 0 && `(${activeFilterCount})`}
            <ChevronDown className={cn('h-3 w-3 transition-transform', filtersOpen && 'rotate-180')} />
          </button>
        </div>

        <AnimatePresence>
          {filtersOpen && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.2 }}
              className="grid grid-cols-2 gap-2 overflow-hidden sm:grid-cols-3 lg:grid-cols-7"
            >
              <FilterSelect label="Department" value={filters.department} onChange={(v) => setFilters((f) => ({ ...f, department: v }))} options={departments} />
              <FilterSelect label="Priority" value={filters.priority} onChange={(v) => setFilters((f) => ({ ...f, priority: v as Mission['priority'] | null }))} options={['low', 'medium', 'high', 'critical']} />
              <FilterSelect label="AI" value={filters.agentKey} onChange={(v) => setFilters((f) => ({ ...f, agentKey: v }))} options={agents.map((a) => a.key)} labels={Object.fromEntries(agents.map((a) => [a.key, a.name]))} />
              <FilterSelect label="Owner" value={filters.owner} onChange={(v) => setFilters((f) => ({ ...f, owner: v }))} options={Array.from(new Set(missions.map((m) => m.owner).filter(Boolean)))} />
              <FilterSelect label="Stage" value={filters.stage} onChange={(v) => setFilters((f) => ({ ...f, stage: v as MissionStage | null }))} options={STAGES.map((s) => s.key)} labels={STAGE_LABELS} />
              <FilterSelect label="Automation" value={filters.automation} onChange={(v) => setFilters((f) => ({ ...f, automation: v as 'auto' | 'manual' | null }))} options={['auto', 'manual']} labels={{ auto: 'Agent-assigned', manual: 'Unassigned' }} />
              <FilterSelect label="Tags" value={filters.tag} onChange={(v) => setFilters((f) => ({ ...f, tag: v }))} options={allTags} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_260px]">
        {!loaded ? (
          <div className="glass-surface flex items-center justify-center rounded-2xl py-16 text-[0.65rem] text-muted-foreground">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading missions…
          </div>
        ) : view === 'pipeline' ? (
          <PipelineView
            grouped={grouped}
            allMissions={missions}
            agentByKey={agentByKey}
            onlineAgentKeys={onlineAgentKeys}
            dragOverStage={dragOverStage}
            dropIndex={dropIndex}
            onDragOverStage={(s, idx) => { setDragOverStage(s); setDropIndex(idx) }}
            onDragLeaveStage={() => { setDragOverStage(null); setDropIndex(null) }}
            onDrop={(s) => {
              const id = dragMissionId.current
              if (id) void moveMission(id, s)
              setDragOverStage(null); setDropIndex(null)
            }}
            onDragStart={(id) => { dragMissionId.current = id }}
            onOpen={(m) => { setEditingMission(m); setComposerOpen(true) }}
            onAdvance={advanceMission}
            onCancel={cancelOne}
            onDelete={deleteOne}
          />
        ) : view === 'timeline' ? (
          <TimelineView missions={visibleMissions} agentByKey={agentByKey} onOpen={(m) => { setEditingMission(m); setComposerOpen(true) }} />
        ) : (
          <DependencyGraphView missions={visibleMissions} agentByKey={agentByKey} onOpen={(m) => { setEditingMission(m); setComposerOpen(true) }} />
        )}

        <div className="glass-surface flex flex-col gap-2 rounded-2xl p-4">
          <div className="mb-1 flex items-center justify-between">
            <h3 className="font-heading text-[0.68rem] text-foreground">Live Feed</h3>
            <span className="flex items-center gap-1 text-[0.5rem] text-primary"><span className="h-1.5 w-1.5 animate-hud-pulse rounded-full bg-primary" /> LIVE</span>
          </div>
          <div className="flex max-h-[560px] flex-col gap-2 overflow-y-auto">
            {feed.length === 0 ? (
              <p className="py-6 text-center text-[0.55rem] text-muted-foreground">No activity yet — the backend's real event stream will populate this.</p>
            ) : (
              feed.map((e) => (
                <div key={e.id} className={cn(
                  'rounded-lg border px-2 py-1.5 text-[0.55rem]',
                  e.tone === 'ok' ? 'border-primary/25 bg-primary/5' : e.tone === 'error' ? 'border-destructive/25 bg-destructive/5' : 'border-border/40 bg-secondary/20',
                )}>
                  <p className="text-foreground">{e.text}</p>
                  <p className="mt-0.5 text-[0.45rem] text-muted-foreground">{new Date(e.at).toLocaleTimeString('en-GB')}</p>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {composerOpen && (
        <MissionComposer
          mission={editingMission}
          agents={agents}
          allMissions={missions}
          onClose={() => setComposerOpen(false)}
          onSave={(input) => { void saveMission(input, editingMission); setComposerOpen(false) }}
          onDelete={editingMission ? () => { void deleteOne(editingMission.id); setComposerOpen(false) } : undefined}
        />
      )}
    </div>
  )
}

/* ─── Filter select ──────────────────────────────────────────────────── */
function FilterSelect({ label, value, onChange, options, labels }: {
  label: string
  value: string | null
  onChange: (v: string | null) => void
  options: string[]
  labels?: Record<string, string>
}) {
  return (
    <label className="flex flex-col gap-1 text-[0.5rem] text-muted-foreground">
      <span>{label}</span>
      <select
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value || null)}
        className="rounded-lg border border-border/50 bg-background/50 px-2 py-1.5 text-[0.6rem] text-foreground outline-none focus:border-primary/60"
      >
        <option value="">Any</option>
        {options.map((o) => <option key={o} value={o}>{labels?.[o] ?? o}</option>)}
      </select>
    </label>
  )
}

/* ─── Pipeline view — a flowing execution pipeline: a continuous animated
   rail runs across every stage node, with each stage's real missions
   stacked in a lane beneath it. Drag between lanes still transitions a
   real mission server-side; this is a visual reframing of the same real
   interaction, not a Trello board with new labels. ──────────────────── */
function PipelineView({
  grouped, allMissions, agentByKey, onlineAgentKeys, dragOverStage, dropIndex,
  onDragOverStage, onDragLeaveStage, onDrop, onDragStart, onOpen, onAdvance, onCancel, onDelete,
}: {
  grouped: Record<MissionStage, Mission[]>
  allMissions: Mission[]
  agentByKey: Map<string, AgentInfo>
  onlineAgentKeys: Set<string>
  dragOverStage: MissionStage | null
  dropIndex: number | null
  onDragOverStage: (s: MissionStage, idx: number | null) => void
  onDragLeaveStage: () => void
  onDrop: (s: MissionStage) => void
  onDragStart: (id: string) => void
  onOpen: (m: Mission) => void
  onAdvance: (m: Mission) => void
  onCancel: (id: string) => void
  onDelete: (id: string) => void
}) {
  return (
    <div className="glass-surface rounded-2xl p-3">
      {/* flow rail — one continuous animated line spanning every stage */}
      <div className="mb-2 flex items-center px-1" style={{ minWidth: STAGES.length * 292 }}>
        {STAGES.map((stage, i) => (
          <div key={stage.key} className="flex flex-1 items-center">
            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-primary/40 bg-primary/10 text-[0.5rem] text-primary">{i + 1}</div>
            {i < STAGES.length - 1 && (
              <div className="mx-1 h-px flex-1 overflow-hidden">
                <div className="animate-flow-dash h-full w-full" style={{ background: 'repeating-linear-gradient(to right, var(--hud) 0 6px, transparent 6px 12px)', opacity: 0.5 }} />
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {STAGES.map((stage) => (
          <StageColumn
            key={stage.key}
            stage={stage}
            missions={grouped[stage.key]}
            allMissions={allMissions}
            agentByKey={agentByKey}
            onlineAgentKeys={onlineAgentKeys}
            dragOverStage={dragOverStage}
            dropIndex={dropIndex}
            onDragOverStage={onDragOverStage}
            onDragLeaveStage={onDragLeaveStage}
            onDrop={onDrop}
            onDragStart={onDragStart}
            onOpen={onOpen}
            onAdvance={onAdvance}
            onCancel={onCancel}
            onDelete={onDelete}
          />
        ))}
      </div>
    </div>
  )
}

/* ─── Stage lane ──────────────────────────────────────────────────────── */
function StageColumn({
  stage, missions, allMissions, agentByKey, onlineAgentKeys, dragOverStage, dropIndex,
  onDragOverStage, onDragLeaveStage, onDrop, onDragStart, onOpen, onAdvance, onCancel, onDelete,
}: {
  stage: { key: MissionStage; label: string }
  missions: Mission[]
  allMissions: Mission[]
  agentByKey: Map<string, AgentInfo>
  onlineAgentKeys: Set<string>
  dragOverStage: MissionStage | null
  dropIndex: number | null
  onDragOverStage: (s: MissionStage, idx: number | null) => void
  onDragLeaveStage: () => void
  onDrop: (s: MissionStage) => void
  onDragStart: (id: string) => void
  onOpen: (m: Mission) => void
  onAdvance: (m: Mission) => void
  onCancel: (id: string) => void
  onDelete: (id: string) => void
}) {
  const isOver = dragOverStage === stage.key
  const nearCapacity = missions.length >= 8

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        const container = e.currentTarget
        const y = e.clientY
        const items = Array.from(container.querySelectorAll<HTMLElement>('[data-mission-row]'))
        let idx: number | null = items.length
        for (let i = 0; i < items.length; i++) {
          const rect = items[i].getBoundingClientRect()
          if (y < rect.top + rect.height / 2) { idx = i; break }
        }
        onDragOverStage(stage.key, idx)
      }}
      onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) onDragLeaveStage() }}
      onDrop={(e) => { e.preventDefault(); onDrop(stage.key) }}
      className={cn('flex min-w-0 flex-col gap-2 rounded-2xl border border-border/30 bg-secondary/5 p-2.5 transition-colors', isOver && 'border-primary/50 bg-primary/5')}
    >
      <div className="sticky top-0 z-10 flex items-center justify-between rounded-xl bg-secondary/20 px-2 py-1.5">
        <span className="font-heading text-[0.6rem] text-muted-foreground">{stage.label}</span>
        <span className={cn('rounded-full px-1.5 py-0.5 text-[0.5rem]', nearCapacity ? 'bg-gold/15 text-gold' : 'bg-secondary/50 text-muted-foreground')}>{missions.length}</span>
      </div>
      <div className="flex flex-1 flex-col gap-2">
        {missions.length === 0 && dropIndex === 0 && isOver && <DropIndicator />}
        {missions.map((m, i) => (
          <div key={m.id} data-mission-row>
            {isOver && dropIndex === i && <DropIndicator />}
            <MissionCard
              mission={m}
              agent={m.assigned_agent ? agentByKey.get(m.assigned_agent) : undefined}
              agentOnline={!!m.assigned_agent && onlineAgentKeys.has(m.assigned_agent)}
              blockedByDependency={m.dependencies.some((d) => allMissions.find((x) => x.id === d)?.stage !== 'archive')}
              onDragStart={() => onDragStart(m.id)}
              onOpen={() => onOpen(m)}
              onAdvance={() => onAdvance(m)}
              onCancel={() => onCancel(m.id)}
              onDelete={() => onDelete(m.id)}
            />
          </div>
        ))}
        {isOver && dropIndex === missions.length && missions.length > 0 && <DropIndicator />}
        {missions.length === 0 && !isOver && <p className="py-4 text-center text-[0.5rem] text-muted-foreground/50">Empty</p>}
      </div>
    </div>
  )
}

function DropIndicator() {
  return <div className="animate-drop-indicator h-0.5 w-full rounded-full bg-primary" />
}

/* ─── Mission card ────────────────────────────────────────────────────── */
function MissionCard({
  mission, agent, agentOnline, blockedByDependency, onDragStart, onOpen, onAdvance, onCancel, onDelete,
}: {
  mission: Mission
  agent?: AgentInfo
  agentOnline: boolean
  blockedByDependency: boolean
  onDragStart: () => void
  onOpen: () => void
  onAdvance: () => void
  onCancel: () => void
  onDelete: () => void
}) {
  const progress = missionProgress(mission)
  const execMs = mission.dispatched_at && mission.result ? (mission.result.at - mission.dispatched_at) * 1000 : null
  const color = agent ? colorFor(agent.domain) : 'var(--muted-foreground)'
  const isLast = mission.stage === 'archive'
  // Real stage-derived accent -- same signal the old animated snake border
  // encoded (cancelled/failed -> error, execution/approval -> in-progress,
  // archive -> settled, else -> the assigned agent's own category color),
  // now a static color instead of a rotating glow.
  const stageColor =
    mission.cancelled || mission.result?.success === false ? 'var(--destructive)'
      : mission.stage === 'archive' ? 'var(--muted-foreground)'
      : mission.stage === 'execution' || mission.stage === 'human_approval' ? 'var(--gold)'
      : color

  return (
    <motion.div
      layout
      draggable
      onDragStart={onDragStart}
      onClick={onOpen}
      whileHover={{ y: -3 }}
      transition={{ type: 'spring', stiffness: 320, damping: 24 }}
      className={cn('group glass-surface relative cursor-pointer overflow-hidden rounded-[14px] p-2.5 pl-3.5 text-left transition-colors duration-200 hover:border-primary/30', mission.cancelled && 'opacity-50')}
    >
      <span className="absolute inset-y-0 left-0 w-[2.5px]" style={{ background: stageColor }} />

        <div className="mb-1.5 flex items-start justify-between gap-2">
          <p className="text-[0.65rem] font-medium leading-snug text-foreground">{mission.title}</p>
          <span className={cn('shrink-0 rounded-md border px-1.5 py-0.5 text-[0.42rem]', PRIORITY_COLOR[mission.priority])}>{mission.priority}</span>
        </div>

        {mission.description && <p className="mb-1.5 line-clamp-2 text-[0.55rem] text-muted-foreground">{mission.description}</p>}

        <div className="mb-1.5 flex items-center gap-1.5">
          <div className="h-1 flex-1 overflow-hidden rounded-full bg-secondary/50">
            <div className="h-full rounded-full transition-all duration-700" style={{ width: `${progress}%`, background: color }} />
          </div>
          <span className="text-[0.42rem] text-muted-foreground">{progress}%</span>
        </div>

        {(mission.tags.length > 0 || mission.risk !== 'low' || blockedByDependency || mission.cancelled || agent) && (
          <div className="mb-1.5 flex flex-wrap items-center gap-1">
            {mission.cancelled && (
              <span className="flex items-center gap-0.5 rounded-md bg-destructive/10 px-1 py-px text-[0.4rem] text-destructive"><Ban className="h-2 w-2" /> cancelled</span>
            )}
            {mission.risk !== 'low' && (
              <span className={cn('flex items-center gap-0.5 rounded-md bg-secondary/40 px-1 py-px text-[0.4rem]', RISK_COLOR[mission.risk])}><AlertTriangle className="h-2 w-2" /> {mission.risk} risk</span>
            )}
            {blockedByDependency && (
              <span className="flex items-center gap-0.5 rounded-md bg-destructive/10 px-1 py-px text-[0.4rem] text-destructive"><Link2 className="h-2 w-2" /> blocked</span>
            )}
            {agent && (
              <span className="flex items-center gap-0.5 rounded-md bg-accent/10 px-1 py-px text-[0.4rem] text-accent" title="Assigned agent's real capability rating, not a per-mission score">
                {(agent.confidence * 100).toFixed(0)}% agent confidence
              </span>
            )}
            {mission.tags.slice(0, 2).map((t) => <span key={t} className="rounded-md bg-primary/10 px-1 py-px text-[0.4rem] text-primary/80">{t}</span>)}
          </div>
        )}

        {mission.result && (
          <div className={cn('mb-1.5 flex items-start gap-1 rounded-lg border px-1.5 py-1 text-[0.48rem]', mission.result.success ? 'border-primary/30 bg-primary/5 text-primary' : 'border-destructive/30 bg-destructive/5 text-destructive')}>
            {mission.result.success ? <CheckCircle2 className="mt-px h-2.5 w-2.5 shrink-0" /> : <XCircle className="mt-px h-2.5 w-2.5 shrink-0" />}
            <span className="line-clamp-2">{mission.result.text}</span>
          </div>
        )}
        {mission.stage === 'execution' && !mission.result && (
          <div className="mb-1.5 flex items-center gap-1 rounded-lg border border-gold/30 bg-gold/5 px-1.5 py-1 text-[0.48rem] text-gold">
            <Loader2 className="h-2.5 w-2.5 shrink-0 animate-spin" /> executing…
          </div>
        )}

        <div className="flex items-center justify-between gap-1 text-[0.42rem] text-muted-foreground">
          <span className="flex items-center gap-1.5 truncate">
            {mission.assigned_agents.length > 0 ? (
              <span className="flex shrink-0 items-center gap-0.5 text-primary"><Sparkles className="h-2.5 w-2.5" /> {mission.assigned_agents.length} agents (parallel)</span>
            ) : mission.assigned_agent && (
              <span className={cn('flex shrink-0 items-center gap-0.5', agentOnline && 'text-primary')}><Sparkles className="h-2.5 w-2.5" /> {mission.assigned_agent}</span>
            )}
            {mission.owner && <span className="flex shrink-0 items-center gap-0.5"><Users className="h-2.5 w-2.5" /> {mission.owner}</span>}
            {execMs !== null && <span className="shrink-0">{(execMs / 1000).toFixed(1)}s</span>}
          </span>
          <span className="flex shrink-0 items-center gap-1.5">
            {mission.due_date && <span className="flex items-center gap-0.5"><CalendarClock className="h-2.5 w-2.5" /> {mission.due_date}</span>}
            {!isLast && !mission.cancelled && (
              <button
                type="button"
                title={`Advance to ${STAGES[Math.min(STAGES.length - 1, STAGE_INDEX[mission.stage] + 1)].label}`}
                aria-label={`Advance "${mission.title}"`}
                onClick={(e) => { e.stopPropagation(); onAdvance() }}
                className="flex h-5 w-5 items-center justify-center rounded-md border border-primary/40 text-primary opacity-0 transition-opacity hover:bg-primary/15 group-hover:opacity-100 group-focus-within:opacity-100 focus-visible:opacity-100"
              >
                {mission.stage === 'agent_assignment' ? <Play className="h-2.5 w-2.5" /> : <ChevronsRight className="h-2.5 w-2.5" />}
              </button>
            )}
            {!mission.cancelled && !isLast && (
              <button
                type="button"
                title="Cancel"
                aria-label={`Cancel "${mission.title}"`}
                onClick={(e) => { e.stopPropagation(); onCancel() }}
                className="flex h-5 w-5 items-center justify-center rounded-md border border-border/50 text-muted-foreground opacity-0 transition-opacity hover:border-destructive/50 hover:text-destructive group-hover:opacity-100 group-focus-within:opacity-100 focus-visible:opacity-100"
              >
                <Ban className="h-2.5 w-2.5" />
              </button>
            )}
            <button
              type="button"
              title="Delete"
              aria-label={`Delete "${mission.title}"`}
              onClick={(e) => { e.stopPropagation(); onDelete() }}
              className="flex h-5 w-5 items-center justify-center rounded-md border border-border/50 text-muted-foreground opacity-0 transition-opacity hover:border-destructive/50 hover:text-destructive group-hover:opacity-100 group-focus-within:opacity-100 focus-visible:opacity-100"
            >
              <Trash2 className="h-2.5 w-2.5" />
            </button>
          </span>
        </div>
    </motion.div>
  )
}

/* ─── Timeline view ───────────────────────────────────────────────────── */
function TimelineView({ missions, agentByKey, onOpen }: { missions: Mission[]; agentByKey: Map<string, AgentInfo>; onOpen: (m: Mission) => void }) {
  const today = useMemo(() => { const d = new Date(); d.setHours(0, 0, 0, 0); return d }, [])
  const days = 31
  const scheduled = missions.filter((m) => m.due_date)
  const unscheduled = missions.filter((m) => !m.due_date)

  const dayOffset = (dueDate: string) => {
    const d = new Date(dueDate); d.setHours(0, 0, 0, 0)
    return Math.round((d.getTime() - today.getTime()) / 86_400_000)
  }

  return (
    <div className="glass-surface flex flex-col gap-3 rounded-2xl p-4">
      {unscheduled.length > 0 && (
        <div>
          <h4 className="mb-1.5 text-[0.55rem] uppercase tracking-wide text-muted-foreground">No due date ({unscheduled.length})</h4>
          <div className="flex flex-wrap gap-1.5">
            {unscheduled.map((m) => (
              <button key={m.id} type="button" onClick={() => onOpen(m)} className="rounded-lg border border-border/40 bg-secondary/20 px-2 py-1 text-[0.55rem] text-foreground hover:border-primary/40">{m.title}</button>
            ))}
          </div>
        </div>
      )}

      <div className="overflow-x-auto">
        <div className="relative min-w-[1100px]">
          <div className="grid text-[0.46rem] text-muted-foreground" style={{ gridTemplateColumns: `repeat(${days}, minmax(34px, 1fr))` }}>
            {Array.from({ length: days }, (_, i) => {
              const d = new Date(today); d.setDate(d.getDate() + i)
              return <div key={i} className={cn('border-l border-border/20 px-1 py-1 text-center', i === 0 && 'text-primary')}>{d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })}</div>
            })}
          </div>
          <div className="flex flex-col gap-1.5 pt-1">
            {STAGES.map((stage) => {
              const rowMissions = scheduled.filter((m) => m.stage === stage.key)
              return (
                <div key={stage.key} className="relative grid items-center rounded-lg" style={{ gridTemplateColumns: `repeat(${days}, minmax(34px, 1fr))`, minHeight: 30 }}>
                  <div className="pointer-events-none absolute inset-0 grid" style={{ gridTemplateColumns: `repeat(${days}, minmax(34px, 1fr))` }}>
                    {Array.from({ length: days }, (_, i) => <div key={i} className="border-l border-border/10" />)}
                  </div>
                  {rowMissions.map((m) => {
                    const offset = Math.min(days - 1, Math.max(0, dayOffset(m.due_date!)))
                    const agent = m.assigned_agent ? agentByKey.get(m.assigned_agent) : undefined
                    const color = agent ? colorFor(agent.domain) : 'var(--hud)'
                    return (
                      <button
                        key={m.id}
                        type="button"
                        onClick={() => onOpen(m)}
                        title={`${m.title} · ${stage.label} · due ${m.due_date}`}
                        className="z-10 truncate rounded-md px-1.5 py-1 text-left text-[0.48rem] text-foreground shadow-sm transition-transform hover:-translate-y-0.5"
                        style={{ gridColumnStart: offset + 1, gridColumnEnd: offset + 2, background: `color-mix(in oklch, ${color} 22%, var(--surface-2))`, border: `1px solid color-mix(in oklch, ${color} 40%, transparent)` }}
                      >
                        {m.title}
                      </button>
                    )
                  })}
                </div>
              )
            })}
          </div>
        </div>
      </div>
      <div className="flex flex-wrap gap-3 border-t border-border/30 pt-2 text-[0.5rem] text-muted-foreground">
        {STAGES.map((s) => <span key={s.key}>{s.label}</span>)}
      </div>
    </div>
  )
}

/* ─── Dependency Graph view — a real DAG from mission.dependencies, laid
   out by topological depth (longest path from a root). An "assigned
   agents" overlay stands in for a separate mission-network view. ──────── */
function DependencyGraphView({ missions, agentByKey, onOpen }: { missions: Mission[]; agentByKey: Map<string, AgentInfo>; onOpen: (m: Mission) => void }) {
  const [showAgents, setShowAgents] = useState(true)

  const { layers, edges, colWidth, rowHeight } = useMemo(() => {
    const missionById = new Map(missions.map((m) => [m.id, m]))
    const depth = new Map<string, number>()
    const computeDepth = (id: string, seen: Set<string>): number => {
      if (depth.has(id)) return depth.get(id)!
      if (seen.has(id)) return 0 // cycle guard -- treat as a root rather than recursing forever
      const m = missionById.get(id)
      if (!m || m.dependencies.length === 0) { depth.set(id, 0); return 0 }
      const next = new Set(seen); next.add(id)
      const d = 1 + Math.max(0, ...m.dependencies.filter((x) => missionById.has(x)).map((x) => computeDepth(x, next)))
      depth.set(id, d)
      return d
    }
    for (const m of missions) computeDepth(m.id, new Set())

    const byLayer = new Map<number, Mission[]>()
    for (const m of missions) {
      const d = depth.get(m.id) ?? 0
      if (!byLayer.has(d)) byLayer.set(d, [])
      byLayer.get(d)!.push(m)
    }
    const layerList = Array.from(byLayer.entries()).sort((a, b) => a[0] - b[0]).map(([, ms]) => ms)

    const edgeList: { from: string; to: string; blocked: boolean; active: boolean }[] = []
    for (const m of missions) {
      for (const depId of m.dependencies) {
        const dep = missionById.get(depId)
        if (!dep) continue
        edgeList.push({ from: dep.id, to: m.id, blocked: dep.stage !== 'archive' && !dep.cancelled, active: dep.stage === 'execution' })
      }
    }
    return { layers: layerList, edges: edgeList, colWidth: 210, rowHeight: 92 }
  }, [missions])

  const positions = useMemo(() => {
    const map = new Map<string, { x: number; y: number }>()
    layers.forEach((layer, col) => {
      layer.forEach((m, row) => {
        map.set(m.id, { x: col * colWidth + 100, y: row * rowHeight + 60 })
      })
    })
    return map
  }, [layers, colWidth, rowHeight])

  const width = Math.max(600, layers.length * colWidth + 120)
  const height = Math.max(300, Math.max(1, ...layers.map((l) => l.length)) * rowHeight + 40)

  if (missions.length === 0) {
    return (
      <div className="glass-surface flex flex-col items-center gap-1.5 rounded-2xl py-14 text-center">
        <GitBranch className="h-5 w-5 text-muted-foreground" />
        <p className="text-[0.62rem] text-muted-foreground">No missions yet.</p>
      </div>
    )
  }

  return (
    <div className="glass-surface flex flex-col gap-3 rounded-2xl p-4">
      <div className="flex items-center justify-between">
        <p className="text-[0.55rem] text-muted-foreground">Layered by real dependency depth — root missions (no dependencies) on the left.</p>
        <button
          type="button"
          onClick={() => setShowAgents((v) => !v)}
          className={cn('flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-[0.55rem] transition-colors', showAgents ? 'border-primary/50 bg-primary/10 text-primary' : 'border-border/50 text-muted-foreground')}
        >
          <Bot className="h-3 w-3" /> Show assigned agents
        </button>
      </div>
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${width} ${height}`} style={{ width, height, minWidth: '100%' }}>
          {edges.map((e, i) => {
            const from = positions.get(e.from); const to = positions.get(e.to)
            if (!from || !to) return null
            const pathId = `dep-edge-${i}`
            const midX = (from.x + to.x) / 2
            return (
              <g key={pathId}>
                <path
                  id={pathId}
                  d={`M ${from.x + 80} ${from.y + 18} C ${midX} ${from.y + 18}, ${midX} ${to.y + 18}, ${to.x} ${to.y + 18}`}
                  stroke={e.blocked ? 'var(--destructive)' : 'var(--hud)'}
                  strokeWidth={1.25}
                  fill="none"
                  opacity={e.blocked ? 0.45 : 0.6}
                  markerEnd="url(#dep-arrow)"
                />
                {e.active && (
                  <circle r={3} fill="var(--gold)">
                    <animateMotion dur="1.6s" repeatCount="indefinite">
                      <mpath href={`#${pathId}`} />
                    </animateMotion>
                  </circle>
                )}
              </g>
            )
          })}
          <defs>
            <marker id="dep-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
              <path d="M0,0 L6,3 L0,6 Z" fill="var(--muted-foreground)" />
            </marker>
          </defs>
          {missions.map((m) => {
            const pos = positions.get(m.id)
            if (!pos) return null
            const agent = m.assigned_agent ? agentByKey.get(m.assigned_agent) : undefined
            const color = agent ? colorFor(agent.domain) : 'var(--muted-foreground)'
            return (
              <foreignObject key={m.id} x={pos.x} y={pos.y} width={180} height={64}>
                <button
                  type="button"
                  onClick={() => onOpen(m)}
                  className="flex h-full w-[176px] flex-col justify-center gap-1 rounded-xl border px-2.5 py-1.5 text-left transition-transform hover:-translate-y-0.5"
                  style={{ background: `color-mix(in oklch, ${color} 12%, var(--surface-2))`, borderColor: `color-mix(in oklch, ${color} 40%, transparent)` }}
                >
                  <span className="truncate text-[0.56rem] font-medium text-foreground">{m.title}</span>
                  <div className="flex items-center justify-between gap-1">
                    <span className="truncate text-[0.44rem] text-muted-foreground">{STAGE_LABELS[m.stage]}</span>
                    {showAgents && agent && (
                      <span className="flex shrink-0 items-center gap-0.5 text-[0.44rem]" style={{ color }}>
                        <Sparkles className="h-2 w-2" /> {agent.name}
                      </span>
                    )}
                  </div>
                </button>
              </foreignObject>
            )
          })}
        </svg>
      </div>
    </div>
  )
}

/* ─── Composer / editor modal ─────────────────────────────────────────── */
function MissionComposer({
  mission, agents, allMissions, onClose, onSave, onDelete,
}: {
  mission: Mission | null
  agents: AgentInfo[]
  allMissions: Mission[]
  onClose: () => void
  onSave: (input: MissionCreateInput) => void
  onDelete?: () => void
}) {
  const [title, setTitle] = useState(mission?.title ?? '')
  const [description, setDescription] = useState(mission?.description ?? '')
  const [tagsInput, setTagsInput] = useState(mission?.tags.join(', ') ?? '')
  const [assignedAgent, setAssignedAgent] = useState(mission?.assigned_agent ?? '')
  const [multiAgentMode, setMultiAgentMode] = useState((mission?.assigned_agents?.length ?? 0) > 0)
  const [assignedAgents, setAssignedAgents] = useState<string[]>(mission?.assigned_agents ?? [])
  const toggleAssignedAgent = (key: string) => setAssignedAgents((keys) => (keys.includes(key) ? keys.filter((k) => k !== key) : [...keys, key]))
  const [owner, setOwner] = useState(mission?.owner ?? '')
  const [priority, setPriority] = useState<Mission['priority']>(mission?.priority ?? 'medium')
  const [risk, setRisk] = useState<Mission['risk']>(mission?.risk ?? 'low')
  const [estimatedCost, setEstimatedCost] = useState(mission?.estimated_cost != null ? String(mission.estimated_cost) : '')
  const [dueDate, setDueDate] = useState(mission?.due_date ?? '')
  const [subtasks, setSubtasks] = useState(mission?.subtasks ?? [])
  const [subtaskDraft, setSubtaskDraft] = useState('')
  const [dependencies, setDependencies] = useState<string[]>(mission?.dependencies ?? [])
  const [historyOpen, setHistoryOpen] = useState(false)

  const addSubtask = () => {
    if (!subtaskDraft.trim()) return
    setSubtasks((s) => [...s, { id: `sub_${Date.now()}_${s.length}`, text: subtaskDraft.trim(), done: false }])
    setSubtaskDraft('')
  }
  const toggleDependency = (id: string) => setDependencies((d) => (d.includes(id) ? d.filter((x) => x !== id) : [...d, id]))

  const submit = () => {
    if (!title.trim()) return
    onSave({
      title: title.trim(),
      description: description.trim(),
      tags: tagsInput.split(',').map((t) => t.trim()).filter(Boolean),
      assigned_agent: multiAgentMode ? null : (assignedAgent || null),
      assigned_agents: multiAgentMode ? assignedAgents : [],
      owner: owner.trim(),
      priority,
      risk,
      estimated_cost: estimatedCost.trim() ? Number(estimatedCost) : null,
      due_date: dueDate || null,
      subtasks,
      dependencies,
    })
  }

  const dependencyCandidates = allMissions.filter((m) => m.id !== mission?.id)

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <button type="button" aria-label="Dismiss" onClick={onClose} className="absolute inset-0 cursor-default bg-background/80 backdrop-blur-md" />
      <motion.div
        initial={{ opacity: 0, y: 12, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        className="glass-surface relative z-10 flex w-full max-w-lg flex-col gap-3.5 rounded-2xl p-4"
        style={{ maxHeight: '88vh', overflowY: 'auto' }}
      >
        <div className="flex items-center justify-between">
          <h3 className="font-heading text-xs text-primary">{mission ? 'Edit Mission' : 'New Mission'}</h3>
          <button type="button" onClick={onClose} className="text-muted-foreground hover:text-foreground"><X className="h-4 w-4" /></button>
        </div>

        {mission && (
          <div className="flex items-center gap-1.5 text-[0.5rem] text-muted-foreground">
            <span>Stage:</span>
            <span className="rounded-full border border-primary/40 bg-primary/10 px-2 py-0.5 text-primary">{STAGE_LABELS[mission.stage]}</span>
            <span className="opacity-60">— use the pipeline to move between stages</span>
          </div>
        )}

        <input
          autoFocus
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Mission title…"
          className="rounded-lg border border-border bg-background/60 px-2.5 py-2 text-[0.7rem] text-foreground outline-none focus:border-primary/60"
        />
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Description — this becomes the query sent to the agent during Execution…"
          rows={3}
          className="resize-none rounded-lg border border-border bg-background/60 px-2.5 py-2 text-[0.65rem] text-foreground outline-none focus:border-primary/60"
        />

        <div className="grid grid-cols-2 gap-2">
          <label className="col-span-2 flex flex-col gap-1 text-[0.5rem] text-muted-foreground">
            <span className="flex items-center justify-between gap-1">
              <span className="flex items-center gap-1"><Bot className="h-3 w-3" /> Assign AI</span>
              <button
                type="button"
                onClick={() => setMultiAgentMode((v) => !v)}
                className={cn(
                  'rounded-full border px-2 py-0.5 text-[0.5rem] transition-colors',
                  multiAgentMode ? 'border-primary/50 bg-primary/10 text-primary' : 'border-border/60 text-muted-foreground hover:text-foreground',
                )}
                title="Run multiple agents in real parallel and synthesize their outputs, instead of a single agent"
              >
                Parallel (multi-agent)
              </button>
            </span>
            {multiAgentMode ? (
              <div className="flex max-h-28 flex-col gap-1 overflow-y-auto rounded-lg border border-border bg-background/60 p-1.5">
                {agents.length === 0 && <span className="px-1 py-1 text-[0.6rem] opacity-60">No agents online</span>}
                {agents.map((a) => (
                  <label key={a.key} className="flex items-center gap-1.5 rounded px-1 py-0.5 text-[0.6rem] text-foreground hover:bg-secondary/40">
                    <input type="checkbox" checked={assignedAgents.includes(a.key)} onChange={() => toggleAssignedAgent(a.key)} className="accent-primary" />
                    {a.name} <span className="opacity-50">({a.status})</span>
                  </label>
                ))}
              </div>
            ) : (
              <select value={assignedAgent} onChange={(e) => setAssignedAgent(e.target.value)} className="rounded-lg border border-border bg-background/60 px-2 py-1.5 text-[0.6rem] text-foreground outline-none focus:border-primary/60">
                <option value="">— unassigned —</option>
                {agents.map((a) => <option key={a.key} value={a.key}>{a.name} ({a.status})</option>)}
              </select>
            )}
          </label>
          <label className="flex flex-col gap-1 text-[0.5rem] text-muted-foreground">
            <span className="flex items-center gap-1"><Users className="h-3 w-3" /> Owner</span>
            <input value={owner} onChange={(e) => setOwner(e.target.value)} placeholder="optional" className="rounded-lg border border-border bg-background/60 px-2 py-1.5 text-[0.6rem] text-foreground outline-none focus:border-primary/60" />
          </label>
          <label className="flex flex-col gap-1 text-[0.5rem] text-muted-foreground">
            <span className="flex items-center gap-1"><Flag className="h-3 w-3" /> Priority</span>
            <select value={priority} onChange={(e) => setPriority(e.target.value as Mission['priority'])} className="rounded-lg border border-border bg-background/60 px-2 py-1.5 text-[0.6rem] text-foreground outline-none focus:border-primary/60">
              <option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-[0.5rem] text-muted-foreground">
            <span className="flex items-center gap-1"><AlertTriangle className="h-3 w-3" /> Risk</span>
            <select value={risk} onChange={(e) => setRisk(e.target.value as Mission['risk'])} className="rounded-lg border border-border bg-background/60 px-2 py-1.5 text-[0.6rem] text-foreground outline-none focus:border-primary/60">
              <option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-[0.5rem] text-muted-foreground">
            <span className="flex items-center gap-1"><CalendarClock className="h-3 w-3" /> Due date</span>
            <input type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} className="rounded-lg border border-border bg-background/60 px-2 py-1.5 text-[0.6rem] text-foreground outline-none focus:border-primary/60" />
          </label>
          <label className="flex flex-col gap-1 text-[0.5rem] text-muted-foreground">
            <span>Est. reasoning cost <span className="opacity-60">(your estimate)</span></span>
            <input type="number" min={0} step="0.01" value={estimatedCost} onChange={(e) => setEstimatedCost(e.target.value)} placeholder="e.g. 0.42" className="rounded-lg border border-border bg-background/60 px-2 py-1.5 text-[0.6rem] text-foreground outline-none focus:border-primary/60" />
          </label>
        </div>

        <label className="flex flex-col gap-1 text-[0.5rem] text-muted-foreground">
          <span className="flex items-center gap-1"><Tag className="h-3 w-3" /> Tags (comma-separated)</span>
          <input value={tagsInput} onChange={(e) => setTagsInput(e.target.value)} placeholder="e.g. research, urgent" className="rounded-lg border border-border bg-background/60 px-2.5 py-1.5 text-[0.6rem] text-foreground outline-none focus:border-primary/60" />
        </label>

        <div>
          <span className="mb-1 flex items-center gap-1 text-[0.5rem] text-muted-foreground"><ListChecks className="h-3 w-3" /> Subtasks</span>
          <div className="flex flex-col gap-1">
            {subtasks.map((s) => (
              <label key={s.id} className="flex items-center gap-2 rounded-lg border border-border/40 bg-secondary/20 px-2 py-1 text-[0.6rem]">
                <input type="checkbox" checked={s.done} onChange={() => setSubtasks((list) => list.map((x) => x.id === s.id ? { ...x, done: !x.done } : x))} className="h-3 w-3 accent-primary" />
                <span className={cn('flex-1', s.done && 'text-muted-foreground line-through')}>{s.text}</span>
                <button type="button" onClick={() => setSubtasks((list) => list.filter((x) => x.id !== s.id))} className="text-muted-foreground hover:text-destructive"><X className="h-3 w-3" /></button>
              </label>
            ))}
          </div>
          <div className="mt-1.5 flex gap-1.5">
            <input value={subtaskDraft} onChange={(e) => setSubtaskDraft(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addSubtask())} placeholder="Add a subtask…" className="flex-1 rounded-lg border border-border bg-background/60 px-2.5 py-1.5 text-[0.6rem] text-foreground outline-none focus:border-primary/60" />
            <button type="button" onClick={addSubtask} className="rounded-lg border border-border px-2.5 py-1.5 text-[0.6rem] text-muted-foreground hover:text-foreground">Add</button>
          </div>
        </div>

        {dependencyCandidates.length > 0 && (
          <div>
            <span className="mb-1 flex items-center gap-1 text-[0.5rem] text-muted-foreground"><Link2 className="h-3 w-3" /> Dependencies <span className="opacity-60">(must reach Archive before this can Execute)</span></span>
            <div className="flex max-h-28 flex-wrap gap-1 overflow-y-auto rounded-lg border border-border/50 bg-background/40 p-2">
              {dependencyCandidates.map((m) => (
                <button key={m.id} type="button" onClick={() => toggleDependency(m.id)} className={cn('rounded-full border px-2 py-0.5 text-[0.5rem] transition-colors', dependencies.includes(m.id) ? 'border-primary bg-primary/15 text-primary' : 'border-border/50 text-muted-foreground hover:border-primary/40')}>
                  {m.title}
                </button>
              ))}
            </div>
          </div>
        )}

        {mission && mission.history.length > 0 && (
          <div>
            <button type="button" onClick={() => setHistoryOpen((v) => !v)} className="flex w-full items-center gap-1 text-[0.5rem] text-muted-foreground hover:text-foreground">
              <History className="h-3 w-3" /> Stage history ({mission.history.length}) <ChevronDown className={cn('h-3 w-3 transition-transform', historyOpen && 'rotate-180')} />
            </button>
            {historyOpen && (
              <div className="mt-1.5 flex flex-col gap-1 rounded-lg border border-border/40 bg-background/30 p-2">
                {mission.history.map((h, i) => (
                  <div key={i} className="flex items-center justify-between text-[0.5rem] text-muted-foreground">
                    <span className="text-foreground">{STAGE_LABELS[h.stage]}</span>
                    <span>{new Date(h.at * 1000).toLocaleString('en-GB')}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="mt-1 flex items-center justify-between gap-2">
          {onDelete ? (
            <button type="button" onClick={onDelete} className="flex items-center gap-1 rounded-lg border border-destructive/40 px-3 py-1.5 text-[0.6rem] text-destructive hover:bg-destructive/10">
              <Trash2 className="h-3 w-3" /> Delete
            </button>
          ) : <span />}
          <div className="flex items-center gap-2">
            <button type="button" onClick={onClose} className="rounded-lg border border-border px-3 py-1.5 text-[0.6rem] text-muted-foreground hover:text-foreground">Cancel</button>
            <button type="button" onClick={submit} disabled={!title.trim()} className="rounded-lg border border-primary bg-primary/15 px-3 py-1.5 text-[0.6rem] text-primary transition-colors hover:bg-primary/25 disabled:opacity-40">
              {mission ? 'Save' : 'Create'}
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  )
}
