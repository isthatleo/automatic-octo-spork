/**
 * Server-side backend access. This module must never be imported from a
 * client component -- it reads BACKEND_AUTH_TOKEN, which is deliberately NOT
 * NEXT_PUBLIC_-prefixed and must never reach the browser.
 *
 * The browser talks to same-origin /api/backend/* instead; the catch-all
 * route there forwards to the real API with the token attached. That way the
 * phone, the desktop shell and the browser all work without any of them ever
 * holding a credential.
 */

export const BACKEND_URL =
  process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

export const BACKEND_AUTH_TOKEN = (process.env.BACKEND_AUTH_TOKEN ?? '').trim()

/** Headers for a server-side call to the backend, with auth if configured. */
export function backendHeaders(extra: HeadersInit = {}): Headers {
  const h = new Headers(extra)
  if (BACKEND_AUTH_TOKEN) h.set('authorization', `Bearer ${BACKEND_AUTH_TOKEN}`)
  return h
}

/** fetch() against the backend with auth applied. Path starts with a slash. */
export function backendFetch(path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`${BACKEND_URL}${path}`, { ...init, headers: backendHeaders(init.headers) })
}
