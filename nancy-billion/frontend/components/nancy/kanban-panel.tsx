'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { cn } from '@/lib/utils'
import { HudPanel } from './hud-bits'
import { listAgents, runAgent, summarizeResult, saveToDesktop, proseFromResult } from '@/lib/nancy/agent-client'
import { timeAgo } from '@/lib/nancy/time'
import type { AgentInfo, AgentResult } from '@/lib/nancy/types'
import {
  Plus,
  X,
  Trash2,
  Play,
  Loader2,
  Flag,
  CalendarClock,
  Tag,
  Bot,
  CheckCircle2,
  XCircle,
  FileDown,
} from 'lucide-react'

type ColumnKey = 'inbox' | 'assigned' | 'in_progress' | 'review' | 'done'
type Priority = 'low' | 'medium' | 'high' | 'critical'

interface KanbanCard {
  id: string
  title: string
  description: string
  tags: string[]
  assignedAgent: string | null
  priority: Priority
  dueDate: string | null
  column: ColumnKey
  createdAt: number
  updatedAt: number
  saveToDesktop: boolean
  runResult?: { success: boolean; text: string; at: number; savedFile?: string }
}

interface FeedEvent {
  id: string
  text: string
  at: number
}

const COLUMNS: { key: ColumnKey; label: string }[] = [
  { key: 'inbox', label: 'Inbox' },
  { key: 'assigned', label: 'Assigned' },
  { key: 'in_progress', label: 'In Progress' },
  { key: 'review', label: 'Review' },
  { key: 'done', label: 'Done' },
]

const PRIORITY_COLOR: Record<Priority, string> = {
  low: 'border-border/60 text-muted-foreground bg-secondary/30',
  medium: 'border-primary/40 text-primary bg-primary/10',
  high: 'border-accent/40 text-accent bg-accent/10',
  critical: 'border-magenta/40 text-magenta bg-magenta/10',
}

const STORAGE_KEY = 'nancy.kanban.cards.v1'

let cardSeq = 0
function newId() {
  cardSeq += 1
  return `card_${Date.now()}_${cardSeq}`
}

function loadCards(): KanbanCard[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    // Normalize cards saved before `saveToDesktop` existed.
    return parsed.map((c: Partial<KanbanCard>) => ({ saveToDesktop: false, ...c }) as KanbanCard)
  } catch {
    return []
  }
}

function saveCards(cards: KanbanCard[]) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(cards))
  } catch {
    // quota / private-mode — the board still works for this session, just won't persist
  }
}

/**
 * A genuinely functional Kanban board for coordinating tasks across Nancy's
 * real agent fleet -- cards persist to localStorage (drag/drop, create,
 * edit, delete all survive a refresh), and a card assigned to a real agent
 * can actually be dispatched to it (via the same /agents/run the Agents tab
 * uses) instead of just sitting there as a static to-do item.
 */
export function KanbanPanel() {
  const [cards, setCards] = useState<KanbanCard[]>([])
  const [loaded, setLoaded] = useState(false)
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [feed, setFeed] = useState<FeedEvent[]>([])
  const [composerOpen, setComposerOpen] = useState(false)
  const [editingCard, setEditingCard] = useState<KanbanCard | null>(null)
  const [dragOverCol, setDragOverCol] = useState<ColumnKey | null>(null)
  const [runningId, setRunningId] = useState<string | null>(null)
  const dragCardId = useRef<string | null>(null)

  const refreshAgents = useCallback(() => {
    listAgents().then((res) => res.success && setAgents(res.agents))
  }, [])

  useEffect(() => {
    setCards(loadCards())
    setLoaded(true)
    refreshAgents()
    const t = setInterval(refreshAgents, 30_000)
    return () => clearInterval(t)
  }, [refreshAgents])

  useEffect(() => {
    if (loaded) saveCards(cards)
  }, [cards, loaded])

  const logEvent = useCallback((text: string) => {
    setFeed((f) => [{ id: newId(), text, at: Date.now() }, ...f].slice(0, 30))
  }, [])

  const upsertCard = useCallback((card: KanbanCard, isNew: boolean) => {
    setCards((prev) => {
      const next = isNew ? [...prev, card] : prev.map((c) => (c.id === card.id ? card : c))
      return next
    })
    logEvent(isNew ? `Created "${card.title}"` : `Updated "${card.title}"`)
  }, [logEvent])

  const deleteCard = useCallback((id: string) => {
    setCards((prev) => {
      const card = prev.find((c) => c.id === id)
      if (card) logEvent(`Deleted "${card.title}"`)
      return prev.filter((c) => c.id !== id)
    })
  }, [logEvent])

  const moveCard = useCallback((id: string, column: ColumnKey) => {
    setCards((prev) => prev.map((c) => {
      if (c.id !== id || c.column === column) return c
      logEvent(`Moved "${c.title}" → ${COLUMNS.find((k) => k.key === column)?.label}`)
      return { ...c, column, updatedAt: Date.now() }
    }))
  }, [logEvent])

  const runCard = useCallback(async (card: KanbanCard) => {
    if (!card.assignedAgent) return
    setRunningId(card.id)
    setCards((prev) => prev.map((c) => c.id === card.id ? { ...c, column: 'in_progress', updatedAt: Date.now() } : c))
    logEvent(`Dispatching "${card.title}" to ${card.assignedAgent}…`)
    try {
      const res: AgentResult = await runAgent(card.assignedAgent, 'query', { query: card.description || card.title })
      const text = summarizeResult(res)
      let savedFile: string | undefined
      if (res.success && card.saveToDesktop) {
        const content = proseFromResult(res as unknown as Record<string, unknown>) ?? JSON.stringify(res, null, 2)
        const slug = card.title.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'task-output'
        const saved = await saveToDesktop(`${slug}.txt`, content)
        if (saved.success && saved.filename) {
          savedFile = saved.filename
          logEvent(`Saved "${card.title}" output to Desktop\\${saved.filename}`)
        } else {
          logEvent(`Could not save "${card.title}" to Desktop: ${saved.error || 'unknown error'}`)
        }
      }
      setCards((prev) => prev.map((c) => c.id === card.id
        ? { ...c, runResult: { success: res.success, text, at: Date.now(), savedFile }, column: res.success ? 'review' : 'assigned', updatedAt: Date.now() }
        : c))
      logEvent(`${card.assignedAgent} ${res.success ? 'completed' : 'failed'}: "${card.title}"`)
    } catch (e) {
      setCards((prev) => prev.map((c) => c.id === card.id
        ? { ...c, runResult: { success: false, text: String(e), at: Date.now() }, column: 'assigned', updatedAt: Date.now() }
        : c))
      logEvent(`${card.assignedAgent} errored on "${card.title}"`)
    } finally {
      setRunningId(null)
      refreshAgents()
    }
  }, [logEvent, refreshAgents])

  // Auto-pickup: assigning an agent to a card is enough to get it worked on --
  // you shouldn't also have to manually hit Run. Any card sitting in Inbox or
  // Assigned with an agent and no result yet gets picked up shortly after it
  // appears, moving Inbox -> Assigned -> In Progress on its own.
  //
  // Real bug this replaced: the Inbox->Assigned setCards call below used to
  // happen inside the same effect that scheduled the run via setTimeout,
  // with `cards` as a dependency and a `clearTimeout` cleanup. That setCards
  // call changes `cards`, which re-runs this very effect, and React tears
  // down the *previous* instance first -- clearTimeout cancelled the timer
  // that had just been scheduled, before it ever fired. The card visibly
  // moved to "Assigned" and then just sat there forever, since the
  // already-picked-up guard (autoPickedUp) also blocked any later effect
  // run from rescheduling it. Fix: the timer's lifetime is no longer tied
  // to this effect's cleanup -- only a genuine component-unmount cancels it.
  const autoPickedUp = useRef<Set<string>>(new Set())
  const unmountedRef = useRef(false)
  useEffect(() => () => { unmountedRef.current = true }, [])

  useEffect(() => {
    if (!loaded || runningId) return
    const pending = cards.find((c) =>
      c.assignedAgent &&
      !c.runResult &&
      (c.column === 'inbox' || c.column === 'assigned') &&
      !autoPickedUp.current.has(c.id),
    )
    if (!pending) return
    autoPickedUp.current.add(pending.id)
    if (pending.column === 'inbox') {
      setCards((prev) => prev.map((c) => c.id === pending.id ? { ...c, column: 'assigned', updatedAt: Date.now() } : c))
      logEvent(`${pending.assignedAgent} picked up "${pending.title}"`)
    }
    setTimeout(() => {
      if (unmountedRef.current) return
      void runCard(pending)
    }, 900)
  }, [cards, loaded, runningId, logEvent, runCard])

  const grouped = useMemo(() => {
    const g: Record<ColumnKey, KanbanCard[]> = { inbox: [], assigned: [], in_progress: [], review: [], done: [] }
    for (const c of cards) g[c.column]?.push(c)
    return g
  }, [cards])

  const onlineAgentKeys = useMemo(() => new Set(agents.filter((a) => a.status === 'online').map((a) => a.key)), [agents])

  const doneToday = cards.filter((c) => c.column === 'done' && new Date(c.updatedAt).toDateString() === new Date().toDateString()).length

  return (
    <div className="mx-auto flex max-w-[1680px] flex-col gap-4">
      {/* Header strip -- real counts, not decorative */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 text-[0.6rem]">
          <span className="rounded-full border border-border/60 bg-secondary/30 px-3 py-1 text-muted-foreground">
            {agents.filter((a) => a.status === 'online').length} agents active
          </span>
          <span className="rounded-full border border-border/60 bg-secondary/30 px-3 py-1 text-muted-foreground">
            {cards.filter((c) => c.column !== 'done').length} tasks in queue
          </span>
          <span className="rounded-full border border-primary/40 bg-primary/10 px-3 py-1 text-primary">
            {doneToday} done today
          </span>
        </div>
        <button
          type="button"
          onClick={() => { setEditingCard(null); setComposerOpen(true) }}
          className="flex items-center gap-1.5 rounded border border-primary bg-primary/15 px-3 py-1.5 text-[0.6rem] text-primary transition-colors hover:bg-primary/25"
        >
          <Plus className="h-3.5 w-3.5" /> New Task
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_260px]">
        {/* Board */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {COLUMNS.map((col) => (
            <div
              key={col.key}
              onDragOver={(e) => { e.preventDefault(); setDragOverCol(col.key) }}
              onDragLeave={() => setDragOverCol((c) => (c === col.key ? null : c))}
              onDrop={(e) => {
                e.preventDefault()
                setDragOverCol(null)
                const id = dragCardId.current
                if (id) moveCard(id, col.key)
              }}
              className={cn(
                'flex min-h-[220px] flex-col gap-2 rounded-md border p-2 transition-colors',
                dragOverCol === col.key ? 'border-primary bg-primary/5' : 'border-border/40 bg-background/30',
              )}
            >
              <div className="flex items-center justify-between px-1">
                <span className="font-heading text-[0.6rem] text-muted-foreground">{col.label}</span>
                <span className="rounded-full bg-secondary/50 px-1.5 py-0.5 text-[0.5rem] text-muted-foreground">{grouped[col.key].length}</span>
              </div>
              <div className="flex flex-1 flex-col gap-2">
                {grouped[col.key].map((card) => {
                  const agentOnline = card.assignedAgent && onlineAgentKeys.has(card.assignedAgent)
                  return (
                    <div
                      key={card.id}
                      draggable
                      onDragStart={() => { dragCardId.current = card.id }}
                      onClick={() => { setEditingCard(card); setComposerOpen(true) }}
                      className={cn(
                        'group cursor-pointer rounded border p-2.5 text-left transition-all duration-200 hover:-translate-y-0.5',
                        agentOnline ? 'glow-ring border-transparent bg-secondary/50' : 'border-border/50 bg-secondary/30 hover:border-primary/40',
                      )}
                    >
                      <div className="mb-1.5 flex items-start justify-between gap-2">
                        <p className="text-[0.65rem] font-medium leading-snug text-foreground">{card.title}</p>
                        <span className={cn('shrink-0 rounded border px-1.5 py-0.5 text-[0.4rem] ', PRIORITY_COLOR[card.priority])}>
                          {card.priority}
                        </span>
                      </div>
                      {card.description && (
                        <p className="mb-1.5 line-clamp-2 text-[0.55rem] text-muted-foreground">{card.description}</p>
                      )}
                      {card.tags.length > 0 && (
                        <div className="mb-1.5 flex flex-wrap gap-1">
                          {card.tags.map((t) => (
                            <span key={t} className="rounded bg-primary/10 px-1 py-px text-[0.42rem] text-primary/80">{t}</span>
                          ))}
                        </div>
                      )}
                      {card.runResult && (
                        <div className={cn(
                          'mb-1.5 flex flex-col gap-1 rounded border px-1.5 py-1 text-[0.5rem]',
                          card.runResult.success ? 'border-primary/30 bg-primary/5 text-primary' : 'border-destructive/30 bg-destructive/5 text-destructive',
                        )}>
                          <div className="flex items-start gap-1">
                            {card.runResult.success ? <CheckCircle2 className="mt-px h-3 w-3 shrink-0" /> : <XCircle className="mt-px h-3 w-3 shrink-0" />}
                            <span className="line-clamp-2">{card.runResult.text}</span>
                          </div>
                          {card.runResult.savedFile && (
                            <div className="flex items-center gap-1 text-primary/80">
                              <FileDown className="h-2.5 w-2.5 shrink-0" />
                              <span className="truncate">Desktop\{card.runResult.savedFile}</span>
                            </div>
                          )}
                        </div>
                      )}
                      {runningId === card.id && (
                        <div className="mb-1.5 flex items-center gap-1 rounded border border-accent/30 bg-accent/5 px-1.5 py-1 text-[0.5rem] text-accent">
                          <Loader2 className="h-3 w-3 shrink-0 animate-spin" /> running…
                        </div>
                      )}
                      <div className="flex items-center justify-between gap-1 text-[0.45rem] text-muted-foreground">
                        <span className="flex items-center gap-1">
                          {card.assignedAgent && (
                            <span className={cn('flex items-center gap-0.5', agentOnline && 'text-primary')}>
                              <Bot className="h-2.5 w-2.5" /> {card.assignedAgent}
                            </span>
                          )}
                        </span>
                        <span className="flex items-center gap-1.5">
                          {card.dueDate && (
                            <span className="flex items-center gap-0.5">
                              <CalendarClock className="h-2.5 w-2.5" /> {card.dueDate}
                            </span>
                          )}
                          {card.assignedAgent && (
                            <button
                              type="button"
                              title="Dispatch to agent"
                              aria-label={`Dispatch "${card.title}" to ${card.assignedAgent}`}
                              onClick={(e) => { e.stopPropagation(); void runCard(card) }}
                              disabled={runningId === card.id}
                              className="flex h-5 w-5 items-center justify-center rounded border border-primary/40 text-primary opacity-0 transition-opacity hover:bg-primary/15 group-hover:opacity-100 group-focus-within:opacity-100 focus-visible:opacity-100"
                            >
                              {runningId === card.id ? <Loader2 className="h-2.5 w-2.5 animate-spin" /> : <Play className="h-2.5 w-2.5" />}
                            </button>
                          )}
                          <button
                            type="button"
                            title="Delete"
                            aria-label={`Delete "${card.title}"`}
                            onClick={(e) => { e.stopPropagation(); deleteCard(card.id) }}
                            className="flex h-5 w-5 items-center justify-center rounded border border-border/50 text-muted-foreground opacity-0 transition-opacity hover:border-destructive/50 hover:text-destructive group-hover:opacity-100 group-focus-within:opacity-100 focus-visible:opacity-100"
                          >
                            <Trash2 className="h-2.5 w-2.5" />
                          </button>
                        </span>
                      </div>
                    </div>
                  )
                })}
                {grouped[col.key].length === 0 && (
                  <p className="py-4 text-center text-[0.5rem] text-muted-foreground/50">Empty</p>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Live feed -- real actions taken on this board this session */}
        <HudPanel title="Live Feed" accent="violet" right={<span className="text-tertiary text-[0.5rem] animate-hud-pulse">● LIVE</span>}>
          <div className="flex max-h-[560px] flex-col gap-2 overflow-y-auto">
            {feed.length === 0 ? (
              <p className="py-6 text-center text-[0.55rem] text-muted-foreground">No activity yet — create a task to get started.</p>
            ) : (
              feed.map((e) => (
                <div key={e.id} className="rounded border border-border/40 bg-secondary/20 px-2 py-1.5 text-[0.55rem]">
                  <p className="text-foreground">{e.text}</p>
                  <p className="mt-0.5 text-[0.45rem] text-muted-foreground">{timeAgo(e.at)}</p>
                </div>
              ))
            )}
          </div>
        </HudPanel>
      </div>

      {composerOpen && (
        <CardComposer
          card={editingCard}
          agents={agents}
          onClose={() => setComposerOpen(false)}
          onSave={(card, isNew) => { upsertCard(card, isNew); setComposerOpen(false) }}
        />
      )}
    </div>
  )
}

function CardComposer({
  card,
  agents,
  onClose,
  onSave,
}: {
  card: KanbanCard | null
  agents: AgentInfo[]
  onClose: () => void
  onSave: (card: KanbanCard, isNew: boolean) => void
}) {
  const [title, setTitle] = useState(card?.title ?? '')
  const [description, setDescription] = useState(card?.description ?? '')
  const [tagsInput, setTagsInput] = useState(card?.tags.join(', ') ?? '')
  const [assignedAgent, setAssignedAgent] = useState(card?.assignedAgent ?? '')
  const [priority, setPriority] = useState<Priority>(card?.priority ?? 'medium')
  const [dueDate, setDueDate] = useState(card?.dueDate ?? '')
  const [column, setColumn] = useState<ColumnKey>(card?.column ?? 'inbox')
  const [saveToDesktopFlag, setSaveToDesktopFlag] = useState(card?.saveToDesktop ?? false)

  const submit = () => {
    if (!title.trim()) return
    const now = Date.now()
    onSave({
      id: card?.id ?? newId(),
      title: title.trim(),
      description: description.trim(),
      tags: tagsInput.split(',').map((t) => t.trim()).filter(Boolean),
      assignedAgent: assignedAgent || null,
      priority,
      dueDate: dueDate || null,
      column,
      saveToDesktop: saveToDesktopFlag,
      createdAt: card?.createdAt ?? now,
      updatedAt: now,
      runResult: card?.runResult,
    }, !card)
  }

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <button type="button" aria-label="Dismiss" onClick={onClose} className="absolute inset-0 cursor-default bg-background/80 backdrop-blur-md" />
      <div className="hud-panel glow-ring relative z-10 w-full max-w-md rounded-lg border-transparent p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-heading text-xs text-primary">
            {card ? 'Edit Task' : 'New Task'}
          </h3>
          <button type="button" onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex flex-col gap-3">
          <input
            autoFocus
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Task title…"
            className="rounded border border-border bg-background/60 px-2.5 py-2 text-[0.7rem] text-foreground outline-none focus:border-primary/60"
          />
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Description — this becomes the query sent to the agent if dispatched…"
            rows={3}
            className="resize-none rounded border border-border bg-background/60 px-2.5 py-2 text-[0.65rem] text-foreground outline-none focus:border-primary/60"
          />
          <div className="grid grid-cols-2 gap-2">
            <label className="flex flex-col gap-1 text-[0.5rem] text-muted-foreground">
              <span className="flex items-center gap-1"><Bot className="h-3 w-3" /> Assign agent</span>
              <span className="text-[0.42rem] normal-case tracking-normal opacity-70">Assigning an agent dispatches this task automatically — no need to also hit Run.</span>
              <select
                value={assignedAgent}
                onChange={(e) => setAssignedAgent(e.target.value)}
                className="rounded border border-border bg-background/60 px-2 py-1.5 text-[0.6rem] text-foreground outline-none focus:border-primary/60"
              >
                <option value="">— unassigned —</option>
                {agents.map((a) => (
                  <option key={a.key} value={a.key}>{a.name} ({a.status})</option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-[0.5rem] text-muted-foreground">
              <span className="flex items-center gap-1"><Flag className="h-3 w-3" /> Priority</span>
              <select
                value={priority}
                onChange={(e) => setPriority(e.target.value as Priority)}
                className="rounded border border-border bg-background/60 px-2 py-1.5 text-[0.6rem] text-foreground outline-none focus:border-primary/60"
              >
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-[0.5rem] text-muted-foreground">
              <span className="flex items-center gap-1"><CalendarClock className="h-3 w-3" /> Due date</span>
              <input
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                className="rounded border border-border bg-background/60 px-2 py-1.5 text-[0.6rem] text-foreground outline-none focus:border-primary/60"
              />
            </label>
            <label className="flex flex-col gap-1 text-[0.5rem] text-muted-foreground">
              <span>Column</span>
              <select
                value={column}
                onChange={(e) => setColumn(e.target.value as ColumnKey)}
                className="rounded border border-border bg-background/60 px-2 py-1.5 text-[0.6rem] text-foreground outline-none focus:border-primary/60"
              >
                {COLUMNS.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
              </select>
            </label>
          </div>
          <label className="flex flex-col gap-1 text-[0.5rem] text-muted-foreground">
            <span className="flex items-center gap-1"><Tag className="h-3 w-3" /> Tags (comma-separated)</span>
            <input
              value={tagsInput}
              onChange={(e) => setTagsInput(e.target.value)}
              placeholder="e.g. research, urgent"
              className="rounded border border-border bg-background/60 px-2.5 py-1.5 text-[0.6rem] text-foreground outline-none focus:border-primary/60"
            />
          </label>
          <label className="flex items-center gap-2 text-[0.55rem] text-muted-foreground">
            <input
              type="checkbox"
              checked={saveToDesktopFlag}
              onChange={(e) => setSaveToDesktopFlag(e.target.checked)}
              className="h-3 w-3 accent-primary"
            />
            <span className="flex items-center gap-1"><FileDown className="h-3 w-3" /> Save the agent's output to a file on the Desktop</span>
          </label>
        </div>

        <div className="mt-4 flex items-center justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded border border-border px-3 py-1.5 text-[0.6rem] text-muted-foreground hover:text-foreground">
            Cancel
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!title.trim()}
            className="rounded border border-primary bg-primary/15 px-3 py-1.5 text-[0.6rem] text-primary transition-colors hover:bg-primary/25 disabled:opacity-40"
          >
            {card ? 'Save' : 'Create'}
          </button>
        </div>
      </div>
    </div>
  )
}
