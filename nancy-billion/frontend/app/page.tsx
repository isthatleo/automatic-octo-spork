'use client'

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { BootSequence } from '@/components/nancy/boot-sequence'
import { MapPanel } from '@/components/nancy/map-panel'
import { KnowledgePanel } from '@/components/nancy/knowledge-panel'
import { TradingDeskPanel } from '@/components/nancy/trading-desk'
import {
  CorePanel,
  SystemPanel,
} from '@/components/nancy/panels'
import { OverviewV2Panel } from '@/components/nancy/overview-v2'
import { MissionControlPanel } from '@/components/nancy/mission-control'
import { PanelErrorBoundary } from '@/components/nancy/panel-error-boundary'
import { ConsoleBar } from '@/components/nancy/console-bar'
import { NancyOrb, type OrbState } from '@/components/nancy/nancy-orb'
import { LyricsTranscript } from '@/components/nancy/lyrics-transcript'
import { WorkflowOrchestratorPanel } from '@/components/nancy/workflow-orchestrator'
import { CanvasPanel } from '@/components/nancy/canvas-panel'
import {
  SessionsPanel, ChannelsPanel, InstancesPanel, CronPanel, SkillsPanel, ModelsPanel,
  KeysPanel, ConfigPanel, UsagePanel, PairingPanel, ProfilesPanel, PluginsPanel,
  WebhooksPanel, MemoryInsightsPanel, AchievementsPanel, ThemingPanel,
} from '@/components/nancy/admin-panels'
import { useVoice, cancelSpeech } from '@/lib/nancy/use-voice'
import { parseCommand } from '@/lib/nancy/commands'
import { TradingViewDialog } from '@/components/nancy/tradingview'
import {
  askNancyStreaming, onEconomicAlert, onExternalReply, onChatImage,
  onConversationEnded, notifyConversationStart, notifyConversationEnd,
} from '@/lib/nancy/ws-client'
import { synthesizeSpeech } from '@/lib/nancy/tts-client'
import { geocode } from '@/lib/nancy/geocode'
import type { KnowledgeCategory, LogEntry, PanelKey, Place } from '@/lib/nancy/types'

// Real-time tool-use progress -- friendly present-progressive text for each
// real tool name, shown in the console log the instant a multi-round
// tool-use call actually starts (see onToolProgress/tool_progress), rather
// than the user seeing nothing until the whole loop finishes.
const TOOL_PROGRESS_LABELS: Record<string, string> = {
  read_file: 'Reading a file…', write_file: 'Writing a file…', edit_file: 'Editing a file…',
  delete_file: 'Deleting a file…', move_file: 'Moving/renaming a file…', list_directory: 'Listing a directory…',
  glob_files: 'Finding files…', search_files: 'Searching your codebase…', execute_command: 'Running a command…',
  fetch_url: 'Fetching a page…', web_search: 'Searching the web…', post_to_canvas: 'Pinning to canvas…',
  open_application: 'Opening an application…', look_at_camera: 'Checking the camera…',
  browser_navigate: 'Opening a page in the browser…', browser_get_text: 'Reading the page…',
  browser_screenshot: 'Taking a screenshot of the page…', browser_click: 'Clicking on the page…',
  browser_fill: 'Typing into the page…', take_screenshot: 'Taking a screenshot…',
  create_subagent: 'Creating a new agent…', extract_document_text: 'Reading a document…',
}
function describeToolProgress(toolName: string): string {
  return TOOL_PROGRESS_LABELS[toolName] ?? `Using ${toolName.replace(/_/g, ' ')}…`
}
import { cn } from '@/lib/utils'
import { sfx, unlockSfx, duckSfx } from '@/lib/nancy/sfx'

import {
  Brain, Bot, Globe2, LayoutDashboard, TerminalSquare, Newspaper, Kanban, X, Mic, MicOff,
  Keyboard, ChevronDown, MessageSquare, PanelLeftClose, PanelLeftOpen, Send, Server, Clock3,
  FileClock, Sparkles, Cpu, Key, Settings2, BarChart3, Link2, User, PlugZap, Webhook, BookOpen,
  StickyNote, Award, Palette, CandlestickChart, PhoneCall, PhoneOff, Workflow,
} from 'lucide-react'

import { DocsHelpPanel } from '@/components/nancy/docs-panel'
import { OnboardingToast } from '@/components/nancy/onboarding-toast'
import { FlowBuilderPanel } from '@/components/nancy/flow-builder-panel'

/** Grouped exactly like OpenClaw/Hermes's sidebar (Control/Agent/Settings/
 * Resources), mapped onto Nancy's real pages -- a top-level "Voice" entry
 * stands in for their "Chat" group. */
const NAV_GROUPS: { group: string; items: { key: PanelKey; label: string; icon: typeof Brain }[] }[] = [
  { group: 'Control', items: [
    { key: 'overview', label: 'Overview', icon: LayoutDashboard },
    { key: 'map', label: 'Recon', icon: Globe2 },
    { key: 'news', label: 'Newsfeed', icon: Newspaper },
    { key: 'market', label: 'Trading Desk', icon: CandlestickChart },
    { key: 'channels', label: 'Channels', icon: Send },
    { key: 'instances', label: 'Instances', icon: Server },
    { key: 'sessions', label: 'Sessions', icon: Clock3 },
    { key: 'cron', label: 'Cron Jobs', icon: FileClock },
  ] },
  { group: 'Agent', items: [
    { key: 'core', label: 'AI Core', icon: Brain },
    { key: 'agents', label: 'Agents', icon: Bot },
    { key: 'kanban', label: 'Kanban', icon: Kanban },
    { key: 'canvas', label: 'Canvas', icon: StickyNote },
    { key: 'flows', label: 'Flows', icon: Workflow },
    { key: 'skills', label: 'Skills', icon: Sparkles },
    { key: 'models', label: 'Models', icon: Cpu },
    { key: 'memory-insights', label: 'Memory Insights', icon: Brain },
    { key: 'achievements', label: 'Achievements', icon: Award },
  ] },
  { group: 'Settings', items: [
    { key: 'system', label: 'Command Layer', icon: TerminalSquare },
    { key: 'config', label: 'Config', icon: Settings2 },
    { key: 'keys', label: 'Keys', icon: Key },
    { key: 'usage', label: 'Usage', icon: BarChart3 },
    { key: 'theming', label: 'Theming', icon: Palette },
    { key: 'profiles', label: 'Profiles', icon: User },
    { key: 'pairing', label: 'Pairing', icon: Link2 },
    { key: 'plugins', label: 'Plugins (MCP)', icon: PlugZap },
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
  useEffect(() => {
    import('@/lib/nancy/theme').then(({ applyStoredTheme }) => applyStoredTheme())
  }, [])
  const [booting, setBooting] = useState(true)
  // `null` = voice-first hero mode (no panel visible). Anything else opens the workspace.
  const [panel, setPanel] = useState<PanelKey | null>(null)
  const [place, setPlace] = useState<Place | null>(null)
  const [mapLoading, setMapLoading] = useState(false)
  // Bumped to a new value to turn on Recon's existing live-tracking toggle
  // from a voice/chat command -- see MapPanel's autoStartTracking prop.
  const [trackTrigger, setTrackTrigger] = useState<number | undefined>(undefined)
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
  // TradingView chart dialog -- only ever set by an explicit "open the
  // chart for X" command (see commands.ts's chartMatch), never shown
  // proactively alongside a plain price mention.
  const [chartSymbol, setChartSymbol] = useState<string | null>(null)
  // Mirrors currentAudioRef as state (not just a ref) so NancyOrb re-renders
  // with the live <audio> element and can analyze its real playback level —
  // only set for the real NeuTTS path, stays null for the Web Speech fallback.
  const [speakingAudioEl, setSpeakingAudioEl] = useState<HTMLAudioElement | null>(null)

  // Streaming playback for askNancyStreaming(): NeuTTS synthesizes per
  // sentence server-side and pushes each chunk as soon as it's ready, so
  // audio is queued and played gaplessly rather than fetched as one blob
  // after the whole reply is generated. currentTurnIdRef gates late chunks
  // from a turn that's since been superseded by a newer one.
  const audioQueueRef = useRef<HTMLAudioElement[]>([])
  const isPlayingQueueRef = useRef(false)
  const currentTurnIdRef = useRef<number | null>(null)

  // ── Context bridge: report live UI state to /api/context so the backend
  // can inject it into Nancy's system prompt (_live_context_bridge_context
  // in main_new.py). Posts on real state changes (debounced) plus a 10s
  // heartbeat -- the bridge's TTL store expires at 15s, so the heartbeat is
  // what keeps bridge_status honest while the dashboard is simply open.
  const contextStateRef = useRef({ panel: null as PanelKey | null, speaking: false, thinking: false })
  contextStateRef.current = { panel, speaking, thinking }
  useEffect(() => {
    let cancelled = false
    const post = () => {
      if (cancelled) return
      const s = contextStateRef.current
      fetch('/api/context', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source: 'dashboard',
          active_panel: s.panel ?? 'voice-hero',
          speaking: s.speaking,
          thinking: s.thinking,
        }),
      }).catch(() => {}) // best-effort -- context is never worth surfacing an error for
    }
    const debounce = setTimeout(post, 400)
    const heartbeat = setInterval(post, 10_000)
    return () => { cancelled = true; clearTimeout(debounce); clearInterval(heartbeat) }
  }, [panel, speaking, thinking])

  const log = useCallback((level: LogEntry['level'], text: string, imageBase64?: string) => {
    setLogs((prev) =>
      [...prev, { id: `l${logSeq++}`, ts: Date.now(), level, text, imageBase64 }].slice(-60),
    )
  }, [])

  const playNextQueuedAudio = useCallback(() => {
    if (isPlayingQueueRef.current) return
    const next = audioQueueRef.current.shift()
    if (!next) return
    isPlayingQueueRef.current = true
    currentAudioRef.current = next
    setSpeakingAudioEl(next)
    next.play().catch(() => {
      isPlayingQueueRef.current = false
      playNextQueuedAudio()
    })
  }, [])

  const enqueueAudioChunk = useCallback((base64: string) => {
    // No turn-id check needed here: ws-client.ts's askNancyStreaming already
    // only invokes onAudioChunk for the currently-active turn (it drops any
    // frame whose turn_id doesn't match before calling out to us at all).
    const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0))
    const blob = new Blob([bytes], { type: 'audio/wav' })
    const url = URL.createObjectURL(blob)
    const audio = new Audio(url)
    audio.addEventListener('ended', () => {
      URL.revokeObjectURL(url)
      isPlayingQueueRef.current = false
      if (currentAudioRef.current === audio) currentAudioRef.current = null
      playNextQueuedAudio()
    })
    audio.addEventListener('error', () => {
      URL.revokeObjectURL(url)
      isPlayingQueueRef.current = false
      playNextQueuedAudio()
    })
    audioQueueRef.current.push(audio)
    playNextQueuedAudio()
  }, [playNextQueuedAudio])

  /** Interrupts whatever's currently speaking/queued and claims playback for
   *  a new turn -- combined with the backend cancelling the old turn's
   *  generation, this is the full fix for Nancy finishing an old reply
   *  instead of switching to the new one. */
  const beginStreamedTurn = useCallback((turnId: number) => {
    if (currentTurnIdRef.current !== null) {
      import('@/components/nancy/onboarding-toast').then(({ fireOnboardingHint }) => fireOnboardingHint('chat-while-busy'))
    }
    cancelSpeech()
    currentAudioRef.current?.pause()
    currentAudioRef.current = null
    audioQueueRef.current.forEach((a) => a.pause())
    audioQueueRef.current = []
    isPlayingQueueRef.current = false
    setSpeakingAudioEl(null)
    if (wordTimerRef.current) {
      clearInterval(wordTimerRef.current)
      wordTimerRef.current = null
    }
    currentTurnIdRef.current = turnId
    setSpeaking(true)
    setWordIndex(-1)
    sfx.confirm()
  }, [])

  /** Voice-first barge-in: hard-stop whatever Nancy is saying RIGHT NOW
   *  (browser TTS, the current NeuTTS <audio>, and every queued chunk) and
   *  drop back to listening. The existing speaking-state effect below
   *  auto-resumes the mic the moment `speaking` flips false, so one call
   *  here is the complete interrupt. Bound to the Escape key globally. */
  const interruptSpeech = useCallback(() => {
    cancelSpeech()
    currentAudioRef.current?.pause()
    currentAudioRef.current = null
    audioQueueRef.current.forEach((a) => a.pause())
    audioQueueRef.current = []
    isPlayingQueueRef.current = false
    setSpeakingAudioEl(null)
    if (wordTimerRef.current) {
      clearInterval(wordTimerRef.current)
      wordTimerRef.current = null
    }
    // Invalidate the in-flight turn so any late streamed audio chunks from
    // it are discarded instead of resurrecting the interrupted speech.
    currentTurnIdRef.current = null
    setSpeaking(false)
    setThinking(false)
    setWordIndex(-1)
    setCurrentUtterance('')
  }, [])

  // Esc = "stop talking, I'm speaking now" -- works anywhere on the page.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') interruptSpeech()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [interruptSpeech])

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

      // Degrade silently if the backend's real neural voice — neu_tts.py —
      // is unreachable or synthesis fails: show the text (already logged
      // above) with no audio, rather than substituting a differently-voiced
      // fallback the user never asked to hear. See use-voice.ts for why the
      // old browser Web Speech API fallback was removed.
      const degradeSilently = () => {
        setSpeaking(false)
        setWordIndex(-1)
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
            degradeSilently()
          })
          audio.play().catch(() => {
            cleanup()
            degradeSilently()
          })
        })
        .catch(() => degradeSilently())
    },
    [log],
  )

  // Real-time NFP/CPI/FOMC alerts (see backend's _economic_calendar_loop):
  // the instant a tracked release's actual value posts, the backend pushes
  // an 'economic_alert' over the WebSocket and this reads it out loud —
  // independent of any chat message, so it fires even if the user never
  // typed anything.
  useEffect(() => {
    const unsubscribe = onEconomicAlert((payload) => {
      sfx.confirm()
      nancySay(payload.text)
    })
    return unsubscribe
  }, [nancySay])

  // Real conversation sync -- a reply that actually originated in Telegram
  // (see main_new.py's _broadcast_reply_to_web) shows up here too, logged
  // but not spoken -- Nancy replying out loud unprompted because a message
  // came in on a phone in another room would be more surprising than
  // helpful. This is what makes the two conversations genuinely the same
  // conversation instead of two that merely share memory.
  useEffect(() => {
    const unsubscribe = onExternalReply((payload) => {
      if (payload.source === 'proactive') {
        // A proactive push (watch alert, self-healing status, etc.) mirrored
        // live into an active continuous-conversation session -- unlike a
        // Telegram-originated reply, you're actually on a live "call" right
        // now, so this genuinely should be spoken, not just logged.
        log('nancy', payload.text)
        nancySay(payload.text)
        return
      }
      log('nancy', `[via Telegram] ${payload.text}`)
    })
    return unsubscribe
  }, [log, nancySay])

  // Real images pushed from another channel or produced by a tool call
  // (map snapshots, screenshots, canvas renders) -- previously never shown
  // to a human in either channel at all.
  useEffect(() => {
    const unsubscribe = onChatImage((payload) => {
      log('nancy', payload.source === 'telegram' ? '[via Telegram] sent an image' : 'Captured an image', payload.imageBase64)
    })
    return unsubscribe
  }, [log])

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
    async (input: string, audioBase64?: string) => {
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
        case 'track':
          sfx.whooshIn()
          setPanel('map')
          setTrackTrigger(Date.now())
          nancySay(result.reply)
          break
        case 'launch':
          nancySay(result.reply)
          doLaunch(result.target)
          break
        case 'chart':
          sfx.whooshIn()
          setChartSymbol(result.symbol)
          nancySay(result.reply)
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
        case 'time': {
          const now = new Date().toLocaleTimeString()
          nancySay(`The local system time is ${now}, Sir.`)
          break
        }
        case 'session':
          sfx.whooshOut()
          setLogs([])
          setPanel('overview')
          setThinking(false)
          nancySay(result.reply)
          break
        case 'unknown': {
          // Not a local command (including Hermes-like slash commands) --
          // send it to the backend and stream the reply: audio for each
          // sentence plays as soon as that sentence is synthesized instead of
          // waiting for the whole response, and a fresh command here
          // immediately supersedes whatever's still speaking (see
          // askNancyStreaming/beginStreamedTurn).
          setThinking(true)
          const turnId = askNancyStreaming(
            input,
            {
              onAudioChunk: enqueueAudioChunk,
              onToolProgress: (toolName) => log('info', describeToolProgress(toolName)),
              onText: (text) => {
                const finalText = text || "I'm not sure how to respond to that, Sir."
                log('nancy', finalText)
                setCurrentUtterance(finalText)
              },
              onDone: () => setThinking(false),
              onError: () => {
                sfx.error()
                setThinking(false)
                nancySay("I'm having trouble reaching my backend right now, Sir.")
              },
            },
            30_000,
            // Only ever set for a voice-originated command (see use-voice.ts's
            // real capture) -- absent for typed input, exactly like today.
            audioBase64,
          )
          beginStreamedTurn(turnId)
          break
        }
      }
    },
    [doLaunch, locate, nancySay, log, enqueueAudioChunk, beginStreamedTurn],
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

  const { state, start, stop, pause, startConversationMode, stopConversationMode } = useVoice({
    onCommand: (text, audioBase64) => {
      if (/^\s*(close|exit|dismiss|hide)\b/i.test(text)) {
        sfx.whooshOut()
        setPanel(null)
        nancySay('Closing workspace, Sir.')
        return
      }
      runCommand(text, audioBase64)
    },
    onWake: () => { sfx.wake(); log('info', 'Wake word detected — awaiting command') },
    onConversationEnd: () => { log('info', 'Conversation mode ended'); notifyConversationEnd() },
  })

  // Pause the mic while Nancy is actively speaking and resume it the instant
  // she stops -- without this, the Web Speech API mic stays hot through
  // speaker output with no echo cancellation, so it can pick up her own
  // voice and misfire a false wake/command. micWasOnRef remembers whether
  // *the user* had the mic on before we paused it, so we only auto-resume
  // for someone who actually wanted to be heard, not someone who'd
  // deliberately muted it.
  const micWasOnRef = useRef(false)
  useEffect(() => {
    if (speaking) {
      if (state.listening) {
        micWasOnRef.current = true
        pause()
      }
    } else if (micWasOnRef.current) {
      micWasOnRef.current = false
      start()
    }
  }, [speaking, state.listening, start, pause])

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

  // Continuous conversation mode -- "like a phone call," no wake word needed
  // per turn until you say an exit phrase or hit this again.
  const toggleConversationMode = useCallback(() => {
    unlockSfx()
    if (state.conversationMode) {
      stopConversationMode()
      sfx.blip()
      log('info', 'Conversation mode disabled')
    } else {
      if (!state.listening) start()
      startConversationMode()
      sfx.confirm()
      log('info', 'Conversation mode active — no wake word needed, say "stop listening" to end')
    }
  }, [state.conversationMode, state.listening, start, startConversationMode, stopConversationMode, log])

  // Tells the backend whenever conversation mode actually turns on, however
  // it was triggered (this button, or the voice phrase handled inside
  // use-voice.ts itself) -- a single source of truth instead of duplicating
  // the notify call at every trigger site.
  useEffect(() => {
    if (state.conversationMode) notifyConversationStart()
  }, [state.conversationMode])

  // Server-side conversation-mode idle timeout (see main_new.py's
  // _conversation_idle_watchdog) -- resyncs local state if the backend ends
  // a session we thought was still active (tab lost focus/network briefly).
  useEffect(() => {
    const unsubscribe = onConversationEnded(() => {
      if (state.conversationMode) stopConversationMode()
    })
    return unsubscribe
  }, [state.conversationMode, stopConversationMode])

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


  // Floating dock orb is draggable anywhere on screen (not just a fixed
  // corner) -- position persists across reloads via localStorage, clamped
  // to the viewport so it can't be dragged out of reach.
  const [orbPos, setOrbPos] = useState<{ x: number; y: number } | null>(null)
  const orbBtnRef = useRef<HTMLDivElement>(null)
  const orbDragRef = useRef({ startX: 0, startY: 0, origX: 0, origY: 0, dragging: false, moved: false })

  useEffect(() => {
    try {
      const saved = localStorage.getItem('nancy.dockOrbPos')
      if (saved) setOrbPos(JSON.parse(saved))
    } catch { /* ignore corrupt/unavailable storage */ }
  }, [])

  const onOrbPointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const btn = orbBtnRef.current
    if (!btn) return
    const rect = btn.getBoundingClientRect()
    orbDragRef.current = { startX: e.clientX, startY: e.clientY, origX: rect.left, origY: rect.top, dragging: true, moved: false }
    btn.setPointerCapture(e.pointerId)
  }, [])

  const onOrbPointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const d = orbDragRef.current
    if (!d.dragging) return
    const dx = e.clientX - d.startX
    const dy = e.clientY - d.startY
    if (!d.moved && Math.hypot(dx, dy) > 5) d.moved = true
    if (!d.moved) return
    const btn = orbBtnRef.current
    const w = btn?.offsetWidth ?? 120
    const h = btn?.offsetHeight ?? 150
    const nx = Math.max(8, Math.min(window.innerWidth - w - 8, d.origX + dx))
    const ny = Math.max(8, Math.min(window.innerHeight - h - 8, d.origY + dy))
    setOrbPos({ x: nx, y: ny })
  }, [])

  const onOrbPointerUp = useCallback(() => {
    const d = orbDragRef.current
    d.dragging = false
    if (d.moved) {
      setOrbPos((p) => {
        if (p) { try { localStorage.setItem('nancy.dockOrbPos', JSON.stringify(p)) } catch { /* ignore */ } }
        return p
      })
      d.moved = false
      return
    }
    closeWorkspace()
  }, [closeWorkspace])

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

      <OnboardingToast />

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
            onLocate={locate}
            trackTrigger={trackTrigger}
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
        <div
          ref={orbBtnRef}
          role="button"
          tabIndex={0}
          onPointerDown={onOrbPointerDown}
          onPointerMove={onOrbPointerMove}
          onPointerUp={onOrbPointerUp}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') closeWorkspace() }}
          title="Drag to move · click to return to voice mode"
          aria-label="Nancy orb — drag to move, click to return to voice mode"
          className={cn(
            'group fixed z-40 flex touch-none cursor-grab flex-col items-center gap-2 focus:outline-none active:cursor-grabbing',
            !orbPos && 'bottom-24 right-6 animate-orb-dock',
          )}
          style={orbPos ? { left: orbPos.x, top: orbPos.y } : undefined}
        >
          <div className="transition-transform duration-300 group-hover:scale-105 group-active:scale-95">
            <NancyOrb state={orbState} size={300} audioElement={speakingAudioEl} />
          </div>
        </div>
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
              onClick={toggleConversationMode}
              disabled={!state.supported}
              title={state.conversationMode ? 'End continuous conversation mode' : 'Start continuous conversation mode (no wake word per turn)'}
              className={cn(
                'flex h-12 w-12 items-center justify-center rounded-full border transition-colors',
                !state.supported && 'cursor-not-allowed opacity-40',
                state.conversationMode
                  ? 'border-emerald-500 bg-emerald-500 text-white'
                  : 'border-border bg-card text-foreground hover:border-emerald-500/50',
              )}
            >
              {state.conversationMode ? <PhoneOff className="h-5 w-5" /> : <PhoneCall className="h-5 w-5" />}
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

      <TradingViewDialog symbol={chartSymbol} onClose={() => setChartSymbol(null)} />
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
  onLocate,
  trackTrigger,
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
  onLocate: (query: string) => void
  /** See page.tsx's Page(): bumped to turn on Recon's live-tracking toggle from a voice/chat command. */
  trackTrigger?: number
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
    market: 'Trading Desk',
    core: 'Neural Core',
    agents: 'Mission Control',
    system: 'Command Layer',
    kanban: 'Workflow Orchestration',
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
    plugins: 'Plugins (MCP)',
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
          {/* key={panel}: navigating to another panel resets the boundary,
              so one bad panel never traps the user on its error card. */}
          <PanelErrorBoundary key={panel} panelName={TITLE[panel] ?? String(panel)}>
          {isMap ? (
            <div className="absolute inset-0">
              <MapPanel place={place} loading={mapLoading} onLocate={onLocate} autoStartTracking={trackTrigger} />
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
              {panel === 'overview' && <OverviewV2Panel onNavigate={onNav} />}
              {panel === 'market' && <TradingDeskPanel />}
              {panel === 'core' && <CorePanel />}
              {panel === 'agents' && <MissionControlPanel />}
              {panel === 'system' && <SystemPanel onLaunch={onLaunch} launched={launched} />}
              {panel === 'kanban' && <WorkflowOrchestratorPanel />}
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
              {panel === 'webhooks' && <WebhooksPanel />}
              {panel === 'memory-insights' && <MemoryInsightsPanel />}
              {panel === 'achievements' && <AchievementsPanel />}
              {panel === 'theming' && <ThemingPanel />}
              {panel === 'canvas' && <CanvasPanel />}
              {panel === 'flows' && <FlowBuilderPanel />}
              {panel === 'docs' && <DocsHelpPanel />}
            </div>
          )}
          </PanelErrorBoundary>
        </div>
      </div>
    </div>
  )
}
