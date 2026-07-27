'use client'

import { useEffect, useState } from 'react'
import { listAgents } from '@/lib/nancy/agent-client'
import { cn } from '@/lib/utils'

/**
 * Real virtual pet companion -- ported from Hermes' Petdex plugin. No
 * fabricated pixel art here (there's no real sprite-gallery asset pipeline
 * in this codebase) -- instead a single calm CSS creature whose mood is
 * driven entirely by the real live agent fleet (base_specialized_agent.py's
 * status field via listAgents()), matching hud-bits.tsx's "quiet, real
 * data, no sci-fi decoration" visual language rather than a mascot prop.
 */
type Mood = 'sleeping' | 'calm' | 'busy' | 'distressed'

function deriveMood(statuses: string[]): Mood {
  if (statuses.length === 0) return 'sleeping'
  if (statuses.some((s) => s === 'error')) return 'distressed'
  const executing = statuses.filter((s) => s === 'executing').length
  if (executing >= 3) return 'busy'
  if (statuses.every((s) => s === 'offline' || s === 'idle')) return 'sleeping'
  return 'calm'
}

const MOOD_COPY: Record<Mood, string> = {
  sleeping: 'The fleet is quiet.',
  calm: 'Ticking along.',
  busy: 'Several agents hard at work.',
  distressed: 'Something needs attention.',
}

const MOOD_COLOR: Record<Mood, string> = {
  sleeping: 'var(--muted-foreground)',
  calm: 'var(--primary)',
  busy: 'var(--gold)',
  distressed: 'var(--destructive)',
}

export function PetdexWidget({ background, border }: { background?: string; border?: string } = {}) {
  const [mood, setMood] = useState<Mood>('sleeping')
  const [executingCount, setExecutingCount] = useState(0)

  useEffect(() => {
    let cancelled = false
    async function poll() {
      const r = await listAgents()
      if (cancelled || !r.success) return
      const statuses = r.agents.map((a) => a.status)
      setMood(deriveMood(statuses))
      setExecutingCount(statuses.filter((s) => s === 'executing').length)
    }
    poll()
    const t = setInterval(poll, 15_000)
    return () => { cancelled = true; clearInterval(t) }
  }, [])

  return (
    <div
      className={cn('flex items-center gap-3 rounded-xl px-3 py-2.5', !background && 'border border-border bg-card/60')}
      style={background ? { background, border: border ? `1px solid ${border}` : undefined } : undefined}
    >
      <div
        className={cn('h-3 w-3 shrink-0 rounded-full', mood === 'busy' && 'animate-pulse')}
        style={{ background: MOOD_COLOR[mood], boxShadow: `0 0 8px ${MOOD_COLOR[mood]}` }}
        aria-hidden
      />
      <div className="min-w-0">
        <div className={cn('text-[0.6rem]', background ? 'text-white/80' : 'text-foreground')}>{MOOD_COPY[mood]}</div>
        {executingCount > 0 && (
          <div className={cn('text-[0.5rem]', background ? 'text-white/50' : 'text-muted-foreground')}>{executingCount} agent{executingCount === 1 ? '' : 's'} executing right now</div>
        )}
      </div>
    </div>
  )
}
