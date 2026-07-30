'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'
import {
  useSystemHealth, useLlmStatus, useSystemAlerts, useCronStatus, useTelegramStatus, useTradeHistory,
} from '@/hooks/useSystemData'
import { listAgents } from '@/lib/nancy/agent-client'
import {
  useAchievementsBrief, useSafetyBrief, useCpuCoreCount, formatRelative,
} from '@/components/nancy/panels'
import type { AgentInfo, PanelKey } from '@/lib/nancy/types'
import {
  Activity, AlertTriangle, Award, Bot, Brain, BrainCircuit, CheckCircle2, ChevronRight,
  Cloud, CloudOff, Cpu, ExternalLink, FileClock, HardDrive, KeyRound, Loader2, LogOut,
  MemoryStick, Radio, Send, ShieldCheck, TrendingUp, Zap,
} from 'lucide-react'

/* ═══════════════════════════════════════════════════════════════════════
   OVERVIEW V2 — "reactor room". A real-data command overview: the arc
   reactor centerpiece breathes with actual CPU load, every tile is a real
   metric (psutil health, live agent fleet, real LLM chain), and the
   Ollama Cloud card is a real connect/disconnect flow against the
   backend. Visual language: the app's own theme tokens (--primary /
   --gold / --card), text always in text tokens, color only on marks —
   no fabricated numbers anywhere.
   ═══════════════════════════════════════════════════════════════════════ */

const ACCENT = 'var(--primary)'
const ACCENT2 = 'var(--gold)'
const GLASS = 'color-mix(in oklch, var(--card) 72%, transparent)'
const BORDER = 'color-mix(in oklch, var(--primary) 18%, transparent)'
const GLOW = 'color-mix(in oklch, var(--primary) 30%, transparent)'

const entry = {
  hidden: { opacity: 0, y: 14 },
  show: (i: number) => ({ opacity: 1, y: 0, transition: { delay: 0.06 * i, duration: 0.45, ease: 'easeOut' as const } }),
}

/* ── Real CPU history collected client-side (one sample per health poll) ── */
function useCpuHistory(cpu: number | null, max = 40) {
  const [history, setHistory] = useState<number[]>([])
  useEffect(() => {
    if (cpu == null) return
    setHistory((h) => [...h, cpu].slice(-max))
  }, [cpu, max])
  return history
}

function useAgentsBrief(intervalMs = 20000) {
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [stats, setStats] = useState<{ agents_online: number; total_tasks: number; failed_tasks: number; success_rate: number } | null>(null)
  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const res = await listAgents()
        if (!cancelled && res.success) {
          setAgents(res.agents)
          setStats(res.stats as typeof stats)
        }
      } catch { /* next poll retries */ }
    }
    load()
    const t = setInterval(load, intervalMs)
    return () => { cancelled = true; clearInterval(t) }
  }, [intervalMs])
  return { agents, stats }
}

/* ── Real recent activity: evidence ledger + memory journey, merged ── */
interface ActivityRow { id: string; tag: string; text: string; tone: 'ok' | 'warn'; at: number }
function useRecentActivity(intervalMs = 20000) {
  const [rows, setRows] = useState<ActivityRow[]>([])
  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const [ev, jr] = await Promise.all([
          fetch('/api/evidence?limit=8').then((r) => r.json()).catch(() => null),
          fetch('/api/memory/journey?limit=6').then((r) => r.json()).catch(() => null),
        ])
        if (cancelled) return
        const merged: ActivityRow[] = []
        if (ev?.success) {
          for (const e of ev.evidence) {
            merged.push({
              id: `ev-${e.id}`, tag: e.kind, tone: e.success ? 'ok' : 'warn',
              text: (e.kind === 'write_file' ? `wrote ${e.action}` : e.kind === 'terminal_command' ? `ran: ${e.action}` : `${e.kind}: ${e.action}`).slice(0, 76),
              at: e.timestamp * 1000,
            })
          }
        }
        if (jr?.success) for (const j of jr.timeline) merged.push({ id: `jr-${j.timestamp}`, tag: j.kind, tone: 'ok', text: j.label, at: j.timestamp * 1000 })
        merged.sort((a, b) => b.at - a.at)
        setRows(merged.slice(0, 9))
      } catch { /* keep previous rows */ }
    }
    load()
    const t = setInterval(load, intervalMs)
    return () => { cancelled = true; clearInterval(t) }
  }, [intervalMs])
  return rows
}

/* ═════════════════════════ ARC REACTOR ═════════════════════════
   Concentric SVG rings around a pulsing core. Everything animated is
   driven by a REAL signal: segment ring lights up with CPU load, the
   core pulse quickens as load rises, and the hero number is the live
   psutil reading (a stat tile at the reactor's heart). */
function ArcReactor({ cpu, agentsOnline }: { cpu: number | null; agentsOnline: number | null }) {
  const load = cpu ?? 0
  const SEGMENTS = 24
  const lit = Math.round((load / 100) * SEGMENTS)
  // Higher load -> faster, tighter pulse. Idle -> slow calm breathing.
  const pulseDur = Math.max(0.9, 3.2 - (load / 100) * 2.1)
  const R = 150

  const segs = useMemo(() => Array.from({ length: SEGMENTS }, (_, i) => {
    const a0 = (i / SEGMENTS) * Math.PI * 2 - Math.PI / 2 + 0.02
    const a1 = ((i + 1) / SEGMENTS) * Math.PI * 2 - Math.PI / 2 - 0.02
    const r0 = 108, r1 = 124
    const p = (a: number, r: number) => `${R + r * Math.cos(a)},${R + r * Math.sin(a)}`
    return `M${p(a0, r0)} L${p(a0, r1)} A${r1},${r1} 0 0 1 ${p(a1, r1)} L${p(a1, r0)} A${r0},${r0} 0 0 0 ${p(a0, r0)} Z`
  }), [])

  return (
    <div className="relative mx-auto h-[300px] w-[300px] select-none">
      <svg viewBox="0 0 300 300" className="absolute inset-0 h-full w-full" role="img" aria-label={`Reactor: neural load ${Math.round(load)} percent`}>
        <defs>
          <radialGradient id="rx-core" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor={ACCENT} stopOpacity="0.9" />
            <stop offset="55%" stopColor={ACCENT} stopOpacity="0.25" />
            <stop offset="100%" stopColor={ACCENT} stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* outer fine ring, slow clockwise drift */}
        <motion.g animate={{ rotate: 360 }} transition={{ duration: 60, repeat: Infinity, ease: 'linear' }} style={{ originX: '150px', originY: '150px' }}>
          <circle cx="150" cy="150" r="146" fill="none" stroke={BORDER} strokeWidth="1" strokeDasharray="2 6" />
          <circle cx="150" cy="150" r="138" fill="none" stroke={GLOW} strokeWidth="1" strokeDasharray="30 14 6 14" />
        </motion.g>

        {/* segment ring -- lit segments = real CPU load */}
        <g>
          {segs.map((d, i) => (
            <path key={i} d={d} fill={i < lit ? ACCENT : 'transparent'} fillOpacity={i < lit ? 0.85 : 1}
              stroke={i < lit ? ACCENT : BORDER} strokeWidth="1" />
          ))}
        </g>

        {/* inner counter-rotating tick ring */}
        <motion.g animate={{ rotate: -360 }} transition={{ duration: 40, repeat: Infinity, ease: 'linear' }} style={{ originX: '150px', originY: '150px' }}>
          <circle cx="150" cy="150" r="96" fill="none" stroke={BORDER} strokeWidth="1" strokeDasharray="1 5" />
          {Array.from({ length: 3 }, (_, i) => {
            const a = (i / 3) * Math.PI * 2
            return <circle key={i} cx={150 + 96 * Math.cos(a)} cy={150 + 96 * Math.sin(a)} r="2.5" fill={ACCENT2} />
          })}
        </motion.g>

        {/* pulsing core glow -- pulse speed follows real load */}
        <motion.circle cx="150" cy="150" r="84" fill="url(#rx-core)"
          animate={{ opacity: [0.55, 1, 0.55], scale: [0.96, 1.03, 0.96] }}
          transition={{ duration: pulseDur, repeat: Infinity, ease: 'easeInOut' }}
          style={{ originX: '150px', originY: '150px' }} />
        <circle cx="150" cy="150" r="70" fill="none" stroke={GLOW} strokeWidth="1.5" />
      </svg>

      {/* hero stat at the core -- real psutil value, text tokens only */}
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        <span className="text-[0.6rem] uppercase tracking-[2.5px] text-muted-foreground">Neural load</span>
        <span className="font-mono text-[2.6rem] font-semibold leading-none text-foreground tabular-nums">
          {cpu == null ? '—' : Math.round(load)}
          <span className="text-[1.1rem] text-muted-foreground">%</span>
        </span>
        <span className="mt-1 flex items-center gap-1 text-[0.6rem] text-muted-foreground">
          <Bot className="h-3 w-3" style={{ color: ACCENT }} />
          {agentsOnline == null ? '—' : agentsOnline} agents online
        </span>
      </div>
    </div>
  )
}

/* ═════════════════════════ STAT TILE ═════════════════════════ */
function StatTile({ i, icon: Icon, label, value, unit, sub, warn }: {
  i: number; icon: typeof Cpu; label: string; value: string; unit?: string; sub?: string; warn?: boolean
}) {
  return (
    <motion.div variants={entry} custom={i} initial="hidden" animate="show"
      className="flex flex-col gap-1 rounded-2xl p-4"
      style={{ background: GLASS, border: `1px solid ${warn ? 'color-mix(in oklch, var(--destructive) 45%, transparent)' : BORDER}`, backdropFilter: 'blur(18px)' }}>
      <div className="flex items-center gap-1.5 text-[0.6rem] uppercase tracking-[1.5px] text-muted-foreground">
        <Icon className="h-3.5 w-3.5" style={{ color: warn ? 'var(--destructive)' : ACCENT }} />
        {label}
        {warn && <AlertTriangle className="h-3 w-3 text-destructive" aria-label="warning" />}
      </div>
      <div className="font-mono text-2xl font-semibold text-foreground tabular-nums">
        {value}{unit && <span className="ml-0.5 text-sm text-muted-foreground">{unit}</span>}
      </div>
      {sub && <div className="text-[0.62rem] text-muted-foreground">{sub}</div>}
    </motion.div>
  )
}

/* ═════════════════════ NAV TILE ═════════════════════
   The reactor room's status-card grammar: one real subsystem per tile,
   summary and navigation in the same place. Restores the subsystem
   coverage the old OverviewPanel's StatusCard grid had (Automations,
   Safety, Channels, Memory, Achievements, Trading, System) that the V2
   redesign otherwise dropped, in the new visual language. */
function NavTile({ i, icon: Icon, label, value, sub, warn, onClick, children }: {
  i: number; icon: typeof Cpu; label: string; value: string; sub?: string; warn?: boolean
  onClick?: () => void; children?: React.ReactNode
}) {
  return (
    <motion.button type="button" onClick={onClick} disabled={!onClick} variants={entry} custom={i} initial="hidden" animate="show"
      className={cn('group flex flex-col gap-1.5 rounded-2xl p-4 text-left transition-colors', onClick ? 'cursor-pointer' : 'cursor-default')}
      style={{ background: GLASS, border: `1px solid ${warn ? 'color-mix(in oklch, var(--destructive) 45%, transparent)' : BORDER}`, backdropFilter: 'blur(18px)' }}>
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-[0.6rem] uppercase tracking-[1.5px] text-muted-foreground">
          <Icon className="h-3.5 w-3.5" style={{ color: warn ? 'var(--destructive)' : ACCENT }} /> {label}
        </span>
        {warn && <AlertTriangle className="h-3 w-3 shrink-0 text-destructive" aria-label="warning" />}
      </div>
      <div className="truncate font-mono text-base font-semibold text-foreground">{value}</div>
      {sub && <div className="truncate text-[0.6rem] text-muted-foreground">{sub}</div>}
      {children}
      {onClick && (
        <span className="mt-0.5 flex items-center gap-1 text-[0.55rem] opacity-0 transition-opacity group-hover:opacity-100" style={{ color: ACCENT }}>
          View <ChevronRight className="h-2.5 w-2.5" />
        </span>
      )}
    </motion.button>
  )
}

/* ═════════════════════ CPU SPARKLINE (single series) ═════════════════════
   One series, 2px line, quiet grid, hover tooltip on nearest sample --
   the title names the series, so no legend box. */
function CpuSparkline({ history }: { history: number[] }) {
  const W = 560, H = 96, PAD = 6
  const [hover, setHover] = useState<number | null>(null)
  const pts = useMemo(() => history.map((v, i) => ({
    x: PAD + (i / Math.max(history.length - 1, 1)) * (W - PAD * 2),
    y: H - PAD - (Math.min(v, 100) / 100) * (H - PAD * 2),
    v,
  })), [history])
  const path = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  const area = pts.length > 1 ? `${path} L${pts[pts.length - 1].x},${H - PAD} L${pts[0].x},${H - PAD} Z` : ''
  const last = pts[pts.length - 1]

  const onMove = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if (!pts.length) return
    const rect = e.currentTarget.getBoundingClientRect()
    const x = ((e.clientX - rect.left) / rect.width) * W
    let best = 0
    for (let i = 1; i < pts.length; i++) if (Math.abs(pts[i].x - x) < Math.abs(pts[best].x - x)) best = i
    setHover(best)
  }, [pts])

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-24 w-full" role="img" aria-label="Neural load, recent samples"
        onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        {[25, 50, 75].map((g) => (
          <line key={g} x1={PAD} x2={W - PAD} y1={H - PAD - (g / 100) * (H - PAD * 2)} y2={H - PAD - (g / 100) * (H - PAD * 2)}
            stroke={BORDER} strokeWidth="0.5" />
        ))}
        {area && <path d={area} fill={ACCENT} fillOpacity="0.08" />}
        {pts.length > 1 && <path d={path} fill="none" stroke={ACCENT} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />}
        {last && <circle cx={last.x} cy={last.y} r="3" fill={ACCENT} stroke="var(--background)" strokeWidth="2" />}
        {hover != null && pts[hover] && (
          <g>
            <line x1={pts[hover].x} x2={pts[hover].x} y1={PAD} y2={H - PAD} stroke={GLOW} strokeWidth="1" />
            <circle cx={pts[hover].x} cy={pts[hover].y} r="4" fill={ACCENT} stroke="var(--background)" strokeWidth="2" />
          </g>
        )}
      </svg>
      {hover != null && pts[hover] && (
        <div className="pointer-events-none absolute -top-1 rounded-md px-2 py-1 font-mono text-[0.62rem] text-foreground"
          style={{ left: `${(pts[hover].x / W) * 100}%`, transform: 'translateX(-50%)', background: 'var(--card)', border: `1px solid ${BORDER}` }}>
          {Math.round(pts[hover].v)}%
        </div>
      )}
      {/* selective direct label on the latest sample only */}
      {last && <span className="absolute bottom-0 right-1 font-mono text-[0.62rem] text-muted-foreground">now {Math.round(last.v)}%</span>}
    </div>
  )
}

/* ═════════════════════ LLM CHAIN STRIP ═════════════════════ */
function ChainStrip({ backends }: { backends: { name: string; model?: string }[] }) {
  if (!backends.length) return <p className="text-[0.65rem] text-muted-foreground">No backends reported yet.</p>
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {backends.map((b, i) => (
        <div key={`${b.name}-${i}`} className="flex items-center gap-1.5">
          <span className="flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[0.62rem] text-foreground"
            style={{ background: i === 0 ? GLOW : GLASS, border: `1px solid ${i === 0 ? ACCENT : BORDER}` }}
            title={b.model ? `${b.name} · ${b.model}` : b.name}>
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: i === 0 ? ACCENT : 'var(--muted-foreground)' }} />
            {b.name}
            {i === 0 && <span className="text-[0.55rem] uppercase tracking-wide text-muted-foreground">primary</span>}
          </span>
          {i < backends.length - 1 && <ChevronRight className="h-3 w-3 text-muted-foreground" aria-hidden />}
        </div>
      ))}
    </div>
  )
}

/* ═════════════════════ OLLAMA CLOUD CONNECT CARD ═════════════════════
   Real connect flow: "Get API key" opens ollama.com's key page, the pasted
   key is validated LIVE by the backend (against ollama.com) before being
   saved to .env and hot-loaded into the fallback chain. Disconnect removes
   it everywhere, instantly. */
interface OllamaCloudStatus { connected: boolean; key_masked: string | null; model: string; in_chain: boolean; connect_url: string }
function OllamaCloudCard({ i }: { i: number }) {
  const [status, setStatus] = useState<OllamaCloudStatus | null>(null)
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  const refresh = useCallback(async () => {
    try {
      const res = await fetch('/api/ollama-cloud/status', { cache: 'no-store' })
      const json = await res.json()
      if (json.success) setStatus(json)
    } catch { /* card shows loading state */ }
  }, [])
  useEffect(() => { refresh() }, [refresh])

  const connect = useCallback(async () => {
    if (!key.trim()) return
    setBusy(true); setMsg(null)
    try {
      const res = await fetch('/api/ollama-cloud/connect', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ api_key: key.trim() }),
      })
      const json = await res.json()
      if (res.ok && json.success) {
        setMsg({ ok: true, text: 'Connected — live in the fallback chain, no restart needed.' })
        setKey('')
      } else {
        setMsg({ ok: false, text: json.detail || json.error || 'Connection failed' })
      }
    } catch {
      setMsg({ ok: false, text: 'Backend unreachable' })
    } finally {
      setBusy(false); refresh()
    }
  }, [key, refresh])

  const disconnect = useCallback(async () => {
    setBusy(true); setMsg(null)
    try {
      const res = await fetch('/api/ollama-cloud/disconnect', { method: 'POST' })
      const json = await res.json()
      setMsg(res.ok && json.success
        ? { ok: true, text: 'Disconnected — key removed from .env and the live chain.' }
        : { ok: false, text: json.detail || json.error || 'Disconnect failed' })
    } catch {
      setMsg({ ok: false, text: 'Backend unreachable' })
    } finally {
      setBusy(false); refresh()
    }
  }, [refresh])

  const connected = status?.connected ?? false
  return (
    <motion.div variants={entry} custom={i} initial="hidden" animate="show"
      className="flex flex-col gap-3 rounded-2xl p-4"
      style={{ background: GLASS, border: `1px solid ${connected ? 'color-mix(in oklch, var(--primary) 45%, transparent)' : BORDER}`, backdropFilter: 'blur(18px)' }}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-[0.6rem] uppercase tracking-[1.5px] text-muted-foreground">
          {connected ? <Cloud className="h-3.5 w-3.5" style={{ color: ACCENT }} /> : <CloudOff className="h-3.5 w-3.5 text-muted-foreground" />}
          Ollama Cloud
        </div>
        {status == null ? (
          <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
        ) : connected ? (
          <span className="flex items-center gap-1 text-[0.6rem] text-foreground"><CheckCircle2 className="h-3 w-3" style={{ color: ACCENT }} /> Connected</span>
        ) : (
          <span className="text-[0.6rem] text-muted-foreground">Not connected</span>
        )}
      </div>

      {connected ? (
        <>
          <div className="flex flex-col gap-1 text-[0.65rem] text-muted-foreground">
            <span>Key <span className="font-mono text-foreground">{status?.key_masked ?? '…'}</span></span>
            <span>Model <span className="font-mono text-foreground">{status?.model}</span></span>
            <span>{status?.in_chain ? 'Active in the LLM fallback chain (after cloud tier, before local Ollama).' : 'Saved — joins the chain on next rebuild.'}</span>
          </div>
          <button type="button" onClick={disconnect} disabled={busy}
            className="flex w-fit items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-[0.65rem] text-foreground transition-colors hover:border-destructive/60 disabled:opacity-40">
            {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <LogOut className="h-3 w-3" />} Disconnect
          </button>
        </>
      ) : (
        <>
          <p className="text-[0.65rem] leading-relaxed text-muted-foreground">
            Run large open models (gpt-oss 120B, deepseek-v3.1 671B…) on Ollama&apos;s GPUs — slots in before local Ollama as a cloud fallback.
          </p>
          <a href={status?.connect_url ?? 'https://ollama.com/settings/keys'} target="_blank" rel="noreferrer"
            className="flex w-fit items-center gap-1.5 rounded-lg px-3 py-1.5 text-[0.65rem] transition-opacity hover:opacity-85"
            style={{ background: GLOW, border: `1px solid ${ACCENT}`, color: 'var(--foreground)' }}>
            <KeyRound className="h-3 w-3" style={{ color: ACCENT }} /> Get API key <ExternalLink className="h-2.5 w-2.5" />
          </a>
          <div className="flex gap-1.5">
            <input value={key} onChange={(e) => setKey(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && connect()}
              placeholder="Paste API key…" type="password" autoComplete="off"
              className="min-w-0 flex-1 rounded-lg bg-transparent px-2.5 py-1.5 font-mono text-[0.65rem] text-foreground outline-none placeholder:text-muted-foreground"
              style={{ border: `1px solid ${BORDER}` }} />
            <button type="button" onClick={connect} disabled={busy || !key.trim()}
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[0.65rem] text-foreground transition-opacity hover:opacity-85 disabled:opacity-40"
              style={{ background: GLOW, border: `1px solid ${ACCENT}` }}>
              {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Zap className="h-3 w-3" style={{ color: ACCENT }} />} Connect
            </button>
          </div>
        </>
      )}
      {msg && (
        <p className={cn('flex items-center gap-1 text-[0.62rem]', msg.ok ? 'text-foreground' : 'text-destructive')}>
          {msg.ok ? <CheckCircle2 className="h-3 w-3" style={{ color: ACCENT }} /> : <AlertTriangle className="h-3 w-3" />} {msg.text}
        </p>
      )}
    </motion.div>
  )
}

/* ═════════════════════════ MAIN PANEL ═════════════════════════ */
export function OverviewV2Panel({ onNavigate }: { onNavigate?: (k: PanelKey) => void }) {
  const health = useSystemHealth()
  const llm = useLlmStatus()
  const alerts = useSystemAlerts()
  const { stats } = useAgentsBrief()
  const cpuHistory = useCpuHistory(health.cpu)
  const activity = useRecentActivity()
  const achievements = useAchievementsBrief()
  const { armed, proxyRunning } = useSafetyBrief()
  const { data: cronData } = useCronStatus()
  const { data: telegramData } = useTelegramStatus()
  const { data: trades } = useTradeHistory(10)
  const cores = useCpuCoreCount()

  const severity = (alerts as { overall_severity?: string } | null)?.overall_severity ?? 'green'
  const successRate = stats ? Math.round((stats.success_rate ?? 0) * 100) : null

  // Real, named reasons behind a non-green severity badge -- each backed by
  // an actual signal, never a fabricated "critical" level with nothing to
  // point at.
  const reasons: string[] = []
  if (armed) reasons.push('Arm switch is armed — approvals are being bypassed')
  if (stats && stats.failed_tasks > 0) reasons.push(`${stats.failed_tasks} failed task${stats.failed_tasks === 1 ? '' : 's'} recorded`)
  if (!llm.loading && !llm.data) reasons.push('LLM reasoning chain unavailable')

  const cronJob = cronData?.jobs?.[0]
  const closedTrades = (trades ?? []).filter((t: { profit_loss?: number }) => typeof t.profit_loss === 'number')
  const latestTrade = closedTrades[closedTrades.length - 1] as { profit_loss: number } | undefined
  const achievementsPct = achievements ? (achievements.unlocked / Math.max(1, achievements.total)) * 100 : 0

  return (
    <div className="relative mx-auto flex max-w-[1500px] flex-col gap-5">
      {/* ambient grid backdrop */}
      <div aria-hidden className="pointer-events-none absolute inset-0 opacity-[0.35]"
        style={{ backgroundImage: `linear-gradient(${BORDER} 1px, transparent 1px), linear-gradient(90deg, ${BORDER} 1px, transparent 1px)`, backgroundSize: '44px 44px', maskImage: 'radial-gradient(ellipse 70% 55% at 50% 32%, black, transparent)' }} />

      {/* header */}
      <motion.div variants={entry} custom={0} initial="hidden" animate="show" className="relative flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[0.62rem] uppercase tracking-[2.5px] text-muted-foreground">Sovereign systems</div>
          <h1 className="font-heading text-xl text-foreground">Command Overview</h1>
        </div>
        <div className="flex items-center gap-2 rounded-full px-3 py-1.5 text-[0.62rem] text-foreground" style={{ background: GLASS, border: `1px solid ${BORDER}` }}>
          {severity === 'green'
            ? <CheckCircle2 className="h-3.5 w-3.5" style={{ color: ACCENT }} />
            : <AlertTriangle className="h-3.5 w-3.5" style={{ color: severity === 'yellow' ? ACCENT2 : 'var(--destructive)' }} />}
          {severity === 'green' ? 'All systems nominal' : severity === 'yellow' ? 'Degraded — check alerts' : 'Attention required'}
        </div>
      </motion.div>

      {reasons.length > 0 && (
        <motion.ul variants={entry} custom={0.5} initial="hidden" animate="show"
          className="relative flex flex-wrap gap-x-4 gap-y-1 text-[0.62rem]" style={{ color: ACCENT2 }}>
          {reasons.map((r) => (
            <li key={r} className="flex items-center gap-1.5">
              <AlertTriangle className="h-3 w-3 shrink-0" /> {r}
            </li>
          ))}
        </motion.ul>
      )}

      {/* reactor + tiles */}
      <div className="relative grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <motion.div variants={entry} custom={1} initial="hidden" animate="show"
          className="flex items-center justify-center rounded-2xl p-6"
          style={{ background: GLASS, border: `1px solid ${BORDER}`, backdropFilter: 'blur(18px)', boxShadow: `0 0 60px ${GLOW} inset` }}>
          <ArcReactor cpu={health.cpu} agentsOnline={stats?.agents_online ?? null} />
        </motion.div>

        <div className="grid grid-cols-2 gap-4">
          <StatTile i={2} icon={MemoryStick} label="Memory" value={health.memory == null ? '—' : String(Math.round(health.memory))} unit="%" sub="system RAM in use" warn={(health.memory ?? 0) > 90} />
          <StatTile i={3} icon={HardDrive} label="Disk" value={health.disk == null ? '—' : String(Math.round(health.disk))} unit="%" sub="primary volume" warn={(health.disk ?? 0) > 90} />
          <StatTile i={4} icon={Bot} label="Fleet" value={stats ? String(stats.agents_online) : '—'} sub={stats ? `${stats.total_tasks} tasks · ${successRate}% success` : 'contacting fleet…'} />
          <OllamaCloudCard i={5} />
        </div>
      </div>

      {/* systems: one real subsystem per tile, same status-card grammar the
          old dashboard used, restored here in the reactor-room style. */}
      <div className="relative grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-4">
        <NavTile i={9} icon={FileClock} label="Automations"
          value={cronJob ? cronJob.name : 'None scheduled'}
          sub={cronJob ? `Next run ${formatRelative(cronJob.next_run)} · ${cronData?.jobs?.length ?? 0} job${(cronData?.jobs?.length ?? 0) === 1 ? '' : 's'}` : undefined}
          onClick={() => onNavigate?.('cron' as PanelKey)} />
        <NavTile i={10} icon={ShieldCheck} label="Safety"
          value={armed == null ? '…' : armed ? 'Armed' : 'Disarmed'}
          sub={proxyRunning == null ? undefined : `Egress proxy ${proxyRunning ? 'running' : 'stopped'}`}
          warn={armed === true} />
        <NavTile i={11} icon={Send} label="Channels"
          value={telegramData?.available ? 'Telegram connected' : 'Telegram not configured'}
          sub={telegramData?.polling ? 'Polling for commands' : undefined}
          onClick={() => onNavigate?.('channels' as PanelKey)} />
        <NavTile i={12} icon={Brain} label="Memory & Growth"
          value={achievements?.activity ? `${achievements.activity.total_memories} memories` : '…'}
          sub={achievements?.activity ? `${achievements.activity.distinct_skills_used}/${achievements.activity.total_skills} skills used · ${achievements.activity.terminal_commands} commands run` : undefined}
          onClick={() => onNavigate?.('memory-insights' as PanelKey)} />
        <NavTile i={13} icon={Award} label="Achievements"
          value={achievements ? `${achievements.unlocked}/${achievements.total} unlocked` : '…'}
          onClick={() => onNavigate?.('achievements' as PanelKey)}>
          <div className="mt-1 h-1.5 overflow-hidden rounded-full" style={{ background: BORDER }}>
            <div className="h-full rounded-full transition-all duration-700" style={{ width: `${achievementsPct}%`, background: ACCENT2 }} />
          </div>
        </NavTile>
        <NavTile i={14} icon={TrendingUp} label="Trading"
          value={!trades?.length && closedTrades.length === 0 ? '…' : !latestTrade ? 'No closed trades' : `${latestTrade.profit_loss >= 0 ? '+' : ''}${Number(latestTrade.profit_loss).toFixed(1)} pips latest`}
          sub={closedTrades.length > 0 ? `${closedTrades.length} recent trade${closedTrades.length === 1 ? '' : 's'}` : undefined}
          onClick={() => onNavigate?.('market' as PanelKey)} />
        <NavTile i={15} icon={Cpu} label="System"
          value={`${health.cpu == null ? '—' : Math.round(health.cpu)}% CPU`}
          sub={`${health.memory == null ? '—' : Math.round(health.memory)}% mem · ${health.disk == null ? '—' : Math.round(health.disk)}% disk${health.tempC != null ? ` · ${Math.round(health.tempC)}°C` : ''}${cores != null ? ` · ${cores} cores` : ''}`}
          onClick={() => onNavigate?.('system' as PanelKey)} />
      </div>

      {/* load history + LLM chain */}
      <div className="relative grid gap-5 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <motion.div variants={entry} custom={6} initial="hidden" animate="show" className="rounded-2xl p-4" style={{ background: GLASS, border: `1px solid ${BORDER}`, backdropFilter: 'blur(18px)' }}>
          <div className="mb-2 flex items-center gap-1.5 text-[0.6rem] uppercase tracking-[1.5px] text-muted-foreground">
            <Activity className="h-3.5 w-3.5" style={{ color: ACCENT }} /> Neural load — live history
          </div>
          {cpuHistory.length > 1
            ? <CpuSparkline history={cpuHistory} />
            : <p className="py-8 text-center text-[0.65rem] text-muted-foreground">Collecting samples…</p>}
        </motion.div>

        <motion.div variants={entry} custom={7} initial="hidden" animate="show" className="rounded-2xl p-4" style={{ background: GLASS, border: `1px solid ${BORDER}`, backdropFilter: 'blur(18px)' }}>
          <div className="mb-2.5 flex items-center gap-1.5 text-[0.6rem] uppercase tracking-[1.5px] text-muted-foreground">
            <BrainCircuit className="h-3.5 w-3.5" style={{ color: ACCENT }} /> LLM fallback chain
          </div>
          <ChainStrip backends={llm.data?.backends ?? []} />
          <button type="button" onClick={() => onNavigate?.('models' as PanelKey)}
            className="mt-3 text-[0.62rem] text-muted-foreground underline-offset-2 transition-colors hover:text-foreground hover:underline">
            Manage models →
          </button>
        </motion.div>
      </div>

      {/* live activity */}
      <motion.div variants={entry} custom={8} initial="hidden" animate="show" className="relative rounded-2xl p-4" style={{ background: GLASS, border: `1px solid ${BORDER}`, backdropFilter: 'blur(18px)' }}>
        <div className="mb-2.5 flex items-center gap-1.5 text-[0.6rem] uppercase tracking-[1.5px] text-muted-foreground">
          <Radio className="h-3.5 w-3.5" style={{ color: ACCENT }} /> Live activity
        </div>
        {activity.length === 0 ? (
          <p className="py-4 text-center text-[0.65rem] text-muted-foreground">No recorded activity yet — it appears here as Billion actually does things.</p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {activity.map((row) => (
              <li key={row.id} className="flex items-center gap-2 text-[0.68rem]">
                <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: row.tone === 'ok' ? ACCENT : 'var(--destructive)' }} aria-hidden />
                <span className="shrink-0 rounded px-1.5 py-0.5 font-mono text-[0.55rem] uppercase text-muted-foreground" style={{ border: `1px solid ${BORDER}` }}>{row.tag}</span>
                <span className="truncate text-foreground">{row.text}</span>
                <span className="ml-auto shrink-0 font-mono text-[0.58rem] text-muted-foreground">{new Date(row.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
              </li>
            ))}
          </ul>
        )}
      </motion.div>
    </div>
  )
}
