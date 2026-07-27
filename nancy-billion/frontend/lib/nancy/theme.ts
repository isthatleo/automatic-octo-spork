/**
 * Real live theme override engine -- ported from Hermes' skin/theming
 * engine. Nancy's actual color system is a fixed set of CSS custom
 * properties on :root (app/globals.css, oklch-based) -- this doesn't
 * reinvent that system, it lets the user override individual variables at
 * runtime (via document.documentElement.style.setProperty, which wins over
 * the :root declaration) and persists the overrides to localStorage so they
 * survive a reload. A plain hex value works fine as an override even though
 * the base values are oklch()  -- CSS custom properties are untyped text
 * substituted wherever var(--x) appears, so `--primary: #ff6a00` is exactly
 * as valid as the oklch() form it replaces.
 */

export interface ThemeableVar {
  key: string
  label: string
  description: string
  group: 'Accent Colors' | 'Status Colors' | 'Shape'
  type: 'color' | 'range'
  /** range only */
  min?: number
  max?: number
  step?: number
  unit?: string
  default?: number
}

export const THEMEABLE_VARS: ThemeableVar[] = [
  { key: '--primary', label: 'Primary (Ember)', description: 'The one confident accent -- active states, primary actions.', group: 'Accent Colors', type: 'color' },
  { key: '--gold', label: 'Gold', description: 'Secondary accent, used sparingly.', group: 'Accent Colors', type: 'color' },
  { key: '--accent', label: 'Accent (Slate)', description: 'Quiet informational color -- links, secondary emphasis.', group: 'Accent Colors', type: 'color' },
  { key: '--tertiary', label: 'Tertiary', description: 'Special-moments-only accent.', group: 'Accent Colors', type: 'color' },
  { key: '--magenta', label: 'Magenta', description: 'Rarely-used warm rose-red accent.', group: 'Accent Colors', type: 'color' },
  { key: '--success', label: 'Success', description: 'Real positive-state color -- confirmations, "ok" badges.', group: 'Status Colors', type: 'color' },
  { key: '--warning', label: 'Warning', description: 'Caution-state color -- degraded/attention-needed badges.', group: 'Status Colors', type: 'color' },
  { key: '--destructive', label: 'Destructive', description: 'Error/failure/delete-state color.', group: 'Status Colors', type: 'color' },
  { key: '--radius', label: 'Corner Radius', description: 'How rounded panels, buttons, and inputs are throughout the app.', group: 'Shape', type: 'range', min: 0, max: 1.5, step: 0.025, unit: 'rem', default: 0.625 },
]

const STORAGE_KEY = 'nancy:theme-overrides'

function readOverrides(): Record<string, string> {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function writeOverrides(overrides: Record<string, string>): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(overrides))
  } catch {
    // localStorage unavailable -- override just won't persist across reload,
    // a harmless degrade, not worth surfacing as an error.
  }
}

export function getThemeOverrides(): Record<string, string> {
  return readOverrides()
}

export function setThemeOverride(key: string, value: string): void {
  const overrides = readOverrides()
  overrides[key] = value
  writeOverrides(overrides)
  document.documentElement.style.setProperty(key, value)
}

export function resetThemeVar(key: string): void {
  const overrides = readOverrides()
  delete overrides[key]
  writeOverrides(overrides)
  document.documentElement.style.removeProperty(key)
}

export function resetAllTheme(): void {
  const overrides = readOverrides()
  for (const key of Object.keys(overrides)) {
    document.documentElement.style.removeProperty(key)
  }
  writeOverrides({})
}

/** Call once on app mount -- applies any saved overrides so a reload
 * doesn't flash back to the default palette before re-applying them. */
export function applyStoredTheme(): void {
  const overrides = readOverrides()
  for (const [key, value] of Object.entries(overrides)) {
    document.documentElement.style.setProperty(key, value)
  }
}
