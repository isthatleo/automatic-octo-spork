'use client'

// Live chat over the backend's persistent WebSocket (see @app.websocket("/ws") in
// backend/main_new.py) — real request/response over one connection, no HTTP
// round trip per message and no artificial word-by-word chunking.

const WS_URL =
  process.env.NEXT_PUBLIC_BACKEND_WS_URL ??
  `${(process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000').replace(/^http/, 'ws')}/ws`

interface Pending {
  resolve: (text: string) => void
  reject: (err: Error) => void
  timer: ReturnType<typeof setTimeout>
}

/** Real server-pushed alert (see manager.broadcast(...) in main_new.py's
 *  _economic_calendar_loop) -- fires the instant a tracked NFP/CPI/FOMC
 *  release gets a real actual value, independent of any in-flight askNancy() call. */
export interface EconomicAlertPayload {
  text: string
  event_name: string
  actual: number | null
  estimate: number | null
  previous: number | null
  [key: string]: unknown
}

let socket: WebSocket | null = null
let connecting: Promise<WebSocket> | null = null
let pending: Pending | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null

const economicAlertListeners = new Set<(payload: EconomicAlertPayload) => void>()

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

      if (!pending) return
      if (msg.type === 'agent_response') {
        clearTimeout(pending.timer)
        const { resolve: res } = pending
        pending = null
        res((msg.data as string) ?? '')
      } else if (msg.type === 'agent_error') {
        clearTimeout(pending.timer)
        const { reject: rej } = pending
        pending = null
        rej(new Error((msg.error as string) ?? 'Backend error'))
      }
    }

    ws.onerror = () => {
      connecting = null
      reject(new Error('WebSocket connection failed'))
    }

    ws.onclose = () => {
      socket = null
      connecting = null
      if (pending) {
        clearTimeout(pending.timer)
        pending.reject(new Error('Connection closed before a response arrived'))
        pending = null
      }
      // Auto-reconnect only while something actually needs the proactive
      // push channel (a trader watching for a live NFP/CPI alert shouldn't
      // lose the connection silently if it drops mid-session).
      if (economicAlertListeners.size > 0 && !reconnectTimer) {
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

/** Ask Nancy's backend a free-form question; resolves with the AI-generated reply. */
export async function askNancy(text: string, timeoutMs = 30_000): Promise<string> {
  if (pending) throw new Error('A request is already in flight')

  let resolveFn!: (text: string) => void
  let rejectFn!: (err: Error) => void
  const promise = new Promise<string>((resolve, reject) => {
    resolveFn = resolve
    rejectFn = reject
  })

  const timer = setTimeout(() => {
    pending = null
    rejectFn(new Error('Nancy did not respond in time'))
  }, timeoutMs)

  // Claim the slot synchronously (before the first await below) so a
  // concurrent askNancy() call can't slip past the guard above.
  pending = { resolve: resolveFn, reject: rejectFn, timer }

  try {
    const ws = await connect()
    ws.send(JSON.stringify({ type: 'user_text', data: text }))
  } catch (err) {
    clearTimeout(timer)
    pending = null
    throw err
  }

  return promise
}
