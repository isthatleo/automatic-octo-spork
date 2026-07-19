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
  const scrollRef = useRef<HTMLDivElement>(null)
  const activeWordRef = useRef<HTMLSpanElement>(null)

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
      return [...deactivated, line].slice(-3)
    })
  }, [text])

  // Follow the exact word currently being spoken -- not just "scroll to the
  // bottom", which clipped the start of any line long enough to wrap past
  // the viewport. This keeps the live word centred regardless of sentence
  // length, and nothing gets truncated: no line-clamp, no "…".
  useEffect(() => {
    activeWordRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [lines, tick, wordIndex])

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
  const isSpeakingNow = speaking && lines.some((l) => l.active)

  return (
    <div className="pointer-events-none flex w-full flex-col items-center gap-2.5 px-4 text-center">
      {lines.length === 0 && !interim ? (
        <p className="font-heading text-[0.7rem] tracking-[0.35em] text-muted-foreground/70">
          {placeholder}
        </p>
      ) : null}

      {isSpeakingNow && (
        <div className="flex items-end gap-[3px]" aria-hidden>
          {[0, 1, 2, 3].map((i) => (
            <span
              key={i}
              className="w-[3px] rounded-full bg-primary shadow-[0_0_6px_var(--hud)]"
              style={{
                height: '10px',
                animation: `hud-pulse ${0.5 + i * 0.12}s ease-in-out infinite alternate`,
                animationDelay: `${i * 0.08}s`,
              }}
            />
          ))}
        </div>
      )}

      <div
        ref={scrollRef}
        className="flex max-h-[13rem] w-full flex-col items-center gap-2.5 overflow-y-hidden"
      >
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
                'text-balance leading-relaxed tracking-tight transition-all duration-500 shrink-0',
                isCurrent
                  ? 'font-heading text-lg font-medium text-foreground/95 md:text-xl'
                  : 'line-clamp-1 font-sans text-[0.72rem] md:text-[0.78rem] text-muted-foreground/70',
              )}
            >
              {line.words.map((w, i) => {
                const active = isCurrent && i <= currentIdx
                const isNow = isCurrent && i === currentIdx
                return (
                  <span
                    key={`${line.id}-${i}`}
                    ref={isNow ? activeWordRef : undefined}
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
      </div>

      {interim && (
        <p className="mt-1 inline-flex items-center gap-1.5 rounded-full border border-accent/30 bg-accent/10 px-3 py-1 font-mono text-[0.6rem] tracking-[0.2em] text-accent/90">
          <span className="h-1.5 w-1.5 shrink-0 animate-hud-pulse rounded-full bg-accent" />
          {interim}
        </p>
      )}
      <span className="hidden">{tick}</span>
    </div>
  )
}
