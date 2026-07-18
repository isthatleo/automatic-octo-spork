'use client'

import { cn } from '@/lib/utils'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'

const ACCENT_DOT: Record<'cyan' | 'amber' | 'violet' | 'magenta', string> = {
  cyan: 'bg-primary',
  amber: 'bg-gold',
  violet: 'bg-tertiary',
  magenta: 'bg-magenta',
}
const ACCENT_PANEL: Record<'cyan' | 'amber' | 'violet' | 'magenta', string> = {
  cyan: '',
  amber: 'hud-panel--amber',
  violet: 'hud-panel--violet',
  magenta: 'hud-panel--magenta',
}

/**
 * The base card. Flat surface, hairline border, a small colored dot instead
 * of a whole glowing all-caps label -- quieter than the previous HUD-panel
 * treatment, on purpose. Kept the export name (used across every panel in
 * the app) so this single file is where the whole visual language actually
 * lives.
 */
export function HudPanel({
  title,
  children,
  className,
  right,
  accent = 'cyan',
  hero = false,
}: {
  title?: string
  children: ReactNode
  className?: string
  right?: ReactNode
  /** Gives a panel a distinct identity via a single accent dot + top rule
   * instead of a fully glowing border -- use amber/violet/magenta sparingly. */
  accent?: 'cyan' | 'amber' | 'violet' | 'magenta'
  /** One step brighter surface for the lead panel on a screen. */
  hero?: boolean
}) {
  return (
    <section
      className={cn(
        'hud-panel rounded-xl p-4',
        ACCENT_PANEL[accent],
        hero && 'hud-panel--hero',
        className,
      )}
    >
      {title && (
        <header className="mb-3 flex items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 font-heading text-[0.72rem] font-medium text-foreground/90">
            <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', ACCENT_DOT[accent])} />
            {title}
          </h2>
          <div className="flex items-center gap-2 text-[0.65rem] text-muted-foreground">
            {right}
          </div>
        </header>
      )}
      {children}
    </section>
  )
}

/** A plain hairline break between groups of panels, with an optional
 * left-aligned label -- no glow, no center ornament. */
export function SectionDivider({ label }: { label?: string }) {
  return (
    <div className="hud-divider col-span-12 py-1 text-[0.65rem] font-medium">
      {label && <span className="shrink-0 text-muted-foreground">{label}</span>}
    </div>
  )
}

/** Animates a numeric value counting up to its target whenever it changes,
 * instead of snapping instantly -- makes real live data (not fake motion)
 * feel alive without lying about the number itself. */
export function AnimatedNumber({
  value,
  decimals = 0,
  className,
}: {
  value: number
  decimals?: number
  className?: string
}) {
  const [display, setDisplay] = useState(value)

  useEffect(() => {
    const from = display
    const to = value
    if (from === to) return
    const start = performance.now()
    const duration = 500
    let raf = 0
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - (1 - t) * (1 - t)
      setDisplay(from + (to - from) * eased)
      if (t < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  return <span className={className}>{display.toFixed(decimals)}</span>
}

/** A calm radial progress ring. Thin stroke, no drop-shadow glow -- reads
 * as a real gauge, not a HUD prop. */
export function RadialGauge({
  value,
  label,
  sub,
  color = 'var(--hud)',
  size = 96,
}: {
  value: number
  label: string
  sub?: string
  color?: string
  size?: number
}) {
  const r = 42
  const c = 2 * Math.PI * r
  const pct = Math.max(0, Math.min(100, value))
  const offset = c - (pct / 100) * c
  return (
    <div
      className="relative flex shrink-0 items-center justify-center"
      style={{ width: size, height: size }}
    >
      <svg viewBox="0 0 100 100" className="absolute inset-0 -rotate-90">
        <circle cx="50" cy="50" r={r} fill="none" stroke="var(--border)" strokeWidth="3" />
        <circle
          cx="50"
          cy="50"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="3"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 0.6s ease' }}
        />
      </svg>
      <div className="flex flex-col items-center">
        <span className="font-heading text-base font-semibold text-foreground">
          {Math.round(pct)}
          <span className="text-[0.6rem] text-muted-foreground">%</span>
        </span>
        <span className="mt-0.5 text-[0.55rem] text-muted-foreground">{label}</span>
        {sub && <span className="text-[0.5rem] text-primary/80">{sub}</span>}
      </div>
    </div>
  )
}

/** A flat labeled progress bar -- no glow, just clean contrast. */
export function StatBar({
  label,
  value,
  unit,
  pct,
  amber,
}: {
  label: string
  value: string
  unit?: string
  pct: number
  amber?: boolean
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between text-[0.65rem]">
        <span className="text-muted-foreground">{label}</span>
        <span className={amber ? 'text-gold' : 'text-primary'}>
          {value}
          {unit && <span className="text-muted-foreground"> {unit}</span>}
        </span>
      </div>
      <div className="h-1 overflow-hidden rounded-full bg-secondary/70">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${Math.min(100, pct)}%`, background: amber ? 'var(--gold)' : 'var(--hud)' }}
        />
      </div>
    </div>
  )
}

/**
 * A calm status sphere -- replaces the old spinning multi-ring "arc
 * reactor" with a single soft-pulsing gradient disc and a thin progress
 * arc. The mechanical-cockpit-part look was exactly the kind of decoration
 * this rebuild set out to drop; this reads as a status indicator, not a
 * machine part on display.
 */
export function ArcReactor({
  active = true,
  size = 220,
}: {
  active?: boolean
  size?: number
}) {
  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }} aria-hidden>
      <svg viewBox="0 0 200 200" className="absolute inset-0">
        <circle cx="100" cy="100" r="92" fill="none" stroke="var(--border)" strokeWidth="1" />
        <circle
          cx="100"
          cy="100"
          r="92"
          fill="none"
          stroke="var(--hud)"
          strokeWidth="1.5"
          strokeDasharray="4 10"
          opacity="0.5"
          className={cn(active && 'animate-hud-spin-slow')}
          style={{ transformOrigin: '100px 100px' }}
        />
      </svg>
      <div
        className={cn('relative flex h-[46%] w-[46%] items-center justify-center rounded-full', active && 'animate-hud-breathe')}
        style={{
          background: 'radial-gradient(circle at 35% 30%, oklch(0.85 0.1 60) 0%, var(--hud) 45%, oklch(0.4 0.08 42) 100%)',
          boxShadow: '0 8px 30px oklch(0 0 0 / 35%)',
        }}
      >
        <div className="h-[58%] w-[58%] rounded-full border border-background/30 bg-background/15" />
      </div>
    </div>
  )
}

/** Retired -- corner brackets were pure sci-fi-HUD decoration. Kept as a
 * no-op so existing <CornerTicks /> call sites don't need to be touched. */
export function CornerTicks() {
  return null
}
