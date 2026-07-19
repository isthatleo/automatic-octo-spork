'use client'

import { useEffect, useState } from 'react'
import { ArcReactor } from './hud-bits'

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

/**
 * A short, honest loading moment -- not a fake "kernel boot log" reciting
 * things that never happened ("calibrating arc reactor", "orbital
 * satellite feed"). The one status line it shows is a real backend
 * connectivity check, not scripted flavor text.
 */
export function BootSequence({ onDone }: { onDone: () => void }) {
  const [status, setStatus] = useState<'checking' | 'connected' | 'offline'>('checking')
  const [closing, setClosing] = useState(false)

  useEffect(() => {
    let cancelled = false
    const check = fetch(BACKEND, { signal: AbortSignal.timeout(2500) })
      .then((r) => { if (!cancelled) setStatus(r.ok ? 'connected' : 'offline') })
      .catch(() => { if (!cancelled) setStatus('offline') })

    // Real check + a short minimum dwell so this doesn't feel like a flash
    // of nothing, but no artificial multi-second scripted sequence either.
    const minDwell = new Promise((r) => setTimeout(r, 900))
    Promise.all([check, minDwell]).then(() => {
      if (cancelled) return
      setClosing(true)
      setTimeout(onDone, 400)
    })

    return () => { cancelled = true }
  }, [onDone])

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-5 bg-background transition-opacity duration-400"
      style={{ opacity: closing ? 0 : 1 }}
    >
      <ArcReactor size={140} />
      <div className="text-center">
        <div className="font-display text-3xl text-foreground">Nancy</div>
        <div className="mt-2 text-[0.7rem] text-muted-foreground">
          {status === 'checking' && 'Waking up…'}
          {status === 'connected' && 'Connected'}
          {status === 'offline' && "Backend unreachable — you'll still be able to type, just not talk yet"}
        </div>
      </div>
    </div>
  )
}
