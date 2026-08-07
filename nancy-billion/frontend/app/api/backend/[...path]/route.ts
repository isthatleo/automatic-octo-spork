import { NextRequest, NextResponse } from 'next/server'
import { BACKEND_URL, backendHeaders } from '@/lib/nancy/backend-server'

/**
 * Authenticated catch-all proxy to the Billion backend.
 *
 * Browser code used to call http://localhost:8000 directly, which meant two
 * things: it broke on a phone (there `localhost` is the phone), and there was
 * nowhere to put a credential that the browser wouldn't also be holding. Now
 * every browser-side call goes to same-origin /api/backend/*, this route adds
 * the bearer token server-side, and the token never leaves the container.
 *
 * The response is streamed through untouched, so SSE, audio and image bodies
 * behave exactly as they did when the browser called the backend directly.
 */

export const dynamic = 'force-dynamic'

// Hop-by-hop headers must not be forwarded; content-length is recomputed.
const STRIP = new Set([
  'host', 'connection', 'keep-alive', 'transfer-encoding', 'upgrade',
  'proxy-authenticate', 'proxy-authorization', 'te', 'trailer',
  'content-length', 'authorization',
])

async function proxy(req: NextRequest, path: string[]) {
  const target = `${BACKEND_URL}/${path.join('/')}${req.nextUrl.search}`

  const headers = backendHeaders()
  req.headers.forEach((value, key) => {
    if (!STRIP.has(key.toLowerCase())) headers.set(key, value)
  })

  const method = req.method
  const hasBody = method !== 'GET' && method !== 'HEAD'

  try {
    const res = await fetch(target, {
      method,
      headers,
      body: hasBody ? await req.arrayBuffer() : undefined,
      redirect: 'manual',
      cache: 'no-store',
      // The backend's own tool-round timeout is 150s (_TOOL_ROUND_TIMEOUT_S
      // in main_new.py -- deliberately raised there to comfortably outlast a
      // live Telegram approval wait, which can itself take up to 120s).
      // Confirmed live as a real bug: this used to be 120_000, shorter than
      // that single backend's own ceiling, so a turn that genuinely needed
      // the full approval wait got its proxy connection aborted here with
      // "backend unreachable" while the backend kept working and completed
      // fine (confirmed by the same request succeeding via Telegram
      // moments later) -- a false negative, not a real outage. 300s gives
      // real headroom above the backend's own worst-case single-round wait.
      signal: AbortSignal.timeout(300_000),
    })

    const out = new Headers(res.headers)
    out.delete('content-encoding')   // fetch already decoded it
    out.delete('content-length')
    return new NextResponse(res.body, { status: res.status, headers: out })
  } catch (err) {
    const timedOut = err instanceof Error && err.name === 'TimeoutError'
    return NextResponse.json(
      {
        success: false,
        error: timedOut ? 'The backend took too long to answer.' : 'Backend unreachable',
      },
      { status: timedOut ? 504 : 502 },
    )
  }
}

type Ctx = { params: Promise<{ path: string[] }> }

export async function GET(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path)
}
export async function POST(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path)
}
export async function PUT(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path)
}
export async function PATCH(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path)
}
export async function DELETE(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path)
}
export async function HEAD(req: NextRequest, ctx: Ctx) {
  return proxy(req, (await ctx.params).path)
}
