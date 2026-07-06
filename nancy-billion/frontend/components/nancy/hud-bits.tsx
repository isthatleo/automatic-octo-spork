'use client'

import { cn } from '@/lib/utils'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'

export function HudPanel({
  title,
  children,
  className,
  right,
}: {
  title?: string
  children: ReactNode
  className?: string
  right?: ReactNode
}) {
  return (
    <section className={cn('hud-panel rounded-md p-3', className)}>
      {title && (
        <header className="mb-2 flex items-center justify-between gap-2">
          <h2 className="font-heading text-[0.62rem] font-medium uppercase tracking-[0.22em] text-primary hud-glow">
            {title}
          </h2>
          <div className="flex items-center gap-2 text-[0.6rem] text-muted-foreground">
            {right}
          </div>
        </header>
      )}
      {children}
    </section>
  )
}

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
  const r = 40
  const c = 2 * Math.PI * r
  const pct = Math.max(0, Math.min(100, value))
  const offset = c - (pct / 100) * c
  return (
    <div
      className="relative flex shrink-0 items-center justify-center"
      style={{ width: size, height: size }}
    >
      <svg viewBox="0 0 100 100" className="absolute inset-0 -rotate-90">
        <circle
          cx="50"
          cy="50"
          r={r}
          fill="none"
          stroke="var(--border)"
          strokeWidth="4"
        />
        <circle
          cx="50"
          cy="50"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="4"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
          style={{
            transition: 'stroke-dashoffset 0.8s ease',
            filter: `drop-shadow(0 0 4px ${color})`,
          }}
        />
        <circle
          cx="50"
          cy="50"
          r="46"
          fill="none"
          stroke={color}
          strokeWidth="0.5"
          strokeDasharray="1 4"
          opacity="0.5"
        />
      </svg>
      <div className="flex flex-col items-center">
        <span className="font-heading text-base font-semibold text-foreground hud-glow">
          {Math.round(pct)}
          <span className="text-[0.6rem] text-muted-foreground">%</span>
        </span>
        <span className="mt-0.5 text-[0.5rem] uppercase tracking-widest text-muted-foreground">
          {label}
        </span>
        {sub && (
          <span className="text-[0.5rem] text-primary/70">{sub}</span>
        )}
      </div>
    </div>
  )
}

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
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-[0.6rem]">
        <span className="uppercase tracking-widest text-muted-foreground">
          {label}
        </span>
        <span className={amber ? 'text-accent' : 'text-primary'}>
          {value}
          {unit && <span className="text-muted-foreground"> {unit}</span>}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-secondary/60">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{
            width: `${Math.min(100, pct)}%`,
            background: amber ? 'var(--accent)' : 'var(--hud)',
            boxShadow: `0 0 8px ${amber ? 'var(--accent)' : 'var(--hud)'}`,
          }}
        />
      </div>
    </div>
  )
}

export function ArcReactor({
  active = true,
  size = 220,
}: {
  active?: boolean
  size?: number
}) {
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  return (
    <div
      className="relative flex items-center justify-center"
      style={{ width: size, height: size }}
      aria-hidden
    >
      {/* outer dashed ring */}
      <svg
        viewBox="0 0 200 200"
        className={cn(
          'absolute inset-0',
          active && 'animate-hud-spin-slow',
        )}
      >
        <circle
          cx="100"
          cy="100"
          r="94"
          fill="none"
          stroke="var(--hud)"
          strokeWidth="0.6"
          strokeDasharray="2 6"
          opacity="0.55"
        />
      </svg>
      {/* segmented ring */}
      <svg
        viewBox="0 0 200 200"
        className={cn('absolute inset-0', active && 'animate-hud-spin-rev')}
      >
        <circle
          cx="100"
          cy="100"
          r="78"
          fill="none"
          stroke="var(--hud)"
          strokeWidth="3"
          strokeDasharray="14 8"
          opacity="0.75"
          style={{ filter: 'drop-shadow(0 0 3px var(--hud))' }}
        />
      </svg>
      {/* ticks */}
      <svg
        viewBox="0 0 200 200"
        className={cn('absolute inset-0', active && 'animate-hud-spin')}
      >
        {mounted &&
          Array.from({ length: 60 }).map((_, i) => {
            const a = (i / 60) * Math.PI * 2
            const x1 = 100 + Math.cos(a) * 62
            const y1 = 100 + Math.sin(a) * 62
            const x2 = 100 + Math.cos(a) * (i % 5 === 0 ? 54 : 58)
            const y2 = 100 + Math.sin(a) * (i % 5 === 0 ? 54 : 58)
            return (
              <line
                key={i}
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke="var(--hud)"
                strokeWidth={i % 5 === 0 ? 1.4 : 0.6}
                opacity={i % 5 === 0 ? 0.9 : 0.4}
              />
            )
          })}
      </svg>
      {/* core */}
      <div
        className={cn(
          'relative flex h-[42%] w-[42%] items-center justify-center rounded-full',
          active && 'animate-hud-pulse',
        )}
        style={{
          background:
            'radial-gradient(circle, oklch(0.95 0.05 200) 0%, oklch(0.82 0.16 210) 32%, oklch(0.45 0.12 220) 70%, transparent 100%)',
          boxShadow:
            '0 0 30px oklch(0.82 0.16 210 / 80%), inset 0 0 18px oklch(0.95 0.05 200 / 60%)',
        }}
      >
        <div className="h-[55%] w-[55%] rounded-full border border-background/40 bg-background/20" />
      </div>
    </div>
  )
}

export function CornerTicks() {
  return (
    <div className="pointer-events-none absolute inset-0" aria-hidden>
      {(
        [
          'left-2 top-2 border-l border-t',
          'right-2 top-2 border-r border-t',
          'left-2 bottom-2 border-l border-b',
          'right-2 bottom-2 border-r border-b',
        ] as const
      ).map((pos) => (
        <span
          key={pos}
          className={cn('absolute h-4 w-4 border-primary/50', pos)}
        />
      ))}
    </div>
  )
}
