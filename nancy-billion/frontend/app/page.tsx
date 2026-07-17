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
import { useVoice, speak, cancelSpeech } from '@/lib/nancy/use-voice'
import { parseCommand } from '@/lib/nancy/commands'
import { askNancy } from '@/lib/nancy/ws-client'
import { synthesizeSpeech } from '@/lib/nancy/tts-client'
import { geocode } from '@/lib/nancy/geocode'
import type { KnowledgeCategory, LogEntry, PanelKey, Place } from '@/lib/nancy/types'
import { cn } from '@/lib/utils'
import { sfx, unlockSfx, duckSfx } from '@/lib/nancy/sfx'

import { Brain, Bot, Globe2, LayoutDashboard, TerminalSquare, Newspaper, X, Mic, MicOff, Keyboard, ChevronDown } from 'lucide-react'

const NAV: { key: PanelKey; label: string; icon: typeof Brain }[] = [
  { key: 'overview', label: 'Overview', icon: LayoutDashboard },
  { key: 'core', label: 'AI Core', icon: Brain },
  { key: 'agents', label: 'Agents', icon: Bot },
  { key: 'system', label: 'System', icon: TerminalSquare },
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
      setCurrentUtterance(text)
      setSpeaking(true)
      setWordIndex(-1)
      sfx.confirm()

      // Compute word start-char offsets so boundary/timing → word index maps cleanly.
      const starts: number[] = []
      let cursor = 0
      const words = text.split(/(\s+)/) // keep whitespace tokens
      for (const tok of words) {
        if (tok.trim()) starts.push(cursor)
        cursor += tok.length
      }

      // Fallback: browser Web Speech API (used if the backend's real neural
      // voice — neu_tts.py — is unreachable or synthesis fails).
      const speakLocally = () => {
        speak(text, {
          onStart: () => setWordIndex(0),
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
            setSpeakingAudioEl(audio)
            setWordIndex(0)
            // NeuTTS doesn't emit per-word boundary events like the Web Speech
            // API does — approximate by spreading words evenly across the
            // real decoded audio duration instead of fabricating exact timing.
            if (durationMs > 0 && starts.length > 0) {
              const startedAt = Date.now()
              wordTimerRef.current = setInterval(() => {
                const elapsed = Date.now() - startedAt
                const idx = Math.min(starts.length - 1, Math.floor((elapsed / durationMs) * starts.length))
                setWordIndex(idx)
              }, 80)
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
        nancySay(`Target acquired. Displaying ${found.name}, ${found.country}.`)
      } else {
        sfx.error()
        nancySay(`I could not locate ${query}. Please try another place.`)
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
          nancySay(`The local system time is ${now}.`)
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
        nancySay('Closing workspace.')
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
        nancySay('Closing workspace.')
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
    const fallback = 'N-Å-N-C-Y online. Say Nancy, Billion, or Jarvis followed by a command.'
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
            : 'idle'

  if (booting) return <BootSequence onDone={() => setBooting(false)} />

  return (
    <main className="relative min-h-dvh overflow-hidden">
      {/* Ambient atmospheric glow (grid removed) */}
      <div className="pointer-events-none fixed inset-0 z-0 bg-[radial-gradient(ellipse_at_50%_-10%,rgba(56,211,235,0.10),transparent_55%),radial-gradient(ellipse_at_50%_110%,rgba(232,178,70,0.06),transparent_60%)]" />
      <div className="pointer-events-none fixed inset-0 z-0 bg-[radial-gradient(ellipse_at_center,transparent_40%,rgba(0,0,0,0.75)_100%)]" />

      {/* Compact top bar — hidden when a workspace is fullscreen */}
      {!workspaceOpen && (
      <header className="relative z-20 mx-auto flex max-w-[1680px] items-center justify-between gap-3 px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="relative h-8 w-8">
            <div className="absolute inset-0 animate-hud-spin rounded-full border border-primary/40" />
            <div className="absolute inset-1.5 rounded-full bg-primary/80 shadow-[0_0_12px_var(--hud)]" />
          </div>
          <div>
            <h1 className="font-heading text-lg leading-none tracking-[0.32em] text-primary hud-glow">
              NÅNCY
            </h1>
            <p className="text-[0.5rem] uppercase tracking-[0.28em] text-muted-foreground">
              Stark-class · Voice Interface
            </p>
          </div>
        </div>

        <nav className="hidden flex-wrap items-center gap-1 md:flex">
          {NAV.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              onClick={() => openPanel(key)}
              className={cn(
                'flex items-center gap-1.5 rounded border px-2.5 py-1.5 text-[0.58rem] uppercase tracking-widest transition-colors',
                panel === key
                  ? 'border-primary bg-primary/15 text-primary hud-glow'
                  : 'border-border/60 bg-secondary/20 text-muted-foreground hover:border-primary/50 hover:text-foreground',
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              <span className="hidden lg:inline">{label}</span>
            </button>
          ))}
        </nav>

        <div className="text-right">
          <div className="font-heading text-sm text-accent hud-glow-amber">
            {clock || '--:--:--'}
          </div>
          <div className="text-[0.5rem] uppercase tracking-widest text-muted-foreground">
            System Time
          </div>
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
            navItems={NAV}
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
          <div className="relative transition-transform duration-300 group-hover:scale-105 group-active:scale-95">
            <NancyOrb state={orbState} size={200} audioElement={speakingAudioEl} />
            <div className="pointer-events-none absolute inset-0 rounded-full ring-1 ring-primary/50 shadow-[0_0_60px_var(--hud)] group-hover:ring-primary/90 group-hover:shadow-[0_0_80px_var(--hud)]" />
            <div className="pointer-events-none absolute -inset-3 rounded-full border border-dashed border-primary/30 animate-hud-spin-slow" />
          </div>
          <span className="rounded border border-primary/30 bg-background/60 px-2 py-0.5 text-[0.5rem] uppercase tracking-[0.35em] text-primary/90 backdrop-blur-sm">
            {speaking ? '● Speaking' : state.listening ? '● Listening' : 'Tap to return'}
          </span>
        </button>
      )}

      {/* Bottom dock: voice-first by default (just a mic toggle + a summon
          affordance for the rare case you want to type). The full terminal
          only appears once you actually ask for it. */}
      <div className="fixed inset-x-0 bottom-0 z-30 mx-auto max-w-[1680px] px-3 pb-3 md:px-4">
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
              className="flex items-center gap-1 rounded border border-border/50 bg-background/50 px-2.5 py-1 text-[0.5rem] uppercase tracking-widest text-muted-foreground backdrop-blur-sm transition-colors hover:border-primary/50 hover:text-primary"
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
                'flex h-11 w-11 items-center justify-center rounded-full border backdrop-blur-sm transition-colors',
                !state.supported && 'cursor-not-allowed opacity-40',
                state.listening
                  ? 'border-primary bg-primary/20 text-primary shadow-[0_0_16px_var(--hud)]'
                  : 'border-border bg-secondary/40 text-foreground hover:border-primary/60',
              )}
            >
              {state.listening ? <Mic className="h-5 w-5" /> : <MicOff className="h-5 w-5" />}
            </button>
            <button
              type="button"
              onClick={() => setConsoleOpen(true)}
              title="Type a command"
              className="flex h-9 w-9 items-center justify-center rounded-full border border-border/50 bg-background/40 text-muted-foreground backdrop-blur-sm transition-colors hover:border-primary/50 hover:text-primary"
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
}: {
  orbState: OrbState
  utterance: string
  speaking: boolean
  wordIndex: number
  interim: string
  audioElement: HTMLAudioElement | null
}) {
  const [orbSize, setOrbSize] = useState(420)
  useEffect(() => {
    const compute = () => {
      const w = window.innerWidth
      const h = window.innerHeight
      // Leave room for header (72), transcript (~140), console (~180) and hint (~40)
      const vertical = Math.max(220, h - 72 - 140 - 180 - 40)
      const horizontal = Math.min(w - 32, 520)
      setOrbSize(Math.max(220, Math.min(vertical, horizontal, 460)))
    }
    compute()
    window.addEventListener('resize', compute)
    return () => window.removeEventListener('resize', compute)
  }, [])

  return (
    <div className="flex min-h-[calc(100dvh-260px)] flex-col items-center justify-center gap-6 py-6 sm:gap-8 sm:py-10">
      <div className="relative">
        <NancyOrb state={orbState} size={orbSize} audioElement={audioElement} />
      </div>

      <div className="w-full max-w-xl px-4">
        <LyricsTranscript
          text={utterance}
          speaking={speaking}
          wordIndex={wordIndex}
          interim={interim}
        />
      </div>


      <p className="max-w-md px-4 text-center text-[0.55rem] uppercase tracking-[0.3em] text-muted-foreground/70 sm:text-[0.6rem] sm:tracking-[0.35em]">
        try &ldquo;Nancy, open the map of Tokyo&rdquo; · &ldquo;Jarvis, show me the dashboard&rdquo; · &ldquo;Billion, system status&rdquo;
      </p>
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
  navItems,
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
  navItems: { key: PanelKey; label: string; icon: typeof Brain }[]
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
  const TITLE: Partial<Record<PanelKey, string>> = {
    overview: 'Command Overview',
    core: 'Neural Core',
    agents: 'Autonomous Agents',
    system: 'Command Layer',
    map: place ? `Recon · ${place.name}` : 'Global Recon',
    news: newsTopic ? `Newsfeed · ${newsTopic}` : 'Newsfeed',
  }
  return (
    <div className="flex h-dvh w-full flex-col bg-transparent">
      {/* Slim workspace header */}
      <div className="relative z-30 flex items-center justify-between gap-3 border-b border-primary/20 bg-background/60 px-4 py-2 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onClose}
            className="flex items-center gap-1.5 rounded border border-primary/40 bg-primary/10 px-2 py-1 text-[0.55rem] uppercase tracking-widest text-primary transition-colors hover:bg-primary/25"
            title="Return to voice mode"
          >
            <X className="h-3 w-3" /> Voice
          </button>
          <div className="h-4 w-px bg-primary/25" />
          <span className="font-heading text-sm tracking-[0.28em] text-primary hud-glow">
            {TITLE[panel] ?? String(panel).toUpperCase()}
          </span>
        </div>
        <nav className="hidden items-center gap-1 md:flex">
          {navItems.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              onClick={() => onNav(key)}
              className={cn(
                'flex items-center gap-1.5 rounded border px-2 py-1 text-[0.55rem] uppercase tracking-widest transition-colors',
                panel === key
                  ? 'border-primary bg-primary/20 text-primary hud-glow'
                  : 'border-border/50 bg-secondary/10 text-muted-foreground hover:border-primary/40 hover:text-foreground',
              )}
            >
              <Icon className="h-3 w-3" />
              <span className="hidden lg:inline">{label}</span>
            </button>
          ))}
        </nav>
        <div className="text-right">
          <div className="font-heading text-xs text-accent hud-glow-amber">{clock || '--:--:--'}</div>
          <div className="text-[0.45rem] uppercase tracking-widest text-muted-foreground">System Time</div>
        </div>
      </div>

      {/* Fullscreen content */}
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
          <div className="absolute inset-0 overflow-y-auto px-4 py-4 pb-32 md:px-8 md:py-6">
            {panel === 'overview' && <OverviewPanel />}
            {panel === 'core' && <CorePanel />}
            {panel === 'agents' && <AgentsPanel />}
            {panel === 'system' && <SystemPanel onLaunch={onLaunch} launched={launched} />}
          </div>
        )}
      </div>
    </div>
  )
}
