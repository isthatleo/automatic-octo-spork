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

let socket: WebSocket | null = null
let connecting: Promise<WebSocket> | null = null
let pending: Pending | null = null

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
      if (!pending) return
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === 'agent_response') {
          clearTimeout(pending.timer)
          const { resolve: res } = pending
          pending = null
          res(msg.data ?? '')
        } else if (msg.type === 'agent_error') {
          clearTimeout(pending.timer)
          const { reject: rej } = pending
          pending = null
          rej(new Error(msg.error ?? 'Backend error'))
        }
      } catch {
        /* ignore malformed frame */
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
    }
  })

  return connecting
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
