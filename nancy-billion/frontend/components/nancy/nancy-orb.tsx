'use client'

import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { cn } from '@/lib/utils'

export type OrbState =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'speaking'
  | 'executing'
  | 'alert'

/*
  HUD-emblem identity, built from a reference image the user supplied
  directly: a ring with a bright sweeping arc, a scattered field of tick
  marks/particles around it, a soft glow, and the name centred inside --
  no solid sphere body, the centre stays open/transparent.

  Every particle and the sweep arc are driven by the same real, smoothed
  mic/TTS amplitude signal used throughout this component: the tick field
  visibly extends and brightens, and the sweep spins faster, exactly when
  Nancy is actually listening or speaking -- not a looping decoration.
*/

// "Graphite & Ember" palette, matching globals.css's tokens.
const HUD = 'rgba(241, 129, 84, 1)'       // ember (--hud / --primary)
const HUD_SOFT = 'rgba(241, 129, 84, 0.5)'
const GOLD = 'rgba(218, 178, 73, 1)'      // mustard gold (--gold)
const PLUM = 'rgba(151, 140, 173, 1)'     // muted plum (--tertiary) -- "thinking"
const ROSE = 'rgba(225, 113, 116, 1)'     // warm rose (--magenta)
const ALERT = 'rgba(229, 76, 74, 1)'      // --destructive

const PARAMS: Record<OrbState, { speed: number; color: string; secondary: string }> = {
  idle:      { speed: 0.15, color: HUD, secondary: PLUM },
  listening: { speed: 0.4,  color: HUD, secondary: HUD_SOFT },
  thinking:  { speed: 0.95, color: PLUM, secondary: ROSE },
  speaking:  { speed: 0.5,  color: HUD, secondary: ROSE },
  executing: { speed: 0.75, color: GOLD, secondary: HUD },
  alert:     { speed: 0.6,  color: ALERT, secondary: GOLD },
}

const STATE_LABEL: Record<OrbState, string> = {
  idle: 'Standing by',
  listening: 'Listening',
  thinking: 'Thinking',
  speaking: 'Speaking',
  executing: 'Working',
  alert: 'Degraded',
}

function alpha(color: string, a: number): string {
  return color.replace(/[\d.]+\)$/, `${a})`)
}

interface Particle {
  angle: number
  radius: number
  phase: number
  long: boolean
}

/** Deterministic, evenly-scattered particle field (golden-angle spacing so
 * points fill the ring without an obvious repeating lattice, unlike an even
 * division which would look like a plain dial). Generated once per orb
 * instance, not re-randomized every frame. */
function buildParticles(count: number): Particle[] {
  const GOLDEN = 137.50776 * (Math.PI / 180)
  return Array.from({ length: count }, (_, i) => {
    const angle = (i * GOLDEN) % (Math.PI * 2)
    // Deterministic pseudo-random 0..1 from i, no Math.random() (keeps
    // server/client render identical, and the scatter stable across re-mounts).
    const jitter = ((i * 9301 + 49297) % 233280) / 233280
    return {
      angle,
      radius: 37 + jitter * 13,
      phase: (i * 2.399963) % (Math.PI * 2),
      long: i % 6 === 0,
    }
  })
}

/** Builds the tick-mark field as one path -- every particle's reach pulses
 * on its own phase, weighted by real amplitude, so the ring reads as a
 * live radial spectrum rather than a static decoration. */
function particlePath(cx: number, cy: number, t: number, amp: number, particles: Particle[]): string {
  let d = ''
  for (const p of particles) {
    const pulse = 0.5 + 0.5 * Math.sin(t * 2.4 + p.phase)
    const len = (p.long ? 3.4 : 1.5) + pulse * (0.8 + amp * 3.2)
    const x1 = cx + Math.cos(p.angle) * p.radius
    const y1 = cy + Math.sin(p.angle) * p.radius
    const x2 = cx + Math.cos(p.angle) * (p.radius + len)
    const y2 = cy + Math.sin(p.angle) * (p.radius + len)
    d += `M${x1.toFixed(2)},${y1.toFixed(2)}L${x2.toFixed(2)},${y2.toFixed(2)}`
  }
  return d
}

/** Reads live microphone amplitude (0..1). Falls back to 0 silently. */
function useMicLevel(active: boolean) {
  const levelRef = useRef(0)
  useEffect(() => {
    if (!active || typeof navigator === 'undefined' || !navigator.mediaDevices) {
      levelRef.current = 0
      return
    }
    let raf = 0
    let stream: MediaStream | null = null
    let ctx: AudioContext | null = null
    let cancelled = false

    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((s) => {
        if (cancelled) {
          s.getTracks().forEach((t) => t.stop())
          return
        }
        stream = s
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const AC = window.AudioContext || (window as any).webkitAudioContext
        ctx = new AC()
        const src = ctx.createMediaStreamSource(s)
        const analyser = ctx.createAnalyser()
        analyser.fftSize = 256
        src.connect(analyser)
        const data = new Uint8Array(analyser.frequencyBinCount)
        const tick = () => {
          analyser.getByteTimeDomainData(data)
          let sum = 0
          for (let i = 0; i < data.length; i++) {
            const v = (data[i] - 128) / 128
            sum += v * v
          }
          const rms = Math.sqrt(sum / data.length)
          levelRef.current = Math.min(1, rms * 3.5)
          raf = requestAnimationFrame(tick)
        }
        tick()
      })
      .catch(() => {
        levelRef.current = 0
      })

    return () => {
      cancelled = true
      cancelAnimationFrame(raf)
      stream?.getTracks().forEach((t) => t.stop())
      ctx?.close().catch(() => {})
      levelRef.current = 0
    }
  }, [active])
  return levelRef
}

/** Reads live amplitude (0..1) from a playing <audio> element -- the real
 * NeuTTS output (see page.tsx's nancySay), not a fake "speaking" wiggle.
 * Falls back to 0 for the browser Web Speech API path, which exposes no
 * analyzable media element. */
function useElementAudioLevel(el: HTMLAudioElement | null) {
  const levelRef = useRef(0)
  useEffect(() => {
    if (!el) {
      levelRef.current = 0
      return
    }
    let raf = 0
    let ctx: AudioContext | null = null
    let cancelled = false
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const AC = window.AudioContext || (window as any).webkitAudioContext
      ctx = new AC()
      const source = ctx.createMediaElementSource(el)
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 256
      source.connect(analyser)
      analyser.connect(ctx.destination) // keep the audio actually audible
      const data = new Uint8Array(analyser.frequencyBinCount)
      const tick = () => {
        if (cancelled) return
        analyser.getByteTimeDomainData(data)
        let sum = 0
        for (let i = 0; i < data.length; i++) {
          const v = (data[i] - 128) / 128
          sum += v * v
        }
        const rms = Math.sqrt(sum / data.length)
        levelRef.current = Math.min(1, rms * 3.5)
        raf = requestAnimationFrame(tick)
      }
      tick()
    } catch {
      levelRef.current = 0
    }
    return () => {
      cancelled = true
      cancelAnimationFrame(raf)
      ctx?.close().catch(() => {})
      levelRef.current = 0
    }
  }, [el])
  return levelRef
}

export interface OrbQuickNavItem {
  key: string
  label: string
  icon: React.ElementType
  active?: boolean
}

export function NancyOrb({
  state = 'idle',
  name = 'Nancy',
  size = 360,
  audioElement = null,
  quickNav,
  onQuickNav,
}: {
  state?: OrbState
  name?: string
  size?: number
  audioElement?: HTMLAudioElement | null
  /** When provided, clicking the ring fans these out as a quick-nav ring
   * around it. Omit to keep an orb purely a status indicator (e.g. the
   * floating workspace-dock orb). */
  quickNav?: OrbQuickNavItem[]
  onQuickNav?: (key: string) => void
}) {
  const particles = useMemo(() => buildParticles(64), [])
  const particlePathRef = useRef<SVGPathElement>(null)
  const sweepRef = useRef<SVGCircleElement>(null)
  const sweep2Ref = useRef<SVGCircleElement>(null)
  const trackRef = useRef<SVGCircleElement>(null)
  const stateRef = useRef<OrbState>(state)
  stateRef.current = state
  const micLevel = useMicLevel(state === 'listening')
  const speakingLevel = useElementAudioLevel(audioElement)
  const [menuOpen, setMenuOpen] = useState(false)
  const [hovered, setHovered] = useState(false)
  const gradId = useId().replace(/:/g, '')
  const sphereRef = useRef<HTMLButtonElement>(null)
  const outerRef = useRef<HTMLDivElement>(null)
  const [ripples, setRipples] = useState<{ id: number; x: number; y: number }[]>([])
  const rippleSeq = useRef(0)

  // Tilt-toward-cursor -- direct DOM writes (no state) so it stays smooth
  // at 60fps without fighting the rAF loop's own style writes.
  const onMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const el = outerRef.current
    const sphere = sphereRef.current
    if (!el || !sphere) return
    const rect = el.getBoundingClientRect()
    const px = (e.clientX - rect.left) / rect.width - 0.5
    const py = (e.clientY - rect.top) / rect.height - 0.5
    sphere.style.transform = `perspective(700px) rotateX(${(-py * 10).toFixed(2)}deg) rotateY(${(px * 10).toFixed(2)}deg) scale(${hovered ? 1.03 : 1})`
  }
  const onMouseLeave = () => {
    setHovered(false)
    const sphere = sphereRef.current
    if (sphere) sphere.style.transform = 'perspective(700px) rotateX(0deg) rotateY(0deg) scale(1)'
  }
  const onSphereClick = (e: React.MouseEvent<HTMLButtonElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const id = rippleSeq.current++
    setRipples((r) => [...r, { id, x: e.clientX - rect.left, y: e.clientY - rect.top }])
    setTimeout(() => setRipples((r) => r.filter((rp) => rp.id !== id)), 650)
    if (quickNav && quickNav.length > 0) setMenuOpen((v) => !v)
  }

  useEffect(() => {
    const reduce = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let raf = 0
    let t = 0
    let ampSmoothed = 0
    let frame = 0

    const draw = () => {
      const p = PARAMS[stateRef.current]
      const live =
        stateRef.current === 'listening' ? micLevel.current
        : stateRef.current === 'speaking' ? speakingLevel.current
        : 0
      ampSmoothed += (live - ampSmoothed) * 0.12

      frame++

      // Scattered tick field -- every particle pulses on its own phase,
      // real amplitude widens the whole field's reach and brightness.
      if (particlePathRef.current && frame % 2 === 0) {
        particlePathRef.current.setAttribute('d', particlePath(50, 50, t, ampSmoothed, particles))
        particlePathRef.current.setAttribute('opacity', String(0.55 + ampSmoothed * 0.4))
      }

      // Bright sweep arc -- the loading-ring read from the reference,
      // spinning faster and glowing harder with real amplitude/state speed.
      if (sweepRef.current) {
        sweepRef.current.style.transform = `rotate(${(t * 70 * (0.6 + p.speed)) % 360}deg)`
      }
      if (sweep2Ref.current) {
        sweep2Ref.current.style.transform = `rotate(${(-t * 40 * (0.6 + p.speed) + 180) % 360}deg)`
        sweep2Ref.current.setAttribute('opacity', String(0.3 + ampSmoothed * 0.4))
      }
      if (trackRef.current) {
        trackRef.current.setAttribute('opacity', String(0.18 + ampSmoothed * 0.12))
      }

      if (!reduce) t += 0.014 * (0.5 + p.speed)
      raf = requestAnimationFrame(draw)
    }
    draw()

    const onVis = () => {
      if (document.hidden) cancelAnimationFrame(raf)
      else raf = requestAnimationFrame(draw)
    }
    document.addEventListener('visibilitychange', onVis)
    return () => {
      cancelAnimationFrame(raf)
      document.removeEventListener('visibilitychange', onVis)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [particles])

  const params = PARAMS[state]
  const hasQuickNav = !!quickNav && quickNav.length > 0
  const circumference = 2 * Math.PI * 34

  return (
    <div className="flex flex-col items-center gap-4">
      <div
        ref={outerRef}
        className="relative flex items-center justify-center"
        style={{ width: size, height: size }}
        role="img"
        aria-label={`${name} — ${STATE_LABEL[state]}`}
        onMouseEnter={() => setHovered(true)}
        onMouseMove={onMouseMove}
        onMouseLeave={onMouseLeave}
      >
        {/* soft ambient glow -- blur scales with the orb's own size instead
            of a fixed px value, which at small sizes (e.g. the 120px
            floating dock orb) blew the glow out so far it swallowed
            everything else. */}
        <div
          className="absolute rounded-full transition-colors duration-700"
          style={{ width: '80%', height: '80%', background: alpha(params.color, 0.22), filter: `blur(${size * 0.13}px)` }}
          aria-hidden
        />

        {/* the emblem itself -- click opens quick-nav when provided, tilts
            toward the cursor on hover, and ripples on every click. No
            solid sphere body: the centre stays open, matching the
            reference -- a ring, a scattered tick field, and the name. */}
        <button
          ref={sphereRef}
          type="button"
          onClick={onSphereClick}
          className="relative flex cursor-pointer items-center justify-center transition-transform duration-300 ease-out"
          style={{ width: '100%', height: '100%' }}
          title={hasQuickNav ? 'Open quick navigation' : 'Nancy'}
        >
          {ripples.map((r) => (
            <span
              key={r.id}
              className="pointer-events-none absolute rounded-full"
              style={{
                left: r.x, top: r.y, width: 4, height: 4,
                background: 'oklch(0.98 0.02 90 / 60%)',
                transform: 'translate(-50%, -50%)',
                animation: 'hud-ripple 0.65s ease-out forwards',
              }}
            />
          ))}

          <svg viewBox="0 0 100 100" className="absolute inset-0 overflow-visible">
            {/* scattered particle field -- real audio-reactive tick marks */}
            <path
              ref={particlePathRef}
              fill="none"
              stroke={params.color}
              strokeWidth="0.6"
              strokeLinecap="round"
              style={{ transition: 'stroke 0.6s ease', filter: `drop-shadow(0 0 1.5px ${alpha(params.color, 0.6)})` }}
            />

            {/* dim full track ring */}
            <circle
              ref={trackRef}
              cx="50" cy="50" r="34"
              fill="none"
              stroke={params.secondary}
              strokeWidth="0.7"
              style={{ transition: 'stroke 0.6s ease' }}
            />

            {/* bright sweep arcs -- the "loading ring" read, two counter-
                rotating segments for depth */}
            <circle
              ref={sweepRef}
              cx="50" cy="50" r="34"
              fill="none"
              stroke={params.color}
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeDasharray={`${circumference * 0.22} ${circumference}`}
              style={{ transformOrigin: '50px 50px', transition: 'stroke 0.6s ease', filter: `drop-shadow(0 0 3px ${params.color})` }}
            />
            <circle
              ref={sweep2Ref}
              cx="50" cy="50" r="34"
              fill="none"
              stroke={params.secondary}
              strokeWidth="1"
              strokeLinecap="round"
              strokeDasharray={`${circumference * 0.12} ${circumference}`}
              style={{ transformOrigin: '50px 50px', transition: 'stroke 0.6s ease' }}
            />
          </svg>

          {/* name badge -- centred, the ring's centre stays open behind it */}
          <div className="relative flex flex-col items-center">
            <span
              className="font-sans text-[0.85em] font-semibold tracking-[0.18em] text-foreground transition-colors duration-500"
              style={{ fontSize: size * 0.09, textShadow: `0 0 ${size * 0.04}px ${alpha(params.color, 0.55)}` }}
            >
              {name.toUpperCase()}
            </span>
          </div>
        </button>

        {/* quick-nav ring */}
        {hasQuickNav && (
          <div
            className={cn('pointer-events-none absolute inset-0 transition-opacity duration-300', menuOpen ? 'opacity-100' : 'opacity-0')}
            aria-hidden={!menuOpen}
          >
            {quickNav!.map((item, i) => {
              const n = quickNav!.length
              const angle = (i / n) * Math.PI * 2 - Math.PI / 2
              const radius = size * 0.44
              const x = Math.cos(angle) * radius
              const y = Math.sin(angle) * radius
              const Icon = item.icon
              return (
                <button
                  key={item.key}
                  type="button"
                  title={item.label}
                  onClick={() => { onQuickNav?.(item.key); setMenuOpen(false) }}
                  className={cn(
                    'absolute flex h-9 w-9 items-center justify-center rounded-full border transition-all duration-300',
                    menuOpen ? 'pointer-events-auto scale-100' : 'scale-0',
                    item.active
                      ? 'border-primary bg-primary/20 text-primary'
                      : 'border-border bg-card text-muted-foreground hover:border-primary/50 hover:text-foreground',
                  )}
                  style={{
                    left: '50%',
                    top: '50%',
                    transform: menuOpen ? `translate(calc(-50% + ${x}px), calc(-50% + ${y}px))` : 'translate(-50%, -50%)',
                    transitionDelay: menuOpen ? `${i * 30}ms` : '0ms',
                  }}
                >
                  <Icon className="h-4 w-4" />
                </button>
              )
            })}
          </div>
        )}
      </div>

      {/* caption below the ring */}
      <div className="text-center">
        <div
          key={state}
          className="animate-[hud-fade-in_0.4s_ease] text-[0.7rem] transition-colors duration-500"
          style={{ color: state === 'idle' ? 'var(--muted-foreground)' : params.color }}
        >
          {STATE_LABEL[state]}
        </div>
      </div>
    </div>
  )
}
