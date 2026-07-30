'use client'

import { useState, useEffect, useRef, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'

/** The one screen that shows before the control room when a passcode is set. */
function Unlock() {
  const router = useRouter()
  const params = useSearchParams()
  const next = params.get('next') || '/'

  const [passcode, setPasscode] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => { input.current?.focus() }, [])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!passcode || busy) return
    setBusy(true)
    setError('')
    try {
      const res = await fetch('/api/unlock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ passcode }),
      })
      if (res.ok) {
        router.replace(next)
        router.refresh()
        return
      }
      const data = (await res.json().catch(() => ({}))) as { error?: string }
      setError(data.error ?? 'That was not accepted.')
      setPasscode('')
      input.current?.focus()
    } catch {
      setError('Could not reach the control room.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-[#05080e] px-6 font-mono text-slate-200">
      <div
        className={`h-24 w-24 rounded-full border-2 border-cyan-400/25 border-t-cyan-400 ${
          busy ? 'animate-spin' : ''
        }`}
        style={{ boxShadow: '0 0 40px rgba(64,224,255,.22), inset 0 0 28px rgba(64,224,255,.1)' }}
      />

      <h1 className="mt-7 text-[0.95rem] font-semibold tracking-[0.35em] text-cyan-300">
        B I L L I O N
      </h1>
      <p className="mt-2 text-[0.7rem] text-slate-500">Locked.</p>

      <form onSubmit={submit} className="mt-7 w-full max-w-[320px]">
        <input
          ref={input}
          type="password"
          value={passcode}
          onChange={(e) => setPasscode(e.target.value)}
          placeholder="Passcode"
          autoComplete="current-password"
          disabled={busy}
          className="w-full rounded-xl border border-cyan-400/25 bg-slate-900/80 px-4 py-3 text-sm text-slate-100 outline-none transition-colors placeholder:text-slate-600 focus:border-cyan-400 focus:ring-4 focus:ring-cyan-400/10 disabled:opacity-50"
        />

        <div className="mt-2 min-h-[18px] text-[0.7rem] text-red-400">{error}</div>

        <button
          type="submit"
          disabled={busy || !passcode}
          className="mt-1 w-full rounded-xl bg-gradient-to-br from-cyan-300 to-cyan-500 px-4 py-3 text-[0.75rem] font-semibold tracking-[0.15em] text-[#05080e] transition-opacity disabled:opacity-40"
        >
          {busy ? 'CHECKING…' : 'UNLOCK'}
        </button>
      </form>

      <p className="mt-6 max-w-[320px] text-center text-[0.65rem] leading-relaxed text-slate-600">
        Set by BILLION_PASSCODE. Clear that variable to run without a lock —
        sensible on a machine only you can reach, not on a shared network.
      </p>
    </main>
  )
}

export default function UnlockPage() {
  return (
    <Suspense fallback={null}>
      <Unlock />
    </Suspense>
  )
}
