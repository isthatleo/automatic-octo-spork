import { NextRequest, NextResponse } from 'next/server'
import { SESSION_COOKIE, passcodeRequired, verifySession } from '@/lib/nancy/session'

/**
 * Gate the whole control room behind the passcode.
 *
 * Without this, locking the backend down would have been theatre: the Next
 * server holds the bearer token, so anything that can load a page on :3005
 * can drive the API through /api/backend/* without ever seeing a credential.
 *
 * No-op unless BILLION_PASSCODE is set.
 */

const OPEN_PATHS = new Set(['/unlock', '/api/unlock', '/manifest.webmanifest', '/favicon.ico'])

function isOpen(pathname: string): boolean {
  return (
    OPEN_PATHS.has(pathname) ||
    pathname.startsWith('/_next/') ||
    pathname.startsWith('/icons/') ||
    pathname === '/icon.png'
  )
}

export async function middleware(req: NextRequest) {
  if (!passcodeRequired()) return NextResponse.next()

  const { pathname } = req.nextUrl
  if (isOpen(pathname)) return NextResponse.next()

  if (await verifySession(req.cookies.get(SESSION_COOKIE)?.value)) {
    return NextResponse.next()
  }

  // An unauthenticated API call gets a 401 it can act on; a page navigation
  // gets sent to the unlock screen and back to where it was going.
  if (pathname.startsWith('/api/')) {
    return NextResponse.json({ success: false, error: 'Locked' }, { status: 401 })
  }

  const url = req.nextUrl.clone()
  url.pathname = '/unlock'
  url.search = pathname === '/' ? '' : `?next=${encodeURIComponent(pathname)}`
  return NextResponse.redirect(url)
}

export const config = {
  matcher: ['/((?!_next/static|_next/image).*)'],
}
