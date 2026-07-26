/**
 * Real contextual onboarding hints -- ported from Hermes' onboarding.py.
 * One-time, non-blocking hints shown the first time a user hits a real UX
 * fork, instead of a blocking first-run questionnaire nobody reads. Each
 * hint fires at most once ever (dismissed state persisted in localStorage),
 * and firing one is entirely the caller's choice -- this module holds no
 * timers/pollers of its own, it's just "has this been shown, and how do I
 * mark it shown."
 */

export interface OnboardingHint {
  id: string
  message: string
}

export const ONBOARDING_HINTS: Record<string, OnboardingHint> = {
  'chat-while-busy': {
    id: 'chat-while-busy',
    message: "You can send a new message any time — it interrupts whatever Nancy is doing and takes over immediately.",
  },
  'first-mission': {
    id: 'first-mission',
    message: 'This mission is now running through the real kanban pipeline — drag it, or just watch it move through the stages on its own.',
  },
  'first-agent-run': {
    id: 'first-agent-run',
    message: 'Specialized agents like this one keep their own task history — check their card any time to see what they’ve done.',
  },
  'first-approval-prompt': {
    id: 'first-approval-prompt',
    message: 'Risky actions (file writes, shell commands) always ask for your yes/no on Telegram first — nothing destructive happens silently.',
  },
}

const STORAGE_KEY = 'nancy:onboarding-dismissed'

function readDismissed(): Set<string> {
  if (typeof window === 'undefined') return new Set()
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    return new Set(raw ? (JSON.parse(raw) as string[]) : [])
  } catch {
    return new Set()
  }
}

function writeDismissed(dismissed: Set<string>): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(dismissed)))
  } catch {
    // localStorage unavailable (private mode, quota) -- hint just re-shows
    // next time, which is a harmless degrade, not worth surfacing an error.
  }
}

export function hasSeenHint(id: string): boolean {
  return readDismissed().has(id)
}

export function markHintSeen(id: string): void {
  const dismissed = readDismissed()
  if (dismissed.has(id)) return
  dismissed.add(id)
  writeDismissed(dismissed)
}

/** Returns the hint to show for `id` only the first time it's called for
 * that id (across the browser's lifetime, via localStorage) -- every
 * subsequent call for the same id returns null. Does NOT mark it seen by
 * itself; call markHintSeen once it's actually been displayed/dismissed, so
 * a hint that never rendered (e.g. component unmounted mid-fetch) can still
 * fire next time. */
export function triggerHintOnce(id: string): OnboardingHint | null {
  if (hasSeenHint(id)) return null
  return ONBOARDING_HINTS[id] ?? null
}
