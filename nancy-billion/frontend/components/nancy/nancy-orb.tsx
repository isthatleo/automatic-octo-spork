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
  Arc-reactor identity: a mechanical power core, not an organic blob and not
  the old cockpit instrument (multiple decorative rings, a radar sweep, tick
  marks, orbiting particle debris, a glass "readout" plate).

  The core is a faceted housing -- hexagon casing, a ring of segmented teeth,
  a triangular power cell at the centre -- surrounded by two wave rings and a
  spinning spoke collar. None of it is decorative filler: every reactive
  piece (teeth brightness, spoke length, wave radius, core flare) is driven
  by the same real, smoothed mic/TTS amplitude signal, so the whole assembly
  visibly "runs hotter" exactly when Nancy is actually listening or speaking.
*/

// "Graphite & Ember" palette, matching globals.css's tokens -- precisely
// converted from the same oklch values (via the real OKLab conversion
// matrices, not eyeballed) to rgba for guaranteed Canvas/SVG support.
const HUD = 'rgba(241, 129, 84, 1)'       // ember (--hud / --primary)
const HUD_SOFT = 'rgba(241, 129, 84, 0.5)'
const GOLD = 'rgba(218, 178, 73, 1)'      // mustard gold (--gold)
const PLUM = 'rgba(151, 140, 173, 1)'     // muted plum (--tertiary) -- "thinking"
const ROSE = 'rgba(225, 113, 116, 1)'     // warm rose (--magenta)
const ALERT = 'rgba(229, 76, 74, 1)'      // --destructive

const PARAMS: Record<OrbState, { ringSpeed: number; waveAmp: number; color: string; secondary: string }> = {
  idle:      { ringSpeed: 0.12, waveAmp: 0.04, color: HUD, secondary: PLUM },
  listening: { ringSpeed: 0.3,  waveAmp: 0.3,  color: HUD, secondary: HUD_SOFT },
  thinking:  { ringSpeed: 0.9,  waveAmp: 0.14, color: PLUM, secondary: ROSE },
  speaking:  { ringSpeed: 0.4,  waveAmp: 0.38, color: HUD, secondary: ROSE },
  executing: { ringSpeed: 0.7,  waveAmp: 0.22, color: GOLD, secondary: HUD },
  alert:     { ringSpeed: 0.5,  waveAmp: 0.18, color: ALERT, secondary: GOLD },
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

/** Builds a smooth closed wave ring as an SVG path -- two overlaid sine
 * harmonics whose amplitude scales with real (mic/TTS) sound level, so the
 * ring visibly breathes at idle and genuinely reacts once something's
 * actually being heard, rather than looping a canned wobble. */
function wavePath(cx: number, cy: number, base: number, t: number, amp: number, points = 72): string {
  const pts: [number, number][] = []
  for (let i = 0; i <= points; i++) {
    const a = (i / points) * Math.PI * 2
    const r =
      base +
      Math.sin(a * 3 + t * 1.6) * (0.9 + amp * 3.2) +
      Math.sin(a * 5 - t * 2.3) * (0.5 + amp * 1.8) +
      Math.sin(a * 8 + t * 0.7) * (0.25 + amp * 0.8)
    pts.push([cx + Math.cos(a) * r, cy + Math.sin(a) * r])
  }
  return 'M' + pts.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join('L') + 'Z'
}

const COLLAR_COUNT = 28

/** Reactor collar as one path of independent spoke segments -- each spoke's
 * outer reach jitters on its own phase, weighted by real amplitude, so the
 * whole ring reads as an equalizer responding to actual sound rather than a
 * uniformly-pulsing decoration. The group housing this path still spins in
 * the render loop for the "physically rotating" read. */
function collarPath(cx: number, cy: number, t: number, amp: number): string {
  let d = ''
  for (let i = 0; i < COLLAR_COUNT; i++) {
    const a = (i / COLLAR_COUNT) * Math.PI * 2
    const long = i % 4 === 0
    const rInner = long ? 30.5 : 32.5
    const jitter = Math.sin(t * 3.4 + i * 0.9) * amp * 3.5
    const rOuter = (long ? 39 : 36) + jitter
    const x1 = cx + Math.cos(a) * rInner
    const y1 = cy + Math.sin(a) * rInner
    const x2 = cx + Math.cos(a) * rOuter
    const y2 = cy + Math.sin(a) * rOuter
    d += `M${x1.toFixed(2)},${y1.toFixed(2)}L${x2.toFixed(2)},${y2.toFixed(2)}`
  }
  return d
}

/** Turbine-blade iris ring for the core -- short blades canted tangentially
 * (not plain radial ticks, which read as a toy sunburst) so the shape reads
 * as a precision aperture. Each blade's reach reacts to real amplitude on
 * its own phase, and the whole ring is independently rotated in the render
 * loop for a slow, deliberate spin distinct from the outer collar's. */
function irisPath(cx: number, cy: number, t: number, amp: number, count = 22): string {
  const rInner = 8.5
  const cant = 0.34 // radians of tangential tilt per blade
  let d = ''
  for (let i = 0; i < count; i++) {
    const a = (i / count) * Math.PI * 2
    const pulse = 0.5 + 0.5 * Math.sin(t * 2.2 + i * 1.1)
    const len = 2.6 + pulse * (1.4 + amp * 3.2)
    const a2 = a + cant
    const x1 = cx + Math.cos(a) * rInner
    const y1 = cy + Math.sin(a) * rInner
    const x2 = cx + Math.cos(a2) * (rInner + len)
    const y2 = cy + Math.sin(a2) * (rInner + len)
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
  /** When provided, clicking the sphere fans these out as a quick-nav ring
   * around it. Omit to keep an orb purely a status indicator (e.g. the
   * floating workspace-dock orb). */
  quickNav?: OrbQuickNavItem[]
  onQuickNav?: (key: string) => void
}) {
  const hotRef = useRef<HTMLDivElement>(null)
  const ringRef = useRef<SVGCircleElement>(null)
  const waveRef = useRef<SVGPathElement>(null)
  const waveOuterRef = useRef<SVGPathElement>(null)
  const collarRef = useRef<SVGGElement>(null)
  const collarPathRef = useRef<SVGPathElement>(null)
  const irisGroupRef = useRef<SVGGElement>(null)
  const irisPathRef = useRef<SVGPathElement>(null)
  const lensOuterRef = useRef<SVGCircleElement>(null)
  const lensInnerRef = useRef<SVGCircleElement>(null)
  const coreDiscRef = useRef<SVGCircleElement>(null)
  const stateRef = useRef<OrbState>(state)
  stateRef.current = state
  const micLevel = useMicLevel(state === 'listening')
  const speakingLevel = useElementAudioLevel(audioElement)
  const [menuOpen, setMenuOpen] = useState(false)
  const [hovered, setHovered] = useState(false)
  const gradId = useId().replace(/:/g, '')

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

      // Precision core -- two concentric lens rings hold their geometry
      // (a deliberately still frame of reference), a turbine iris spins
      // and reacts per-blade to real amplitude, and the hot core disc
      // flares with it. Sophistication comes from restraint and layering,
      // not from adding more shapes.
      if (irisGroupRef.current) {
        irisGroupRef.current.style.transform = `rotate(${(t * 14) % 360}deg)`
      }
      if (irisPathRef.current && frame % 2 === 0) {
        irisPathRef.current.setAttribute('d', irisPath(50, 50, t, ampSmoothed))
        irisPathRef.current.setAttribute('opacity', String(0.6 + ampSmoothed * 0.4))
      }
      if (lensOuterRef.current) {
        lensOuterRef.current.setAttribute('opacity', String(0.5 + ampSmoothed * 0.3))
      }
      if (lensInnerRef.current) {
        lensInnerRef.current.setAttribute('stroke-dashoffset', String((-t * 24) % 100))
      }
      if (coreDiscRef.current) {
        const r = 46 + ampSmoothed * 2.2
        coreDiscRef.current.setAttribute('r', String(r))
      }

      // A single thin ring whose radius/opacity breathes with real amplitude.
      if (ringRef.current) {
        const r = 46 + ampSmoothed * 4
        ringRef.current.setAttribute('r', String(r))
        ringRef.current.setAttribute('opacity', String(0.25 + ampSmoothed * 0.35))
      }

      // Two overlaid wave rings -- inner tight to the sphere, outer looser --
      // both driven by the same real smoothed amplitude, so the whole orb
      // feels like it's genuinely resonating rather than just orbited by chrome.
      if (waveRef.current) {
        waveRef.current.setAttribute('d', wavePath(50, 50, 41, t, ampSmoothed))
        waveRef.current.setAttribute('opacity', String(0.35 + ampSmoothed * 0.45))
      }
      if (waveOuterRef.current) {
        waveOuterRef.current.setAttribute('d', wavePath(50, 50, 47.5, -t * 0.8 + 3.1, ampSmoothed * 0.8))
        waveOuterRef.current.setAttribute('opacity', String(0.18 + ampSmoothed * 0.3))
      }

      // Reactor collar -- a ring of energy spokes physically spinning around
      // the core, each spoke's own length reacting to real amplitude
      // (equalizer-style) on top of the whole ring's rotation/state speed.
      if (collarRef.current) {
        collarRef.current.style.transform = `rotate(${(t * (30 + p.ringSpeed * 40)) % 360}deg)`
        collarRef.current.style.opacity = String(0.5 + ampSmoothed * 0.5)
      }
      if (collarPathRef.current && frame % 2 === 0) {
        collarPathRef.current.setAttribute('d', collarPath(50, 50, t, ampSmoothed))
      }

      // Hot specular core -- a small bright point that flares with amplitude,
      // selling "energy source" rather than just a soft gradient blob.
      if (hotRef.current) {
        const flare = 0.55 + ampSmoothed * 0.45
        hotRef.current.style.opacity = String(flare)
        hotRef.current.style.transform = `translate(-50%, -50%) scale(${0.85 + ampSmoothed * 0.35})`
      }

      if (!reduce) t += 0.012 * (0.4 + p.ringSpeed)
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

  return (
    <div className="flex flex-col items-center gap-4">
      <div
        className="relative flex items-center justify-center"
        style={{ width: size, height: size }}
        role="img"
        aria-label={`${name} — ${STATE_LABEL[state]}`}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        {/* soft ambient shadow beneath the sphere -- blur scales with the
            orb's own size instead of a fixed 64px, which at small sizes
            (e.g. the 120px floating dock orb) blew the glow out so far it
            swallowed the sphere entirely and left only a blur visible. */}
        <div
          className="absolute rounded-full transition-colors duration-700"
          style={{ width: '78%', height: '78%', background: alpha(params.color, 0.32), filter: `blur(${size * 0.12}px)` }}
          aria-hidden
        />

        {/* wave rings + reactor collar + one thin state ring */}
        <svg viewBox="0 0 100 100" className="absolute inset-0">
          <g ref={collarRef} style={{ transformOrigin: '50px 50px' }}>
            <path
              ref={collarPathRef}
              fill="none"
              stroke={params.color}
              strokeWidth="0.7"
              strokeLinecap="round"
              style={{ transition: 'stroke 0.6s ease' }}
            />
          </g>
          <path
            ref={waveOuterRef}
            fill="none"
            stroke={params.secondary}
            strokeWidth="0.5"
            style={{ transition: 'stroke 0.6s ease' }}
          />
          <path
            ref={waveRef}
            fill="none"
            stroke={params.color}
            strokeWidth="0.7"
            style={{ transition: 'stroke 0.6s ease' }}
          />
          <circle
            ref={ringRef}
            cx="50"
            cy="50"
            r="46"
            fill="none"
            stroke={params.color}
            strokeWidth="0.35"
            strokeOpacity="0.5"
            strokeDasharray={state === 'thinking' || state === 'executing' ? '3 5' : undefined}
            className={cn(state !== 'idle' && 'animate-hud-spin-slow')}
            style={{ transformOrigin: '50px 50px', transition: 'stroke 0.5s ease' }}
          />
        </svg>

        {/* the sphere itself -- click opens quick-nav when provided */}
        <button
          type="button"
          disabled={!hasQuickNav}
          onClick={() => hasQuickNav && setMenuOpen((v) => !v)}
          className={cn(
            'relative flex items-center justify-center overflow-hidden rounded-full transition-transform duration-300',
            hasQuickNav && 'cursor-pointer',
            hovered && hasQuickNav && 'scale-[1.02]',
          )}
          style={{
            width: '58%',
            height: '58%',
            // Shadow/glow spread scales with size for the same reason as the
            // ambient shadow above -- fixed pixel values overwhelmed small
            // renders like the 120px floating dock orb.
            boxShadow: `0 ${size * 0.055}px ${size * 0.14}px oklch(0 0 0 / 40%), inset 0 1px 0 oklch(1 0 0 / 10%), 0 0 ${size * 0.11}px ${alpha(params.color, 0.35)}`,
            transition: 'box-shadow 0.6s ease',
          }}
          title={hasQuickNav ? 'Open quick navigation' : undefined}
        >
          {/* precision core -- the glow fills the whole sphere (no bare dark
              gap), with two still lens rings and a turbine iris etched into
              it as detail lines rather than floating around a small disc */}
          <svg viewBox="0 0 100 100" className="absolute inset-0">
            <defs>
              <radialGradient id={`orb-core-${gradId}`} cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="oklch(0.98 0.02 90)" />
                <stop offset="22%" stopColor={params.color} stopOpacity="1" />
                <stop offset="60%" stopColor={params.color} stopOpacity="0.85" />
                <stop offset="88%" stopColor={params.secondary} stopOpacity="0.55" />
                <stop offset="100%" stopColor="oklch(0.1 0.006 75)" stopOpacity="0.9" />
              </radialGradient>
            </defs>

            <circle ref={coreDiscRef} cx="50" cy="50" r="47" fill={`url(#orb-core-${gradId})`} />

            <circle
              ref={lensOuterRef}
              cx="50" cy="50" r="19.5"
              fill="none"
              stroke="oklch(0.98 0.02 90 / 55%)"
              strokeWidth="0.5"
              style={{ transition: 'stroke 0.6s ease' }}
            />
            <circle
              ref={lensInnerRef}
              cx="50" cy="50" r="15"
              fill="none"
              stroke="oklch(0.1 0.01 75 / 45%)"
              strokeWidth="0.5"
              strokeDasharray="1.2 2.6"
              style={{ transition: 'stroke 0.6s ease' }}
            />

            <g ref={irisGroupRef} style={{ transformOrigin: '50px 50px' }}>
              <path
                ref={irisPathRef}
                fill="none"
                stroke="oklch(0.99 0.01 90 / 80%)"
                strokeWidth="1"
                strokeLinecap="round"
                style={{ transition: 'stroke 0.6s ease' }}
              />
            </g>
          </svg>

          {/* soft bloom over the core disc -- reads as genuine light spill,
              not a separate decorative element */}
          <div
            ref={hotRef}
            className="pointer-events-none absolute left-1/2 top-1/2 rounded-full"
            style={{
              width: '20%',
              height: '20%',
              background: `radial-gradient(circle, oklch(0.98 0.02 90 / 85%) 0%, ${alpha(params.color, 0.4)} 55%, transparent 78%)`,
              filter: 'blur(3px)',
              mixBlendMode: 'screen',
              transition: 'background 0.6s ease',
            }}
          />
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
