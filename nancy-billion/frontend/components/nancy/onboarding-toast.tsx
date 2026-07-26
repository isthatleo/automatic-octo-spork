'use client'

import { useEffect, useState } from 'react'
import { markHintSeen, type OnboardingHint } from '@/lib/nancy/onboarding-hints'

/**
 * A single quiet, dismissible toast for one-time onboarding hints -- no
 * glow, no sci-fi chrome, matching hud-bits.tsx's calm flat-surface
 * language. Mounted once near the app root; fired via
 * window.dispatchEvent(new CustomEvent('nancy:hint', { detail: hint })) so
 * any component can trigger a hint without prop-drilling a setter down to
 * wherever this is mounted.
 */
export function OnboardingToast() {
  const [hint, setHint] = useState<OnboardingHint | null>(null)

  useEffect(() => {
    function onHint(e: Event) {
      const detail = (e as CustomEvent<OnboardingHint>).detail
      if (detail) setHint(detail)
    }
    window.addEventListener('nancy:hint', onHint as EventListener)
    return () => window.removeEventListener('nancy:hint', onHint as EventListener)
  }, [])

  if (!hint) return null

  function dismiss() {
    if (hint) markHintSeen(hint.id)
    setHint(null)
  }

  return (
    <div className="pointer-events-auto fixed bottom-5 left-1/2 z-50 max-w-md -translate-x-1/2 rounded-xl border border-border bg-card/95 px-4 py-3 text-xs text-foreground shadow-lg backdrop-blur">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
        <p className="flex-1 leading-relaxed text-muted-foreground">{hint.message}</p>
        <button
          onClick={dismiss}
          className="shrink-0 text-muted-foreground/70 hover:text-foreground"
          aria-label="Dismiss"
        >
          ✕
        </button>
      </div>
    </div>
  )
}

/** Call from anywhere to fire a one-time hint by id -- no-ops silently if
 * already seen or unknown. */
export function fireOnboardingHint(id: string): void {
  import('@/lib/nancy/onboarding-hints').then(({ triggerHintOnce }) => {
    const hint = triggerHintOnce(id)
    if (hint) window.dispatchEvent(new CustomEvent('nancy:hint', { detail: hint }))
  })
}
