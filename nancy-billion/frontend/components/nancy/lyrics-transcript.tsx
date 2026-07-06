'use client'

import { useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/utils'

export interface LyricsTranscriptProps {
  /** Current utterance being spoken. Changing this string starts a new lyric line. */
  text: string
  /** True while TTS is actively speaking `text`. When it goes false the line finishes. */
  speaking: boolean
  /**
   * When provided (>= 0), highlights up to and including this word index in the
   * current line — driven by real TTS `onboundary` events for perfect sync.
   * Set to `-1` to fall back to time-based estimation.
   */
  wordIndex?: number
  /** Optional interim user speech to show at the bottom. */
  interim?: string
  /** Optional prompt shown when there's nothing to render. */
  placeholder?: string
}

interface Line {
  id: number
  text: string
  words: string[]
  startedAt: number
  durationMs: number
  active: boolean
}

let lineSeq = 0

/**
 * Apple Music / Spotify-style lyrics transcript for Nancy's speech.
 * Words in the active line light up in sequence as she speaks.
 */
export function LyricsTranscript({
  text,
  speaking,
  wordIndex,
  interim,
  placeholder = 'Say "Nancy", "Billion" or "Jarvis" to begin.',
}: LyricsTranscriptProps) {
  const [lines, setLines] = useState<Line[]>([])
  const [tick, setTick] = useState(0)
  const lastTextRef = useRef<string>('')

  useEffect(() => {
    const t = text.trim()
    if (!t || t === lastTextRef.current) return
    lastTextRef.current = t
    const words = t.split(/\s+/)
    const durationMs = Math.min(14000, 900 + words.length * 320)
    const line: Line = {
      id: ++lineSeq,
      text: t,
      words,
      startedAt: performance.now(),
      durationMs,
      active: true,
    }
    setLines((prev) => {
      const deactivated = prev.map((l) => ({ ...l, active: false }))
      return [...deactivated, line].slice(-4)
    })
  }, [text])

  useEffect(() => {
    if (speaking) return
    setLines((prev) =>
      prev.map((l, i) =>
        i === prev.length - 1 ? { ...l, active: false } : l,
      ),
    )
  }, [speaking])

  // Fallback time-based animation when wordIndex isn't driven.
  useEffect(() => {
    if (wordIndex !== undefined && wordIndex >= 0) return
    if (!lines.some((l) => l.active)) return
    let raf = 0
    const loop = () => {
      setTick((n) => (n + 1) % 100000)
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [lines, wordIndex])

  const now = performance.now()

  return (
    <div className="pointer-events-none flex w-full flex-col items-center gap-2 px-4 text-center">
      {lines.length === 0 && !interim ? (
        <p className="text-[0.7rem] uppercase tracking-[0.35em] text-muted-foreground/70">
          {placeholder}
        </p>
      ) : null}

      {lines.map((line, idx) => {
        const isCurrent = line.active
        let currentIdx: number
        if (isCurrent && wordIndex !== undefined && wordIndex >= 0) {
          currentIdx = Math.min(line.words.length - 1, wordIndex)
        } else {
          const elapsed = now - line.startedAt
          const perWord = line.durationMs / Math.max(1, line.words.length)
          currentIdx = Math.floor(elapsed / perWord)
        }
        const opacity = isCurrent
          ? 1
          : Math.max(0.15, 0.55 - (lines.length - 1 - idx) * 0.15)
        return (
          <p
            key={line.id}
            style={{ opacity }}
            className={cn(
              'text-balance font-medium leading-relaxed tracking-tight transition-all duration-500',
              isCurrent
                ? 'text-base md:text-lg text-foreground/95'
                : 'text-[0.72rem] md:text-[0.78rem] text-muted-foreground/70',
            )}
          >
            {line.words.map((w, i) => {
              const active = isCurrent && i <= currentIdx
              const isNow = isCurrent && i === currentIdx
              return (
                <span
                  key={`${line.id}-${i}`}
                  className={cn(
                    'mx-[0.15em] inline-block transition-all duration-300',
                    active ? 'text-primary' : 'opacity-45',
                    isNow && 'text-primary drop-shadow-[0_0_10px_var(--hud)]',
                  )}
                >
                  {w}
                </span>
              )
            })}
          </p>
        )
      })}

      {interim && (
        <p className="mt-1 text-[0.6rem] uppercase tracking-[0.25em] text-accent/70">
          <span className="opacity-60">you · </span>
          {interim}
        </p>
      )}
      <span className="hidden">{tick}</span>
    </div>
  )
}
