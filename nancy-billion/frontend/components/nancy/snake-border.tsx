'use client'

import type { CSSProperties, ReactNode } from 'react'
import { cn } from '@/lib/utils'

export type SnakeState = 'idle' | 'thinking' | 'executing' | 'waiting' | 'error' | 'offline'

/**
 * Speed/color per real state. Idle is a faint slow breathe, executing is a
 * fast sweep, offline freezes entirely -- these are the only six states
 * the spec defines, and every caller maps real backend state into exactly
 * one of them (see mapAgentStatus/mapMissionStage below), never a
 * decorative default.
 */
const STATE_CONFIG: Record<SnakeState, { c1: string; c2: string; duration: string; opacity: number }> = {
  idle:      { c1: 'var(--hud)',         c2: 'var(--hud)',         duration: '9s',   opacity: 0.22 },
  thinking:  { c1: 'var(--hud)',         c2: 'var(--tertiary)',    duration: '4.5s', opacity: 0.7 },
  executing: { c1: 'var(--hud)',         c2: 'var(--gold)',        duration: '1.4s', opacity: 1 },
  waiting:   { c1: 'var(--gold)',        c2: 'var(--gold)',        duration: '3s',   opacity: 0.85 },
  error:     { c1: 'var(--destructive)', c2: 'var(--destructive)', duration: '1.1s', opacity: 1 },
  offline:   { c1: 'var(--border)',      c2: 'var(--border)',      duration: '0s',   opacity: 0.12 },
}

/**
 * The required "snake border" -- a rotating conic-gradient ring plus a
 * blurred bloom layer behind it (see `.snake-border` in globals.css for the
 * mask/conic-gradient mechanics). Speed and color are driven entirely by
 * `state`, which every caller derives from real backend data (an agent's
 * live `status`, a mission's real `stage`) -- never a fixed decoration.
 */
export function SnakeBorder({
  state,
  className,
  radiusClassName = 'rounded-[18px]',
  children,
}: {
  state: SnakeState
  className?: string
  radiusClassName?: string
  children: ReactNode
}) {
  const cfg = STATE_CONFIG[state]
  const style = {
    '--snake-c1': cfg.c1,
    '--snake-c2': cfg.c2,
    '--snake-duration': cfg.duration,
    '--snake-opacity': cfg.opacity,
    '--snake-play': state === 'offline' ? 'paused' : 'running',
  } as CSSProperties

  return (
    <div
      className={cn('snake-border', radiusClassName, state === 'offline' && 'snake-border--offline', className)}
      style={style}
    >
      {children}
    </div>
  )
}

/** Real agent.status -> snake state. `idle` in the backend means "not yet
 * initialised" (see base_specialized_agent.py), which reads as the agent
 * still coming up -- closer to "waiting" than a calm resting state. */
export function snakeStateForAgent(status: string): SnakeState {
  switch (status) {
    case 'executing': return 'executing'
    case 'online': return 'idle'
    case 'idle': return 'waiting'
    case 'training': return 'thinking'
    case 'error': return 'error'
    case 'offline': return 'offline'
    default: return 'idle'
  }
}

/** Real mission.stage (+ cancelled/result) -> snake state. */
export function snakeStateForMission(stage: string, cancelled: boolean, resultSuccess?: boolean | null): SnakeState {
  if (cancelled) return 'error'
  if (resultSuccess === false) return 'error'
  if (stage === 'archive') return 'offline'
  if (stage === 'execution') return 'executing'
  if (stage === 'human_approval') return 'waiting'
  return 'thinking'
}
