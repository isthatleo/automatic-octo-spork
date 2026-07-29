'use client'

// Live chat over the backend's persistent WebSocket (see @app.websocket("/ws") in
// backend/main_new.py) — real request/response over one connection, no HTTP
// round trip per message and no artificial word-by-word chunking.

import type { DomainEvent, DomainEventType } from './types'

const DOMAIN_EVENT_TYPES = new Set<DomainEventType>([
  'MISSION_CREATED', 'MISSION_UPDATED', 'MISSION_ASSIGNED', 'MISSION_STARTED',
  'MISSION_COMPLETED', 'MISSION_CANCELLED', 'MISSION_DELETED',
  'AGENT_ONLINE', 'AGENT_OFFLINE', 'AGENT_TASK_STARTED', 'AGENT_TASK_FINISHED',
  'CANVAS_ITEM_ADDED', 'CANVAS_ITEM_UPDATED', 'CANVAS_ITEM_REMOVED',
])

const WS_URL =
  process.env.NEXT_PUBLIC_BACKEND_WS_URL ??
  `${(process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000').replace(/^http/, 'ws')}/ws`

/** Callbacks for one streaming chat turn -- see askNancyStreaming(). */
export interface TurnHandlers {
  /** Fired once per sentence as its audio becomes ready (NeuTTS synthesizes
   *  per-sentence server-side, not the whole reply at once). */
  onAudioChunk?: (audioBase64: string, seq: number) => void
  /** Fired once, with the complete reply text, as soon as generation finishes
   *  (may arrive before the last sentence's audio does). */
  onText?: (text: string, debug?: unknown) => void
  /** Fired right before each real tool call runs during a multi-round
   *  tool-use loop -- previously nothing was visible until the whole loop
   *  (which can take 30-90s) finished. See main_new.py's
   *  _broadcast_tool_progress. */
  onToolProgress?: (toolName: string) => void
  /** Fired once all audio chunks for this turn have been sent. */
  onDone?: () => void
  onError?: (err: Error) => void
}

interface ActiveTurn extends TurnHandlers {
  turnId: number
  timer: ReturnType<typeof setTimeout>
}

/** Real server-pushed alert (see manager.broadcast(...) in main_new.py's
 *  _economic_calendar_loop) -- fires the instant a tracked NFP/CPI/FOMC
 *  release gets a real actual value, independent of any in-flight chat turn. */
export interface EconomicAlertPayload {
  text: string
  event_name: string
  actual: number | null
  estimate: number | null
  previous: number | null
  [key: string]: unknown
}

/** A real reply that originated in a different channel (currently: Telegram)
 *  rather than a turn this tab itself started -- see main_new.py's
 *  _broadcast_reply_to_web. This is what keeps the web UI and Telegram
 *  showing the same real conversation instead of two separate ones that
 *  just happen to share memory. */
export interface ExternalReplyPayload {
  text: string
  source: string
}
/** A real image (currently: a Telegram location-query map snapshot, or a
 *  screenshot/canvas image a tool call produced) pushed from another
 *  channel -- see main_new.py's _broadcast_reply_to_web /
 *  set_image_broadcaster. Previously a tool-produced image was never shown
 *  to a human in either channel at all, only fed to the model internally. */
export interface ChatImagePayload {
  imageBase64: string
  source: string
}

/** Real voice_id.verify()/enroll() result -- see backend/voice_id.py.
 *  match is null when there was nothing conclusive to compare (too-short/
 *  silent clip, or no profile enrolled for verify). */
export interface VoiceCheckResult {
  success: boolean
  error?: string
  match?: boolean | null
  similarity?: number
}

/** A real green/yellow/red category status (see backend/alert_center.py) --
 *  every field here reflects a signal some other real backend module
 *  already computes (system_monitor.py thresholds, OSV.dev vulnerability
 *  results, a rolling-window failed-auth counter), never a fabricated
 *  severity. Pushed live whenever a category's color actually changes (see
 *  main_new.py's _broadcast_alert_status). */
export interface AlertStatusPayload {
  key: string
  category: string
  title: string
  severity: 'green' | 'yellow' | 'red'
  detail: string
  updated_at: number
  since: number
}

let socket: WebSocket | null = null
let connecting: Promise<WebSocket> | null = null
let activeTurn: ActiveTurn | null = null
let turnIdCounter = 0
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let pendingVoiceEnroll: { resolve: (r: VoiceCheckResult) => void } | null = null
let pendingVoiceVerify: { resolve: (r: VoiceCheckResult) => void } | null = null

const economicAlertListeners = new Set<(payload: EconomicAlertPayload) => void>()
const domainEventListeners = new Set<(event: DomainEvent) => void>()
const externalReplyListeners = new Set<(payload: ExternalReplyPayload) => void>()
const chatImageListeners = new Set<(payload: ChatImagePayload) => void>()
/** Fires when the backend ends a continuous-conversation session server-side
 *  (see main_new.py's _conversation_idle_watchdog) -- a real safety net for
 *  a tab that crashed/lost network without sending conversation_end itself. */
const conversationEndedListeners = new Set<(reason: string) => void>()
/** Fires on every real category-status change pushed from alert_center.py. */
const alertStatusListeners = new Set<(status: AlertStatusPayload) => void>()
/** Fires on every real-time orb pulse (see main_new.py's _pulse_orb) --
 *  'yellow' the instant a real check/process starts, 'green' on a clean
 *  result, 'red' on an error or a genuine security/attack signal. */
const orbPulseListeners = new Set<(color: 'green' | 'yellow' | 'red', reason: string) => void>()

function connect(): Promise<WebSocket> {
  if (socket && socket.readyState === WebSocket.OPEN) return Promise.resolve(socket)
  if (connecting) return connecting

  connecting = new Promise((resolve, reject) => {
    const ws = new WebSocket(WS_URL)

    ws.onopen = () => {
      socket = ws
      connecting = null
      resolve(ws)
    }

    ws.onmessage = (event) => {
      let msg: Record<string, unknown>
      try {
        msg = JSON.parse(event.data)
      } catch {
        return // ignore malformed frame
      }

      // Proactive server pushes fire regardless of whether a request is pending.
      if (msg.type === 'economic_alert') {
        for (const cb of economicAlertListeners) cb(msg as unknown as EconomicAlertPayload)
        return
      }

      // Real domain events (agent lifecycle, mission stage transitions --
      // see backend/event_bus.py) -- the UI is a live projection of these,
      // not something that polls to find out what already happened.
      if (typeof msg.type === 'string' && DOMAIN_EVENT_TYPES.has(msg.type as DomainEventType)) {
        for (const cb of domainEventListeners) cb(msg as unknown as DomainEvent)
        return
      }

      // A real reply/image pushed from another channel (Telegram) -- not
      // tied to any turn this tab itself started (turn_id is a synthetic
      // 0), so it's dispatched here rather than through the activeTurn gate
      // below, which only ever matches this tab's own in-flight turn.
      if (msg.type === 'chat_image') {
        const payload: ChatImagePayload = { imageBase64: (msg.data as string) ?? '', source: (msg.source as string) ?? 'unknown' }
        for (const cb of chatImageListeners) cb(payload)
        return
      }
      // Telegram-originated replies, and real proactive pushes (self-healing
      // status, watch alerts, etc. -- see main_new.py's _send_or_queue)
      // mirrored live into an active continuous-conversation session --
      // both share the same "not tied to a turn this tab started" shape.
      if (msg.type === 'agent_response' && (msg.source === 'telegram' || msg.source === 'proactive')) {
        const payload: ExternalReplyPayload = { text: (msg.data as string) ?? '', source: msg.source as string }
        for (const cb of externalReplyListeners) cb(payload)
        return
      }
      if (msg.type === 'conversation_ended') {
        const reason = (msg.reason as string) ?? 'unknown'
        for (const cb of conversationEndedListeners) cb(reason)
        return
      }

      if (msg.type === 'alert_status') {
        const status = msg.status as AlertStatusPayload
        for (const cb of alertStatusListeners) cb(status)
        return
      }

      if (msg.type === 'orb_pulse') {
        const color = msg.color as 'green' | 'yellow' | 'red'
        const reason = (msg.reason as string) ?? ''
        for (const cb of orbPulseListeners) cb(color, reason)
        return
      }

      // Real voice_id enroll/verify results (see backend's voice_enroll/
      // voice_verify WS handlers) -- one-shot request/response, not tied to
      // a chat turn, so it's resolved through its own pending-promise slot
      // rather than the activeTurn gate below.
      if (msg.type === 'voice_enroll_result') {
        pendingVoiceEnroll?.resolve(msg as unknown as VoiceCheckResult)
        pendingVoiceEnroll = null
        return
      }
      if (msg.type === 'voice_verify_result') {
        pendingVoiceVerify?.resolve(msg as unknown as VoiceCheckResult)
        pendingVoiceVerify = null
        return
      }

      // Streaming chat turn frames -- only act on them if they belong to the
      // turn we're currently waiting on. A stale frame from a superseded turn
      // (the backend cancels the old task, but a message already in flight
      // over the wire can't be un-sent) is silently dropped here instead of
      // being mistaken for the current turn's data.
      const msgTurnId = msg.turn_id as number | undefined
      if (activeTurn && msgTurnId === activeTurn.turnId) {
        if (msg.type === 'tts_audio_chunk') {
          activeTurn.onAudioChunk?.((msg.data as string) ?? '', (msg.seq as number) ?? 0)
        } else if (msg.type === 'tool_progress') {
          activeTurn.onToolProgress?.((msg.tool as string) ?? '')
        } else if (msg.type === 'agent_response') {
          activeTurn.onText?.((msg.data as string) ?? '', msg.debug)
        } else if (msg.type === 'tts_done') {
          clearTimeout(activeTurn.timer)
          const { onDone } = activeTurn
          activeTurn = null
          onDone?.()
        } else if (msg.type === 'agent_error') {
          clearTimeout(activeTurn.timer)
          const { onError } = activeTurn
          activeTurn = null
          onError?.(new Error((msg.error as string) ?? 'Backend error'))
        }
      }
    }

    ws.onerror = () => {
      connecting = null
      reject(new Error('WebSocket connection failed'))
    }

    ws.onclose = () => {
      socket = null
      connecting = null
      if (activeTurn) {
        clearTimeout(activeTurn.timer)
        const { onError } = activeTurn
        activeTurn = null
        onError?.(new Error('Connection closed before a response arrived'))
      }
      // Auto-reconnect only while something actually needs the proactive
      // push channel (a trader watching for a live NFP/CPI alert shouldn't
      // lose the connection silently if it drops mid-session).
      if ((economicAlertListeners.size > 0 || domainEventListeners.size > 0 || alertStatusListeners.size > 0 || orbPulseListeners.size > 0) && !reconnectTimer) {
        reconnectTimer = setTimeout(() => {
          reconnectTimer = null
          connect().catch(() => {
            /* will retry again on the next onclose */
          })
        }, 5000)
      }
    }
  })

  return connecting
}

/**
 * Subscribe to real-time economic-release alerts (NFP/CPI/FOMC). Eagerly
 * opens the WebSocket connection so the alert arrives even if the user
 * never sends a chat message. Returns an unsubscribe function.
 */
export function onEconomicAlert(callback: (payload: EconomicAlertPayload) => void): () => void {
  economicAlertListeners.add(callback)
  connect().catch((err) => console.warn('[ws-client] economic-alert subscription connect failed:', err))
  return () => {
    economicAlertListeners.delete(callback)
  }
}

/**
 * Subscribe to real backend domain events (agent lifecycle + mission stage
 * transitions). Eagerly opens the same persistent WebSocket the chat and
 * economic-alert channels share. Returns an unsubscribe function.
 */
export function onDomainEvent(callback: (event: DomainEvent) => void): () => void {
  domainEventListeners.add(callback)
  connect().catch((err) => console.warn('[ws-client] domain-event subscription connect failed:', err))
  return () => {
    domainEventListeners.delete(callback)
  }
}

/**
 * Subscribe to real replies pushed from another channel (currently:
 * Telegram) so the web/voice UI's own conversation transcript can show the
 * exact same reply Telegram just received -- real two-way sync, not two
 * separate conversations that merely share memory. Returns an unsubscribe
 * function.
 */
export function onExternalReply(callback: (payload: ExternalReplyPayload) => void): () => void {
  externalReplyListeners.add(callback)
  connect().catch((err) => console.warn('[ws-client] external-reply subscription connect failed:', err))
  return () => {
    externalReplyListeners.delete(callback)
  }
}

/**
 * Subscribe to real images pushed from another channel or produced by a
 * tool call (map snapshots, screenshots, canvas renders) -- these used to
 * never actually reach a human in either channel. Returns an unsubscribe
 * function.
 */
export function onChatImage(callback: (payload: ChatImagePayload) => void): () => void {
  chatImageListeners.add(callback)
  connect().catch((err) => console.warn('[ws-client] chat-image subscription connect failed:', err))
  return () => {
    chatImageListeners.delete(callback)
  }
}

/**
 * Subscribe to the backend ending a continuous-conversation session on its
 * own (idle timeout) so a UI still displaying "conversation mode active" can
 * resync -- see use-voice.ts's stopConversationMode, wired to this in
 * page.tsx. Returns an unsubscribe function.
 */
export function onConversationEnded(callback: (reason: string) => void): () => void {
  conversationEndedListeners.add(callback)
  connect().catch((err) => console.warn('[ws-client] conversation-ended subscription connect failed:', err))
  return () => {
    conversationEndedListeners.delete(callback)
  }
}

/**
 * Subscribe to real-time green/yellow/red category-status changes (see
 * backend/alert_center.py). Eagerly opens the WS connection, same pattern as
 * onEconomicAlert -- a status dashboard should update the instant something
 * changes, not only on the next poll. Returns an unsubscribe function.
 */
export function onAlertStatus(callback: (status: AlertStatusPayload) => void): () => void {
  alertStatusListeners.add(callback)
  connect().catch((err) => console.warn('[ws-client] alert-status subscription connect failed:', err))
  return () => {
    alertStatusListeners.delete(callback)
  }
}

/**
 * Subscribe to real-time orb pulses (see backend/main_new.py's _pulse_orb) --
 * yellow while a real check/process is running, green on a clean result,
 * red on an error or attack signal. Eagerly opens the WS connection.
 * Returns an unsubscribe function.
 */
export function onOrbPulse(callback: (color: 'green' | 'yellow' | 'red', reason: string) => void): () => void {
  orbPulseListeners.add(callback)
  connect().catch((err) => console.warn('[ws-client] orb-pulse subscription connect failed:', err))
  return () => {
    orbPulseListeners.delete(callback)
  }
}

/** Tells the backend a continuous-conversation session just started/ended --
 *  see main_new.py's ConnectionManager.start_conversation/end_conversation.
 *  Best-effort: a send failure here just means the server-side idle
 *  watchdog and live-push mirroring won't apply this session, nothing the
 *  client itself depends on. */
export function notifyConversationStart(): void {
  connect()
    .then((ws) => ws.send(JSON.stringify({ type: 'conversation_start' })))
    .catch(() => { /* best-effort */ })
}

export function notifyConversationEnd(): void {
  connect()
    .then((ws) => ws.send(JSON.stringify({ type: 'conversation_end' })))
    .catch(() => { /* best-effort */ })
}

/**
 * Ask Nancy's backend a free-form question, streamed: audio for each sentence
 * arrives as soon as that sentence is synthesized (not the whole reply at
 * once), and the full text arrives separately as soon as generation finishes.
 *
 * Unlike the old single-slot askNancy(), calling this while a previous turn
 * is still in flight is expected, not an error -- it immediately supersedes
 * the previous turn (the backend cancels that turn's generation the instant
 * it sees the new message; see ConnectionManager.start_turn in main_new.py),
 * which is real barge-in and the actual fix for Nancy finishing an old reply
 * instead of switching to a new one.
 *
 * Returns the turn id immediately (synchronously) so the caller can tag its
 * own local playback state and safely ignore anything that isn't for this
 * turn.
 */
export function askNancyStreaming(
  text: string, handlers: TurnHandlers, timeoutMs = 30_000, audioBase64?: string,
): number {
  const turnId = ++turnIdCounter

  if (activeTurn) clearTimeout(activeTurn.timer)

  const timer = setTimeout(() => {
    if (activeTurn?.turnId === turnId) {
      const { onError } = activeTurn
      activeTurn = null
      onError?.(new Error('Nancy did not respond in time'))
    }
  }, timeoutMs)

  // Claim the slot synchronously (before the first await below) so this
  // turn is recognized as "active" even before the socket send resolves.
  activeTurn = { turnId, timer, ...handlers }

  // audioBase64 is only ever set for a voice-originated command (see
  // use-voice.ts's real capture) -- the backend's voice_id.verify() check
  // (main_new.py's final_transcript/user_text handler) simply doesn't run
  // when it's absent, exactly like a typed message today.
  const payload: Record<string, unknown> = { type: 'user_text', data: text, turn_id: turnId }
  if (audioBase64) payload.audio_b64 = audioBase64

  connect()
    .then((ws) => ws.send(JSON.stringify(payload)))
    .catch((err) => {
      if (activeTurn?.turnId === turnId) {
        clearTimeout(timer)
        const { onError } = activeTurn
        activeTurn = null
        onError?.(err instanceof Error ? err : new Error(String(err)))
      }
    })

  return turnId
}

/** Real speaker-verification enrollment -- sends one short raw-audio sample
 *  to the backend (voice_id.enroll(), see backend/voice_id.py) and resolves
 *  with the real result. Not tied to a chat turn. */
export function enrollVoice(audioBase64: string, timeoutMs = 15_000): Promise<VoiceCheckResult> {
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      if (pendingVoiceEnroll) {
        pendingVoiceEnroll = null
        resolve({ success: false, error: 'Timed out waiting for the backend.' })
      }
    }, timeoutMs)
    pendingVoiceEnroll = { resolve: (r) => { clearTimeout(timer); resolve(r) } }
    connect()
      .then((ws) => ws.send(JSON.stringify({ type: 'voice_enroll', data: audioBase64 })))
      .catch((err) => {
        if (pendingVoiceEnroll) {
          clearTimeout(timer)
          pendingVoiceEnroll = null
          resolve({ success: false, error: err instanceof Error ? err.message : String(err) })
        }
      })
  })
}

/** Real speaker-verification test against whatever's currently enrolled --
 *  same round trip as enrollVoice, different backend call (voice_id.verify()). */
export function verifyVoice(audioBase64: string, timeoutMs = 15_000): Promise<VoiceCheckResult> {
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      if (pendingVoiceVerify) {
        pendingVoiceVerify = null
        resolve({ success: false, error: 'Timed out waiting for the backend.' })
      }
    }, timeoutMs)
    pendingVoiceVerify = { resolve: (r) => { clearTimeout(timer); resolve(r) } }
    connect()
      .then((ws) => ws.send(JSON.stringify({ type: 'voice_verify', data: audioBase64 })))
      .catch((err) => {
        if (pendingVoiceVerify) {
          clearTimeout(timer)
          pendingVoiceVerify = null
          resolve({ success: false, error: err instanceof Error ? err.message : String(err) })
        }
      })
  })
}
