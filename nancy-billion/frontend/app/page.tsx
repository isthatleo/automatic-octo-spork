'use client'

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { BootSequence } from '@/components/nancy/boot-sequence'
import { MapPanel } from '@/components/nancy/map-panel'
import { KnowledgePanel } from '@/components/nancy/knowledge-panel'
import {
  AgentsPanel,
  CorePanel,
  OverviewPanel,
  SystemPanel,
} from '@/components/nancy/panels'
import { ConsoleBar } from '@/components/nancy/console-bar'
import { NancyOrb, type OrbState } from '@/components/nancy/nancy-orb'
import { LyricsTranscript } from '@/components/nancy/lyrics-transcript'
import { KanbanPanel } from '@/components/nancy/kanban-panel'
import {
  SessionsPanel, ChannelsPanel, InstancesPanel, CronPanel, SkillsPanel, ModelsPanel,
  KeysPanel, ConfigPanel, UsagePanel, PairingPanel, ProfilesPanel, PluginsPanel,
  McpPanel, WebhooksPanel, DocsPanel,
} from '@/components/nancy/admin-panels'
import { useVoice, speak, cancelSpeech } from '@/lib/nancy/use-voice'
import { parseCommand } from '@/lib/nancy/commands'
import { askNancy } from '@/lib/nancy/ws-client'
import { synthesizeSpeech } from '@/lib/nancy/tts-client'
import { geocode } from '@/lib/nancy/geocode'
import type { KnowledgeCategory, LogEntry, PanelKey, Place } from '@/lib/nancy/types'
import { cn } from '@/lib/utils'
import { sfx, unlockSfx, duckSfx } from '@/lib/nancy/sfx'

import {
  Brain, Bot, Globe2, LayoutDashboard, TerminalSquare, Newspaper, Kanban, X, Mic, MicOff,
  Keyboard, ChevronDown, MessageSquare, PanelLeftClose, PanelLeftOpen, Send, Server, Clock3,
  FileClock, Sparkles, Cpu, Key, Settings2, BarChart3, Link2, User, PlugZap, Wrench, Webhook, BookOpen,
} from 'lucide-react'

/** Grouped exactly like OpenClaw/Hermes's sidebar (Control/Agent/Settings/
 * Resources), mapped onto Nancy's real pages -- a top-level "Voice" entry
 * stands in for their "Chat" group. */
const NAV_GROUPS: { group: string; items: { key: PanelKey; label: string; icon: typeof Brain }[] }[] = [
  { group: 'Control', items: [
    { key: 'overview', label: 'Overview', icon: LayoutDashboard },
    { key: 'map', label: 'Recon', icon: Globe2 },
    { key: 'news', label: 'Newsfeed', icon: Newspaper },
    { key: 'channels', label: 'Channels', icon: Send },
    { key: 'instances', label: 'Instances', icon: Server },
    { key: 'sessions', label: 'Sessions', icon: Clock3 },
    { key: 'cron', label: 'Cron Jobs', icon: FileClock },
  ] },
  { group: 'Agent', items: [
    { key: 'core', label: 'AI Core', icon: Brain },
    { key: 'agents', label: 'Agents', icon: Bot },
    { key: 'kanban', label: 'Kanban', icon: Kanban },
    { key: 'skills', label: 'Skills', icon: Sparkles },
    { key: 'models', label: 'Models', icon: Cpu },
  ] },
  { group: 'Settings', items: [
    { key: 'system', label: 'Command Layer', icon: TerminalSquare },
    { key: 'config', label: 'Config', icon: Settings2 },
    { key: 'keys', label: 'Keys', icon: Key },
    { key: 'usage', label: 'Usage', icon: BarChart3 },
    { key: 'profiles', label: 'Profiles', icon: User },
    { key: 'pairing', label: 'Pairing', icon: Link2 },
    { key: 'plugins', label: 'Plugins', icon: PlugZap },
    { key: 'mcp', label: 'MCP', icon: Wrench },
    { key: 'webhooks', label: 'Webhooks', icon: Webhook },
  ] },
  { group: 'Resources', items: [
    { key: 'docs', label: 'Docs', icon: BookOpen },
  ] },
]
// Orb quick-nav stays compact -- only the highest-traffic pages, not all 20.
const ORB_QUICK_NAV: { key: PanelKey; label: string; icon: typeof Brain }[] = [
  { key: 'overview', label: 'Overview', icon: LayoutDashboard },
  { key: 'core', label: 'AI Core', icon: Brain },
  { key: 'agents', label: 'Agents', icon: Bot },
  { key: 'kanban', label: 'Kanban', icon: Kanban },
  { key: 'map', label: 'Recon', icon: Globe2 },
  { key: 'news', label: 'Newsfeed', icon: Newspaper },
]

let logSeq = 0

export default function Page() {
  const [booting, setBooting] = useState(true)
  // `null` = voice-first hero mode (no panel visible). Anything else opens the workspace.
  const [panel, setPanel] = useState<PanelKey | null>(null)
  const [place, setPlace] = useState<Place | null>(null)
  const [mapLoading, setMapLoading] = useState(false)
  const [launched, setLaunched] = useState<string | null>(null)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [clock, setClock] = useState('')
  const [speaking, setSpeaking] = useState(false)
  const [thinking, setThinking] = useState(false)
  const [currentUtterance, setCurrentUtterance] = useState('')
  const [wordIndex, setWordIndex] = useState(-1)
  // Voice is the primary interaction; the full terminal (scrollback + typed
  // input) is hidden until explicitly summoned, so voice-first actually
  // means voice-first instead of a permanent command bar under everything.
  const [consoleOpen, setConsoleOpen] = useState(false)
  const launchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const currentAudioRef = useRef<HTMLAudioElement | null>(null)
  const wordTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  // News/briefing panel state, set by voice commands ("Nancy, news on
  // Nvidia") and read by KnowledgePanel (see WorkspaceLayout below).
  const [newsCategory, setNewsCategory] = useState<KnowledgeCategory | null>(null)
  const [newsTopic, setNewsTopic] = useState<string | null>(null)
  const [newsMedia, setNewsMedia] = useState<'articles' | 'videos'>('articles')
  const [newsAutoOpenTop, setNewsAutoOpenTop] = useState(false)
  const [newsRequestId, setNewsRequestId] = useState(0)
  // Mirrors currentAudioRef as state (not just a ref) so NancyOrb re-renders
  // with the live <audio> element and can analyze its real playback level —
  // only set for the real NeuTTS path, stays null for the Web Speech fallback.
  const [speakingAudioEl, setSpeakingAudioEl] = useState<HTMLAudioElement | null>(null)

  const log = useCallback((level: LogEntry['level'], text: string) => {
    setLogs((prev) =>
      [...prev, { id: `l${logSeq++}`, ts: Date.now(), level, text }].slice(-60),
    )
  }, [])

  const nancySay = useCallback(
    (text: string) => {
      // Interrupt any current speech cleanly first — prevents overlap glitches.
      cancelSpeech()
      currentAudioRef.current?.pause()
      currentAudioRef.current = null
      setSpeakingAudioEl(null)
      if (wordTimerRef.current) {
        clearInterval(wordTimerRef.current)
        wordTimerRef.current = null
      }
      log('nancy', text)
      sfx.confirm()

      // Deliberately NOT setting currentUtterance/speaking here: the lyrics
      // transcript starts its own line timer the instant currentUtterance
      // changes, driven by wall-clock time. If we set it before the audio
      // actually exists, the transcript plays out and finishes while the
      // real synthesis (which can take real, sometimes double-digit,
      // seconds — see neu_tts.py) is still running, so Nancy's voice lands
      // long after her words have already scrolled past. Both speech paths
      // below defer this to the moment audio genuinely starts.
      const beginUtterance = () => {
        setCurrentUtterance(text)
        setSpeaking(true)
        setWordIndex(-1)
      }

      // Compute word start-char offsets so boundary/timing → word index maps cleanly.
      const starts: number[] = []
      let cursor = 0
      const words = text.split(/(\s+)/) // keep whitespace tokens
      for (const tok of words) {
        if (tok.trim()) starts.push(cursor)
        cursor += tok.length
      }

      // Per-word timing weights for the estimated-pace fallback below: a real
      // word's speaking time tracks its length (and a longer pause after
      // punctuation), not a uniform per-word slice -- weighting by these
      // keeps the estimate visibly closer to the real audio's cadence
      // instead of drifting on longer sentences.
      const wordWeights: number[] = starts.map((_, i) => {
        const tok = words.filter((w) => w.trim())[i] ?? ''
        const pause = /[.,!?;:]$/.test(tok) ? 3.5 : 0
        return Math.max(2, tok.length) + pause
      })
      const totalWeight = wordWeights.reduce((a, b) => a + b, 0) || 1
      const cumWeights: number[] = []
      wordWeights.reduce((acc, w) => {
        const next = acc + w
        cumWeights.push(next)
        return next
      }, 0)

      // Fallback: browser Web Speech API (used if the backend's real neural
      // voice — neu_tts.py — is unreachable or synthesis fails).
      const speakLocally = () => {
        speak(text, {
          onStart: () => {
            beginUtterance()
            setWordIndex(0)
          },
          onBoundary: (charIndex) => {
            let idx = 0
            for (let i = 0; i < starts.length; i++) {
              if (starts[i] <= charIndex) idx = i
              else break
            }
            setWordIndex(idx)
          },
          onEnd: () => {
            setSpeaking(false)
            setWordIndex(-1)
          },
        })
      }

      synthesizeSpeech(text)
        .then(({ audioUrl, durationMs }) => {
          const audio = new Audio(audioUrl)
          currentAudioRef.current = audio

          const cleanup = () => {
            if (wordTimerRef.current) {
              clearInterval(wordTimerRef.current)
              wordTimerRef.current = null
            }
            if (currentAudioRef.current === audio) currentAudioRef.current = null
            setSpeakingAudioEl((cur) => (cur === audio ? null : cur))
            setSpeaking(false)
            setWordIndex(-1)
            URL.revokeObjectURL(audioUrl)
          }

          audio.addEventListener('play', () => {
            beginUtterance()
            setSpeakingAudioEl(audio)
            setWordIndex(0)
            // NeuTTS doesn't emit per-word boundary events like the Web Speech
            // API does — approximate by spreading words evenly across the
            // real decoded audio duration instead of fabricating exact timing.
            if (durationMs > 0 && starts.length > 0) {
              const startedAt = Date.now()
              wordTimerRef.current = setInterval(() => {
                const elapsed = Date.now() - startedAt
                const targetWeight = (elapsed / durationMs) * totalWeight
                let idx = 0
                for (let i = 0; i < cumWeights.length; i++) {
                  if (cumWeights[i] <= targetWeight) idx = i
                  else break
                }
                setWordIndex(Math.min(starts.length - 1, idx))
              }, 60)
            }
          })
          audio.addEventListener('ended', cleanup)
          audio.addEventListener('error', () => {
            cleanup()
            speakLocally()
          })
          audio.play().catch(() => {
            cleanup()
            speakLocally()
          })
        })
        .catch(() => speakLocally())
    },
    [log],
  )

  const doLaunch = useCallback((target: string) => {
    setPanel('system')
    sfx.whooshIn()
    setLaunched(target)
    if (launchTimer.current) clearTimeout(launchTimer.current)
    launchTimer.current = setTimeout(() => setLaunched(null), 4000)
  }, [])

  const locate = useCallback(
    async (query: string) => {
      setPanel('map')
      sfx.whooshIn()
      sfx.scan()
      setMapLoading(true)
      setThinking(true)
      const found = await geocode(query)
      setThinking(false)
      setMapLoading(false)
      if (found) {
        setPlace(found)
        sfx.lock()
        nancySay(`Target acquired, Sir. Displaying ${found.name}, ${found.country}.`)
      } else {
        sfx.error()
        nancySay(`I could not locate ${query}, Sir. Please try another place.`)
      }
    },
    [nancySay],
  )

  const runCommand = useCallback(
    (input: string) => {
      const result = parseCommand(input)
      switch (result.type) {
        case 'navigate':
          sfx.whooshIn()
          setPanel(result.panel)
          nancySay(result.reply)
          break
        case 'locate':
          nancySay(result.reply)
          void locate(result.query)
          break
        case 'launch':
          nancySay(result.reply)
          doLaunch(result.target)
          break
        case 'news':
          sfx.whooshIn()
          setNewsCategory(result.category)
          setNewsTopic(result.topic)
          setNewsMedia(result.media)
          setNewsAutoOpenTop(true)
          setNewsRequestId((n) => n + 1)
          setPanel('news')
          nancySay(result.reply)
          break
        case 'scan':
          sfx.whooshIn()
          nancySay(result.reply)
          setPanel('overview')
          break
        case 'time': {
          const now = new Date().toLocaleTimeString()
          nancySay(`The local system time is ${now}, Sir.`)
          break
        }
        case 'status':
        case 'greet':
          nancySay(result.reply)
          break
        case 'unknown':
          setThinking(true)
          askNancy(input)
            .then((reply) => {
              nancySay(reply || result.reply)
            })
            .catch(() => {
              sfx.error()
              nancySay(result.reply)
            })
            .finally(() => setThinking(false))
          break
      }
    },
    [doLaunch, locate, nancySay],
  )

  const onUserInput = useCallback(
    (text: string) => {
      log('user', text)
      // Voice-first hint: if user types "close" collapse workspace
      if (/^\s*(close|exit|dismiss|hide)\b/i.test(text)) {
        sfx.whooshOut()
        setPanel(null)
        nancySay('Closing workspace, Sir.')
        return
      }
      runCommand(text)
    },
    [log, runCommand, nancySay],
  )

  const { state, start, stop } = useVoice({
    onCommand: (text) => {
      if (/^\s*(close|exit|dismiss|hide)\b/i.test(text)) {
        sfx.whooshOut()
        setPanel(null)
        nancySay('Closing workspace, Sir.')
        return
      }
      runCommand(text)
    },
    onWake: () => { sfx.wake(); log('info', 'Wake word detected — awaiting command') },
  })

  useEffect(() => {
    const t = setInterval(
      () => setClock(new Date().toLocaleTimeString('en-GB')),
      1000,
    )
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    if (booting) return
    unlockSfx()
    sfx.boot()
    sfx.startHum()
    const fallback = 'Online, Sir. Say my name whenever you need me.'
    const t = setTimeout(() => {
      // Real personalized greeting (live forex rates, memory/projects, open
      // trades, pending self-improvement proposals -- see
      // backend/main_new.py's _build_real_personal_context). Falls back to
      // the plain boot line if the backend's unreachable or has nothing to say.
      fetch('/api/greeting/personalized', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
        .then((res) => (res.ok ? res.json() : Promise.reject(res)))
        .then((json) => nancySay(json?.greeting || fallback))
        .catch(() => nancySay(fallback))
    }, 1400)
    return () => clearTimeout(t)
  }, [booting, nancySay])

  const toggleMic = useCallback(() => {
    unlockSfx()
    if (state.listening) {
      stop()
      sfx.blip()
      log('info', 'Microphone disabled')
    } else {
      start()
      sfx.confirm()
      log('info', 'Microphone armed — listening for wake word')
    }
  }, [state.listening, start, stop, log])

  // Debounce rapid nav clicks so animations + audio don't stack.
  const lastTransition = useRef(0)
  const canTransition = () => {
    const now = Date.now()
    if (now - lastTransition.current < 220) return false
    lastTransition.current = now
    return true
  }

  // Nav button click helper — plays whoosh + updates panel
  const openPanel = useCallback((k: PanelKey) => {
    unlockSfx()
    if (k === panel) return
    if (!canTransition()) return
    duckSfx(160)
    sfx.whooshIn()
    setPanel(k)
  }, [panel])

  const closeWorkspace = useCallback(() => {
    if (panel === null) return
    if (!canTransition()) return
    duckSfx(160)
    cancelSpeech()
    setSpeaking(false)
    setWordIndex(-1)
    sfx.whooshOut()
    setPanel(null)
  }, [panel])


  const workspaceOpen = panel !== null
  const orbState: OrbState =
    mapLoading || launched
      ? 'executing'
      : speaking
        ? 'speaking'
        : thinking
          ? 'thinking'
          : state.listening
            ? 'listening'
            // Real degraded-mode signal: this browser can't do speech
            // recognition at all, not a fabricated "warning" for effect.
            : !state.supported
              ? 'alert'
              : 'idle'

  if (booting) return <BootSequence onDone={() => setBooting(false)} />

  return (
    <main className="relative min-h-dvh overflow-hidden">
      {/* One quiet ambient wash instead of competing glow layers. */}
      <div className="pointer-events-none fixed inset-0 z-0 bg-[radial-gradient(ellipse_at_50%_-10%,oklch(0.24_0.03_60_/_35%),transparent_60%)]" />

      {/* Minimal top bar — hidden when a workspace is fullscreen. No nav
          row here: the orb's own click-to-open quick nav is the single way
          to move around from voice-first mode, so this stays uncluttered. */}
      {!workspaceOpen && (
      <header className="relative z-20 mx-auto flex max-w-[1680px] items-center justify-between gap-3 px-5 py-4">
        <span className="font-display text-lg text-foreground">Nancy</span>
        <div className="text-right font-mono text-xs text-muted-foreground">
          {clock || '--:--:--'}
        </div>
      </header>
      )}

      {/* Content area */}
      {workspaceOpen ? (
        <div key={panel} className="workspace-fullscreen animate-panel-enter">
          <WorkspaceLayout
            panel={panel!}
            place={place}
            mapLoading={mapLoading}
            launched={launched}
            onLaunch={doLaunch}
            onClose={closeWorkspace}
            clock={clock}
            logs={logs}
            onNav={openPanel}
            newsCategory={newsCategory}
            newsTopic={newsTopic}
            newsMedia={newsMedia}
            newsAutoOpenTop={newsAutoOpenTop}
            newsRequestId={newsRequestId}
            onNewsReadout={nancySay}
          />
        </div>
      ) : (
        <section className="relative z-10 mx-auto flex max-w-[1680px] flex-col gap-3 px-3 pb-40 md:px-4">
          <HeroVoice
            orbState={orbState}
            utterance={currentUtterance}
            speaking={speaking}
            wordIndex={wordIndex}
            interim={state.interim}
            audioElement={speakingAudioEl}
            quickNav={ORB_QUICK_NAV}
            onQuickNav={openPanel}
          />
        </section>
      )}

      {/* Floating orb — visible when a workspace panel is open.
          Click to return to voice-first mode. */}
      {workspaceOpen && (
        <button
          type="button"
          onClick={closeWorkspace}
          title="Return to voice mode"
          aria-label="Return to voice mode"
          className="group fixed bottom-24 right-6 z-40 flex flex-col items-center gap-2 animate-orb-dock focus:outline-none"
        >
          <div className="transition-transform duration-300 group-hover:scale-105 group-active:scale-95">
            <NancyOrb state={orbState} size={120} audioElement={speakingAudioEl} />
          </div>
        </button>
      )}

      {/* Bottom dock: voice-first by default (just a mic toggle + a summon
          affordance for the rare case you want to type). The full terminal
          only appears once you actually ask for it. */}
      <div className="fixed inset-x-0 bottom-0 z-30 mx-auto max-w-[1680px] px-3 pb-4 md:px-4">
        {consoleOpen ? (
          <div className="flex flex-col items-center gap-1.5">
            <ConsoleBar
              logs={logs}
              listening={state.listening}
              awake={state.awake}
              supported={state.supported}
              interim={state.interim}
              onToggleMic={toggleMic}
              onSubmit={onUserInput}
            />
            <button
              type="button"
              onClick={() => setConsoleOpen(false)}
              className="flex items-center gap-1 rounded-lg border border-border bg-card px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              <ChevronDown className="h-3 w-3" /> Hide console
            </button>
          </div>
        ) : (
          <div className="flex items-center justify-center gap-3 pb-1">
            <button
              type="button"
              onClick={toggleMic}
              disabled={!state.supported}
              title={state.supported ? 'Toggle microphone' : 'Speech recognition not supported in this browser'}
              className={cn(
                'flex h-12 w-12 items-center justify-center rounded-full border transition-colors',
                !state.supported && 'cursor-not-allowed opacity-40',
                state.listening
                  ? 'border-primary bg-primary text-primary-foreground'
                  : 'border-border bg-card text-foreground hover:border-primary/50',
              )}
            >
              {state.listening ? <Mic className="h-5 w-5" /> : <MicOff className="h-5 w-5" />}
            </button>
            <button
              type="button"
              onClick={() => setConsoleOpen(true)}
              title="Type a command"
              className="flex h-9 w-9 items-center justify-center rounded-full border border-border bg-card text-muted-foreground transition-colors hover:text-foreground"
            >
              <Keyboard className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>
    </main>
  )
}

/* ─── Hero voice-first mode (orb + lyrics) ─────────────────────────────── */

function HeroVoice({
  orbState,
  utterance,
  speaking,
  wordIndex,
  interim,
  audioElement,
  quickNav,
  onQuickNav,
}: {
  orbState: OrbState
  utterance: string
  speaking: boolean
  wordIndex: number
  interim: string
  audioElement: HTMLAudioElement | null
  quickNav?: { key: PanelKey; label: string; icon: typeof Brain }[]
  onQuickNav?: (k: PanelKey) => void
}) {
  const [orbSize, setOrbSize] = useState(360)
  useEffect(() => {
    const compute = () => {
      const w = window.innerWidth
      const h = window.innerHeight
      // Leave room for header (72), the orb's own caption (~60), transcript
      // (~140), console (~180) and hint (~40).
      const vertical = Math.max(180, h - 72 - 60 - 140 - 180 - 40)
      const horizontal = Math.min(w - 32, 440)
      setOrbSize(Math.max(180, Math.min(vertical, horizontal, 380)))
    }
    compute()
    window.addEventListener('resize', compute)
    return () => window.removeEventListener('resize', compute)
  }, [])

  return (
    <div className="flex min-h-[calc(100dvh-260px)] flex-col items-center justify-center gap-8 py-6 sm:gap-10 sm:py-10">
      <NancyOrb
        state={orbState}
        size={orbSize}
        audioElement={audioElement}
        quickNav={quickNav}
        onQuickNav={onQuickNav ? (k) => onQuickNav(k as PanelKey) : undefined}
      />

      <div className="w-full max-w-xl px-4">
        <LyricsTranscript
          text={utterance}
          speaking={speaking}
          wordIndex={wordIndex}
          interim={interim}
        />
      </div>
    </div>
  )
}

/* ─── Workspace layout when a panel is opened by voice ─────────────────── */

function WorkspaceLayout({
  panel,
  place,
  mapLoading,
  launched,
  onLaunch,
  onClose,
  clock,
  logs,
  onNav,
  newsCategory,
  newsTopic,
  newsMedia,
  newsAutoOpenTop,
  newsRequestId,
  onNewsReadout,
}: {
  panel: PanelKey
  place: Place | null
  mapLoading: boolean
  launched: string | null
  onLaunch: (t: string) => void
  onClose: () => void
  clock: string
  logs: LogEntry[]
  onNav: (k: PanelKey) => void
  newsCategory: KnowledgeCategory | null
  newsTopic: string | null
  newsMedia: 'articles' | 'videos'
  newsAutoOpenTop: boolean
  newsRequestId: number
  onNewsReadout: (text: string) => void
}) {
  const isMap = panel === 'map'
  const isNews = panel === 'news'
  const [collapsed, setCollapsed] = useState(false)
  const TITLE: Partial<Record<PanelKey, string>> = {
    overview: 'Command Overview',
    core: 'Neural Core',
    agents: 'Autonomous Agents',
    system: 'Command Layer',
    kanban: 'Task Board',
    map: place ? `Recon · ${place.name}` : 'Global Recon',
    news: newsTopic ? `Newsfeed · ${newsTopic}` : 'Newsfeed',
    channels: 'Channels',
    instances: 'Instances',
    sessions: 'Sessions',
    cron: 'Cron Jobs',
    skills: 'Skills',
    models: 'Models',
    config: 'Config',
    keys: 'Keys',
    usage: 'Usage',
    profiles: 'Profiles',
    pairing: 'Pairing',
    plugins: 'Plugins',
    mcp: 'MCP Servers',
    webhooks: 'Webhooks',
    docs: 'Docs',
  }
  return (
    <div className="flex h-dvh w-full bg-transparent">
      {/* ── Persistent grouped sidebar — plain hairline border, no glow,
          sentence case throughout. Structurally still grouped like
          OpenClaw/Hermes; visually its own quiet thing. ── */}
      <aside
        className={cn(
          'relative z-30 flex shrink-0 flex-col border-r border-border bg-card/60 transition-[width] duration-200',
          collapsed ? 'w-[60px]' : 'w-60',
        )}
      >
        {/* Brand */}
        <div className="flex items-center gap-2.5 border-b border-border px-4 py-4">
          <div className="h-2 w-2 shrink-0 rounded-full bg-primary" />
          {!collapsed && <h1 className="font-display text-base text-foreground">Nancy</h1>}
        </div>

        {/* Voice entry point -- always first, like OpenClaw's "Chat" */}
        <div className="px-2.5 pt-3">
          <button
            type="button"
            onClick={onClose}
            title="Return to voice mode"
            className="flex w-full items-center gap-2 rounded-lg bg-primary px-3 py-2 text-[0.75rem] font-medium text-primary-foreground transition-opacity hover:opacity-90"
          >
            <MessageSquare className="h-3.5 w-3.5 shrink-0" />
            {!collapsed && 'Voice'}
          </button>
        </div>

        {/* Grouped nav */}
        <nav className="flex-1 overflow-y-auto px-2.5 py-4">
          {NAV_GROUPS.map((g) => (
            <div key={g.group} className="mb-5">
              {!collapsed && (
                <p className="mb-1.5 px-2 text-[0.65rem] font-medium text-muted-foreground">{g.group}</p>
              )}
              <div className="flex flex-col gap-0.5">
                {g.items.map(({ key, label, icon: Icon }) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => onNav(key)}
                    title={label}
                    className={cn(
                      'flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-[0.75rem] transition-colors',
                      panel === key
                        ? 'bg-secondary text-foreground'
                        : 'text-muted-foreground hover:bg-secondary/50 hover:text-foreground',
                    )}
                  >
                    <Icon className="h-3.5 w-3.5 shrink-0" />
                    {!collapsed && <span className="truncate">{label}</span>}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </nav>

        {/* Footer: real clock + collapse toggle */}
        <div className="border-t border-border px-3 py-2.5">
          {!collapsed && (
            <div className="mb-2 font-mono text-[0.7rem] text-muted-foreground">{clock || '--:--:--'}</div>
          )}
          <button
            type="button"
            onClick={() => setCollapsed((c) => !c)}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-border py-1.5 text-muted-foreground transition-colors hover:text-foreground"
          >
            {collapsed ? <PanelLeftOpen className="h-3.5 w-3.5" /> : <PanelLeftClose className="h-3.5 w-3.5" />}
          </button>
        </div>
      </aside>

      {/* ── Main content ── */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="relative z-20 flex items-center gap-2 border-b border-border bg-card/30 px-5 py-3">
          <span className="font-heading text-sm text-foreground">
            {TITLE[panel] ?? String(panel)}
          </span>
        </div>

        <div className="relative flex-1 overflow-hidden">
          {isMap ? (
            <div className="absolute inset-0">
              <MapPanel place={place} loading={mapLoading} />
            </div>
          ) : isNews ? (
            <div className="absolute inset-0 p-3 md:p-4">
              <KnowledgePanel
                category={newsCategory ?? 'general'}
                topic={newsTopic}
                media={newsMedia}
                autoOpenTop={newsAutoOpenTop}
                requestId={newsRequestId}
                onReadout={onNewsReadout}
                onClose={onClose}
              />
            </div>
          ) : (
            <div className="absolute inset-0 overflow-y-auto px-4 py-4 pb-10 md:px-8 md:py-6">
              {panel === 'overview' && <OverviewPanel />}
              {panel === 'core' && <CorePanel />}
              {panel === 'agents' && <AgentsPanel />}
              {panel === 'system' && <SystemPanel onLaunch={onLaunch} launched={launched} />}
              {panel === 'kanban' && <KanbanPanel />}
              {panel === 'sessions' && <SessionsPanel logs={logs} />}
              {panel === 'channels' && <ChannelsPanel />}
              {panel === 'instances' && <InstancesPanel />}
              {panel === 'cron' && <CronPanel />}
              {panel === 'skills' && <SkillsPanel />}
              {panel === 'models' && <ModelsPanel />}
              {panel === 'config' && <ConfigPanel />}
              {panel === 'keys' && <KeysPanel />}
              {panel === 'usage' && <UsagePanel />}
              {panel === 'profiles' && <ProfilesPanel />}
              {panel === 'pairing' && <PairingPanel />}
              {panel === 'plugins' && <PluginsPanel />}
              {panel === 'mcp' && <McpPanel />}
              {panel === 'webhooks' && <WebhooksPanel />}
              {panel === 'docs' && <DocsPanel />}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
