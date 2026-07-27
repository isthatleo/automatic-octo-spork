'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { HudPanel } from './hud-bits'
import { listAgents } from '@/lib/nancy/agent-client'
import {
  useCronStatus, useConfigPublic, useTelegramStatus, useLlmStatus,
  useScreenContextStatus, setScreenContextEnabled, captureScreenContextNow,
  useChannelsStatus, sendChannelTest, type ChannelStatus,
  useNodes, registerNode, removeNode, checkNodeHealth,
  useFleetHealth, useFleetCells, createFleetCell, stopFleetCell, removeFleetCell,
  useMdnsStatus, mdnsAdvertise, mdnsStop, mdnsDiscover, type MdnsService,
  useSessionsStatus, useConversationHistory,
  useCronBlueprints, instantiateBlueprint, type CronBlueprint, type BlueprintField,
  useSkillLibrary, archiveSkill, restoreSkill, type LibrarySkill,
  useSkillBundles, createSkillBundle, deleteSkillBundle,
} from '@/hooks/useSystemData'
import type { AgentInfo, LogEntry } from '@/lib/nancy/types'
import { cn } from '@/lib/utils'
import { timeAgo } from '@/lib/nancy/time'
import {
  Send, MessagesSquare, Hash, Phone, Globe2, CheckCircle2, XCircle,
  Wrench, Sparkles, Cpu, Waves, Eye, EyeOff, Key, User, Server,
  BookOpen, BarChart3, PlugZap, Webhook, Link2, Loader2,
  Plus, Trash2, Save, Bot, ToggleLeft, ToggleRight,
  Radar, ChevronRight, Lock, ShieldCheck,
  CalendarClock, Library, ArrowRight, FileCode2,
  Fingerprint, Layers, MessageCircle, SendHorizonal, Upload, Mic,
  Moon, CheckSquare, Network, Award, Bell, Home, PhoneCall, MessageSquare,
  Archive, ArchiveRestore, Package, GitMerge,
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
/** Real persisted conversation turns (memory graph CONVERSATION nodes --
 * see memory/manager.py's process_conversation). Unlike the live transcript
 * above (this browser tab's in-memory `logs`, lost on refresh), this
 * genuinely survives a reload or a second device -- the same memory graph
 * every other memory-backed feature in the app reads from. */
function ConversationHistoryCard() {
  const { data, loading } = useConversationHistory(30)
  const conversations = data?.conversations ?? []

  return (
    <div className="rounded-xl border border-border bg-card/60 p-4">
      <div className="mb-2.5 flex items-center gap-2">
        <Library className="h-4 w-4 text-primary" />
        <h3 className="font-heading text-xs text-foreground">Conversation History</h3>
        <span className="text-[0.5rem] text-muted-foreground">real, persisted across reloads</span>
      </div>
      {loading && conversations.length === 0 ? (
        <div className="flex items-center justify-center py-4 text-[0.55rem] text-muted-foreground"><Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> Loading…</div>
      ) : conversations.length === 0 ? (
        <EmptyNote>No conversation turns have been persisted to memory yet. This reads the same real memory graph as Memory Insights (MemoryType.CONVERSATION), not the tab-local log above.</EmptyNote>
      ) : (
        <div className="flex max-h-72 flex-col gap-1.5 overflow-y-auto pr-1">
          {conversations.map((c) => (
            <div key={c.id} className="flex items-start gap-2 rounded border border-border/40 bg-secondary/10 px-2.5 py-1.5 text-[0.6rem]">
              <span className={cn('mt-0.5 shrink-0 text-[0.5rem]', c.source === 'user' ? 'text-accent' : 'text-primary')}>
                {c.source === 'user' ? <User className="h-2.5 w-2.5" /> : <Sparkles className="h-2.5 w-2.5" />}
              </span>
              <p className="min-w-0 flex-1 truncate text-foreground">{c.content}</p>
              <span className="shrink-0 text-[0.48rem] text-muted-foreground">{new Date(c.created_at).toLocaleString('en-GB')}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function SessionsPanel({ logs }: { logs: LogEntry[] }) {
  const userTurns = logs.filter((l) => l.level === 'user').length
  const nancyTurns = logs.filter((l) => l.level === 'nancy').length
  const started = logs[0]?.ts ?? Date.now()
  const { data: sessionStatus } = useSessionsStatus()
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
          {sessionStatus && (
            <span className="flex items-center gap-1.5 text-muted-foreground" title="Real open WebSocket connections to this backend right now">
              <Network className="h-3 w-3 text-primary" /> {sessionStatus.active_connections} connected
            </span>
          )}
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

      <ConversationHistoryCard />
    </div>
  )
}

/* ═══════════════════ CHANNELS — real Telegram, honest about the rest ═══ */
/** Every real icon this backend's channels/bootstrap.py actually loads,
 * plus Telegram (which predates the registry). Nothing here stands in for
 * a channel that doesn't exist -- the old Discord/WhatsApp/"Web Voice"
 * entries this page used to show were fictional (Discord and WhatsApp
 * weren't built at all; "Web" wasn't a real notification channel, just the
 * live chat UI itself). All nine of these are real, working integrations
 * -- some just need their own API keys before they'll show connected. */
const CHANNEL_ICONS: Record<string, React.ElementType> = {
  telegram: Send,
  ntfy: Bell,
  home_assistant: Home,
  photon: MessageCircle,
  reef: Waves,
  clickclack: MessageSquare,
  slack: MessagesSquare,
  voice_call: PhoneCall,
  discord: Hash,
  whatsapp: Phone,
}

function ChannelCard({ channel }: { channel: ChannelStatus }) {
  const Icon = CHANNEL_ICONS[channel.key] ?? Globe2
  const [testing, setTesting] = useState(false)
  const [result, setResult] = useState<'ok' | 'fail' | null>(null)

  const runTest = async () => {
    setTesting(true)
    setResult(null)
    try {
      const res = await sendChannelTest(channel.key)
      setResult(res.success ? 'ok' : 'fail')
    } catch {
      setResult('fail')
    } finally {
      setTesting(false)
      setTimeout(() => setResult(null), 4000)
    }
  }

  return (
    <div className="flex flex-col gap-2.5 rounded-xl border border-border bg-card/60 p-4">
      <div className="flex items-center gap-2.5">
        <span className={cn('flex h-9 w-9 shrink-0 items-center justify-center rounded-full border', channel.configured ? 'border-primary/50 bg-primary/10' : 'border-border/50 bg-secondary/20')}>
          <Icon className={cn('h-4 w-4', channel.configured ? 'text-primary' : 'text-muted-foreground')} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="truncate font-heading text-xs text-foreground">{channel.label}</span>
            {channel.two_way && (
              <span className="shrink-0 rounded-full border border-border/60 px-1.5 py-px text-[0.42rem] text-muted-foreground">two-way</span>
            )}
          </div>
          <StatusPill ok={channel.configured} label={channel.configured ? 'connected' : 'not configured'} />
        </div>
      </div>

      <p className="text-[0.55rem] leading-snug text-muted-foreground">{channel.description}</p>
      {channel.detail && <p className="text-[0.5rem] text-destructive">{channel.detail}</p>}

      {channel.configured ? (
        <button
          type="button"
          onClick={runTest}
          disabled={testing}
          className={cn(
            'flex items-center justify-center gap-1.5 rounded border px-2.5 py-1.5 text-[0.55rem] transition-colors disabled:opacity-50',
            result === 'ok'
              ? 'border-primary bg-primary/15 text-primary'
              : result === 'fail'
                ? 'border-destructive bg-destructive/10 text-destructive'
                : 'border-border text-muted-foreground hover:border-primary/50 hover:text-primary',
          )}
        >
          {testing ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : result === 'ok' ? (
            <CheckCircle2 className="h-3 w-3" />
          ) : result === 'fail' ? (
            <XCircle className="h-3 w-3" />
          ) : (
            <Send className="h-3 w-3" />
          )}
          {testing ? 'Sending…' : result === 'ok' ? 'Sent' : result === 'fail' ? 'Failed' : 'Send test message'}
        </button>
      ) : (
        <div className="rounded border border-dashed border-border/60 px-2.5 py-1.5 text-[0.5rem] text-muted-foreground">
          Set{' '}
          {channel.required_env.map((e, i) => (
            <span key={e}>
              <code className="text-foreground/80">{e}</code>
              {i < channel.required_env.length - 1 ? ', ' : ''}
            </span>
          ))}{' '}
          in the backend .env
        </div>
      )}
    </div>
  )
}

export function ChannelsPanel() {
  const { data, loading } = useChannelsStatus()
  const channels = data?.channels ?? []
  const liveCount = channels.filter((c) => c.configured).length

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
          <span className="text-primary">{liveCount}</span> / {channels.length} channels live
        </span>
      </div>

      {/* real per-channel cards -- every channel actually built into this
          backend (channels/bootstrap.py), each testable in place rather
          than a read-only status pill. */}
      {loading && channels.length === 0 ? (
        <div className="flex items-center justify-center rounded-xl border border-border bg-card/60 py-8 text-[0.6rem] text-muted-foreground">
          <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> Checking channels…
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {channels.map((c) => (
            <ChannelCard key={c.key} channel={c} />
          ))}
        </div>
      )}
    </div>
  )
}

/* ═══════════════════ INSTANCES — a topology ladder, not a card pair. Same
   real llm-status data (online? agents_ready?) drawn as a connected node
   rail: root process → the two real subsystems it hosts. Nothing below the
   real signal is invented — there's genuinely no multi-instance fleet, so
   the ladder stays honestly short rather than padded with fake nodes. ═══ */
/** Real paired remote nodes (node_host.py) -- a second machine running
 * node_agent_stub.py that this backend can dispatch to, gated by
 * approval_policy.py. Empty until you actually pair one; the pairing form
 * writes a real registration, not a placeholder. */
function PairedNodesCard() {
  const { data, loading } = useNodes()
  const nodes = Object.entries(data?.nodes ?? {})
  const [healthById, setHealthById] = useState<Record<string, { ok: boolean; detail: string }>>({})
  const [checking, setChecking] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [nodeId, setNodeId] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [secret, setSecret] = useState('')
  const [pairing, setPairing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const checkHealth = async (id: string) => {
    setChecking(id)
    try {
      const res = await checkNodeHealth(id)
      setHealthById((prev) => ({ ...prev, [id]: { ok: !!res.success, detail: res.success ? 'reachable' : res.error ?? 'unreachable' } }))
    } finally {
      setChecking(null)
    }
  }

  const pair = async () => {
    setPairing(true); setError(null)
    try {
      const res = await registerNode(nodeId.trim(), baseUrl.trim(), secret.trim())
      if (!res.success) { setError(res.detail ?? 'Failed to pair node'); return }
      setNodeId(''); setBaseUrl(''); setSecret(''); setOpen(false)
    } finally {
      setPairing(false)
    }
  }

  return (
    <div className="rounded-xl border border-border bg-card/60 p-4">
      <div className="mb-2.5 flex items-center gap-2">
        <Network className="h-4 w-4 text-primary" />
        <h3 className="font-heading text-xs text-foreground">Paired Nodes</h3>
        <span className="text-[0.5rem] text-muted-foreground">{loading ? '…' : `${nodes.length} paired`}</span>
        <button type="button" onClick={() => setOpen((v) => !v)} className="ml-auto rounded border border-border px-2 py-1 text-[0.5rem] text-muted-foreground hover:text-foreground">
          {open ? 'Cancel' : 'Pair a node'}
        </button>
      </div>

      {open && (
        <div className="mb-3 flex flex-col gap-2 rounded-lg border border-border bg-secondary/20 p-3">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            <input className={inputCls} placeholder="node_id" value={nodeId} onChange={(e) => setNodeId(e.target.value)} />
            <input className={inputCls} placeholder="http://host:8100" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
            <input className={inputCls} type="password" placeholder="shared secret" value={secret} onChange={(e) => setSecret(e.target.value)} />
          </div>
          {error && <p className="text-[0.55rem] text-destructive">{error}</p>}
          <PrimaryButton onClick={pair} disabled={pairing || !nodeId.trim() || !baseUrl.trim() || !secret.trim()}>
            {pairing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />} Pair
          </PrimaryButton>
          <p className="text-[0.48rem] leading-snug text-muted-foreground">
            The remote machine must be running node_agent_stub.py with the same shared secret.
          </p>
        </div>
      )}

      {nodes.length === 0 ? (
        <EmptyNote>No nodes paired yet. This is a real capability (node_host.py) -- pair a second machine running node_agent_stub.py to dispatch real commands to it.</EmptyNote>
      ) : (
        <div className="flex flex-col gap-1.5">
          {nodes.map(([id, cfg]) => {
            const health = healthById[id]
            return (
              <div key={id} className="flex items-center gap-3 rounded border border-border/50 bg-secondary/10 px-3 py-2">
                <span className={cn('flex h-7 w-7 shrink-0 items-center justify-center rounded-full border', health?.ok ? 'border-primary/50 bg-primary/10' : 'border-border/50 bg-secondary/20')}>
                  <Server className={cn('h-3.5 w-3.5', health?.ok ? 'text-primary' : 'text-muted-foreground')} />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[0.62rem] text-foreground">{id}</div>
                  <div className="truncate text-[0.5rem] text-muted-foreground">{cfg.base_url} · {health ? health.detail : 'not checked yet'}</div>
                </div>
                <button type="button" onClick={() => checkHealth(id)} disabled={checking === id} className="rounded border border-border px-2 py-1 text-[0.5rem] text-muted-foreground hover:text-foreground disabled:opacity-50">
                  {checking === id ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Check'}
                </button>
                <button
                  type="button"
                  onClick={async () => { await removeNode(id) }}
                  className="rounded border border-border px-2 py-1 text-[0.5rem] text-muted-foreground hover:border-destructive/60 hover:text-destructive"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

/** Real Docker-backed multi-tenant fleet cells (fleet/manager.py,
 * fleet/cell.py) -- each cell is a genuine isolated container with real
 * resource limits. Honestly reports when Docker itself isn't reachable,
 * rather than showing an empty list indistinguishable from "no cells yet". */
function FleetCellsCard() {
  const { data: health } = useFleetHealth()
  const { data, loading, error: _err } = useFleetCells()
  const cells = data?.cells ?? []
  const [open, setOpen] = useState(false)
  const [tenantId, setTenantId] = useState('')
  const [image, setImage] = useState('python:3.11-slim')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  const create = async () => {
    setCreating(true); setError(null)
    try {
      const res = await createFleetCell({ tenant_id: tenantId.trim(), image: image.trim() || undefined })
      if (!res.success) { setError(res.detail ?? 'Failed to create cell'); return }
      setTenantId(''); setOpen(false)
    } finally {
      setCreating(false)
    }
  }

  const doStop = async (id: string) => { setBusyId(id); try { await stopFleetCell(id) } finally { setBusyId(null) } }
  const doRemove = async (id: string) => { setBusyId(id); try { await removeFleetCell(id) } finally { setBusyId(null) } }

  return (
    <div className="rounded-xl border border-border bg-card/60 p-4">
      <div className="mb-2.5 flex items-center gap-2">
        <Layers className="h-4 w-4 text-primary" />
        <h3 className="font-heading text-xs text-foreground">Fleet Cells</h3>
        {health && (
          <StatusPill ok={!!health.docker_available} label={health.docker_available ? `docker · ${health.containers_running ?? 0} running` : 'docker unavailable'} />
        )}
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          disabled={!health?.docker_available}
          className="ml-auto rounded border border-border px-2 py-1 text-[0.5rem] text-muted-foreground hover:text-foreground disabled:opacity-40"
        >
          {open ? 'Cancel' : 'New cell'}
        </button>
      </div>

      {health && !health.docker_available && (
        <p className="mb-2 text-[0.5rem] text-muted-foreground">{health.error ?? 'Docker Desktop (or another Docker Engine) is not reachable from this backend.'}</p>
      )}

      {open && (
        <div className="mb-3 flex flex-col gap-2 rounded-lg border border-border bg-secondary/20 p-3">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <input className={inputCls} placeholder="tenant_id" value={tenantId} onChange={(e) => setTenantId(e.target.value)} />
            <input className={inputCls} placeholder="image (default python:3.11-slim)" value={image} onChange={(e) => setImage(e.target.value)} />
          </div>
          {error && <p className="text-[0.55rem] text-destructive">{error}</p>}
          <PrimaryButton onClick={create} disabled={creating || !tenantId.trim()}>
            {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />} Create (requires approval on your phone)
          </PrimaryButton>
        </div>
      )}

      {loading && cells.length === 0 ? (
        <div className="flex items-center justify-center py-4 text-[0.55rem] text-muted-foreground"><Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> Loading…</div>
      ) : cells.length === 0 ? (
        <EmptyNote>No fleet cells running. This is real Docker-backed multi-tenant isolation (fleet/cell.py) -- create one to see a real container spun up with real resource limits.</EmptyNote>
      ) : (
        <div className="flex flex-col gap-1.5">
          {cells.map((c) => (
            <div key={c.cell_id} className="flex items-center gap-3 rounded border border-border/50 bg-secondary/10 px-3 py-2">
              <span className={cn('flex h-7 w-7 shrink-0 items-center justify-center rounded-full border', c.status === 'running' ? 'border-primary/50 bg-primary/10' : 'border-border/50 bg-secondary/20')}>
                <Layers className={cn('h-3.5 w-3.5', c.status === 'running' ? 'text-primary' : 'text-muted-foreground')} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[0.62rem] text-foreground">{c.tenant_id} <span className="text-muted-foreground">· {c.image}</span></div>
                <div className="truncate text-[0.5rem] text-muted-foreground">{c.mem_limit} · {c.nano_cpus} CPU · {c.status}</div>
              </div>
              <button type="button" onClick={() => doStop(c.cell_id)} disabled={busyId === c.cell_id} className="rounded border border-border px-2 py-1 text-[0.5rem] text-muted-foreground hover:text-foreground disabled:opacity-50">
                Stop
              </button>
              <button type="button" onClick={() => doRemove(c.cell_id)} disabled={busyId === c.cell_id} className="rounded border border-border px-2 py-1 text-[0.5rem] text-muted-foreground hover:border-destructive/60 hover:text-destructive disabled:opacity-50">
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/** Real LAN discovery (mdns_discovery.py) -- advertises this backend as
 * _nancy-gateway._tcp.local. and/or browses for other instances on the
 * network. No credential needed, local-network-only by design. */
function LanDiscoveryCard() {
  const { data: status } = useMdnsStatus()
  const [busy, setBusy] = useState(false)
  const [services, setServices] = useState<MdnsService[] | null>(null)
  const [scanning, setScanning] = useState(false)

  const toggle = async () => {
    setBusy(true)
    try {
      if (status?.advertising) await mdnsStop()
      else await mdnsAdvertise()
    } finally {
      setBusy(false)
    }
  }
  const scan = async () => {
    setScanning(true)
    try {
      const res = await mdnsDiscover()
      setServices(res.services ?? [])
    } finally {
      setScanning(false)
    }
  }

  return (
    <div className="rounded-xl border border-border bg-card/60 p-4">
      <div className="mb-2.5 flex items-center gap-2">
        <Radar className="h-4 w-4 text-primary" />
        <h3 className="font-heading text-xs text-foreground">LAN Discovery</h3>
        <StatusPill ok={!!status?.advertising} label={status?.advertising ? 'advertising' : 'not advertising'} />
        <div className="ml-auto flex gap-1.5">
          <button type="button" onClick={scan} disabled={scanning} className="rounded border border-border px-2 py-1 text-[0.5rem] text-muted-foreground hover:text-foreground disabled:opacity-50">
            {scanning ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Scan LAN'}
          </button>
          <button
            type="button"
            onClick={toggle}
            disabled={busy}
            className={cn('rounded border px-2 py-1 text-[0.5rem] disabled:opacity-50', status?.advertising ? 'border-destructive/50 text-destructive' : 'border-primary/50 text-primary')}
          >
            {status?.advertising ? 'Stop advertising' : 'Advertise'}
          </button>
        </div>
      </div>
      <p className="mb-2 text-[0.5rem] text-muted-foreground">
        {status?.advertising ? `Advertising as ${status.name}` : 'Not currently discoverable on the LAN.'}
      </p>
      {services === null ? (
        <EmptyNote>Run a scan to browse for other _nancy-gateway._tcp instances (or paired node-agents) on this network.</EmptyNote>
      ) : services.length === 0 ? (
        <EmptyNote>Scan found nothing on this network right now.</EmptyNote>
      ) : (
        <div className="flex flex-col gap-1.5">
          {services.map((s) => (
            <div key={s.name} className="flex items-center gap-3 rounded border border-border/50 bg-secondary/10 px-3 py-2 text-[0.6rem]">
              <Server className="h-3.5 w-3.5 shrink-0 text-primary" />
              <span className="truncate text-foreground">{s.name}</span>
              <span className="truncate text-muted-foreground">{s.addresses.join(', ')}:{s.port}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function InstancesPanel() {
  const { data: llm, loading } = useLlmStatus()
  const online = !!llm
  const agentsReady = !!llm?.agents_ready

  const nodes: { label: string; sub: string; ok: boolean; icon: React.ElementType }[] = [
    { label: 'LLM Runtime', sub: llm ? `${llm.backends.length} backend${llm.backends.length !== 1 ? 's' : ''} reachable` : 'not responding', ok: online, icon: Cpu },
    { label: 'Agent Fleet', sub: agentsReady ? 'initialised, accepting tasks' : 'still booting', ok: agentsReady, icon: Bot },
  ]

  return (
    <div className="mx-auto flex max-w-[900px] flex-col gap-4">
      <div className="flex flex-col">
        {/* root node */}
        <div className="flex items-center gap-3 rounded-xl border border-border bg-card/60 px-4 py-3.5">
          <span className={cn('flex h-10 w-10 shrink-0 items-center justify-center rounded-full border', online ? 'border-primary/50 bg-primary/10' : 'border-destructive/50 bg-destructive/10')}>
            <Server className={cn('h-5 w-5', online ? 'text-primary' : 'text-destructive')} />
          </span>
          <div className="min-w-0 flex-1">
            <div className="font-heading text-xs text-foreground">Backend Process</div>
            <div className="text-[0.55rem] text-muted-foreground">This machine's local process — the root of everything below</div>
          </div>
          {loading ? <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-muted-foreground" /> : <StatusPill ok={online} label={online ? 'online' : 'unreachable'} />}
        </div>

        {/* connecting rail down to the two in-process subsystems */}
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
      </div>

      {/* Real expansion capabilities beyond this one process -- paired
          remote nodes, Docker fleet cells, and LAN discovery all actually
          exist in the backend (node_host.py, fleet/*.py, mdns_discovery.py)
          and previously had zero surface on this page. */}
      <PairedNodesCard />
      <FleetCellsCard />
      <LanDiscoveryCard />
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
  action_type: 'telegram_message' | 'agent_task' | 'run_skill' | 'terminal_command' | 'run_script' | 'channel_message' | 'memory_consolidate' | 'commitment_checkin'
  action_payload: Record<string, unknown>
  enabled: boolean
  next_run: string
  last_run: string | null
  last_result: string | null
}

/** Every real ActionType cron_store.py actually accepts (see cron_store.py's
 * ActionType Literal + the validation in POST /cron/jobs) -- the old form
 * only ever offered 2 of these 8, silently hiding run_skill, terminal_command,
 * run_script, channel_message, memory_consolidate, and commitment_checkin
 * even though the backend has always accepted them. */
type CronActionType =
  | 'telegram_message' | 'agent_task' | 'run_skill' | 'terminal_command'
  | 'run_script' | 'channel_message' | 'memory_consolidate' | 'commitment_checkin'

const ACTION_TYPE_LABELS: Record<CronActionType, string> = {
  telegram_message: 'Send Telegram message',
  agent_task: 'Run an agent task',
  run_skill: 'Run a skill',
  terminal_command: 'Run a terminal command',
  run_script: 'Run a backend script',
  channel_message: 'Send to a channel',
  memory_consolidate: 'Memory consolidation cycle',
  commitment_checkin: 'Open commitments check-in',
}

function NewCronJobForm({ agents, onCreated }: { agents: AgentInfo[]; onCreated: () => void }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [hour, setHour] = useState('9')
  const [minute, setMinute] = useState('0')
  const [useCronExpr, setUseCronExpr] = useState(false)
  const [cronExpr, setCronExpr] = useState('')
  const [actionType, setActionType] = useState<CronActionType>('telegram_message')
  const [text, setText] = useState('')
  const [agentKey, setAgentKey] = useState('')
  const [taskType, setTaskType] = useState('query')
  const [skillName, setSkillName] = useState('')
  const [command, setCommand] = useState('')
  const [script, setScript] = useState('')
  const [channelKey, setChannelKey] = useState('')
  const [channelMessage, setChannelMessage] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { data: channelsData } = useChannelsStatus()
  const configuredChannels = (channelsData?.channels ?? []).filter((c) => c.configured)

  const actionPayload = (): Record<string, unknown> => {
    switch (actionType) {
      case 'telegram_message': return { text }
      case 'agent_task': return { agent_key: agentKey, task_type: taskType, payload: {} }
      case 'run_skill': return { skill_name: skillName }
      case 'terminal_command': return { command }
      case 'run_script': return { script }
      case 'channel_message': return { channel: channelKey, message: channelMessage }
      case 'memory_consolidate':
      case 'commitment_checkin': return {}
    }
  }
  const isValid = (): boolean => {
    if (!name.trim()) return false
    if (useCronExpr && !cronExpr.trim()) return false
    switch (actionType) {
      case 'telegram_message': return !!text.trim()
      case 'agent_task': return !!agentKey
      case 'run_skill': return !!skillName.trim()
      case 'terminal_command': return !!command.trim()
      case 'run_script': return !!script.trim()
      case 'channel_message': return !!channelKey && !!channelMessage.trim()
      case 'memory_consolidate':
      case 'commitment_checkin': return true
    }
  }

  const submit = async () => {
    setSaving(true); setError(null)
    try {
      const res = await fetch('/api/cron/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name, description,
          ...(useCronExpr ? { cron_expression: cronExpr.trim() } : { hour: Number(hour), minute: Number(minute) }),
          action_type: actionType, action_payload: actionPayload(),
        }),
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
      <PrimaryButton onClick={() => setOpen(true)}><Plus className="h-3.5 w-3.5" /> New job (advanced)</PrimaryButton>
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

        <div className="sm:col-span-2">
          <div className="mb-1 flex items-center justify-between">
            <FieldLabel>When</FieldLabel>
            <button type="button" onClick={() => setUseCronExpr((v) => !v)} className="text-[0.5rem] text-muted-foreground hover:text-primary">
              {useCronExpr ? 'Use hour/minute instead' : 'Use a cron expression instead'}
            </button>
          </div>
          {useCronExpr ? (
            <input className={inputCls} value={cronExpr} onChange={(e) => setCronExpr(e.target.value)} placeholder="e.g. */30 9-17 * * 1-5" />
          ) : (
            <div className="flex gap-2">
              <input className={inputCls} type="number" min={0} max={23} value={hour} onChange={(e) => setHour(e.target.value)} placeholder="hour (0-23)" />
              <input className={inputCls} type="number" min={0} max={59} value={minute} onChange={(e) => setMinute(e.target.value)} placeholder="minute (0-59)" />
            </div>
          )}
        </div>

        <div className="sm:col-span-2">
          <FieldLabel>Action</FieldLabel>
          <select className={inputCls} value={actionType} onChange={(e) => setActionType(e.target.value as CronActionType)}>
            {(Object.keys(ACTION_TYPE_LABELS) as CronActionType[]).map((t) => (
              <option key={t} value={t}>{ACTION_TYPE_LABELS[t]}</option>
            ))}
          </select>
        </div>

        {actionType === 'telegram_message' && (
          <div className="sm:col-span-2">
            <FieldLabel>Message text</FieldLabel>
            <input className={inputCls} value={text} onChange={(e) => setText(e.target.value)} placeholder="What should Nancy send?" />
          </div>
        )}
        {actionType === 'agent_task' && (
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
        {actionType === 'run_skill' && (
          <div className="sm:col-span-2">
            <FieldLabel>Skill name</FieldLabel>
            <input className={inputCls} value={skillName} onChange={(e) => setSkillName(e.target.value)} placeholder="e.g. system-monitoring" />
          </div>
        )}
        {actionType === 'terminal_command' && (
          <div className="sm:col-span-2">
            <FieldLabel>Command</FieldLabel>
            <input className={inputCls} value={command} onChange={(e) => setCommand(e.target.value)} placeholder="a real shell command, run through the same safety gate as chat" />
          </div>
        )}
        {actionType === 'run_script' && (
          <div className="sm:col-span-2">
            <FieldLabel>Script filename</FieldLabel>
            <input className={inputCls} value={script} onChange={(e) => setScript(e.target.value)} placeholder="e.g. disk_cleanup.py (under backend/scripts/)" />
          </div>
        )}
        {actionType === 'channel_message' && (
          <>
            <div>
              <FieldLabel>Channel</FieldLabel>
              <select className={inputCls} value={channelKey} onChange={(e) => setChannelKey(e.target.value)}>
                <option value="">Select a channel…</option>
                {configuredChannels.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
              </select>
              {configuredChannels.length === 0 && <p className="mt-1 text-[0.48rem] text-muted-foreground">No channels configured yet -- see the Channels page.</p>}
            </div>
            <div>
              <FieldLabel>Message</FieldLabel>
              <input className={inputCls} value={channelMessage} onChange={(e) => setChannelMessage(e.target.value)} placeholder="What should it say?" />
            </div>
          </>
        )}
        {(actionType === 'memory_consolidate' || actionType === 'commitment_checkin') && (
          <p className="sm:col-span-2 text-[0.5rem] text-muted-foreground">No extra fields needed -- this runs the real {actionType === 'memory_consolidate' ? 'memory/dreaming.py consolidation' : 'memory/commitments.py check-in'}.</p>
        )}
      </div>
      {error && <p className="text-[0.55rem] text-destructive">{error}</p>}
      <div className="flex gap-2">
        <PrimaryButton onClick={submit} disabled={saving || !isValid()}>
          {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />} Create job
        </PrimaryButton>
        <button type="button" onClick={() => setOpen(false)} className="rounded-lg border border-border px-3 py-1.5 text-[0.6rem] text-muted-foreground hover:text-foreground">
          Cancel
        </button>
      </div>
    </div>
  )
}

const CATEGORY_LABELS: Record<string, string> = {
  daily: 'Daily', weekly: 'Weekly', general: 'General', maintenance: 'Maintenance',
}

function BlueprintFieldInput({ field, value, onChange }: { field: BlueprintField; value: string; onChange: (v: string) => void }) {
  if (field.type === 'time') {
    return <input className={inputCls} type="time" value={value} onChange={(e) => onChange(e.target.value)} />
  }
  if (field.type === 'enum' || field.type === 'weekdays') {
    return (
      <select className={inputCls} value={value} onChange={(e) => onChange(e.target.value)}>
        {field.options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    )
  }
  return <input className={inputCls} type="text" value={value} onChange={(e) => onChange(e.target.value)} placeholder={field.label} />
}

/** One real automation blueprint (blueprint_catalog.py) -- the same slot
 * schema drives this form and the real job blueprint_catalog.fill_blueprint()
 * produces server-side, so what you fill in here is exactly what runs. */
function BlueprintCard({ blueprint, onCreated }: { blueprint: CronBlueprint; onCreated: () => void }) {
  const [open, setOpen] = useState(false)
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(blueprint.fields.map((f) => [f.name, f.default ?? ''])),
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  const submit = async () => {
    setSaving(true); setError(null)
    try {
      const res = await instantiateBlueprint(blueprint.key, values)
      if (!res.success) { setError(res.detail ?? 'Failed to create job from blueprint'); return }
      setDone(true)
      onCreated()
      setTimeout(() => { setOpen(false); setDone(false) }, 1500)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-secondary/20 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-heading text-[0.68rem] text-foreground">{blueprint.title}</div>
          <p className="mt-0.5 text-[0.55rem] leading-snug text-muted-foreground">{blueprint.description}</p>
        </div>
        <span className="shrink-0 rounded-full border border-tertiary/40 px-1.5 py-0 text-[0.45rem] uppercase tracking-wide text-tertiary">
          {CATEGORY_LABELS[blueprint.category] ?? blueprint.category}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-1.5 text-[0.48rem] text-muted-foreground">
        <CalendarClock className="h-3 w-3" /> {blueprint.scheduleHuman}
        {blueprint.tags.map((t) => <span key={t} className="rounded-full border border-border/50 px-1.5 py-0">{t}</span>)}
      </div>

      {!open ? (
        <PrimaryButton onClick={() => setOpen(true)} className="self-start">
          <Plus className="h-3.5 w-3.5" /> Use this
        </PrimaryButton>
      ) : done ? (
        <p className="flex items-center gap-1.5 text-[0.6rem] text-primary"><CheckCircle2 className="h-3.5 w-3.5" /> Scheduled.</p>
      ) : (
        <div className="flex flex-col gap-2 border-t border-border/50 pt-2">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {blueprint.fields.map((f) => (
              <div key={f.name}>
                <FieldLabel>{f.label}</FieldLabel>
                <BlueprintFieldInput field={f} value={values[f.name] ?? ''} onChange={(v) => setValues((prev) => ({ ...prev, [f.name]: v }))} />
                {f.help && <p className="mt-0.5 text-[0.45rem] text-muted-foreground">{f.help}</p>}
              </div>
            ))}
          </div>
          {error && <p className="text-[0.55rem] text-destructive">{error}</p>}
          <div className="flex gap-2">
            <PrimaryButton onClick={submit} disabled={saving}>
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />} Schedule it
            </PrimaryButton>
            <button type="button" onClick={() => setOpen(false)} className="rounded-lg border border-border px-3 py-1.5 text-[0.6rem] text-muted-foreground hover:text-foreground">
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

/** 14 real pre-built automation templates (blueprint_catalog.py) --
 * previously fully built on the backend (real form schema, real validation,
 * real job creation) with zero frontend surface. Filling in a few slots
 * here is the same real path as hand-writing a cron_expression and a
 * dispatcher-agent prompt, just without needing to know cron syntax. */
function BlueprintGallery({ onCreated }: { onCreated: () => void }) {
  const { data, loading } = useCronBlueprints()
  const blueprints = data?.blueprints ?? []
  const categories = useMemo(() => Array.from(new Set(blueprints.map((b) => b.category))), [blueprints])
  const [category, setCategory] = useState<string | null>(null)
  const shown = category ? blueprints.filter((b) => b.category === category) : blueprints

  if (loading && blueprints.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-xl border border-border bg-card/60 py-8 text-[0.6rem] text-muted-foreground">
        <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> Loading blueprints…
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-border bg-card/60 p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Sparkles className="h-4 w-4 text-primary" />
        <h3 className="font-heading text-xs text-foreground">Automation Blueprints</h3>
        <span className="text-[0.5rem] text-muted-foreground">{blueprints.length} real templates -- fill in a few slots instead of hand-writing a cron job</span>
        <div className="ml-auto flex flex-wrap gap-1.5">
          <button type="button" onClick={() => setCategory(null)} className={cn('rounded-full border px-2 py-0.5 text-[0.5rem]', !category ? 'border-primary bg-primary/15 text-primary' : 'border-border text-muted-foreground hover:text-foreground')}>
            All
          </button>
          {categories.map((c) => (
            <button key={c} type="button" onClick={() => setCategory(c)} className={cn('rounded-full border px-2 py-0.5 text-[0.5rem]', category === c ? 'border-primary bg-primary/15 text-primary' : 'border-border text-muted-foreground hover:text-foreground')}>
              {CATEGORY_LABELS[c] ?? c}
            </button>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
        {shown.map((b) => <BlueprintCard key={b.key} blueprint={b} onCreated={onCreated} />)}
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
    const customItems: RailItem[] = jobs.map((job) => {
      const p = job.action_payload
      const actionDetail: Record<string, string> = {
        telegram_message: 'Telegram message',
        agent_task: `Agent: ${p.agent_key}`,
        run_skill: `Skill: ${p.skill_name ?? p.bundle_name}`,
        terminal_command: `Command: ${p.command}`,
        run_script: `Script: ${p.script}`,
        channel_message: `Channel: ${p.channel}`,
        memory_consolidate: 'Memory consolidation cycle',
        commitment_checkin: 'Open commitments check-in',
      }
      return {
        kind: 'custom', key: `c:${job.id}`, name: job.name, next_run: job.next_run, enabled: job.enabled,
        detail: job.description || actionDetail[job.action_type] || job.action_type,
        time: `${String(job.hour).padStart(2, '0')}:${String(job.minute).padStart(2, '0')} daily`, job,
      }
    })
    return [...builtinItems, ...customItems].sort((a, b) => new Date(a.next_run).getTime() - new Date(b.next_run).getTime())
  }, [data, jobs])

  return (
    <div className="mx-auto flex max-w-[1300px] flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card/60 px-4 py-3">
        <div className="flex items-center gap-2">
          <CalendarClock className="h-4 w-4 text-primary" />
          <span className="font-heading text-xs text-foreground">Schedule</span>
          <span className="text-[0.55rem] text-muted-foreground">next-run ordered · real jobs, checked every 30s by the backend</span>
        </div>
        <NewCronJobForm agents={agents} onCreated={fetchJobs} />
      </div>

      <BlueprintGallery onCreated={fetchJobs} />

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

/* ═══════════════════ SKILLS — the real, invokable procedure library
   (skill_loader.py's SKILL.md files, real keyword-matched, real usage
   stats) is the centerpiece; real bundles, real agent specializations, and
   purely descriptive custom-skill tags are all real but categorically
   different things, kept clearly separate rather than blurred into one
   undifferentiated "skills" list the way the previous page did. ═════════ */

/** One real, invokable skill -- archiving moves its real folder to
 * skills/_archived/ so it stops being keyword-matched (restore brings it
 * straight back); never deletes it outright. */
function SkillLibraryCard({ skill }: { skill: LibrarySkill }) {
  const [busy, setBusy] = useState(false)
  const archive = async () => {
    setBusy(true)
    try { await archiveSkill(skill.name) } finally { setBusy(false) }
  }
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-secondary/20 p-3">
      <div className="flex items-start justify-between gap-2">
        <span className="font-heading text-[0.65rem] text-foreground">{skill.name}</span>
        <button type="button" onClick={archive} disabled={busy} className="shrink-0 text-muted-foreground hover:text-destructive disabled:opacity-40" title="Archive (stops matching, doesn't delete)">
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Archive className="h-3.5 w-3.5" />}
        </button>
      </div>
      <p className="text-[0.55rem] leading-snug text-muted-foreground">{skill.description}</p>
      <div className="flex flex-wrap gap-1">
        {skill.trigger_keywords.slice(0, 5).map((k) => (
          <span key={k} className="rounded-full border border-border/50 px-1.5 py-0 text-[0.45rem] text-muted-foreground">{k}</span>
        ))}
        {skill.trigger_keywords.length > 5 && <span className="text-[0.45rem] text-muted-foreground">+{skill.trigger_keywords.length - 5}</span>}
      </div>
      <div className="flex items-center justify-between text-[0.5rem] text-muted-foreground">
        <span className={skill.match_count > 0 ? 'text-primary' : ''}>{skill.match_count} real match{skill.match_count !== 1 ? 'es' : ''}</span>
        <span>{skill.last_matched_at ? `last: ${timeAgo(skill.last_matched_at * 1000)}` : 'never matched yet'}</span>
      </div>
    </div>
  )
}

function SkillLibrarySection() {
  const { data, loading } = useSkillLibrary()
  const [sortByUsage, setSortByUsage] = useState(true)
  const skills = data?.skills ?? []
  const archived = data?.archived ?? []
  const sorted = sortByUsage ? [...skills].sort((a, b) => b.match_count - a.match_count) : skills

  // useSkillLibrary polls every 30s on its own; archive/restore just wait
  // for the next real tick to reflect rather than faking an optimistic
  // update ahead of what the backend actually confirms.
  const restoreOne = async (name: string) => {
    await restoreSkill(name)
  }

  return (
    <div className="rounded-xl border border-primary/30 bg-card/60">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/50 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-primary" />
          <h3 className="font-heading text-[0.68rem] text-foreground">Skill Library</h3>
          <span className="text-[0.5rem] text-muted-foreground">real, invokable, keyword-matched into live prompts</span>
        </div>
        <button type="button" onClick={() => setSortByUsage((v) => !v)} className="rounded border border-border px-2 py-1 text-[0.5rem] text-muted-foreground hover:text-foreground">
          {sortByUsage ? 'Sorted by real usage' : 'Sorted alphabetically'}
        </button>
      </div>
      {loading && skills.length === 0 ? (
        <div className="flex items-center justify-center py-6 text-[0.6rem] text-muted-foreground">
          <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> Reading skill library…
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-2.5 p-4 sm:grid-cols-2 lg:grid-cols-3">
          {sorted.map((s) => <SkillLibraryCard key={s.name} skill={s} />)}
        </div>
      )}
      {archived.length > 0 && (
        <div className="border-t border-border/50 px-4 py-3">
          <div className="mb-2 flex items-center gap-2 text-[0.55rem] text-muted-foreground">
            <Archive className="h-3 w-3" /> Archived ({archived.length}) -- not matched while archived
          </div>
          <div className="flex flex-wrap gap-1.5">
            {archived.map((name) => (
              <button
                key={name}
                type="button"
                onClick={() => restoreOne(name)}
                className="flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-[0.5rem] text-muted-foreground hover:border-primary/50 hover:text-primary"
              >
                <ArchiveRestore className="h-2.5 w-2.5" /> {name}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/** Real named groups of real library skills (skill_bundles.py) -- a cron or
 * webhook run_skill action referencing bundle_name injects every named
 * skill's real instructions together as one combined procedure. */
function SkillBundlesSection() {
  const { data: libData } = useSkillLibrary()
  const { data, loading } = useSkillBundles()
  const bundles = data?.bundles ?? []
  const librarySkills = libData?.skills ?? []
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const toggle = (n: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(n)) next.delete(n); else next.add(n)
      return next
    })
  }

  const submit = async () => {
    setSaving(true); setError(null)
    try {
      const res = await createSkillBundle(name.trim(), Array.from(selected), description)
      if (!res.success) { setError(res.detail ?? 'Failed to create bundle'); return }
      setName(''); setDescription(''); setSelected(new Set()); setOpen(false)
    } finally {
      setSaving(false)
    }
  }
  const remove = async (id: string) => {
    await deleteSkillBundle(id)
  }

  return (
    <div className="rounded-xl border border-border bg-card/60">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/50 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <Package className="h-3.5 w-3.5 text-accent" />
          <h3 className="font-heading text-[0.68rem] text-foreground">Skill Bundles</h3>
          <span className="text-[0.5rem] text-muted-foreground">real named groups, usable in cron/webhook run_skill actions</span>
        </div>
        <button type="button" onClick={() => setOpen((v) => !v)} className="rounded border border-border px-2 py-1 text-[0.5rem] text-muted-foreground hover:text-foreground">
          {open ? 'Cancel' : '+ New bundle'}
        </button>
      </div>

      {open && (
        <div className="flex flex-col gap-2 border-b border-border/50 p-3">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <input className={inputCls} placeholder="Bundle name" value={name} onChange={(e) => setName(e.target.value)} />
            <input className={inputCls} placeholder="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
          <div className="flex max-h-28 flex-wrap gap-1 overflow-y-auto rounded border border-border/50 bg-background/40 p-2">
            {librarySkills.map((s) => (
              <button
                key={s.name}
                type="button"
                onClick={() => toggle(s.name)}
                className={cn('rounded-full border px-2 py-0.5 text-[0.5rem]', selected.has(s.name) ? 'border-primary bg-primary/15 text-primary' : 'border-border/50 text-muted-foreground hover:border-primary/40')}
              >
                {s.name}
              </button>
            ))}
          </div>
          {error && <p className="text-[0.55rem] text-destructive">{error}</p>}
          <div className="flex gap-2">
            <PrimaryButton onClick={submit} disabled={saving || !name.trim() || selected.size === 0}>
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />} Create bundle
            </PrimaryButton>
          </div>
        </div>
      )}

      {loading && bundles.length === 0 ? (
        <div className="flex items-center justify-center py-4 text-[0.55rem] text-muted-foreground"><Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> Loading…</div>
      ) : bundles.length === 0 ? (
        <div className="p-4"><EmptyNote>No bundles yet -- group a few library skills above to inject them together as one combined procedure.</EmptyNote></div>
      ) : (
        <ul className="divide-y divide-border/40">
          {bundles.map((b) => (
            <li key={b.id} className="flex items-center gap-3 px-4 py-2.5">
              <Package className="h-3.5 w-3.5 shrink-0 text-accent" />
              <div className="min-w-0 flex-1">
                <div className="text-[0.62rem] text-foreground">{b.name}</div>
                <p className="truncate text-[0.5rem] text-muted-foreground">{b.skill_names.join(', ')}</p>
              </div>
              <button type="button" onClick={() => remove(b.id)} className="shrink-0 text-muted-foreground hover:text-destructive">
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

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
  const { data: libData } = useSkillLibrary()
  const { data: bundleData } = useSkillBundles()

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
    <div className="mx-auto flex max-w-[1300px] flex-col gap-4">
      {/* catalog header — real counts across every distinct real system this
          page surfaces: the invokable library, bundles, purely descriptive
          custom tags, and read-only agent specializations. Previously this
          page only ever showed the latter two -- the actual invokable skill
          system (the thing achievements.py's "skills used" stat is even
          about) had zero presence here. */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card/60 px-4 py-3">
        <div className="flex items-center gap-2">
          <Library className="h-4 w-4 text-primary" />
          <span className="font-heading text-xs text-foreground">Skills</span>
          <span className="text-[0.55rem] text-muted-foreground">
            {libData?.skills.length ?? '…'} library · {bundleData?.bundles.length ?? 0} bundles · {customSkills.length} custom tags · {skills.length} built-in specializations
          </span>
        </div>
        <NewSkillForm agents={agents} onCreated={fetchCustom} />
      </div>

      <SkillLibrarySection />
      <SkillBundlesSection />

      {/* shelf — purely descriptive, user-created tags (skills_store.py).
          Explicitly NOT invokable: nothing in the system reads agent_keys
          or category to change real behavior -- this is a note, not a
          procedure. Kept separate from the real library above so the two
          "skill" concepts are never conflated the way the old single list
          used to blur them. */}
      <div className="rounded-xl border border-tertiary/30 bg-card/60">
        <div className="flex items-center gap-2 border-b border-border/50 px-4 py-2.5">
          <span className="h-1.5 w-1.5 rounded-full bg-tertiary" />
          <h3 className="font-heading text-[0.68rem] text-foreground">Custom Skill Tags</h3>
          <span className="text-[0.5rem] text-muted-foreground">descriptive only -- not invokable, unlike the library above</span>
        </div>
        {customSkills.length === 0 ? (
          <div className="p-4"><EmptyNote>No custom tags yet — create one above and assign it to real agents. Persisted server-side, purely descriptive.</EmptyNote></div>
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
    <div className="mx-auto flex max-w-[900px] flex-col gap-1">
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

      <ModelPerformanceRow />
      <MixtureOfAgentsCard />
      <VoiceCloneCard />
    </div>
  )
}

/** Real per-backend call volume/latency/tokens (usage_analytics.py) --
 * previously only shown on Overview's summary chart; this page is
 * specifically about the model chain, so it earns a direct spot here too. */
function ModelPerformanceRow() {
  const [usage, setUsage] = useState<{ per_backend: Array<{ backend: string; call_count: number; success_count: number; avg_latency_s: number; tokens_per_sec: number | null }> } | null>(null)
  useEffect(() => {
    const load = () => fetch('/api/usage/llm').then((r) => r.json()).then((json) => { if (json.success) setUsage(json) }).catch(() => {})
    load()
    const t = setInterval(load, 30000)
    return () => clearInterval(t)
  }, [])
  const perBackend = usage?.per_backend ?? []
  if (perBackend.length === 0) return null
  return (
    <div className="mt-2 rounded-xl border border-border bg-card/60 p-3">
      <div className="mb-2 flex items-center gap-2">
        <BarChart3 className="h-3.5 w-3.5 text-primary" />
        <h3 className="font-heading text-[0.65rem] text-foreground">Real Performance This Run</h3>
      </div>
      <div className="flex flex-col gap-1.5">
        {perBackend.map((b) => (
          <div key={b.backend} className="flex flex-wrap items-center justify-between gap-2 rounded border border-border/40 bg-secondary/10 px-2.5 py-1.5 text-[0.55rem]">
            <span className="text-foreground">{b.backend}</span>
            <span className="text-muted-foreground">{b.call_count} call{b.call_count !== 1 ? 's' : ''} · {b.success_count} ok</span>
            <span className="text-muted-foreground">{b.avg_latency_s?.toFixed(2)}s avg</span>
            {b.tokens_per_sec != null && <span className="text-primary">{b.tokens_per_sec} tok/s</span>}
          </div>
        ))}
      </div>
    </div>
  )
}

/** Real Mixture-of-Agents (moa.py) -- calls several distinct, actually-
 * configured LLM backends on the same prompt in parallel, then has the
 * best-performing one critically synthesize their answers. Previously
 * fully built (a real endpoint) with zero frontend surface. */
interface MoaReference { backend: string; text: string }
interface MoaResult {
  success: boolean
  response?: string
  references?: MoaReference[]
  aggregated?: boolean
  aggregation_error?: string
  error?: string
}
function MixtureOfAgentsCard() {
  const [prompt, setPrompt] = useState('')
  const [referenceCount, setReferenceCount] = useState(3)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<MoaResult | null>(null)

  const run = async () => {
    if (!prompt.trim()) return
    setRunning(true); setResult(null)
    try {
      const res = await fetch('/api/llm/moa', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: prompt.trim(), reference_count: referenceCount }),
      })
      const json = await res.json()
      setResult(json)
    } catch (e) {
      setResult({ success: false, error: String(e) })
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="mt-2 rounded-xl border border-primary/30 bg-card/60 p-4">
      <div className="mb-2.5 flex items-center gap-2">
        <GitMerge className="h-4 w-4 text-primary" />
        <h3 className="font-heading text-xs text-foreground">Mixture-of-Agents</h3>
        <span className="text-[0.5rem] text-muted-foreground">real parallel reference models, critically synthesized</span>
      </div>
      <div className="flex flex-col gap-2">
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Ask something and see how the real configured models compare…"
          rows={2}
          className="w-full resize-none rounded border border-border bg-background/60 px-2.5 py-1.5 text-[0.62rem] text-foreground outline-none focus:border-primary/60"
        />
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[0.55rem] text-muted-foreground">References</span>
          <select value={referenceCount} onChange={(e) => setReferenceCount(Number(e.target.value))} className="rounded border border-border bg-background/60 px-2 py-1 text-[0.55rem] text-foreground outline-none focus:border-primary/60">
            {[2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
          <PrimaryButton onClick={run} disabled={running || !prompt.trim()} className="ml-auto">
            {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />} Run
          </PrimaryButton>
        </div>
      </div>

      {result && (
        <div className="mt-3 flex flex-col gap-2 border-t border-border/50 pt-3">
          {!result.success ? (
            <p className="text-[0.6rem] text-destructive">{result.error}</p>
          ) : (
            <>
              {result.references && result.references.length > 1 && (
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {result.references.map((r) => (
                    <div key={r.backend} className="rounded border border-border/50 bg-secondary/10 p-2">
                      <div className="mb-1 flex items-center gap-1.5 text-[0.5rem] text-muted-foreground"><Cpu className="h-3 w-3 text-primary" /> {r.backend}</div>
                      <p className="line-clamp-4 text-[0.58rem] leading-relaxed text-muted-foreground">{r.text}</p>
                    </div>
                  ))}
                </div>
              )}
              <div className="rounded-lg border border-primary/40 bg-primary/5 p-3">
                <div className="mb-1.5 flex items-center gap-1.5 text-[0.55rem] text-primary">
                  <GitMerge className="h-3.5 w-3.5" /> {result.aggregated ? 'Synthesized answer' : 'Best single answer'}
                  {result.aggregation_error && <span className="text-muted-foreground">(synthesis failed: {result.aggregation_error})</span>}
                </div>
                <p className="whitespace-pre-wrap text-[0.65rem] leading-relaxed text-foreground">{result.response}</p>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

/* ═══ VOICE CLONE — real upload -> auto-transcribe -> clone, no restart ═══ */
function VoiceCloneCard() {
  const [status, setStatus] = useState<{ available: boolean; voice_source: string; error: string | null } | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const res = await fetch('/api/tts/status', { cache: 'no-store' })
      const json = await res.json()
      if (json.success) setStatus(json)
    } catch { /* transient — next poll retries */ }
  }, [])

  useEffect(() => { void refresh() }, [refresh])

  const onUpload = useCallback(async (file: File) => {
    setBusy(true)
    setMessage(null)
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch('/api/voice/reference', { method: 'POST', body: form })
      const json = await res.json()
      if (json.success) {
        setStatus(json)
        setMessage('Voice cloned from your clip — every reply now speaks in it.')
      } else {
        setMessage(json.detail ?? 'Upload failed.')
      }
    } catch {
      setMessage('Upload failed.')
    } finally {
      setBusy(false)
    }
  }, [])

  const onRevert = useCallback(async () => {
    setBusy(true)
    setMessage(null)
    try {
      const res = await fetch('/api/voice/reference', { method: 'DELETE' })
      const json = await res.json()
      if (json.success) { setStatus(json); setMessage('Reverted to the default placeholder voice.') }
    } finally {
      setBusy(false)
    }
  }, [])

  if (!status?.available) return null
  const isUser = status.voice_source === 'user'

  return (
    <div className="mt-2 flex flex-col gap-2 rounded-xl border border-border bg-card/60 px-4 py-3">
      <div className="flex items-center gap-2">
        <Mic className="h-4 w-4 text-tertiary" />
        <span className="font-heading text-xs text-foreground">Voice Clone</span>
        <span className={cn(
          'ml-auto rounded-full border px-2 py-0.5 text-[0.5rem] uppercase',
          isUser ? 'border-primary/40 bg-primary/10 text-primary' : 'border-border/60 text-muted-foreground',
        )}>
          {isUser ? 'your voice' : 'default placeholder'}
        </span>
      </div>
      <p className="text-[0.55rem] text-muted-foreground">
        Drop in a clean .wav clip of your voice (a few sentences is enough) — Nancy auto-transcribes it and clones it immediately, no restart needed.
      </p>
      <div className="flex items-center gap-2">
        <label className={cn(
          'flex cursor-pointer items-center gap-1.5 rounded-lg border border-primary/50 bg-primary/10 px-3 py-1.5 text-[0.6rem] text-primary transition-colors hover:bg-primary/20',
          busy && 'pointer-events-none opacity-40',
        )}>
          <Upload className="h-3 w-3" /> {busy ? 'Working…' : 'Upload clip (.wav)'}
          <input
            type="file"
            accept=".wav,audio/wav"
            className="hidden"
            disabled={busy}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void onUpload(f); e.target.value = '' }}
          />
        </label>
        {isUser && (
          <button type="button" onClick={onRevert} disabled={busy} className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-[0.6rem] text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40">
            <Trash2 className="h-3 w-3" /> Revert to default
          </button>
        )}
      </div>
      {message && <div className="text-[0.55rem] text-primary">{message}</div>}
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

/** Real, user-controlled opt-in ambient screen awareness (see
 * backend/screen_context.py) -- off by default. Shows the actual last
 * captured summary in the open, not hidden, so trust doesn't depend on
 * taking the toggle's word for it: whatever Nancy currently "knows" from
 * your screen is always visible right here. */
function ScreenAwarenessCard() {
  const { data: status } = useScreenContextStatus()
  const [busy, setBusy] = useState(false)

  const toggle = async () => {
    if (!status) return
    setBusy(true)
    try {
      await setScreenContextEnabled(!status.enabled)
    } finally {
      setBusy(false)
    }
  }
  const refreshNow = async () => {
    setBusy(true)
    try {
      await captureScreenContextNow()
    } finally {
      setBusy(false)
    }
  }

  const enabled = status?.enabled ?? false

  return (
    <div className="rounded-xl border border-border bg-card/60 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          {enabled ? <Eye className="h-4 w-4 text-primary" /> : <EyeOff className="h-4 w-4 text-muted-foreground" />}
          <div>
            <h3 className="font-heading text-xs text-foreground">Screen Awareness</h3>
            <p className="text-[0.5rem] text-muted-foreground">
              Real, opt-in only — a screenshot is captured and described (Claude vision) roughly every 45s while on.
            </p>
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {enabled && (
            <button
              type="button"
              onClick={refreshNow}
              disabled={busy}
              className="rounded border border-border px-2 py-1 text-[0.5rem] text-muted-foreground transition-colors hover:border-primary/50 hover:text-primary disabled:opacity-40"
            >
              Capture now
            </button>
          )}
          <button
            type="button"
            onClick={toggle}
            disabled={busy || !status}
            className={cn(
              'flex items-center gap-1.5 rounded border px-2.5 py-1.5 text-[0.6rem] transition-colors disabled:opacity-40',
              enabled ? 'border-primary bg-primary/15 text-primary' : 'border-border bg-secondary/30 text-muted-foreground hover:text-foreground',
            )}
          >
            {enabled ? <ToggleRight className="h-4 w-4" /> : <ToggleLeft className="h-4 w-4" />}
            {enabled ? 'On' : 'Off'}
          </button>
        </div>
      </div>

      {status && !status.configured && (
        <p className="mt-2 text-[0.5rem] text-muted-foreground">
          Set ANTHROPIC_API_KEY in the backend .env to enable vision description.
        </p>
      )}
      {enabled && (
        <div className="mt-3 rounded border border-border/50 bg-secondary/20 px-2.5 py-2 text-[0.6rem]">
          {status?.error ? (
            <span className="text-destructive">{status.error}</span>
          ) : status?.last_summary ? (
            <>
              <span className="text-muted-foreground">Last seen: </span>
              <span className="text-foreground">{status.last_summary}</span>
            </>
          ) : (
            <span className="text-muted-foreground">Waiting on the first capture…</span>
          )}
        </div>
      )}
    </div>
  )
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

      <ScreenAwarenessCard />

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
  const [llmUsage, setLlmUsage] = useState<{ overall_calls: number; overall_success: number; overall_tokens: number; per_backend: any[]; note: string } | null>(null)
  useEffect(() => { listAgents().then((r) => r.success && setStats(r.stats)) }, [])
  useEffect(() => {
    fetch('/api/usage/llm').then((r) => r.json()).then((json) => { if (json.success) setLlmUsage(json) }).catch(() => {})
  }, [])

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

      {llmUsage && llmUsage.overall_calls > 0 ? (
        <div className="rounded-xl border border-border bg-card/60">
          <p className="border-b border-border/50 px-4 py-2 text-[0.55rem] text-muted-foreground">
            Real per-backend LLM metrics — {llmUsage.note}
          </p>
          <ul className="divide-y divide-border/40">
            {llmUsage.per_backend.map((b) => (
              <li key={b.backend} className="px-4 py-3">
                <div className="flex items-center justify-between">
                  <span className="text-[0.65rem] text-foreground">{b.backend}</span>
                  <span className="text-[0.55rem] text-muted-foreground">{b.call_count}x · {b.success_count} ok · {b.avg_latency_s}s avg latency</span>
                </div>
                <div className="mt-1.5 grid grid-cols-2 gap-x-4 gap-y-1 text-[0.55rem] text-muted-foreground sm:grid-cols-4">
                  <div>
                    <span className="text-muted-foreground/70">Prompt tok{b.tokens_exact ? '' : ' (est.)'}: </span>
                    <span className="text-foreground">{b.prompt_tokens}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground/70">Completion tok{b.tokens_exact ? '' : ' (est.)'}: </span>
                    <span className="text-foreground">{b.completion_tokens}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground/70">Prompt proc.: </span>
                    <span className="text-foreground">{b.avg_prompt_time_s !== null ? `${b.avg_prompt_time_s}s` : 'n/a'}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground/70">Decode: </span>
                    <span className="text-foreground">{b.avg_decode_time_s !== null ? `${b.avg_decode_time_s}s` : 'n/a'}</span>
                  </div>
                </div>
                {b.tokens_per_sec !== null && (
                  <div className="mt-1 text-[0.55rem] text-primary">{b.tokens_per_sec} tok/s inference speed</div>
                )}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="text-[0.55rem] text-muted-foreground">
          No LLM calls recorded yet this run — usage_analytics.py tracks real call volume/latency/tokens/inference speed per backend as they happen.
        </p>
      )}
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

  useEffect(() => {
    fetch(`${BACKEND}/greeting`)
      .then((res) => res.json())
      .then((json) => { if (json.success && json.persona) setActive(json.persona) })
      .catch(() => { /* keep the default 'nancy' state -- backend may not be reachable yet */ })
  }, [])

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

/* ═══════════════════ PLUGINS / MCP — real MCP client, real servers ═════
   Backed by mcp_client.py's official-SDK MCP client: real subprocess
   servers, real tool lists, real tool calls through Claude's tool-use loop.
   "Plugins" and "MCP" are the same real capability now, so both nav entries
   render this one panel instead of duplicating it. ═══════════════════════ */
interface PluginServer {
  id: string
  name: string
  command: string
  args: string[]
  env: Record<string, string>
  enabled: boolean
  connected: boolean
  error: string | null
  tools: string[]
}

export function PluginsPanel(_props: { onNavigate?: () => void } = {}) {
  const [servers, setServers] = useState<PluginServer[]>([])
  const [loading, setLoading] = useState(true)
  const [name, setName] = useState('')
  const [command, setCommand] = useState('npx')
  const [argsInput, setArgsInput] = useState('')
  const [creating, setCreating] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)

  const fetchServers = useCallback(async () => {
    try {
      const res = await fetch('/api/plugins', { cache: 'no-store' })
      const json = await res.json()
      if (json.success) setServers(json.servers)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchServers()
    const t = setInterval(fetchServers, 15_000)
    return () => clearInterval(t)
  }, [fetchServers])

  const createServer = async () => {
    if (!name.trim() || !command.trim()) return
    setCreating(true); setFormError(null)
    try {
      const res = await fetch('/api/plugins', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), command: command.trim(), args: argsInput.trim().split(/\s+/).filter(Boolean) }),
      })
      const json = await res.json()
      if (!json.success) { setFormError(json.detail || 'Failed to register server (approval denied or timed out)'); return }
      setName(''); setArgsInput('')
      fetchServers()
    } catch (e) {
      setFormError(String(e))
    } finally {
      setCreating(false)
    }
  }

  const toggleServer = async (s: PluginServer) => {
    await fetch(`/api/plugins/${s.id}?enabled=${!s.enabled}`, { method: 'PATCH' })
    fetchServers()
  }
  const deleteServer = async (s: PluginServer) => {
    await fetch(`/api/plugins/${s.id}`, { method: 'DELETE' })
    fetchServers()
  }

  return (
    <div className="mx-auto flex max-w-[900px] flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card/60 px-4 py-3">
        <div className="flex items-center gap-2">
          <PlugZap className="h-4 w-4 text-primary" />
          <span className="font-heading text-xs text-foreground">MCP Plugin Servers</span>
        </div>
        <span className="text-[0.55rem] text-muted-foreground">
          {servers.length} configured · {servers.filter((s) => s.connected).length} connected · real tools via the official MCP SDK
        </span>
      </div>

      <div className="rounded-xl border border-border bg-card/60 p-4">
        <h3 className="mb-2.5 flex items-center gap-2 font-heading text-[0.68rem] text-foreground">
          <Plus className="h-3.5 w-3.5 text-primary" /> Connect a server
        </h3>
        <p className="mb-2.5 text-[0.55rem] text-muted-foreground">
          Registers a real local subprocess (e.g. <code>npx -y @modelcontextprotocol/server-filesystem C:\path</code>) — Nancy asks for Telegram approval before spawning it, the same gate as running any other command.
        </p>
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-[160px_120px_1fr_auto]">
          <div>
            <FieldLabel>Name</FieldLabel>
            <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="filesystem" />
          </div>
          <div>
            <FieldLabel>Command</FieldLabel>
            <input className={inputCls} value={command} onChange={(e) => setCommand(e.target.value)} placeholder="npx" />
          </div>
          <div>
            <FieldLabel>Args (space-separated)</FieldLabel>
            <input className={inputCls} value={argsInput} onChange={(e) => setArgsInput(e.target.value)} placeholder="-y @modelcontextprotocol/server-filesystem C:\path" />
          </div>
          <div className="flex items-end">
            <PrimaryButton onClick={createServer} disabled={creating || !name.trim() || !command.trim()}>
              {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />} {creating ? 'Awaiting approval…' : 'Connect'}
            </PrimaryButton>
          </div>
        </div>
        {formError && <p className="mt-2 text-[0.55rem] text-destructive">{formError}</p>}
      </div>

      <div className="rounded-xl border border-border bg-card/60">
        <p className="border-b border-border/50 px-4 py-2 text-[0.55rem] text-muted-foreground">
          Connected servers&rsquo; tools appear automatically in every tool-use-capable chat turn and cron run_skill job — no separate activation step.
        </p>
        {loading && servers.length === 0 ? (
          <div className="flex items-center justify-center py-6 text-[0.6rem] text-muted-foreground">
            <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> Loading…
          </div>
        ) : servers.length === 0 ? (
          <EmptyNote>No plugin servers yet — connect one above to give Nancy real third-party tools.</EmptyNote>
        ) : (
          <ul className="divide-y divide-border/40">
            {servers.map((s) => (
              <li key={s.id} className="flex flex-col gap-1.5 px-4 py-2.5">
                <div className="flex flex-wrap items-center gap-3">
                  <span className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-full border', s.connected ? 'border-primary/40 bg-primary/10' : 'border-border/50 bg-secondary/20')}>
                    <PlugZap className={cn('h-3.5 w-3.5', s.connected ? 'text-primary' : 'text-muted-foreground')} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[0.62rem] text-foreground">{s.name}</div>
                    <div className="truncate text-[0.5rem] text-muted-foreground">
                      {s.command} {s.args.join(' ')} · {s.connected ? `${s.tools.length} tool${s.tools.length !== 1 ? 's' : ''}` : (s.error ? `error: ${s.error}` : 'disconnected')}
                    </div>
                  </div>
                  {s.connected && s.tools.length > 0 && (
                    <button type="button" onClick={() => setExpanded(expanded === s.id ? null : s.id)} className="rounded p-1.5 text-muted-foreground hover:text-primary" title="Show tools" aria-label={`Show tools for ${s.name}`}>
                      <ChevronRight className={cn('h-3.5 w-3.5 transition-transform', expanded === s.id && 'rotate-90')} />
                    </button>
                  )}
                  <button type="button" onClick={() => toggleServer(s)} className="rounded p-1.5 text-muted-foreground hover:text-primary" title="Toggle enabled" aria-label={s.enabled ? `Disable ${s.name}` : `Enable ${s.name}`}>
                    {s.enabled ? <ToggleRight className="h-4 w-4 text-primary" /> : <ToggleLeft className="h-4 w-4" />}
                  </button>
                  <button type="button" onClick={() => deleteServer(s)} className="rounded p-1.5 text-muted-foreground hover:text-destructive" title="Remove" aria-label={`Remove ${s.name}`}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
                {expanded === s.id && (
                  <div className="ml-11 flex flex-wrap gap-1.5">
                    {s.tools.map((t) => (
                      <span key={t} className="rounded-full border border-border/60 bg-secondary/30 px-2 py-0.5 text-[0.5rem] text-muted-foreground">{t}</span>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
export function McpPanel(props: { onNavigate?: () => void } = {}) {
  return <PluginsPanel {...props} />
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

/* ═══════════════════ MEMORY INSIGHTS — real journey timeline, dream diary,
   commitments, and the memory wiki, all backed by real backend data (memory/
   journey.py, memory/dreaming.py, memory/commitments.py, memory/wiki_store.py).
   One panel, tabbed, matching the lighter-touch DOCS treatment above rather
   than a full CRUD form since three of these four surfaces are read-mostly. ═══ */
type MemoryTab = 'journey' | 'dreams' | 'commitments' | 'wiki'

export function MemoryInsightsPanel() {
  const [tab, setTab] = useState<MemoryTab>('journey')
  const [journey, setJourney] = useState<{ timeline: any[]; stats: any } | null>(null)
  const [dreams, setDreams] = useState<any[]>([])
  const [openCommitments, setOpenCommitments] = useState<any[]>([])
  const [wikiPages, setWikiPages] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  const fetchAll = useCallback(async () => {
    try {
      const [j, d, c, w] = await Promise.all([
        fetch('/api/memory/journey').then((r) => r.json()).catch(() => null),
        fetch('/api/memory/dream-diary').then((r) => r.json()).catch(() => null),
        fetch('/api/memory/commitments').then((r) => r.json()).catch(() => null),
        fetch('/api/memory/wiki').then((r) => r.json()).catch(() => null),
      ])
      if (j?.success) setJourney({ timeline: j.timeline, stats: j.stats })
      if (d?.success) setDreams(d.entries)
      if (c?.success) setOpenCommitments(c.commitments)
      if (w?.success) setWikiPages(w.pages)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAll()
    const t = setInterval(fetchAll, 60_000)
    return () => clearInterval(t)
  }, [fetchAll])

  const resolveCommitment = async (id: string) => {
    await fetch(`/api/memory/commitments/${id}/resolve`, { method: 'POST' })
    fetchAll()
  }

  const tabs: { key: MemoryTab; label: string; icon: typeof CalendarClock }[] = [
    { key: 'journey', label: 'Journey', icon: CalendarClock },
    { key: 'dreams', label: 'Dream Diary', icon: Moon },
    { key: 'commitments', label: 'Commitments', icon: CheckSquare },
    { key: 'wiki', label: 'Memory Wiki', icon: Network },
  ]

  return (
    <div className="mx-auto flex max-w-[900px] flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card/60 px-3 py-2">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={cn(
              'flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[0.6rem] transition-colors',
              tab === t.key ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <t.icon className="h-3.5 w-3.5" /> {t.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-8 text-[0.6rem] text-muted-foreground">
          <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> Loading…
        </div>
      ) : tab === 'journey' ? (
        <div className="rounded-xl border border-border bg-card/60">
          {journey?.stats && (
            <div className="flex flex-wrap gap-4 border-b border-border/50 px-4 py-2.5 text-[0.55rem] text-muted-foreground">
              <span>{journey.stats.total_memories} memories</span>
              <span>{journey.stats.skills_used_count} skills used</span>
              <span>{journey.stats.skill_uses_total} total skill invocations</span>
            </div>
          )}
          {!journey?.timeline?.length ? (
            <EmptyNote>No journey events yet — memories and skill usage will appear here as they happen.</EmptyNote>
          ) : (
            <ul className="divide-y divide-border/40">
              {journey.timeline.map((e: any, i: number) => (
                <li key={i} className="flex items-center gap-3 px-4 py-2.5">
                  {e.kind === 'skill' ? <Wrench className="h-3.5 w-3.5 shrink-0 text-tertiary" /> : <Sparkles className="h-3.5 w-3.5 shrink-0 text-primary" />}
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[0.62rem] text-foreground">{e.label}</div>
                    <div className="text-[0.5rem] text-muted-foreground">{new Date(e.timestamp * 1000).toLocaleString()}</div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : tab === 'dreams' ? (
        <div className="rounded-xl border border-border bg-card/60">
          <p className="border-b border-border/50 px-4 py-2 text-[0.55rem] text-muted-foreground">
            Real memory-consolidation cycles — deduped near-duplicates and promoted recurring themes into insights.
          </p>
          {dreams.length === 0 ? (
            <EmptyNote>No consolidation cycles have run yet — schedule the &ldquo;Memory consolidation cycle&rdquo; blueprint in Cron Jobs.</EmptyNote>
          ) : (
            <ul className="divide-y divide-border/40">
              {dreams.map((entry: any, i: number) => (
                <li key={i} className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <Moon className="h-3.5 w-3.5 shrink-0 text-tertiary" />
                    <span className="text-[0.62rem] text-foreground">{entry.narrative}</span>
                  </div>
                  <div className="mt-1 pl-5.5 text-[0.5rem] text-muted-foreground">
                    {new Date(entry.timestamp * 1000).toLocaleString()} · merged {entry.light?.removed ?? 0} · promoted {entry.deep?.clusters_found ?? 0}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : tab === 'commitments' ? (
        <div className="rounded-xl border border-border bg-card/60">
          <p className="border-b border-border/50 px-4 py-2 text-[0.55rem] text-muted-foreground">
            Real promises/follow-ups extracted from conversation — resurfaced daily if the check-in blueprint is scheduled.
          </p>
          {openCommitments.length === 0 ? (
            <EmptyNote>Nothing open right now.</EmptyNote>
          ) : (
            <ul className="divide-y divide-border/40">
              {openCommitments.map((c: any) => (
                <li key={c.id} className="flex items-center gap-3 px-4 py-2.5">
                  <CheckSquare className="h-3.5 w-3.5 shrink-0 text-primary" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[0.62rem] text-foreground">{c.text}</div>
                    <div className="text-[0.5rem] text-muted-foreground">{c.category} · {c.sensitivity}{c.due_hint ? ` · ${c.due_hint}` : ''}</div>
                  </div>
                  <button type="button" onClick={() => resolveCommitment(c.id)} className="rounded p-1.5 text-muted-foreground hover:text-primary" title="Mark resolved" aria-label={`Mark "${c.text}" resolved`}>
                    <CheckCircle2 className="h-3.5 w-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-border bg-card/60">
          <p className="border-b border-border/50 px-4 py-2 text-[0.55rem] text-muted-foreground">
            Real Markdown pages with structured claim/evidence/provenance metadata — Obsidian-compatible files under backend/data/memory_wiki/.
          </p>
          {wikiPages.length === 0 ? (
            <EmptyNote>No wiki pages yet.</EmptyNote>
          ) : (
            <ul className="divide-y divide-border/40">
              {wikiPages.map((p: any) => (
                <li key={p.slug} className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <Library className="h-3.5 w-3.5 shrink-0 text-primary" />
                    <span className="text-[0.65rem] text-foreground">{p.title}</span>
                    {p.contradiction_of && <span className="rounded bg-destructive/15 px-1.5 py-0.5 text-[0.5rem] text-destructive">contradicts {p.contradiction_of}</span>}
                  </div>
                  <p className="mt-1 pl-5.5 text-[0.6rem] text-muted-foreground">{p.claim}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

/* ═══════════════════ ACHIEVEMENTS — real badges computed from real activity
   (achievements_store.py), no fake incrementing counters. ═══════════════ */
const TIER_COLOR: Record<string, string> = {
  copper: 'text-[#b87333]', bronze: 'text-[#cd7f32]', silver: 'text-slate-300',
  gold: 'text-gold', olympian: 'text-primary',
}

export function AchievementsPanel() {
  const [data, setData] = useState<{ unlocked: any[]; locked: any[] } | null>(null)
  useEffect(() => {
    fetch('/api/achievements').then((r) => r.json()).then((json) => { if (json.success) setData(json) }).catch(() => {})
  }, [])

  return (
    <div className="mx-auto flex max-w-[900px] flex-col gap-4">
      <div className="flex items-center gap-2 rounded-xl border border-border bg-card/60 px-4 py-3">
        <Award className="h-4 w-4 text-primary" />
        <span className="font-heading text-xs text-foreground">Achievements</span>
        {data && <span className="ml-auto text-[0.55rem] text-muted-foreground">{data.unlocked.length}/{data.unlocked.length + data.locked.length} unlocked</span>}
      </div>

      {!data ? (
        <div className="flex items-center justify-center py-8 text-[0.6rem] text-muted-foreground">
          <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> Loading…
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
          {data.unlocked.map((a) => (
            <div key={a.key} className="flex items-center gap-3 rounded-xl border border-primary/30 bg-primary/5 px-3.5 py-3">
              <Award className={cn('h-5 w-5 shrink-0', TIER_COLOR[a.tier] ?? 'text-primary')} />
              <div className="min-w-0">
                <div className="text-[0.65rem] text-foreground">{a.title}</div>
                <div className="text-[0.55rem] text-muted-foreground">{a.description}</div>
              </div>
            </div>
          ))}
          {data.locked.map((a) => (
            <div key={a.key} className="flex items-center gap-3 rounded-xl border border-border/50 bg-secondary/10 px-3.5 py-3 opacity-60">
              <Lock className="h-5 w-5 shrink-0 text-muted-foreground" />
              <div className="min-w-0">
                <div className="text-[0.65rem] text-foreground">{a.title}</div>
                <div className="text-[0.55rem] text-muted-foreground">{a.description}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* ═══════════════════ THEMING — live CSS-variable overrides, persisted to
   localStorage (lib/nancy/theme.ts). Real values applied immediately via
   document.documentElement.style, not a preview-only mock. ═══════════════ */
export function ThemingPanel() {
  const [overrides, setOverrides] = useState<Record<string, string>>({})

  useEffect(() => {
    import('@/lib/nancy/theme').then(({ getThemeOverrides }) => setOverrides(getThemeOverrides()))
  }, [])

  const currentValue = (key: string) => {
    if (overrides[key]) return overrides[key]
    if (typeof window === 'undefined') return '#888888'
    const computed = getComputedStyle(document.documentElement).getPropertyValue(key).trim()
    return computed || '#888888'
  }

  const handleChange = async (key: string, value: string) => {
    const { setThemeOverride } = await import('@/lib/nancy/theme')
    setThemeOverride(key, value)
    setOverrides((prev) => ({ ...prev, [key]: value }))
  }

  const handleReset = async (key: string) => {
    const { resetThemeVar } = await import('@/lib/nancy/theme')
    resetThemeVar(key)
    setOverrides((prev) => { const next = { ...prev }; delete next[key]; return next })
  }

  const handleResetAll = async () => {
    const { resetAllTheme } = await import('@/lib/nancy/theme')
    resetAllTheme()
    setOverrides({})
  }

  return (
    <div className="mx-auto flex max-w-[700px] flex-col gap-4">
      <div className="flex items-center justify-between gap-2 rounded-xl border border-border bg-card/60 px-4 py-3">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-primary" />
          <span className="font-heading text-xs text-foreground">Theme</span>
        </div>
        <button type="button" onClick={handleResetAll} className="text-[0.55rem] text-muted-foreground hover:text-foreground">
          Reset all to defaults
        </button>
      </div>

      <div className="divide-y divide-border/40 rounded-xl border border-border bg-card/60">
        {THEMEABLE_VARS_META.map(({ key, label, description }) => (
          <div key={key} className="flex items-center gap-3 px-4 py-3">
            <input
              type="color"
              value={/^#/.test(currentValue(key)) ? currentValue(key) : '#888888'}
              onChange={(e) => handleChange(key, e.target.value)}
              className="h-8 w-8 shrink-0 cursor-pointer rounded border border-border bg-transparent"
            />
            <div className="min-w-0 flex-1">
              <div className="text-[0.62rem] text-foreground">{label}</div>
              <div className="text-[0.5rem] text-muted-foreground">{description}</div>
            </div>
            {overrides[key] && (
              <button type="button" onClick={() => handleReset(key)} className="text-[0.5rem] text-muted-foreground hover:text-destructive">
                Reset
              </button>
            )}
          </div>
        ))}
      </div>
      <p className="text-[0.55rem] text-muted-foreground">
        Base colors use oklch() for perceptual consistency; a picked color here overrides that variable directly (valid CSS, applied immediately) and persists across reloads until reset.
      </p>
    </div>
  )
}

const THEMEABLE_VARS_META = [
  { key: '--primary', label: 'Primary (Ember)', description: 'The one confident accent — active states, primary actions.' },
  { key: '--gold', label: 'Gold', description: 'Secondary accent, used sparingly.' },
  { key: '--accent', label: 'Accent (Slate)', description: 'Quiet informational color — links, secondary emphasis.' },
  { key: '--tertiary', label: 'Tertiary', description: 'Special-moments-only accent.' },
  { key: '--magenta', label: 'Magenta', description: 'Rarely-used warm rose-red accent.' },
]
