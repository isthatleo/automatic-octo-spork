import { NextRequest, NextResponse } from 'next/server'
import {
  SESSION_COOKIE, SESSION_TTL_S, mintSession, passcodeMatches, passcodeRequired,
} from '@/lib/nancy/session'

export const runtime = 'nodejs'

// A wrong passcode costs a second. Not a real rate limiter -- just enough that
// guessing over a LAN is tedious rather than instant.
const WRONG_ANSWER_DELAY_MS = 1000

export async function POST(req: NextRequest) {
  if (!passcodeRequired()) {
    return NextResponse.json({ success: true, required: false })
  }

  let passcode = ''
  try {
    passcode = String(((await req.json()) as { passcode?: unknown }).passcode ?? '')
  } catch {
    return NextResponse.json({ success: false, error: 'Bad request' }, { status: 400 })
  }

  if (!passcodeMatches(passcode)) {
    await new Promise((r) => setTimeout(r, WRONG_ANSWER_DELAY_MS))
    return NextResponse.json({ success: false, error: "That's not it." }, { status: 401 })
  }

  const res = NextResponse.json({ success: true })
  res.cookies.set(SESSION_COOKIE, await mintSession(), {
    httpOnly: true,
    sameSite: 'lax',
    path: '/',
    maxAge: SESSION_TTL_S,
    // Left off deliberately: this runs over plain http on a LAN, and a
    // secure-only cookie would simply never be sent.
    secure: false,
  })
  return res
}

/** Sign out. */
export async function DELETE() {
  const res = NextResponse.json({ success: true })
  res.cookies.set(SESSION_COOKIE, '', { httpOnly: true, path: '/', maxAge: 0 })
  return res
}
