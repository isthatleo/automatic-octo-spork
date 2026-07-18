'use client'

import { useEffect, useId, useRef, useState } from 'react'
import { cn } from '@/lib/utils'

export type OrbState =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'speaking'
  | 'executing'
  | 'alert'

/*
  Liquid metal identity: a smooth molten-metal sphere, not a machine part.
  Every earlier pass (plasma blobs, a mechanical reactor, a precision core
  with lens rings/turbine iris) added geometry -- rings, spokes, facets.
  This one removes it. The only moving pieces are the metal's own surface:
  a real SVG feTurbulence/feDisplacementMap filter warps the fill into
  genuine liquid ripples (not a hand-animated wobble), and its displacement
  scale is driven directly by real mic/TTS amplitude -- the surface
  visibly gets more turbulent exactly when Nancy is actually listening or
  speaking, and settles to an almost-still mirror at idle.
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
  listening: { speed: 0.35, color: HUD, secondary: HUD_SOFT },
  thinking:  { speed: 0.85, color: PLUM, secondary: ROSE },
  speaking:  { speed: 0.45, color: HUD, secondary: ROSE },
  executing: { speed: 0.65, color: GOLD, secondary: HUD },
  alert:     { speed: 0.5,  color: ALERT, secondary: GOLD },
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
  /** When provided, clicking the sphere fans these out as a quick-nav ring
   * around it. Omit to keep an orb purely a status indicator (e.g. the
   * floating workspace-dock orb). */
  quickNav?: OrbQuickNavItem[]
  onQuickNav?: (key: string) => void
}) {
  const turbRef = useRef<SVGFETurbulenceElement>(null)
  const dispRef = useRef<SVGFEDisplacementMapElement>(null)
  const spec1Ref = useRef<SVGCircleElement>(null)
  const spec2Ref = useRef<SVGCircleElement>(null)
  const rimRef = useRef<SVGCircleElement>(null)
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
    sphere.style.transform = `perspective(600px) rotateX(${(-py * 14).toFixed(2)}deg) rotateY(${(px * 14).toFixed(2)}deg) scale(${hovered ? 1.03 : 1})`
  }
  const onMouseLeave = () => {
    setHovered(false)
    const sphere = sphereRef.current
    if (sphere) sphere.style.transform = 'perspective(600px) rotateX(0deg) rotateY(0deg) scale(1)'
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

      // The liquid surface itself -- a real turbulence field slowly
      // morphing (baseFrequency drifts on its own clock) and warping the
      // metal fill more violently the louder the real audio gets.
      if (frame % 2 === 0) {
        if (turbRef.current) {
          const freq = 0.016 + Math.sin(t * 0.5) * 0.005
          turbRef.current.setAttribute('baseFrequency', freq.toFixed(4))
        }
        if (dispRef.current) {
          const scale = 2 + ampSmoothed * 13
          dispRef.current.setAttribute('scale', scale.toFixed(2))
        }
      }

      // Two specular highlights drift across the surface like light
      // reflecting off a moving liquid -- real amplitude widens their
      // orbit and brightens the effect, everything else is idle drift.
      if (spec1Ref.current) {
        const spread = 1 + ampSmoothed * 0.6
        const x = 50 + Math.cos(t * 0.42) * 16 * spread
        const y = 50 + Math.sin(t * 0.34 + 1.1) * 14 * spread
        spec1Ref.current.setAttribute('cx', x.toFixed(2))
        spec1Ref.current.setAttribute('cy', y.toFixed(2))
        spec1Ref.current.setAttribute('opacity', (0.55 + ampSmoothed * 0.4).toFixed(2))
      }
      if (spec2Ref.current) {
        const spread = 1 + ampSmoothed * 0.5
        const x = 50 + Math.cos(-t * 0.3 + 2.4) * 20 * spread
        const y = 50 + Math.sin(-t * 0.37 + 0.6) * 18 * spread
        spec2Ref.current.setAttribute('cx', x.toFixed(2))
        spec2Ref.current.setAttribute('cy', y.toFixed(2))
        spec2Ref.current.setAttribute('opacity', (0.35 + ampSmoothed * 0.35).toFixed(2))
      }

      // Fresnel rim light -- the bright edge a liquid metal sphere always
      // shows at a grazing angle, breathing gently with real amplitude.
      if (rimRef.current) {
        rimRef.current.setAttribute('opacity', (0.35 + ampSmoothed * 0.4).toFixed(2))
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
  }, [])

  const params = PARAMS[state]
  const hasQuickNav = !!quickNav && quickNav.length > 0
  const filterId = `orb-liquid-${gradId}`
  const baseGradId = `orb-base-${gradId}`

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
        {/* soft ambient shadow beneath the sphere -- blur scales with the
            orb's own size instead of a fixed px value, which at small
            sizes (e.g. the 120px floating dock orb) blew the glow out so
            far it swallowed the sphere entirely. */}
        <div
          className="absolute rounded-full transition-colors duration-700"
          style={{ width: '72%', height: '72%', background: alpha(params.color, 0.28), filter: `blur(${size * 0.11}px)` }}
          aria-hidden
        />

        {/* the sphere itself -- click opens quick-nav when provided, tilts
            toward the cursor on hover, and ripples on every click. */}
        <button
          ref={sphereRef}
          type="button"
          onClick={onSphereClick}
          className="relative flex cursor-pointer items-center justify-center overflow-hidden rounded-full transition-transform duration-300 ease-out"
          style={{
            width: '58%',
            height: '58%',
            boxShadow: `0 ${size * 0.055}px ${size * 0.14}px oklch(0 0 0 / 40%), inset 0 1px 0 oklch(1 0 0 / 10%), 0 0 ${size * 0.1}px ${alpha(params.color, 0.3)}`,
            transition: 'box-shadow 0.6s ease, transform 0.15s ease-out',
          }}
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

          {/* liquid metal surface -- a real SVG turbulence/displacement
              filter warps the metal fill into genuine ripples, not a
              hand-tuned wobble. Two drifting specular highlights read as
              light sliding across a moving liquid. */}
          <svg viewBox="0 0 100 100" className="absolute inset-0">
            <defs>
              <filter id={filterId} x="-30%" y="-30%" width="160%" height="160%">
                <feTurbulence ref={turbRef} type="fractalNoise" baseFrequency="0.016" numOctaves="2" seed="7" result="noise" />
                <feDisplacementMap ref={dispRef} in="SourceGraphic" in2="noise" scale="2" xChannelSelector="R" yChannelSelector="G" result="warped" />
                <feGaussianBlur in="warped" stdDeviation="0.35" />
              </filter>
              <radialGradient id={baseGradId} cx="38%" cy="28%" r="80%">
                <stop offset="0%" stopColor="oklch(0.93 0.02 90)" />
                <stop offset="30%" stopColor={params.color} stopOpacity="0.92" />
                <stop offset="66%" stopColor={params.secondary} stopOpacity="0.55" />
                <stop offset="100%" stopColor="oklch(0.07 0.006 75)" />
              </radialGradient>
            </defs>

            <g style={{ filter: `url(#${filterId})`, transition: 'filter 0.4s ease' }}>
              <circle cx="50" cy="50" r="48" fill={`url(#${baseGradId})`} />
              <circle ref={spec1Ref} cx="42" cy="34" r="9" fill="oklch(0.99 0.01 95 / 65%)" />
              <circle ref={spec2Ref} cx="62" cy="60" r="6" fill={alpha(params.color, 0.55)} />
            </g>

            {/* crisp rim light -- outside the liquid filter so it stays sharp */}
            <circle
              ref={rimRef}
              cx="50" cy="50" r="47.6"
              fill="none"
              stroke="oklch(0.97 0.02 90 / 45%)"
              strokeWidth="0.6"
              style={{ transition: 'stroke 0.6s ease' }}
            />
          </svg>

          <div
            className="pointer-events-none absolute inset-0 rounded-full"
            style={{ background: 'radial-gradient(ellipse at 32% 24%, oklch(1 0 0 / 10%) 0%, transparent 45%)' }}
          />
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

      {/* caption below the sphere, not a glowing plate inside it */}
      <div className="text-center">
        <div className="font-display text-2xl text-foreground">{name}</div>
        <div
          key={state}
          className="mt-0.5 animate-[hud-fade-in_0.4s_ease] text-[0.7rem] transition-colors duration-500"
          style={{ color: state === 'idle' ? 'var(--muted-foreground)' : params.color }}
        >
          {STATE_LABEL[state]}
        </div>
      </div>
    </div>
  )
}
