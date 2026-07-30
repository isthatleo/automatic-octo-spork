/**
 * Passcode session for the control room.
 *
 * Locking the backend behind a bearer token only moves the problem if the
 * frontend that holds that token is itself wide open -- anything on the LAN
 * could just load the page and use the proxy. So the app gets a passcode.
 *
 * Set BILLION_PASSCODE to switch it on; leave it empty and everything below
 * is a no-op, exactly as before, which keeps a localhost-only setup friction
 * free. The cookie is httpOnly and carries no secret: just an expiry and an
 * HMAC over it, verified server-side.
 *
 * Uses Web Crypto only, so it runs unchanged in middleware (edge runtime).
 */

export const SESSION_COOKIE = 'billion_session'
export const SESSION_TTL_S = 60 * 60 * 24 * 30 // 30 days -- this is a personal device

export const PASSCODE = (process.env.BILLION_PASSCODE ?? '').trim()

/** Signing key: an explicit secret if given, else derived from the passcode. */
const SECRET = (process.env.BILLION_SESSION_SECRET ?? '').trim() || `derived:${PASSCODE}`

export function passcodeRequired(): boolean {
  return PASSCODE.length > 0
}

const enc = new TextEncoder()

async function key(): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    'raw', enc.encode(SECRET), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign', 'verify'],
  )
}

function b64url(bytes: ArrayBuffer): string {
  let s = ''
  const view = new Uint8Array(bytes)
  for (let i = 0; i < view.length; i++) s += String.fromCharCode(view[i])
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

async function sign(payload: string): Promise<string> {
  return b64url(await crypto.subtle.sign('HMAC', await key(), enc.encode(payload)))
}

/** Mint a cookie value valid for SESSION_TTL_S. */
export async function mintSession(): Promise<string> {
  const exp = String(Math.floor(Date.now() / 1000) + SESSION_TTL_S)
  return `${exp}.${await sign(exp)}`
}

/** True only for an unexpired cookie carrying a signature we produced. */
export async function verifySession(value: string | undefined): Promise<boolean> {
  if (!value) return false
  const dot = value.lastIndexOf('.')
  if (dot < 1) return false
  const exp = value.slice(0, dot)
  const sig = value.slice(dot + 1)
  if (!/^\d+$/.test(exp) || Number(exp) < Math.floor(Date.now() / 1000)) return false

  const expected = await sign(exp)
  // Constant-time-ish compare: same length, accumulate differences.
  if (expected.length !== sig.length) return false
  let diff = 0
  for (let i = 0; i < expected.length; i++) diff |= expected.charCodeAt(i) ^ sig.charCodeAt(i)
  return diff === 0
}

/** Compare a submitted passcode without leaking length via early exit. */
export function passcodeMatches(submitted: string): boolean {
  const a = enc.encode(submitted ?? '')
  const b = enc.encode(PASSCODE)
  let diff = a.length ^ b.length
  const n = Math.max(a.length, b.length)
  for (let i = 0; i < n; i++) diff |= (a[i] ?? 0) ^ (b[i] ?? 0)
  return diff === 0
}
