'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { HudPanel } from './hud-bits'
import { listAgents } from '@/lib/nancy/agent-client'
import { useCronStatus, useConfigPublic, useTelegramStatus, useLlmStatus } from '@/hooks/useSystemData'
import type { AgentInfo, LogEntry } from '@/lib/nancy/types'
import { cn } from '@/lib/utils'
import {
  Send, MessagesSquare, Hash, Phone, Globe2, CheckCircle2, XCircle,
  Wrench, Sparkles, Cpu, Waves, Eye, EyeOff, Key, User, Server,
  BookOpen, BarChart3, PlugZap, Webhook, Link2, Loader2,
  Plus, Trash2, Save, Bot, ToggleLeft, ToggleRight,
  Radar, ChevronRight, Lock, ShieldCheck,
  CalendarClock, Library, ArrowRight, FileCode2,
  Fingerprint, Layers, MessageCircle, SendHorizonal,
} from 'lucide-react'

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

/* Small shared primitives for the CRUD panels below */
function PrimaryButton({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={cn(
        'flex items-center justify-center gap-1.5 rounded-lg border border-primary bg-primary/15 px-3 py-1.5 text-[0.6rem] text-primary transition-colors hover:bg-primary/25 disabled:cursor-not-allowed disabled:opacity-40',
        props.className,
      )}
    >
      {children}
    </button>
  )
}
function FieldLabel({ children }: { children: React.ReactNode }) {
  return <label className="mb-1 block text-[0.55rem] text-muted-foreground">{children}</label>
}
const inputCls = 'w-full rounded border border-border bg-background/60 px-2 py-1.5 text-[0.6rem] text-foreground outline-none focus:border-primary/60'

function EmptyNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded border border-dashed border-border/60 bg-secondary/10 px-3 py-4 text-center text-[0.6rem] text-muted-foreground">
      {children}
    </div>
  )
}

function LegendDotLocal({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="h-2 w-2 rounded-sm" style={{ background: color }} />
      {label}
    </span>
  )
}

function StatusPill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={cn(
      'flex items-center gap-1 rounded-full border px-2 py-0.5 text-[0.5rem] ',
      ok ? 'border-primary/40 bg-primary/10 text-primary' : 'border-border/50 text-muted-foreground',
    )}>
      {ok ? <CheckCircle2 className="h-2.5 w-2.5" /> : <XCircle className="h-2.5 w-2.5" />}
      {label}
    </span>
  )
}

/* ═══════════════════ SESSIONS — a live transcript rail, not a stat grid.
   Same real `logs` prop, same real turn counts — presented as a running
   conversation stream: user turns right-aligned, Nancy turns left-aligned
   on a center rail, system-level entries collapse to thin center dividers
   instead of taking a full turn slot. ═══════════════════════════════════ */
export function SessionsPanel({ logs }: { logs: LogEntry[] }) {
  const userTurns = logs.filter((l) => l.level === 'user').length
  const nancyTurns = logs.filter((l) => l.level === 'nancy').length
  const started = logs[0]?.ts ?? Date.now()
  return (
    <div className="mx-auto flex max-w-[1100px] flex-col gap-3">
      {/* slim session bar — live counts inline, no boxed stat grid */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card/60 px-4 py-3">
        <div className="flex items-center gap-2">
          <MessageCircle className="h-4 w-4 text-primary animate-hud-breathe" />
          <span className="font-heading text-xs text-foreground">Live Session</span>
          <span className="text-[0.55rem] text-muted-foreground">
            started {new Date(started).toLocaleTimeString('en-GB')} · this browser tab only
          </span>
        </div>
        <div className="flex items-center gap-4 text-[0.62rem]">
          <span className="flex items-center gap-1.5 text-accent">
            <span className="h-1.5 w-1.5 rounded-full bg-accent" /> {userTurns} you
          </span>
          <span className="flex items-center gap-1.5 text-primary">
            <span className="h-1.5 w-1.5 rounded-full bg-primary" /> {nancyTurns} nancy
          </span>
        </div>
      </div>

      <div className="rounded-xl border border-border bg-card/60 p-4">
        {logs.length === 0 ? (
          <EmptyNote>No conversation yet — say something to Nancy to populate this.</EmptyNote>
        ) : (
          <div className="flex max-h-[560px] flex-col gap-2 overflow-y-auto pr-1">
            {logs.map((l) => {
              if (l.level !== 'user' && l.level !== 'nancy') {
                return (
                  <div key={l.id} className="flex items-center gap-2 py-1 text-[0.55rem] text-muted-foreground">
                    <span className="h-px flex-1 bg-border/50" />
                    <span className="shrink-0 font-mono">{l.text}</span>
                    <span className="shrink-0 font-mono opacity-70">{new Date(l.ts).toLocaleTimeString('en-GB')}</span>
                    <span className="h-px flex-1 bg-border/50" />
                  </div>
                )
              }
              const isUser = l.level === 'user'
              return (
                <div key={l.id} className={cn('flex w-full', isUser ? 'justify-end' : 'justify-start')}>
                  <div className={cn('flex max-w-[78%] flex-col gap-1', isUser ? 'items-end' : 'items-start')}>
                    <span className={cn('flex items-center gap-1.5 text-[0.5rem] text-muted-foreground', isUser && 'flex-row-reverse')}>
                      {isUser ? <User className="h-2.5 w-2.5" /> : <Sparkles className="h-2.5 w-2.5" />}
                      {isUser ? 'you' : 'nancy'} · {new Date(l.ts).toLocaleTimeString('en-GB')}
                    </span>
                    <div
                      className={cn(
                        'rounded-2xl px-3 py-2 text-[0.65rem] leading-relaxed',
                        isUser
                          ? 'rounded-tr-sm border border-accent/30 bg-accent/10 text-foreground'
                          : 'rounded-tl-sm border border-primary/30 bg-primary/10 text-foreground',
                      )}
                    >
                      {l.text}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

/* ═══════════════════ CHANNELS — real Telegram, honest about the rest ═══ */
const CHANNEL_DEFS = [
  { key: 'telegram', label: 'Telegram', icon: Send },
  { key: 'discord', label: 'Discord', icon: Hash },
  { key: 'slack', label: 'Slack', icon: MessagesSquare },
  { key: 'whatsapp', label: 'WhatsApp', icon: Phone },
  { key: 'web', label: 'Web Voice/Chat', icon: Globe2 },
]
/** Binary connectivity → 4 signal bars, all lit or all dim. Never invents a
 * fake strength reading — this is a step function of the one real boolean
 * each channel actually has (connected / not), just drawn like a signal
 * meter instead of a text pill. */
function SignalBars({ connected, pending }: { connected: boolean; pending?: boolean }) {
  return (
    <div className="flex items-end gap-0.5" aria-hidden>
      {[3, 5, 7, 9].map((h, i) => (
        <span
          key={i}
          className={cn(
            'w-1 rounded-sm transition-colors',
            pending ? 'bg-border/60 animate-hud-pulse' : connected ? 'bg-primary' : 'bg-border/50',
          )}
          style={{ height: h, boxShadow: connected && !pending ? '0 0 5px var(--hud)' : undefined }}
        />
      ))}
    </div>
  )
}

export function ChannelsPanel() {
  const { data: tg, loading } = useTelegramStatus()
  const liveCount = CHANNEL_DEFS.filter(({ key }) => (key === 'telegram' ? !!tg?.available : key === 'web')).length
  return (
    <div className="mx-auto flex max-w-[1680px] flex-col gap-4">
      {/* board header — a radar sweep icon and a real live-channel count,
          the only "headline number" this page can honestly show */}
      <div className="flex items-center justify-between rounded-xl border border-border bg-card/60 px-4 py-3">
        <div className="flex items-center gap-2">
          <Radar className="h-4 w-4 text-primary animate-hud-spin-slow" />
          <span className="font-heading text-xs text-foreground">Signal Board</span>
        </div>
        <span className="text-[0.6rem] text-muted-foreground">
          <span className="text-primary">{liveCount}</span> / {CHANNEL_DEFS.length} channels live
        </span>
      </div>

      {/* the strip itself — a single continuous rail of tiles, not a wrapping
          grid of equal boxes */}
      <div className="grid grid-cols-1 divide-y divide-border/50 overflow-hidden rounded-xl border border-border bg-card/60 sm:grid-cols-5 sm:divide-x sm:divide-y-0">
        {CHANNEL_DEFS.map(({ key, label, icon: Icon }) => {
          const isTelegram = key === 'telegram'
          const isWeb = key === 'web'
          const connected = isTelegram ? !!tg?.available : isWeb
          const pending = isTelegram && loading
          return (
            <div key={key} className="flex flex-col items-center gap-2 px-3 py-4 text-center">
              <span
                className={cn(
                  'flex h-9 w-9 items-center justify-center rounded-full border',
                  connected ? 'border-primary/50 bg-primary/10' : 'border-border/50 bg-secondary/20',
                )}
              >
                <Icon className={cn('h-4 w-4', connected ? 'text-primary' : 'text-muted-foreground')} />
              </span>
              <span className="font-heading text-[0.65rem] text-foreground">{label}</span>
              <SignalBars connected={connected} pending={pending} />
              {pending ? (
                <span className="flex items-center gap-1 text-[0.5rem] text-muted-foreground"><Loader2 className="h-2.5 w-2.5 animate-spin" /> checking</span>
              ) : (
                <StatusPill ok={connected} label={connected ? 'connected' : 'not configured'} />
              )}
              <p className="text-[0.5rem] leading-snug text-muted-foreground">
                {isTelegram
                  ? (tg?.available ? 'Two-way chat + approval gate active.' : tg?.error || 'TELEGRAM_BOT_TOKEN/CHAT_ID not set.')
                  : isWeb
                    ? 'This browser session — always on.'
                    : 'No integration built yet.'}
              </p>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ═══════════════════ INSTANCES — a topology ladder, not a card pair. Same
   real llm-status data (online? agents_ready?) drawn as a connected node
   rail: root process → the two real subsystems it hosts. Nothing below the
   real signal is invented — there's genuinely no multi-instance fleet, so
   the ladder stays honestly short rather than padded with fake nodes. ═══ */
export function InstancesPanel() {
  const { data: llm, loading } = useLlmStatus()
  const online = !!llm
  const agentsReady = !!llm?.agents_ready

  const nodes: { label: string; sub: string; ok: boolean; icon: React.ElementType }[] = [
    { label: 'LLM Runtime', sub: llm ? `${llm.backends.length} backend${llm.backends.length !== 1 ? 's' : ''} reachable` : 'not responding', ok: online, icon: Cpu },
    { label: 'Agent Fleet', sub: agentsReady ? 'initialised, accepting tasks' : 'still booting', ok: agentsReady, icon: Bot },
  ]

  return (
    <div className="mx-auto flex max-w-[760px] flex-col">
      {/* root node */}
      <div className="flex items-center gap-3 rounded-xl border border-border bg-card/60 px-4 py-3.5">
        <span className={cn('flex h-10 w-10 shrink-0 items-center justify-center rounded-full border', online ? 'border-primary/50 bg-primary/10' : 'border-destructive/50 bg-destructive/10')}>
          <Server className={cn('h-5 w-5', online ? 'text-primary' : 'text-destructive')} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="font-heading text-xs text-foreground">Backend Process</div>
          <div className="text-[0.55rem] text-muted-foreground">Single local process for one user — not a distributed gateway</div>
        </div>
        {loading ? <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-muted-foreground" /> : <StatusPill ok={online} label={online ? 'online' : 'unreachable'} />}
      </div>

      {/* connecting rail down to the two real subsystems */}
      <div className="ml-9 flex flex-col">
        {nodes.map((n, i) => (
          <div key={n.label} className="relative flex items-center gap-3 pl-6">
            <span
              className={cn('absolute left-0 top-0 w-px bg-border', i === nodes.length - 1 ? 'h-1/2' : 'h-full')}
              aria-hidden
            />
            <span className="absolute left-0 top-1/2 h-px w-6 bg-border" aria-hidden />
            <div className="flex flex-1 items-center gap-3 rounded-xl border border-border bg-card/50 px-4 py-3 my-1.5">
              <span className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-full border', n.ok ? 'border-primary/50 bg-primary/10' : 'border-border/50 bg-secondary/20')}>
                <n.icon className={cn('h-4 w-4', n.ok ? 'text-primary' : 'text-muted-foreground')} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-[0.65rem] text-foreground">{n.label}</div>
                <div className="text-[0.5rem] text-muted-foreground">{n.sub}</div>
              </div>
              <StatusPill ok={n.ok} label={n.ok ? 'ready' : 'not ready'} />
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3">
        <EmptyNote>Nancy runs as a single local backend process for one user — there&apos;s no multi-instance fleet to list here.</EmptyNote>
      </div>
    </div>
  )
}

/* ═══════════════════ CRON JOBS — built-in briefing + real, creatable
   custom jobs (data/cron_jobs.json on the backend, actually executed
   every 30s by _cron_execution_loop — see cron_store.py) ═══════════════ */
interface CustomCronJob {
  id: string
  name: string
  description: string
  hour: number
  minute: number
  action_type: 'telegram_message' | 'agent_task'
  action_payload: Record<string, unknown>
  enabled: boolean
  next_run: string
  last_run: string | null
  last_result: string | null
}

function NewCronJobForm({ agents, onCreated }: { agents: AgentInfo[]; onCreated: () => void }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [hour, setHour] = useState('9')
  const [minute, setMinute] = useState('0')
  const [actionType, setActionType] = useState<'telegram_message' | 'agent_task'>('telegram_message')
  const [text, setText] = useState('')
  const [agentKey, setAgentKey] = useState('')
  const [taskType, setTaskType] = useState('query')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    setSaving(true); setError(null)
    try {
      const action_payload = actionType === 'telegram_message'
        ? { text }
        : { agent_key: agentKey, task_type: taskType, payload: {} }
      const res = await fetch('/api/cron/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, description, hour: Number(hour), minute: Number(minute), action_type: actionType, action_payload }),
      })
      const json = await res.json()
      if (!json.success) { setError(json.detail || 'Failed to create job'); return }
      setName(''); setDescription(''); setText(''); setOpen(false)
      onCreated()
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  if (!open) {
    return (
      <PrimaryButton onClick={() => setOpen(true)}><Plus className="h-3.5 w-3.5" /> New job</PrimaryButton>
    )
  }

  return (
    <div className="flex flex-col gap-2.5 rounded-lg border border-border bg-secondary/20 p-3">
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
        <div>
          <FieldLabel>Name</FieldLabel>
          <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="Evening portfolio check" />
        </div>
        <div>
          <FieldLabel>Description</FieldLabel>
          <input className={inputCls} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="optional" />
        </div>
        <div className="flex gap-2">
          <div className="flex-1">
            <FieldLabel>Hour (0-23)</FieldLabel>
            <input className={inputCls} type="number" min={0} max={23} value={hour} onChange={(e) => setHour(e.target.value)} />
          </div>
          <div className="flex-1">
            <FieldLabel>Minute (0-59)</FieldLabel>
            <input className={inputCls} type="number" min={0} max={59} value={minute} onChange={(e) => setMinute(e.target.value)} />
          </div>
        </div>
        <div>
          <FieldLabel>Action</FieldLabel>
          <select className={inputCls} value={actionType} onChange={(e) => setActionType(e.target.value as 'telegram_message' | 'agent_task')}>
            <option value="telegram_message">Send Telegram message</option>
            <option value="agent_task">Run an agent task</option>
          </select>
        </div>
        {actionType === 'telegram_message' ? (
          <div className="sm:col-span-2">
            <FieldLabel>Message text</FieldLabel>
            <input className={inputCls} value={text} onChange={(e) => setText(e.target.value)} placeholder="What should Nancy send?" />
          </div>
        ) : (
          <>
            <div>
              <FieldLabel>Agent</FieldLabel>
              <select className={inputCls} value={agentKey} onChange={(e) => setAgentKey(e.target.value)}>
                <option value="">Select an agent…</option>
                {agents.map((a) => <option key={a.key} value={a.key}>{a.name}</option>)}
              </select>
            </div>
            <div>
              <FieldLabel>Task type</FieldLabel>
              <input className={inputCls} value={taskType} onChange={(e) => setTaskType(e.target.value)} placeholder="query" />
            </div>
          </>
        )}
      </div>
      {error && <p className="text-[0.55rem] text-destructive">{error}</p>}
      <div className="flex gap-2">
        <PrimaryButton
          onClick={submit}
          disabled={saving || !name.trim() || (actionType === 'telegram_message' ? !text.trim() : !agentKey)}
        >
          {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />} Create job
        </PrimaryButton>
        <button type="button" onClick={() => setOpen(false)} className="rounded-lg border border-border px-3 py-1.5 text-[0.6rem] text-muted-foreground hover:text-foreground">
          Cancel
        </button>
      </div>
    </div>
  )
}

export function CronPanel() {
  const { data, loading } = useCronStatus()
  const [jobs, setJobs] = useState<CustomCronJob[]>([])
  const [agents, setAgents] = useState<AgentInfo[]>([])

  const fetchJobs = useCallback(async () => {
    const res = await fetch('/api/cron/jobs')
    const json = await res.json()
    if (json.success) setJobs(json.jobs)
  }, [])

  useEffect(() => {
    fetchJobs()
    listAgents().then((r) => r.success && setAgents(r.agents))
    const t = setInterval(fetchJobs, 30_000)
    return () => clearInterval(t)
  }, [fetchJobs])

  const toggleJob = async (job: CustomCronJob) => {
    await fetch(`/api/cron/jobs/${job.id}?enabled=${!job.enabled}`, { method: 'PATCH' })
    fetchJobs()
  }
  const deleteJob = async (job: CustomCronJob) => {
    await fetch(`/api/cron/jobs/${job.id}`, { method: 'DELETE' })
    fetchJobs()
  }

  // Real jobs from both real sources merged into one next-run-ordered rail —
  // display grouping only, no new data invented. Built-in briefing entries
  // stay read-only (no id to toggle/delete against); custom entries keep
  // their real toggle/delete controls wired to the handlers above.
  type RailItem =
    | { kind: 'builtin'; key: string; name: string; next_run: string; enabled: boolean; detail: string; time: string }
    | { kind: 'custom'; key: string; name: string; next_run: string; enabled: boolean; detail: string; time: string; job: CustomCronJob }

  const rail = useMemo<RailItem[]>(() => {
    const builtinItems: RailItem[] = (data?.jobs ?? []).map((job) => ({
      kind: 'builtin', key: `b:${job.name}`, name: job.name, next_run: job.next_run, enabled: job.enabled,
      detail: job.description, time: job.schedule,
    }))
    const customItems: RailItem[] = jobs.map((job) => ({
      kind: 'custom', key: `c:${job.id}`, name: job.name, next_run: job.next_run, enabled: job.enabled,
      detail: job.description || (job.action_type === 'telegram_message' ? 'Telegram message' : `Agent: ${job.action_payload.agent_key}`),
      time: `${String(job.hour).padStart(2, '0')}:${String(job.minute).padStart(2, '0')} daily`, job,
    }))
    return [...builtinItems, ...customItems].sort((a, b) => new Date(a.next_run).getTime() - new Date(b.next_run).getTime())
  }, [data, jobs])

  return (
    <div className="mx-auto flex max-w-[1100px] flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card/60 px-4 py-3">
        <div className="flex items-center gap-2">
          <CalendarClock className="h-4 w-4 text-primary" />
          <span className="font-heading text-xs text-foreground">Schedule</span>
          <span className="text-[0.55rem] text-muted-foreground">next-run ordered · real jobs, checked every 30s by the backend</span>
        </div>
        <NewCronJobForm agents={agents} onCreated={fetchJobs} />
      </div>

      {loading && !data ? (
        <div className="flex items-center justify-center rounded-xl border border-border bg-card/60 py-8 text-[0.6rem] text-muted-foreground">
          <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> Loading schedule…
        </div>
      ) : rail.length === 0 ? (
        <EmptyNote>No jobs yet — create one above.</EmptyNote>
      ) : (
        <ol className="relative flex flex-col gap-3 rounded-xl border border-border bg-card/60 p-4 pl-8">
          <div className="absolute bottom-4 left-[19px] top-4 w-px bg-border" aria-hidden />
          {rail.map((item) => (
            <li key={item.key} className="relative">
              <span
                className={cn(
                  'absolute -left-[13px] top-2 h-2.5 w-2.5 rounded-full ring-4 ring-card',
                  item.enabled ? 'bg-primary' : 'bg-muted-foreground/60',
                )}
              />
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border/50 bg-secondary/20 p-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-heading text-xs text-foreground">{item.name}</span>
                    <span className={cn(
                      'rounded-full border px-1.5 py-0 text-[0.45rem] uppercase tracking-wide',
                      item.kind === 'builtin' ? 'border-accent/40 text-accent' : 'border-tertiary/40 text-tertiary',
                    )}>
                      {item.kind === 'builtin' ? 'built-in' : 'custom'}
                    </span>
                    <StatusPill ok={item.enabled} label={item.enabled ? 'enabled' : (item.kind === 'builtin' ? 'telegram not configured' : 'disabled')} />
                  </div>
                  {item.detail && <p className="mt-1 text-[0.55rem] text-muted-foreground">{item.detail}</p>}
                  {item.kind === 'custom' && item.job.last_run && (
                    <p className="mt-1 text-[0.5rem] text-muted-foreground">last ran {new Date(item.job.last_run).toLocaleString('en-GB')} — {item.job.last_result}</p>
                  )}
                </div>
                <div className="flex items-center gap-2 text-right text-[0.55rem]">
                  <div>
                    <div className="text-primary">{item.time}</div>
                    <div className="text-muted-foreground">next: {new Date(item.next_run).toLocaleString('en-GB')}</div>
                  </div>
                  {item.kind === 'custom' && (
                    <>
                      <button type="button" onClick={() => toggleJob(item.job)} className="rounded p-1.5 text-muted-foreground hover:text-primary" title="Toggle enabled" aria-label={item.job.enabled ? `Disable job "${item.job.name}"` : `Enable job "${item.job.name}"`}>
                        {item.job.enabled ? <ToggleRight className="h-4 w-4 text-primary" /> : <ToggleLeft className="h-4 w-4" />}
                      </button>
                      <button type="button" onClick={() => deleteJob(item.job)} className="rounded p-1.5 text-muted-foreground hover:text-destructive" title="Delete" aria-label={`Delete job "${item.job.name}"`}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

/* ═══════════════════ SKILLS — real specializations across the fleet, plus
   real, creatable custom skill records (data/skills.json on the backend —
   see skills_store.py) assignable to real agents ═══════════════════════ */
interface CustomSkill {
  id: string
  name: string
  description: string
  category: string
  agent_keys: string[]
}

function NewSkillForm({ agents, onCreated }: { agents: AgentInfo[]; onCreated: () => void }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState('general')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const toggleAgent = (key: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key); else next.add(key)
      return next
    })
  }

  const submit = async () => {
    setSaving(true); setError(null)
    try {
      const res = await fetch('/api/skills/custom', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, description, category, agent_keys: Array.from(selected) }),
      })
      const json = await res.json()
      if (!json.success) { setError(json.detail || 'Failed to create skill'); return }
      setName(''); setDescription(''); setSelected(new Set()); setOpen(false)
      onCreated()
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  if (!open) {
    return <PrimaryButton onClick={() => setOpen(true)}><Plus className="h-3.5 w-3.5" /> New skill</PrimaryButton>
  }

  return (
    <div className="flex flex-col gap-2.5 rounded-lg border border-border bg-secondary/20 p-3">
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
        <div>
          <FieldLabel>Name</FieldLabel>
          <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Portfolio rebalancing" />
        </div>
        <div>
          <FieldLabel>Category</FieldLabel>
          <input className={inputCls} value={category} onChange={(e) => setCategory(e.target.value)} placeholder="general" />
        </div>
        <div className="sm:col-span-2">
          <FieldLabel>Description</FieldLabel>
          <input className={inputCls} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What this skill covers" />
        </div>
        <div className="sm:col-span-2">
          <FieldLabel>Assign to agents</FieldLabel>
          <div className="flex max-h-32 flex-wrap gap-1 overflow-y-auto rounded border border-border/50 bg-background/40 p-2">
            {agents.map((a) => (
              <button
                key={a.key}
                type="button"
                onClick={() => toggleAgent(a.key)}
                className={cn(
                  'rounded-full border px-2 py-0.5 text-[0.5rem] transition-colors',
                  selected.has(a.key) ? 'border-primary bg-primary/15 text-primary' : 'border-border/50 text-muted-foreground hover:border-primary/40',
                )}
              >
                {a.name}
              </button>
            ))}
          </div>
        </div>
      </div>
      {error && <p className="text-[0.55rem] text-destructive">{error}</p>}
      <div className="flex gap-2">
        <PrimaryButton onClick={submit} disabled={saving || !name.trim()}>
          {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />} Create skill
        </PrimaryButton>
        <button type="button" onClick={() => setOpen(false)} className="rounded-lg border border-border px-3 py-1.5 text-[0.6rem] text-muted-foreground hover:text-foreground">
          Cancel
        </button>
      </div>
    </div>
  )
}

export function SkillsPanel() {
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [customSkills, setCustomSkills] = useState<CustomSkill[]>([])

  const fetchCustom = useCallback(async () => {
    const res = await fetch('/api/skills/custom')
    const json = await res.json()
    if (json.success) setCustomSkills(json.skills)
  }, [])

  useEffect(() => {
    listAgents().then((r) => { if (r.success) setAgents(r.agents); setLoading(false) })
    fetchCustom()
  }, [fetchCustom])

  const deleteSkill = async (id: string) => {
    await fetch(`/api/skills/custom/${id}`, { method: 'DELETE' })
    fetchCustom()
  }

  const agentName = (key: string) => agents.find((a) => a.key === key)?.name ?? key

  const skillMap = new Map<string, string[]>()
  for (const a of agents) {
    for (const s of a.specializations) {
      if (!skillMap.has(s)) skillMap.set(s, [])
      skillMap.get(s)!.push(a.name)
    }
  }
  const skills = Array.from(skillMap.entries()).sort((a, b) => b[1].length - a[1].length)

  return (
    <div className="mx-auto flex max-w-[1100px] flex-col gap-4">
      {/* catalog header — index count + composer, no card grid */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card/60 px-4 py-3">
        <div className="flex items-center gap-2">
          <Library className="h-4 w-4 text-tertiary" />
          <span className="font-heading text-xs text-foreground">Skill Catalog</span>
          <span className="text-[0.55rem] text-muted-foreground">{customSkills.length} custom · {skills.length} built-in</span>
        </div>
        <NewSkillForm agents={agents} onCreated={fetchCustom} />
      </div>

      {/* shelf 1 — custom, creatable, deletable */}
      <div className="rounded-xl border border-tertiary/30 bg-card/60">
        <div className="flex items-center gap-2 border-b border-border/50 px-4 py-2.5">
          <span className="h-1.5 w-1.5 rounded-full bg-tertiary" />
          <h3 className="font-heading text-[0.68rem] text-foreground">Custom Skills</h3>
        </div>
        {customSkills.length === 0 ? (
          <div className="p-4"><EmptyNote>No custom skills yet — create one above and assign it to real agents. Persisted server-side.</EmptyNote></div>
        ) : (
          <ul className="divide-y divide-border/40">
            {customSkills.map((s) => (
              <li key={s.id} className="flex items-center gap-3 px-4 py-2.5">
                <Sparkles className="h-3.5 w-3.5 shrink-0 text-tertiary" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[0.62rem] text-foreground">{s.name}</span>
                    <span className="text-[0.5rem] text-muted-foreground">{s.category}</span>
                  </div>
                  {(s.description || s.agent_keys.length > 0) && (
                    <p className="truncate text-[0.5rem] text-muted-foreground">
                      {s.description}
                      {s.description && s.agent_keys.length > 0 ? ' · ' : ''}
                      {s.agent_keys.length > 0 && <span className="text-primary">{s.agent_keys.map(agentName).join(', ')}</span>}
                    </p>
                  )}
                </div>
                <button type="button" onClick={() => deleteSkill(s.id)} className="shrink-0 text-muted-foreground hover:text-destructive">
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* shelf 2 — built-in, read-only index sorted by how many real agents hold it */}
      <div className="rounded-xl border border-border bg-card/60">
        <div className="flex items-center justify-between gap-2 border-b border-border/50 px-4 py-2.5">
          <div className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-primary" />
            <h3 className="font-heading text-[0.68rem] text-foreground">Built-in Specializations</h3>
          </div>
          <span className="text-[0.5rem] text-muted-foreground">read-only · compiled into each agent&apos;s Python class</span>
        </div>
        {loading ? (
          <div className="flex items-center justify-center py-6 text-[0.6rem] text-muted-foreground">
            <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> Reading fleet specializations…
          </div>
        ) : (
          <ul className="divide-y divide-border/40">
            {skills.map(([skill, holders]) => (
              <li key={skill} className="flex items-center gap-3 px-4 py-2">
                <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground" />
                <span className="w-48 shrink-0 truncate text-[0.62rem] text-foreground">{skill}</span>
                <span className="shrink-0 rounded-full border border-border/50 px-1.5 text-[0.45rem] text-muted-foreground">{holders.length}</span>
                <span className="min-w-0 flex-1 truncate text-[0.5rem] text-muted-foreground">{holders.join(', ')}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

/* ═══════════════════ MODELS — real LLM/STT/TTS stack ═══════════════════ */
/* ═══════════════════ MODELS — a vertical fallback-chain diagram. Distinct
   from CorePanel's flat "Model Stack" list (panels.tsx): here the real
   backend order from /llm/status is drawn as an actual pipeline — voice in
   → numbered LLM fallback links, each one a stop the request only reaches
   if everything above it failed → voice out. Same real data, no invented
   latency/uptime numbers per link. ═══════════════════════════════════════ */
export function ModelsPanel() {
  const { data: llm, loading } = useLlmStatus()
  const backends = llm?.backends ?? []
  return (
    <div className="mx-auto flex max-w-[720px] flex-col gap-1">
      <div className="mb-2 flex items-center justify-between rounded-xl border border-border bg-card/60 px-4 py-3">
        <div className="flex items-center gap-2">
          <Layers className="h-4 w-4 text-primary" />
          <span className="font-heading text-xs text-foreground">Reasoning Pipeline</span>
        </div>
        <span className="text-[0.55rem] text-muted-foreground">
          {loading && !llm ? 'reading live chain…' : `${backends.length} backend${backends.length !== 1 ? 's' : ''} configured`}
        </span>
      </div>

      {loading && !llm ? (
        <div className="flex items-center justify-center rounded-xl border border-border bg-card/60 py-8 text-[0.6rem] text-muted-foreground">
          <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> Reading live chain…
        </div>
      ) : (
        <div className="flex flex-col items-stretch">
          {/* pipeline start: voice in */}
          <div className="flex items-center gap-3 rounded-xl border border-accent/30 bg-accent/5 px-4 py-2.5">
            <Waves className="h-4 w-4 shrink-0 text-accent" />
            <div className="min-w-0 flex-1">
              <div className="text-[0.62rem] text-foreground">Speech-to-Text · {llm?.stt.backend ?? '…'}</div>
              {llm?.stt.model && <div className="text-[0.5rem] text-muted-foreground">{llm.stt.model} on {llm.stt.device}</div>}
            </div>
          </div>

          <div className="flex justify-center py-1"><ArrowDownConnector /></div>

          {/* numbered fallback chain */}
          {backends.map((b, i) => (
            <div key={`${b.name}-${i}`}>
              <div className={cn(
                'flex items-center gap-3 rounded-xl border px-4 py-2.5',
                i === 0 ? 'border-primary/50 bg-primary/10' : 'border-border/50 bg-secondary/20',
              )}>
                <span className={cn(
                  'flex h-6 w-6 shrink-0 items-center justify-center rounded-full font-mono text-[0.55rem]',
                  i === 0 ? 'bg-primary/20 text-primary' : 'bg-secondary/60 text-muted-foreground',
                )}>
                  {i + 1}
                </span>
                <Cpu className={cn('h-3.5 w-3.5 shrink-0', i === 0 ? 'text-primary' : 'text-muted-foreground')} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 text-[0.62rem] text-foreground">
                    {b.name}
                    {i === 0 && <span className="rounded-full border border-primary/40 px-1.5 text-[0.45rem] uppercase text-primary">primary</span>}
                  </div>
                  <div className="truncate text-[0.5rem] text-muted-foreground">{b.model ?? 'fallback route'}</div>
                </div>
              </div>
              {i < backends.length - 1 && (
                <div className="flex justify-center py-1">
                  <span className="text-[0.5rem] text-muted-foreground">if unreachable ↓</span>
                </div>
              )}
            </div>
          ))}

          {backends.length === 0 && (
            <div className="px-4 py-3"><EmptyNote>No reasoning backend reachable — Nancy has nothing to fall back to right now.</EmptyNote></div>
          )}

          <div className="flex justify-center py-1"><ArrowDownConnector /></div>

          {/* pipeline end: voice out */}
          <div className="flex items-center gap-3 rounded-xl border border-tertiary/30 bg-tertiary/5 px-4 py-2.5">
            <Eye className="h-4 w-4 shrink-0 text-tertiary" />
            <div className="text-[0.62rem] text-foreground">Voice Synthesis · {llm?.tts.backend ?? '…'}</div>
          </div>
        </div>
      )}
    </div>
  )
}
function ArrowDownConnector() {
  return (
    <span className="flex flex-col items-center text-border">
      <span className="h-3 w-px bg-border" />
      <ArrowRight className="h-3 w-3 rotate-90 text-muted-foreground" />
    </span>
  )
}

/* ═══════════════════ KEYS — real per-provider configured state ═════════ */
const WRITABLE_KEYS = [
  { name: 'ANTHROPIC_API_KEY', label: 'Anthropic (Claude)' },
  { name: 'GROQ_API_KEY', label: 'Groq' },
  { name: 'GEMINI_API_KEY', label: 'Gemini' },
  { name: 'OPENROUTER_API_KEY', label: 'OpenRouter' },
  { name: 'OPENCODE_API_KEY', label: 'OpenCode Zen' },
  { name: 'TELEGRAM_BOT_TOKEN', label: 'Telegram bot token' },
  { name: 'TELEGRAM_CHAT_ID', label: 'Telegram chat ID' },
]

function AddKeyForm() {
  const [name, setName] = useState(WRITABLE_KEYS[0].name)
  const [value, setValue] = useState('')
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)

  const submit = async () => {
    if (!value.trim()) return
    setSaving(true); setMessage(null)
    try {
      const res = await fetch('/api/config/keys', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, value }),
      })
      const json = await res.json()
      setMessage({ ok: !!json.success, text: json.message || json.detail || (json.success ? 'Saved.' : 'Failed to save.') })
      if (json.success) setValue('')
    } catch (e) {
      setMessage({ ok: false, text: String(e) })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-2.5 rounded-lg border border-border bg-secondary/20 p-3">
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-[1fr_1fr_auto]">
        <div>
          <FieldLabel>Key</FieldLabel>
          <select className={inputCls} value={name} onChange={(e) => setName(e.target.value)}>
            {WRITABLE_KEYS.map((k) => <option key={k.name} value={k.name}>{k.label}</option>)}
          </select>
        </div>
        <div>
          <FieldLabel>Value</FieldLabel>
          <input className={inputCls} type="password" value={value} onChange={(e) => setValue(e.target.value)} placeholder="pasted once, never shown again" autoComplete="off" />
        </div>
        <div className="flex items-end">
          <PrimaryButton onClick={submit} disabled={saving || !value.trim()} className="w-full sm:w-auto">
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />} Save
          </PrimaryButton>
        </div>
      </div>
      {message && (
        <p className={cn('text-[0.55rem]', message.ok ? 'text-primary' : 'text-destructive')}>{message.text}</p>
      )}
      <p className="text-[0.5rem] text-muted-foreground">
        Writes directly to backend/.env on disk (allowlisted names only). The running backend reads env vars at
        startup, so a saved key takes effect on the next backend restart, not immediately.
      </p>
    </div>
  )
}

/** A vault row: masked dots by default, click reveal to swap them for the
 * one honest thing there is to show — the real configured-state, since the
 * actual secret value is never sent to the browser and never will be. No
 * fabricated key material is ever rendered here. */
function VaultRow({ label, ok }: { label: string; ok: boolean }) {
  const [revealed, setRevealed] = useState(false)
  return (
    <li className="flex items-center gap-3 px-4 py-2.5">
      <span className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-full border', ok ? 'border-primary/40 bg-primary/10' : 'border-border/50 bg-secondary/20')}>
        <Lock className={cn('h-3.5 w-3.5', ok ? 'text-primary' : 'text-muted-foreground')} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-[0.62rem] text-foreground">{label}</div>
        <div className="font-mono text-[0.58rem] text-muted-foreground">
          {!ok ? '— not set —' : revealed ? 'configured · value stored server-side only, never sent to the browser' : '••••••••••••••••'}
        </div>
      </div>
      <StatusPill ok={ok} label={ok ? 'configured' : 'not set'} />
      <button
        type="button"
        onClick={() => setRevealed((v) => !v)}
        disabled={!ok}
        className="shrink-0 text-muted-foreground hover:text-primary disabled:cursor-not-allowed disabled:opacity-30"
        title={ok ? (revealed ? 'Hide' : 'Reveal') : 'Nothing to reveal'}
      >
        {revealed ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
      </button>
    </li>
  )
}

export function KeysPanel() {
  const { data: llm, loading } = useLlmStatus()
  const configuredNames = new Set((llm?.backends ?? []).map((b) => b.name))
  const providers = [
    { name: 'AnthropicLLM', label: 'Anthropic (Claude)' },
    { name: 'GroqLLM', label: 'Groq' },
    { name: 'GeminiLLM', label: 'Gemini' },
    { name: 'OpenRouterLLM', label: 'OpenRouter' },
    { name: 'OpenCodeLLM', label: 'OpenCode Zen' },
  ]
  const configuredCount = providers.filter((p) => configuredNames.has(p.name)).length
  return (
    <div className="mx-auto flex max-w-[760px] flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card/60 px-4 py-3">
        <div className="flex items-center gap-2">
          <Fingerprint className="h-4 w-4 text-gold" />
          <span className="font-heading text-xs text-foreground">Credential Vault</span>
        </div>
        <span className="text-[0.55rem] text-muted-foreground">{configuredCount} / {providers.length} configured</span>
      </div>

      <div className="rounded-xl border border-gold/30 bg-card/60">
        <p className="border-b border-border/50 px-4 py-2 text-[0.55rem] text-muted-foreground">
          Real configured-state only, derived from which backends actually initialised — no key values are ever exposed here or anywhere in this app.
        </p>
        {loading && !llm ? (
          <div className="flex items-center justify-center py-6 text-[0.6rem] text-muted-foreground">
            <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
          </div>
        ) : (
          <ul className="divide-y divide-border/40">
            {providers.map((p) => (
              <VaultRow key={p.name} label={p.label} ok={configuredNames.has(p.name)} />
            ))}
          </ul>
        )}
      </div>

      <div className="rounded-xl border border-border bg-card/60 p-4">
        <h3 className="mb-2.5 flex items-center gap-2 font-heading text-[0.68rem] text-foreground">
          <Key className="h-3.5 w-3.5 text-primary" /> Add / Update a Key
        </h3>
        <AddKeyForm />
      </div>
    </div>
  )
}

/* ═══════════════════ CONFIG — real non-secret backend settings ═════════ */
/* ═══════════════════ CONFIG — real non-secret backend settings, grouped
   into sections instead of one flat box. Grouping is a display-only
   heuristic over the real key names returned by /config/public — every
   value shown is exactly what the backend reports, nothing invented. ═══ */
const CONFIG_GROUPS: { label: string; icon: React.ElementType; test: RegExp }[] = [
  { label: 'Messaging', icon: Send, test: /telegram|chat|message/i },
  { label: 'Reasoning', icon: Cpu, test: /llm|model|backend|reason/i },
  { label: 'Voice', icon: Waves, test: /voice|tts|stt|audio|speech/i },
  { label: 'Scheduling', icon: CalendarClock, test: /cron|briefing|schedule|timezone|tz/i },
]
function groupConfig(config: Record<string, string | number | boolean>) {
  const groups = new Map<string, [string, string | number | boolean][]>()
  for (const [k, v] of Object.entries(config)) {
    const match = CONFIG_GROUPS.find((g) => g.test.test(k))
    const label = match?.label ?? 'General'
    if (!groups.has(label)) groups.set(label, [])
    groups.get(label)!.push([k, v])
  }
  return groups
}

export function ConfigPanel() {
  const { data, loading } = useConfigPublic()
  const groups = useMemo(() => groupConfig(data?.config ?? {}), [data])
  const entryCount = Object.keys(data?.config ?? {}).length

  return (
    <div className="mx-auto flex max-w-[900px] flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card/60 px-4 py-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-primary" />
          <span className="font-heading text-xs text-foreground">Backend Configuration</span>
        </div>
        <span className="text-[0.55rem] text-muted-foreground">{entryCount} real setting{entryCount !== 1 ? 's' : ''} · read-only</span>
      </div>

      {loading && !data ? (
        <div className="flex items-center justify-center rounded-xl border border-border bg-card/60 py-8 text-[0.6rem] text-muted-foreground">
          <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
        </div>
      ) : entryCount === 0 ? (
        <EmptyNote>No public configuration reported by the backend.</EmptyNote>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {Array.from(groups.entries()).map(([label, entries]) => {
            const meta = CONFIG_GROUPS.find((g) => g.label === label)
            const Icon = meta?.icon ?? Wrench
            return (
              <div key={label} className="overflow-hidden rounded-xl border border-border bg-card/60">
                <div className="flex items-center gap-2 border-b border-border/50 bg-secondary/10 px-3.5 py-2">
                  <Icon className="h-3.5 w-3.5 text-primary" />
                  <h3 className="font-heading text-[0.65rem] text-foreground">{label}</h3>
                  <span className="ml-auto text-[0.5rem] text-muted-foreground">{entries.length}</span>
                </div>
                <dl className="divide-y divide-border/30">
                  {entries.map(([k, v]) => (
                    <div key={k} className="flex items-center justify-between gap-3 px-3.5 py-1.5 text-[0.6rem]">
                      <dt className="min-w-0 truncate text-muted-foreground">{k}</dt>
                      <dd className="shrink-0 text-primary">{String(v)}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

/* ═══════════════════ USAGE — real task/success stats ═══════════════════ */
/* ═══════════════════ USAGE — a metrics ledger, distinct from Overview's
   recharts telemetry (panels.tsx). No charting library here at all: one
   real headline number plus a real proportional bar (success vs failure
   out of the real total_tasks/failed_tasks the fleet reports) and a
   ledger-style stat list. Same single fetch-on-mount as before. ═══════ */
export function UsagePanel() {
  const [stats, setStats] = useState<{ agents_online: number; total_tasks: number; failed_tasks: number; success_rate: number } | null>(null)
  useEffect(() => { listAgents().then((r) => r.success && setStats(r.stats)) }, [])

  const succeeded = stats ? Math.max(0, stats.total_tasks - stats.failed_tasks) : 0
  const successPct = stats && stats.total_tasks > 0 ? (succeeded / stats.total_tasks) * 100 : 0
  const failPct = stats && stats.total_tasks > 0 ? (stats.failed_tasks / stats.total_tasks) * 100 : 0

  return (
    <div className="mx-auto flex max-w-[900px] flex-col gap-4">
      <div className="flex items-center gap-2 rounded-xl border border-border bg-card/60 px-4 py-3">
        <BarChart3 className="h-4 w-4 text-primary" />
        <span className="font-heading text-xs text-foreground">Fleet Usage Ledger</span>
      </div>

      {/* headline metric */}
      <div className="rounded-xl border border-primary/25 bg-gradient-to-br from-card via-card to-primary/5 p-5">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="text-[0.55rem] text-muted-foreground">Success Rate</div>
            <div className="font-display text-4xl text-primary">
              {stats ? `${(stats.success_rate * 100).toFixed(0)}` : '…'}<span className="text-lg text-muted-foreground">%</span>
            </div>
          </div>
          <div className="text-right text-[0.55rem] text-muted-foreground">
            {stats ? `${succeeded} succeeded of ${stats.total_tasks} tasks run` : 'loading…'}
          </div>
        </div>
        {/* real proportional bar — succeeded vs failed out of total_tasks */}
        <div className="mt-3 flex h-2 overflow-hidden rounded-full bg-secondary/40">
          <div className="h-full bg-primary transition-all duration-700" style={{ width: `${successPct}%` }} />
          <div className="h-full bg-destructive/70 transition-all duration-700" style={{ width: `${failPct}%` }} />
        </div>
        <div className="mt-1.5 flex items-center gap-4 text-[0.5rem] text-muted-foreground">
          <LegendDotLocal color="var(--hud)" label={`${succeeded} succeeded`} />
          <LegendDotLocal color="var(--destructive)" label={`${stats?.failed_tasks ?? 0} failed`} />
        </div>
      </div>

      {/* ledger rows */}
      <div className="divide-y divide-border/40 rounded-xl border border-border bg-card/60">
        {[
          { label: 'Agents Online', v: stats?.agents_online ?? '…', icon: Bot, tone: 'text-primary' },
          { label: 'Tasks Run', v: stats?.total_tasks ?? '…', icon: Layers, tone: 'text-foreground' },
          { label: 'Failures', v: stats?.failed_tasks ?? '…', icon: XCircle, tone: 'text-destructive' },
        ].map(({ label, v, icon: Icon, tone }) => (
          <div key={label} className="flex items-center justify-between px-4 py-2.5">
            <span className="flex items-center gap-2 text-[0.62rem] text-muted-foreground">
              <Icon className={cn('h-3.5 w-3.5', tone)} /> {label}
            </span>
            <span className={cn('font-heading text-xs', tone)}>{v}</span>
          </div>
        ))}
      </div>

      <p className="text-[0.55rem] text-muted-foreground">
        Nancy doesn&apos;t meter LLM token spend per-request yet, so cost/usage-by-provider isn&apos;t shown here — this reflects real agent task volume only.
      </p>
    </div>
  )
}

/* ═══════════════════ PAIRING — real Telegram chat_id pairing ═══════════ */
function PairingFlow() {
  const [code, setCode] = useState<string | null>(null)
  const [status, setStatus] = useState<'idle' | 'starting' | 'waiting' | 'paired' | 'expired' | 'error'>('idle')
  const [chatId, setChatId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const start = async () => {
    setStatus('starting'); setError(null)
    try {
      const res = await fetch('/api/telegram/pair/start', { method: 'POST' })
      const json = await res.json()
      if (!json.success) { setError(json.error || 'Could not start pairing'); setStatus('error'); return }
      setCode(json.code)
      setStatus('waiting')
    } catch (e) {
      setError(String(e)); setStatus('error')
    }
  }

  useEffect(() => {
    if (status !== 'waiting') return
    const t = setInterval(async () => {
      const res = await fetch('/api/telegram/pair/status')
      const json = await res.json()
      if (json.paired) {
        setChatId(json.chat_id); setStatus('paired'); clearInterval(t)
      } else if (json.expired) {
        setStatus('expired'); clearInterval(t)
      }
    }, 3000)
    return () => clearInterval(t)
  }, [status])

  // Real status collapsed to a 3-step position for the stepper below —
  // display grouping only, the actual state machine above is untouched.
  const stepIndex = status === 'idle' || status === 'starting' ? 0
    : status === 'waiting' ? 1
      : status === 'paired' ? 2
        : status === 'expired' || status === 'error' ? 1 : 0
  const failed = status === 'expired' || status === 'error'

  const STEPS = [
    { label: 'Start', icon: Link2 },
    { label: 'Message the code', icon: SendHorizonal },
    { label: 'Paired', icon: CheckCircle2 },
  ]

  return (
    <div className="flex flex-col gap-4">
      {/* step rail */}
      <div className="flex items-center">
        {STEPS.map((s, i) => {
          const reached = i <= stepIndex
          const isCurrentFailed = failed && i === stepIndex
          return (
            <div key={s.label} className="flex flex-1 items-center last:flex-none">
              <div className="flex flex-col items-center gap-1">
                <span className={cn(
                  'flex h-7 w-7 items-center justify-center rounded-full border-2',
                  isCurrentFailed ? 'border-destructive text-destructive' : reached ? 'border-tertiary text-tertiary bg-tertiary/10' : 'border-border/50 text-muted-foreground',
                )}>
                  <s.icon className="h-3.5 w-3.5" />
                </span>
                <span className={cn('text-[0.5rem]', reached ? 'text-foreground' : 'text-muted-foreground')}>{s.label}</span>
              </div>
              {i < STEPS.length - 1 && (
                <span className={cn('mx-1 h-px flex-1', i < stepIndex ? 'bg-tertiary' : 'bg-border/50')} />
              )}
            </div>
          )
        })}
      </div>

      <p className="text-[0.55rem] text-muted-foreground">
        Real pairing flow — no manual .env editing. Start it, message the code to your bot from any Telegram
        account, and the backend captures that chat_id and saves it to .env.
      </p>

      <div className="rounded-lg border border-border/50 bg-secondary/10 p-3">
        {status === 'idle' && <PrimaryButton onClick={start}><Link2 className="h-3.5 w-3.5" /> Start pairing</PrimaryButton>}
        {status === 'starting' && <div className="flex items-center gap-2 text-[0.6rem] text-muted-foreground"><Loader2 className="h-3.5 w-3.5 animate-spin" /> Starting…</div>}
        {status === 'waiting' && code && (
          <div className="text-center">
            <p className="text-[0.55rem] text-muted-foreground">Message this code to your bot on Telegram:</p>
            <p className="mt-1 font-display text-3xl tracking-[0.3em] text-tertiary">{code}</p>
            <p className="mt-2 flex items-center justify-center gap-1.5 text-[0.55rem] text-muted-foreground"><Loader2 className="h-3 w-3 animate-spin" /> Waiting for your message…</p>
          </div>
        )}
        {status === 'paired' && (
          <p className="flex items-center gap-1.5 text-[0.6rem] text-primary"><CheckCircle2 className="h-3.5 w-3.5" /> Paired! chat_id {chatId} saved to .env — restart the backend to activate it.</p>
        )}
        {status === 'expired' && (
          <div className="flex items-center gap-2">
            <p className="text-[0.6rem] text-destructive">Code expired without a match.</p>
            <PrimaryButton onClick={start}>Try again</PrimaryButton>
          </div>
        )}
        {status === 'error' && <p className="text-[0.6rem] text-destructive">{error}</p>}
      </div>
    </div>
  )
}

export function PairingPanel() {
  const { data: tg, loading } = useTelegramStatus()
  return (
    <div className="mx-auto flex max-w-[760px] flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-tertiary/30 bg-card/60 px-4 py-3">
        <div className="flex items-center gap-3">
          <Link2 className="h-5 w-5 text-tertiary" />
          <div>
            <div className="text-[0.65rem] text-foreground">Telegram bot ↔ chat_id</div>
            <p className="text-[0.5rem] text-muted-foreground">The only real pairing mechanism in this build.</p>
          </div>
        </div>
        {loading ? <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" /> : <StatusPill ok={!!tg?.available} label={tg?.available ? 'paired' : 'not paired'} />}
      </div>
      <div className="rounded-xl border border-border bg-card/60 p-4">
        <h3 className="mb-3 flex items-center gap-2 font-heading text-[0.68rem] text-foreground">
          <Fingerprint className="h-3.5 w-3.5 text-tertiary" /> Pair a Chat
        </h3>
        <PairingFlow />
      </div>
    </div>
  )
}

/* ═══════════════════ PROFILES — real, functional persona switcher ══════ */
const PERSONAS = ['nancy', 'billion', 'jarvis'] as const
export function ProfilesPanel() {
  const [active, setActive] = useState<string>('nancy')
  const [switching, setSwitching] = useState<string | null>(null)

  const switchPersona = async (name: string) => {
    setSwitching(name)
    try {
      const res = await fetch(`${BACKEND}/persona/${name}`, { method: 'POST' })
      const json = await res.json()
      if (json.success) setActive(json.persona)
    } finally {
      setSwitching(null)
    }
  }

  return (
    <div className="mx-auto flex max-w-[1200px] flex-col gap-4">
      <div className="flex items-center gap-2 rounded-xl border border-border bg-card/60 px-4 py-3">
        <User className="h-4 w-4 text-primary" />
        <span className="font-heading text-xs text-foreground">Identity</span>
        <span className="text-[0.55rem] text-muted-foreground">
          real, functional — POST /persona/&lt;name&gt; changes Nancy&apos;s greeting/response persona backend-side
        </span>
      </div>

      {/* ID-badge rack — a row of credential cards, not a settings list */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {PERSONAS.map((p) => {
          const isActive = active === p
          const isSwitching = switching === p
          return (
            <button
              key={p}
              type="button"
              onClick={() => switchPersona(p)}
              disabled={isSwitching}
              className={cn(
                'group relative flex flex-col overflow-hidden rounded-2xl border text-left transition-all',
                isActive ? 'glow-ring border-transparent bg-secondary/40' : 'border-border/50 bg-card/60 hover:border-primary/40',
              )}
            >
              {/* card top strip — badge photo area */}
              <div className="flex items-center justify-between px-4 pt-4">
                <span className="font-mono text-[0.5rem] uppercase tracking-widest text-muted-foreground">Nancy/Billion ID</span>
                {isSwitching ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
                ) : isActive ? (
                  <span className="flex items-center gap-1 text-[0.5rem] text-primary"><CheckCircle2 className="h-3 w-3" /> ACTIVE</span>
                ) : (
                  <span className="text-[0.5rem] text-muted-foreground">tap to set</span>
                )}
              </div>
              <div className="flex flex-col items-center gap-2 px-4 py-5">
                <span className={cn(
                  'flex h-16 w-16 items-center justify-center rounded-full border-2 font-display text-2xl',
                  isActive ? 'border-primary text-primary' : 'border-border/60 text-muted-foreground',
                )}>
                  {p.charAt(0).toUpperCase()}
                </span>
                <span className="font-heading text-sm capitalize text-foreground">{p}</span>
              </div>
              {/* card bottom strip — signature/id bar */}
              <div className={cn('mt-auto flex items-center justify-between border-t px-4 py-2 font-mono text-[0.5rem]', isActive ? 'border-primary/30 text-primary' : 'border-border/40 text-muted-foreground')}>
                <span>ID/{p.toUpperCase().slice(0, 3)}-01</span>
                <span>{isActive ? 'in session' : 'standby'}</span>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}

/* ═══════════════════ PLUGINS / MCP — honestly not built ════════════════
   No fake marketplace or protocol client -- these capabilities genuinely
   don't exist yet. Redesigned as a considered "not built" state (icon
   badge + explanation + a real pointer to what actually provides that
   capability today) instead of the plain EmptyNote box, without
   pretending either system is real. ══════════════════════════════════ */
function NotYetBuilt({
  icon: Icon, title, body, pointerLabel, onPointerClick,
}: {
  icon: React.ElementType
  title: string
  body: string
  pointerLabel: string
  onPointerClick?: () => void
}) {
  return (
    <div className="mx-auto flex max-w-[560px] flex-col items-center gap-4 rounded-xl border border-dashed border-border/60 bg-card/40 px-6 py-12 text-center">
      <span className="flex h-14 w-14 items-center justify-center rounded-full border border-border/60 bg-secondary/30">
        <Icon className="h-6 w-6 text-muted-foreground" />
      </span>
      <div>
        <h2 className="font-heading text-sm text-foreground">{title}</h2>
        <p className="mt-2 text-[0.62rem] leading-relaxed text-muted-foreground">{body}</p>
      </div>
      {onPointerClick && (
        <button type="button" onClick={onPointerClick} className="flex items-center gap-1.5 rounded-full border border-primary/40 bg-primary/10 px-3 py-1.5 text-[0.58rem] text-primary transition-colors hover:bg-primary/20">
          <Bot className="h-3 w-3" /> {pointerLabel}
        </button>
      )}
    </div>
  )
}

export function PluginsPanel({ onNavigate }: { onNavigate?: () => void } = {}) {
  return (
    <NotYetBuilt
      icon={PlugZap}
      title="No plugin system in this build"
      body="Nancy's extensibility is real specialized agents and self-created subagents, not a plugin marketplace. Adding a capability here means adding a real agent, not installing a package."
      pointerLabel="See the real agent fleet →"
      onPointerClick={onNavigate}
    />
  )
}
export function McpPanel({ onNavigate }: { onNavigate?: () => void } = {}) {
  return (
    <NotYetBuilt
      icon={Wrench}
      title="No MCP integration wired up yet"
      body="Nancy's tool-use today is Claude's native tool-calling against a fixed local tool set, not external Model Context Protocol servers. This page will become real the day that integration actually exists."
      pointerLabel="See the real model stack →"
      onPointerClick={onNavigate}
    />
  )
}
/* ═══════════════════ WEBHOOKS — real outbound HTTP delivery ═══════════
   A genuine subscription system: POST /webhooks stores a real (url, event)
   pair, and _fire_webhooks in main_new.py actually POSTs to it when the
   event really happens (_cron_execution_loop for "cron_job_ran", the
   /agents/run endpoint for "agent_task_completed"). Not a form that writes
   to a list nothing ever reads. ═══════════════════════════════════════ */
interface WebhookRecord {
  id: string
  url: string
  event: string
  enabled: boolean
  created_at: number
  last_fired_at: number | null
  last_status: string | null
  fire_count: number
}
const WEBHOOK_EVENT_LABELS: Record<string, string> = {
  cron_job_ran: 'Cron job ran',
  agent_task_completed: 'Agent task completed',
}

export function WebhooksPanel() {
  const [hooks, setHooks] = useState<WebhookRecord[]>([])
  const [validEvents, setValidEvents] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [url, setUrl] = useState('')
  const [event, setEvent] = useState('')
  const [creating, setCreating] = useState(false)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)

  const fetchHooks = useCallback(async () => {
    try {
      const res = await fetch('/api/webhooks')
      const json = await res.json()
      if (json.success) {
        setHooks(json.webhooks)
        setValidEvents(json.valid_events)
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchHooks()
    const t = setInterval(fetchHooks, 30_000)
    return () => clearInterval(t)
  }, [fetchHooks])

  useEffect(() => {
    if (!event && validEvents.length > 0) setEvent(validEvents[0])
  }, [validEvents, event])

  const createHook = async () => {
    if (!url.trim() || !event) return
    setCreating(true); setFormError(null)
    try {
      const res = await fetch('/api/webhooks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url.trim(), event }),
      })
      const json = await res.json()
      if (!json.success) { setFormError(json.detail || 'Failed to create webhook'); return }
      setUrl('')
      fetchHooks()
    } catch (e) {
      setFormError(String(e))
    } finally {
      setCreating(false)
    }
  }

  const toggleHook = async (hook: WebhookRecord) => {
    await fetch(`/api/webhooks/${hook.id}?enabled=${!hook.enabled}`, { method: 'PATCH' })
    fetchHooks()
  }
  const deleteHook = async (hook: WebhookRecord) => {
    await fetch(`/api/webhooks/${hook.id}`, { method: 'DELETE' })
    fetchHooks()
  }
  const testHook = async (hook: WebhookRecord) => {
    setTestingId(hook.id)
    try {
      await fetch(`/api/webhooks/${hook.id}/test`, { method: 'POST' })
      fetchHooks()
    } finally {
      setTestingId(null)
    }
  }

  return (
    <div className="mx-auto flex max-w-[900px] flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card/60 px-4 py-3">
        <div className="flex items-center gap-2">
          <Webhook className="h-4 w-4 text-primary" />
          <span className="font-heading text-xs text-foreground">Outbound Webhooks</span>
        </div>
        <span className="text-[0.55rem] text-muted-foreground">
          {hooks.length} subscribed · real delivery on {validEvents.map((e) => WEBHOOK_EVENT_LABELS[e] ?? e).join(' & ') || '…'}
        </span>
      </div>

      <div className="rounded-xl border border-border bg-card/60 p-4">
        <h3 className="mb-2.5 flex items-center gap-2 font-heading text-[0.68rem] text-foreground">
          <Plus className="h-3.5 w-3.5 text-primary" /> New Subscription
        </h3>
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-[1fr_180px_auto]">
          <div>
            <FieldLabel>Target URL</FieldLabel>
            <input className={inputCls} value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com/hook" />
          </div>
          <div>
            <FieldLabel>Event</FieldLabel>
            <select className={inputCls} value={event} onChange={(e) => setEvent(e.target.value)}>
              {validEvents.map((ev) => <option key={ev} value={ev}>{WEBHOOK_EVENT_LABELS[ev] ?? ev}</option>)}
            </select>
          </div>
          <div className="flex items-end">
            <PrimaryButton onClick={createHook} disabled={creating || !url.trim()}>
              {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />} Add
            </PrimaryButton>
          </div>
        </div>
        {formError && <p className="mt-2 text-[0.55rem] text-destructive">{formError}</p>}
      </div>

      <div className="rounded-xl border border-border bg-card/60">
        <p className="border-b border-border/50 px-4 py-2 text-[0.55rem] text-muted-foreground">
          Real HTTP POST delivery — fired by the actual cron execution loop and the agent-run endpoint in the backend, not simulated.
        </p>
        {loading && hooks.length === 0 ? (
          <div className="flex items-center justify-center py-6 text-[0.6rem] text-muted-foreground">
            <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> Loading…
          </div>
        ) : hooks.length === 0 ? (
          <EmptyNote>No webhooks yet — add one above. It&rsquo;ll receive a real POST the next time its event fires.</EmptyNote>
        ) : (
          <ul className="divide-y divide-border/40">
            {hooks.map((h) => (
              <li key={h.id} className="flex flex-wrap items-center gap-3 px-4 py-2.5">
                <span className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-full border', h.enabled ? 'border-primary/40 bg-primary/10' : 'border-border/50 bg-secondary/20')}>
                  <Webhook className={cn('h-3.5 w-3.5', h.enabled ? 'text-primary' : 'text-muted-foreground')} />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[0.62rem] text-foreground">{h.url}</div>
                  <div className="text-[0.5rem] text-muted-foreground">
                    {WEBHOOK_EVENT_LABELS[h.event] ?? h.event} · fired {h.fire_count}x
                    {h.last_status && <> · last: <span className={h.last_status === 'ok' ? 'text-primary' : 'text-destructive'}>{h.last_status}</span></>}
                  </div>
                </div>
                <button type="button" onClick={() => testHook(h)} disabled={testingId === h.id} className="rounded p-1.5 text-muted-foreground hover:text-primary" title="Send test delivery" aria-label={`Send test delivery to ${h.url}`}>
                  {testingId === h.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                </button>
                <button type="button" onClick={() => toggleHook(h)} className="rounded p-1.5 text-muted-foreground hover:text-primary" title="Toggle enabled" aria-label={h.enabled ? `Disable webhook to ${h.url}` : `Enable webhook to ${h.url}`}>
                  {h.enabled ? <ToggleRight className="h-4 w-4 text-primary" /> : <ToggleLeft className="h-4 w-4" />}
                </button>
                <button type="button" onClick={() => deleteHook(h)} className="rounded p-1.5 text-muted-foreground hover:text-destructive" title="Delete" aria-label={`Delete webhook to ${h.url}`}>
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

/* ═══════════════════ DOCS — real, local, no fabricated links ═══════════ */
/* ═══════════════════ DOCS — a real doc-index, lighter touch since it's
   static real content with no fabrication risk. Numbered reference rows
   instead of a two-column card grid; entries pointing at real source files
   get a file icon, everything else gets a book icon. ═══════════════════ */
export function DocsPanel() {
  const entries = [
    { title: 'What Nancy actually is', body: 'A voice-first personal assistant: real STT/TTS, a multi-provider LLM fallback chain, 29 specialized agents, Telegram remote control, and gated file access — see AI Core and Agents for live status.', isPath: false },
    { title: 'Backend source', body: 'nancy-billion/backend/main_new.py is the FastAPI entrypoint; llm.py holds the reasoning fallback chain; agents/specialized/ holds the real agent roster.', isPath: true },
    { title: 'Frontend source', body: 'nancy-billion/frontend/app/page.tsx is the shell; components/nancy/ holds every panel in this sidebar.', isPath: true },
    { title: 'No hosted docs site', body: "This is a personal single-user build with no public documentation site — this page just points at the real files instead of linking somewhere that may not exist.", isPath: false },
  ]
  return (
    <div className="mx-auto flex max-w-[820px] flex-col gap-3">
      <div className="flex items-center gap-2 rounded-xl border border-border bg-card/60 px-4 py-3">
        <BookOpen className="h-4 w-4 text-primary" />
        <span className="font-heading text-xs text-foreground">Reference Index</span>
      </div>
      <ol className="divide-y divide-border/40 rounded-xl border border-border bg-card/60">
        {entries.map((e, i) => (
          <li key={e.title} className="flex gap-3 px-4 py-3.5">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-border/50 font-mono text-[0.55rem] text-muted-foreground">
              {String(i + 1).padStart(2, '0')}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                {e.isPath ? <FileCode2 className="h-3 w-3 text-tertiary" /> : <BookOpen className="h-3 w-3 text-primary" />}
                <h3 className="font-heading text-[0.68rem] text-foreground">{e.title}</h3>
              </div>
              <p className={cn('mt-1 text-[0.6rem] leading-relaxed text-muted-foreground', e.isPath && 'font-mono')}>{e.body}</p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}
