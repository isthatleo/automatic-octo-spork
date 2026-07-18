'use client'

import { useEffect, useState } from 'react'
import { HudPanel } from './hud-bits'
import { listAgents } from '@/lib/nancy/agent-client'
import { useCronStatus, useConfigPublic, useTelegramStatus, useLlmStatus } from '@/hooks/useSystemData'
import type { AgentInfo, LogEntry } from '@/lib/nancy/types'
import { cn } from '@/lib/utils'
import {
  Send, MessagesSquare, Hash, Phone, Globe2, CheckCircle2, XCircle,
  Clock, Wrench, Sparkles, Cpu, Waves, Eye, Key, User, Server,
  BookOpen, BarChart3, PlugZap, Webhook, Link2, Loader2,
} from 'lucide-react'

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

function EmptyNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded border border-dashed border-border/60 bg-secondary/10 px-3 py-4 text-center text-[0.6rem] text-muted-foreground">
      {children}
    </div>
  )
}

function StatusPill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={cn(
      'flex items-center gap-1 rounded-full border px-2 py-0.5 text-[0.5rem] uppercase tracking-widest',
      ok ? 'border-primary/40 bg-primary/10 text-primary' : 'border-border/50 text-muted-foreground',
    )}>
      {ok ? <CheckCircle2 className="h-2.5 w-2.5" /> : <XCircle className="h-2.5 w-2.5" />}
      {label}
    </span>
  )
}

/* ═══════════════════ SESSIONS — this tab's real conversation session ═══ */
export function SessionsPanel({ logs }: { logs: LogEntry[] }) {
  const userTurns = logs.filter((l) => l.level === 'user').length
  const nancyTurns = logs.filter((l) => l.level === 'nancy').length
  const started = logs[0]?.ts ?? Date.now()
  return (
    <div className="mx-auto grid max-w-[1680px] grid-cols-12 gap-4">
      <HudPanel hero title="Current Session" className="col-span-12 lg:col-span-4">
        <div className="grid grid-cols-2 gap-2 text-center">
          <div className="rounded border border-border/50 bg-secondary/20 p-3">
            <div className="font-display text-xl text-primary hud-glow">{userTurns}</div>
            <div className="text-[0.45rem] uppercase tracking-widest text-muted-foreground">Your turns</div>
          </div>
          <div className="rounded border border-border/50 bg-secondary/20 p-3">
            <div className="font-display text-xl text-accent hud-glow-amber">{nancyTurns}</div>
            <div className="text-[0.45rem] uppercase tracking-widest text-muted-foreground">Nancy turns</div>
          </div>
        </div>
        <p className="mt-3 text-[0.55rem] text-muted-foreground">
          Started {new Date(started).toLocaleTimeString('en-GB')} · this browser tab only, real conversation log below.
        </p>
      </HudPanel>
      <HudPanel title="Transcript" accent="violet" className="col-span-12 lg:col-span-8">
        {logs.length === 0 ? (
          <EmptyNote>No conversation yet — say something to Nancy to populate this.</EmptyNote>
        ) : (
          <div className="max-h-[420px] space-y-1.5 overflow-y-auto font-mono text-[0.6rem]">
            {logs.map((l) => (
              <div key={l.id} className="flex items-start gap-2 border-b border-border/20 py-1 last:border-none">
                <span className={cn('w-14 shrink-0 uppercase tracking-widest', l.level === 'user' ? 'text-accent' : l.level === 'nancy' ? 'text-primary' : 'text-muted-foreground')}>
                  {l.level}
                </span>
                <span className="flex-1 text-foreground">{l.text}</span>
                <span className="shrink-0 text-muted-foreground">{new Date(l.ts).toLocaleTimeString('en-GB')}</span>
              </div>
            ))}
          </div>
        )}
      </HudPanel>
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
export function ChannelsPanel() {
  const { data: tg, loading } = useTelegramStatus()
  return (
    <div className="mx-auto grid max-w-[1680px] grid-cols-12 gap-4">
      {CHANNEL_DEFS.map(({ key, label, icon: Icon }) => {
        const isTelegram = key === 'telegram'
        const isWeb = key === 'web'
        const connected = isTelegram ? !!tg?.available : isWeb ? true : false
        return (
          <HudPanel key={key} className="col-span-12 md:col-span-6 xl:col-span-4" accent={connected ? 'cyan' : undefined}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Icon className="h-4 w-4 text-primary" />
                <span className="font-heading text-xs text-foreground">{label}</span>
              </div>
              {isTelegram && loading ? (
                <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
              ) : (
                <StatusPill ok={connected} label={connected ? 'connected' : 'not configured'} />
              )}
            </div>
            <p className="mt-2 text-[0.55rem] text-muted-foreground">
              {isTelegram
                ? (tg?.available ? 'Real two-way chat + approval gate active.' : tg?.error || 'TELEGRAM_BOT_TOKEN/CHAT_ID not set.')
                : isWeb
                  ? 'This browser session — always on.'
                  : 'No integration built for this channel yet.'}
            </p>
          </HudPanel>
        )
      })}
    </div>
  )
}

/* ═══════════════════ INSTANCES — single real backend process ═══════════ */
export function InstancesPanel() {
  const { data: llm, loading } = useLlmStatus()
  return (
    <div className="mx-auto grid max-w-[1680px] grid-cols-12 gap-4">
      <HudPanel hero title="Backend Instance" className="col-span-12 lg:col-span-6">
        <div className="flex items-center gap-3">
          <Server className="h-8 w-8 text-primary" />
          <div>
            <div className="font-display text-lg text-primary hud-glow">{loading ? '…' : llm ? '1 instance' : 'unreachable'}</div>
            <div className="text-[0.5rem] uppercase tracking-widest text-muted-foreground">Single local process — not a distributed gateway</div>
          </div>
        </div>
        <div className="mt-3 flex items-center gap-2">
          <StatusPill ok={!!llm} label={llm ? 'online' : 'offline'} />
          <StatusPill ok={!!llm?.agents_ready} label={llm?.agents_ready ? 'agents ready' : 'agents initialising'} />
        </div>
      </HudPanel>
      <div className="col-span-12 lg:col-span-6">
        <EmptyNote>Nancy runs as a single local backend process for one user — there's no multi-instance fleet to list here.</EmptyNote>
      </div>
    </div>
  )
}

/* ═══════════════════ CRON JOBS — real scheduled briefing ═══════════════ */
export function CronPanel() {
  const { data, loading } = useCronStatus()
  return (
    <div className="mx-auto grid max-w-[1680px] grid-cols-12 gap-4">
      <HudPanel hero title="Scheduled Jobs" accent="amber" className="col-span-12">
        {loading && !data ? (
          <div className="flex items-center justify-center py-6 text-[0.6rem] text-muted-foreground">
            <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> Loading…
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {(data?.jobs ?? []).map((job) => (
              <div key={job.name} className="flex flex-wrap items-center justify-between gap-2 rounded border border-border/50 bg-secondary/20 p-3">
                <div>
                  <div className="flex items-center gap-2">
                    <Clock className="h-3.5 w-3.5 text-primary" />
                    <span className="font-heading text-xs text-foreground">{job.name}</span>
                    <StatusPill ok={job.enabled} label={job.enabled ? 'enabled' : 'telegram not configured'} />
                  </div>
                  <p className="mt-1 text-[0.55rem] text-muted-foreground">{job.description}</p>
                </div>
                <div className="text-right text-[0.55rem]">
                  <div className="text-primary">{job.schedule}</div>
                  <div className="text-muted-foreground">next: {new Date(job.next_run).toLocaleString('en-GB')}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </HudPanel>
    </div>
  )
}

/* ═══════════════════ SKILLS — real specializations across the fleet ════ */
export function SkillsPanel() {
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [loading, setLoading] = useState(true)
  useEffect(() => { listAgents().then((r) => { if (r.success) setAgents(r.agents); setLoading(false) }) }, [])

  const skillMap = new Map<string, string[]>()
  for (const a of agents) {
    for (const s of a.specializations) {
      if (!skillMap.has(s)) skillMap.set(s, [])
      skillMap.get(s)!.push(a.name)
    }
  }
  const skills = Array.from(skillMap.entries()).sort((a, b) => b[1].length - a[1].length)

  return (
    <div className="mx-auto grid max-w-[1680px] grid-cols-12 gap-4">
      <HudPanel hero title={`Skills · ${skills.length} unique`} accent="violet" className="col-span-12">
        {loading ? (
          <div className="flex items-center justify-center py-6 text-[0.6rem] text-muted-foreground">
            <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> Reading fleet specializations…
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {skills.map(([skill, holders]) => (
              <div key={skill} className="rounded border border-border/50 bg-secondary/20 p-2.5">
                <div className="flex items-center gap-1.5">
                  <Sparkles className="h-3 w-3 text-tertiary" />
                  <span className="text-[0.6rem] text-foreground">{skill}</span>
                </div>
                <p className="mt-1 truncate text-[0.5rem] text-muted-foreground">{holders.join(', ')}</p>
              </div>
            ))}
          </div>
        )}
      </HudPanel>
    </div>
  )
}

/* ═══════════════════ MODELS — real LLM/STT/TTS stack ═══════════════════ */
export function ModelsPanel() {
  const { data: llm, loading } = useLlmStatus()
  return (
    <div className="mx-auto grid max-w-[1680px] grid-cols-12 gap-4">
      <HudPanel hero title="Reasoning Backends" className="col-span-12 lg:col-span-8">
        {loading && !llm ? (
          <div className="flex items-center justify-center py-6 text-[0.6rem] text-muted-foreground">
            <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> Reading live chain…
          </div>
        ) : (
          <ul className="grid grid-cols-1 gap-1.5 md:grid-cols-2">
            {(llm?.backends ?? []).map((b, i) => (
              <li key={`${b.name}-${i}`} className="flex items-center justify-between gap-2 rounded border border-border/50 bg-secondary/20 px-2.5 py-2">
                <span className="flex items-center gap-2 text-[0.6rem] text-muted-foreground">
                  <Cpu className="h-3.5 w-3.5 text-primary" /> {b.name} {i === 0 && <span className="text-[0.45rem] uppercase text-primary">primary</span>}
                </span>
                <span className="truncate text-[0.6rem] text-primary">{b.model ?? 'fallback'}</span>
              </li>
            ))}
          </ul>
        )}
      </HudPanel>
      <div className="col-span-12 flex flex-col gap-4 lg:col-span-4">
        <HudPanel title="Speech-to-Text" accent="amber">
          <div className="flex items-center gap-2">
            <Waves className="h-4 w-4 text-accent" />
            <span className="text-[0.65rem] text-foreground">{llm?.stt.backend ?? '…'}</span>
          </div>
          {llm?.stt.model && <p className="mt-1 text-[0.5rem] text-muted-foreground">{llm.stt.model} on {llm.stt.device}</p>}
        </HudPanel>
        <HudPanel title="Voice Synthesis" accent="violet">
          <div className="flex items-center gap-2">
            <Eye className="h-4 w-4 text-tertiary" />
            <span className="text-[0.65rem] text-foreground">{llm?.tts.backend ?? '…'}</span>
          </div>
        </HudPanel>
      </div>
    </div>
  )
}

/* ═══════════════════ KEYS — real per-provider configured state ═════════ */
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
  return (
    <div className="mx-auto grid max-w-[1680px] grid-cols-12 gap-4">
      <HudPanel hero title="Provider Keys" accent="amber" className="col-span-12">
        <p className="mb-3 text-[0.55rem] text-muted-foreground">
          Real configured-state only, derived from which backends actually initialised — no key values are ever exposed here or anywhere in this app.
        </p>
        {loading && !llm ? (
          <div className="flex items-center justify-center py-6 text-[0.6rem] text-muted-foreground">
            <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {providers.map((p) => {
              const ok = configuredNames.has(p.name)
              return (
                <div key={p.name} className="flex items-center justify-between rounded border border-border/50 bg-secondary/20 px-2.5 py-2">
                  <span className="flex items-center gap-2 text-[0.6rem] text-foreground">
                    <Key className="h-3.5 w-3.5 text-primary" /> {p.label}
                  </span>
                  <StatusPill ok={ok} label={ok ? 'configured' : 'not set'} />
                </div>
              )
            })}
          </div>
        )}
      </HudPanel>
    </div>
  )
}

/* ═══════════════════ CONFIG — real non-secret backend settings ═════════ */
export function ConfigPanel() {
  const { data, loading } = useConfigPublic()
  return (
    <div className="mx-auto grid max-w-[1680px] grid-cols-12 gap-4">
      <HudPanel hero title="Backend Configuration" className="col-span-12">
        {loading && !data ? (
          <div className="flex items-center justify-center py-6 text-[0.6rem] text-muted-foreground">
            <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-1.5 md:grid-cols-2">
            {Object.entries(data?.config ?? {}).map(([k, v]) => (
              <div key={k} className="flex items-center justify-between rounded border border-border/40 bg-secondary/10 px-2.5 py-1.5 text-[0.6rem]">
                <span className="text-muted-foreground">{k}</span>
                <span className="text-primary">{String(v)}</span>
              </div>
            ))}
          </div>
        )}
      </HudPanel>
    </div>
  )
}

/* ═══════════════════ USAGE — real task/success stats ═══════════════════ */
export function UsagePanel() {
  const [stats, setStats] = useState<{ agents_online: number; total_tasks: number; failed_tasks: number; success_rate: number } | null>(null)
  useEffect(() => { listAgents().then((r) => r.success && setStats(r.stats)) }, [])
  return (
    <div className="mx-auto grid max-w-[1680px] grid-cols-12 gap-4">
      <HudPanel hero title="Fleet Usage" className="col-span-12">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            { label: 'Agents Online', v: stats?.agents_online ?? '…', icon: BarChart3 },
            { label: 'Tasks Run', v: stats?.total_tasks ?? '…', icon: BarChart3 },
            { label: 'Failures', v: stats?.failed_tasks ?? '…', icon: BarChart3 },
            { label: 'Success Rate', v: stats ? `${(stats.success_rate * 100).toFixed(0)}%` : '…', icon: BarChart3 },
          ].map(({ label, v, icon: Icon }) => (
            <div key={label} className="rounded border border-border/50 bg-secondary/20 p-3 text-center">
              <Icon className="mx-auto mb-1 h-4 w-4 text-primary" />
              <div className="font-display text-lg text-primary hud-glow">{v}</div>
              <div className="text-[0.45rem] uppercase tracking-widest text-muted-foreground">{label}</div>
            </div>
          ))}
        </div>
        <p className="mt-3 text-[0.55rem] text-muted-foreground">
          Nancy doesn't meter LLM token spend per-request yet, so cost/usage-by-provider isn't shown here — this reflects real agent task volume only.
        </p>
      </HudPanel>
    </div>
  )
}

/* ═══════════════════ PAIRING — real Telegram chat_id pairing ═══════════ */
export function PairingPanel() {
  const { data: tg, loading } = useTelegramStatus()
  return (
    <div className="mx-auto grid max-w-[1680px] grid-cols-12 gap-4">
      <HudPanel hero title="Device Pairing" accent="violet" className="col-span-12 lg:col-span-6">
        <div className="flex items-center gap-3">
          <Link2 className="h-6 w-6 text-tertiary" />
          <div>
            <div className="text-[0.65rem] text-foreground">Telegram bot ↔ chat_id</div>
            <p className="text-[0.5rem] text-muted-foreground">The only real pairing mechanism in this build — a fixed bot token paired to one Telegram chat_id in .env.</p>
          </div>
        </div>
        <div className="mt-3">
          {loading ? <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" /> : <StatusPill ok={!!tg?.available} label={tg?.available ? 'paired' : 'not paired'} />}
        </div>
      </HudPanel>
      <div className="col-span-12 lg:col-span-6">
        <EmptyNote>No QR/device pairing flow exists for the web or voice interface — this browser session doesn&apos;t need one.</EmptyNote>
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
    <div className="mx-auto grid max-w-[1680px] grid-cols-12 gap-4">
      <HudPanel hero title="Active Persona" className="col-span-12">
        <p className="mb-3 text-[0.55rem] text-muted-foreground">
          Real, functional — changes the greeting/response persona backend-side via POST /persona/&lt;name&gt;.
        </p>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          {PERSONAS.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => switchPersona(p)}
              disabled={switching === p}
              className={cn(
                'flex items-center justify-between rounded border p-3 text-left transition-colors',
                active === p ? 'glow-ring border-transparent bg-secondary/50' : 'border-border/50 bg-secondary/20 hover:border-primary/40',
              )}
            >
              <span className="flex items-center gap-2">
                <User className="h-4 w-4 text-primary" />
                <span className="font-heading text-xs uppercase tracking-widest text-foreground">{p}</span>
              </span>
              {switching === p ? <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" /> : active === p && <CheckCircle2 className="h-3.5 w-3.5 text-primary" />}
            </button>
          ))}
        </div>
      </HudPanel>
    </div>
  )
}

/* ═══════════════════ PLUGINS / MCP / WEBHOOKS — honestly not built ═════ */
export function PluginsPanel() {
  return (
    <div className="mx-auto max-w-[1680px]">
      <HudPanel hero title="Plugins" className="col-span-12">
        <EmptyNote>
          <PlugZap className="mx-auto mb-2 h-5 w-5 text-muted-foreground" />
          No plugin system exists in this build. Nancy's extensibility is real specialized agents (see Agents) and self-created subagents, not a plugin marketplace.
        </EmptyNote>
      </HudPanel>
    </div>
  )
}
export function McpPanel() {
  return (
    <div className="mx-auto max-w-[1680px]">
      <HudPanel hero title="MCP Servers" className="col-span-12">
        <EmptyNote>
          <Wrench className="mx-auto mb-2 h-5 w-5 text-muted-foreground" />
          No Model Context Protocol integration is wired up yet — Nancy's tool-use is Claude's native tool-calling (see AI Core → Model Stack) against a fixed local tool set, not external MCP servers.
        </EmptyNote>
      </HudPanel>
    </div>
  )
}
export function WebhooksPanel() {
  return (
    <div className="mx-auto max-w-[1680px]">
      <HudPanel hero title="Webhooks" className="col-span-12">
        <EmptyNote>
          <Webhook className="mx-auto mb-2 h-5 w-5 text-muted-foreground" />
          No outbound webhook subscription system exists. Real-time delivery today is Telegram push notifications (see Channels) and the live WebSocket session, not configurable webhooks.
        </EmptyNote>
      </HudPanel>
    </div>
  )
}

/* ═══════════════════ DOCS — real, local, no fabricated links ═══════════ */
export function DocsPanel() {
  const entries = [
    { title: 'What Nancy actually is', body: 'A voice-first personal assistant: real STT/TTS, a multi-provider LLM fallback chain, 29 specialized agents, Telegram remote control, and gated file access — see AI Core and Agents for live status.' },
    { title: 'Backend source', body: 'nancy-billion/backend/main_new.py is the FastAPI entrypoint; llm.py holds the reasoning fallback chain; agents/specialized/ holds the real agent roster.' },
    { title: 'Frontend source', body: 'nancy-billion/frontend/app/page.tsx is the shell; components/nancy/ holds every panel in this sidebar.' },
    { title: 'No hosted docs site', body: "This is a personal single-user build with no public documentation site — this page just points at the real files instead of linking somewhere that may not exist." },
  ]
  return (
    <div className="mx-auto grid max-w-[1680px] grid-cols-12 gap-4">
      {entries.map((e) => (
        <HudPanel key={e.title} title={e.title} className="col-span-12 md:col-span-6" right={<BookOpen className="h-3.5 w-3.5 text-primary" />}>
          <p className="text-[0.6rem] leading-relaxed text-muted-foreground">{e.body}</p>
        </HudPanel>
      ))}
    </div>
  )
}
