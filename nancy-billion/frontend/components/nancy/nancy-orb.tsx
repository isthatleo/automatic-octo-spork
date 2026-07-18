'use client'

import { useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/utils'

export type OrbState =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'speaking'
  | 'executing'
  | 'alert'

const HUD = 'rgba(56, 211, 235, 1)'
const HUD_SOFT = 'rgba(56, 211, 235, 0.55)'
const AMBER = 'rgba(232, 178, 70, 1)'
// Matches the design system's --tertiary token -- gives "thinking" its own
// identity instead of looking identical to idle/listening (both cyan).
const VIOLET = 'rgba(196, 130, 235, 1)'
// A real degraded-mode signal (e.g. speech recognition unsupported in this
// browser) gets its own honest color instead of pretending everything's fine.
const ALERT = 'rgba(235, 90, 90, 1)'

// Per-state animation parameters driving the canvas + plasma core.
const PARAMS: Record<
  OrbState,
  {
    ringSpeed: number
    particleSpeed: number
    particleCount: number
    waveAmp: number
    waveSpeed: number
    color: string
    secondary: string
  }
> = {
  idle:      { ringSpeed: 0.15, particleSpeed: 0.2, particleCount: 48, waveAmp: 0.05, waveSpeed: 1.2, color: HUD, secondary: VIOLET },
  listening: { ringSpeed: 0.35, particleSpeed: 0.5, particleCount: 64, waveAmp: 0.35, waveSpeed: 3,   color: HUD, secondary: HUD_SOFT },
  thinking:  { ringSpeed: 1.1,  particleSpeed: 1.4, particleCount: 90, waveAmp: 0.18, waveSpeed: 4.5, color: VIOLET, secondary: HUD },
  speaking:  { ringSpeed: 0.5,  particleSpeed: 0.7, particleCount: 72, waveAmp: 0.45, waveSpeed: 6,   color: HUD, secondary: AMBER },
  executing: { ringSpeed: 0.9,  particleSpeed: 1.8, particleCount: 110, waveAmp: 0.3, waveSpeed: 5,   color: AMBER, secondary: HUD },
  alert:     { ringSpeed: 0.6,  particleSpeed: 0.4, particleCount: 40, waveAmp: 0.22, waveSpeed: 2.5, color: ALERT, secondary: AMBER },
}

const STATE_LABEL: Record<OrbState, string> = {
  idle: 'Standing By',
  listening: 'Listening',
  thinking: 'Processing',
  speaking: 'Responding',
  executing: 'Executing',
  alert: 'Degraded',
}

/** Strips the alpha channel off an `rgba(r,g,b,a)` string and substitutes a
 * new one -- used everywhere below to derive translucent variants of a
 * state's color without hardcoding a parallel palette. */
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
      // createMediaElementSource throws if called twice on the same element,
      // or if the browser blocks it -- fail silently, orb just shows no
      // audio-reactivity for this utterance rather than crashing.
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
  name = 'NÅNCY',
  size = 360,
  audioElement = null,
  quickNav,
  onQuickNav,
}: {
  state?: OrbState
  name?: string
  size?: number
  /** The <audio> element currently playing Nancy's real TTS output, if any
   * (see page.tsx's nancySay) -- drives real audio-reactivity while
   * speaking instead of a fixed decorative wobble. */
  audioElement?: HTMLAudioElement | null
  /** When provided, clicking the orb's core fans these out as a radial
   * quick-nav menu around it instead of doing nothing. Omit to keep an orb
   * purely decorative (e.g. the floating workspace-dock orb). */
  quickNav?: OrbQuickNavItem[]
  onQuickNav?: (key: string) => void
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const coreRef = useRef<HTMLDivElement>(null)
  const stateRef = useRef<OrbState>(state)
  stateRef.current = state
  const micLevel = useMicLevel(state === 'listening')
  const speakingLevel = useElementAudioLevel(audioElement)
  const [menuOpen, setMenuOpen] = useState(false)
  const [hovered, setHovered] = useState(false)
  const [liveAmp, setLiveAmp] = useState(0)

  // Particle + waveform engine on canvas, plus the plasma core's animated
  // multi-blob background (driven from the same rAF loop so they never
  // drift out of sync with each other).
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // Low-end heuristic: cap DPR + shrink particle pool on small viewports/mobile.
    const isSmall = Math.min(window.innerWidth, window.innerHeight) < 640
    const hwCores = (navigator as unknown as { hardwareConcurrency?: number }).hardwareConcurrency ?? 8
    const lowPower = isSmall || hwCores <= 4
    const dpr = Math.min(lowPower ? 1.25 : 1.75, window.devicePixelRatio || 1)
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let raf = 0
    let t = 0
    let frame = 0
    // Cap effective FPS to ~40 on low-power to save GPU without visible jank.
    const frameSkip = lowPower ? 1 : 0

    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      canvas.width = rect.width * dpr
      canvas.height = rect.height * dpr
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(canvas)

    type P = { angle: number; radius: number; speed: number; sz: number; off: number }
    const poolSize = reduce ? 40 : lowPower ? 70 : 120
    const particles: P[] = Array.from({ length: poolSize }).map(() => ({
      angle: Math.random() * Math.PI * 2,
      radius: 0.55 + Math.random() * 0.42,
      speed: 0.2 + Math.random() * 0.8,
      sz: 0.6 + Math.random() * 1.8,
      off: Math.random() * Math.PI * 2,
    }))

    let pulse = 0 // expanding shockwave for "executing"
    let prevState: OrbState = stateRef.current
    let ampSmoothed = 0
    let ampTickCounter = 0

    const draw = () => {
      const w = canvas.width
      const h = canvas.height
      const cx = w / 2
      const cy = h / 2
      const R = Math.min(w, h) / 2
      const p = PARAMS[stateRef.current]

      ctx.clearRect(0, 0, w, h)

      // trigger a shockwave when entering "executing"
      if (stateRef.current === 'executing' && prevState !== 'executing') {
        pulse = 0.001
      }
      prevState = stateRef.current

      // ---- outer glow halo ----
      const breathe = 1 + Math.sin(t * 1.5) * 0.03
      const haloR = R * 0.9 * breathe
      const halo = ctx.createRadialGradient(cx, cy, R * 0.2, cx, cy, haloR)
      halo.addColorStop(0, alpha(p.color, 0.18))
      halo.addColorStop(0.6, alpha(p.color, 0.06))
      halo.addColorStop(1, 'rgba(0,0,0,0)')
      ctx.fillStyle = halo
      ctx.fillRect(0, 0, w, h)

      // ---- expanding pulse waves (executing) ----
      if (pulse > 0) {
        pulse += 0.012
        const pr = R * pulse
        ctx.beginPath()
        ctx.arc(cx, cy, pr, 0, Math.PI * 2)
        ctx.strokeStyle = alpha(AMBER, Math.max(0, 0.6 - pulse * 0.6))
        ctx.lineWidth = 2 * dpr
        ctx.stroke()
        if (pulse >= 1) pulse = stateRef.current === 'executing' ? 0.001 : 0
      }

      // ---- audio-reactive waveform ring ----
      const live =
        stateRef.current === 'listening'
          ? micLevel.current
          : stateRef.current === 'speaking'
            ? speakingLevel.current
            : 0
      const amp = (p.waveAmp + live * 0.6) * R * 0.16
      const baseR = R * 0.6
      const segs = 160
      ctx.beginPath()
      for (let i = 0; i <= segs; i++) {
        const a = (i / segs) * Math.PI * 2
        const wobble =
          Math.sin(a * 6 + t * p.waveSpeed) * 0.6 +
          Math.sin(a * 11 - t * p.waveSpeed * 0.7) * 0.4
        const rr = baseR + wobble * amp
        const x = cx + Math.cos(a) * rr
        const y = cy + Math.sin(a) * rr
        if (i === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      }
      ctx.closePath()
      ctx.strokeStyle = p.color
      ctx.lineWidth = 1.5 * dpr
      ctx.shadowBlur = 12 * dpr
      ctx.shadowColor = p.color
      ctx.stroke()
      ctx.shadowBlur = 0

      // ---- orbiting particle system (clamped to pool + low-power scale) ----
      const scale = lowPower ? 0.7 : 1
      const count = Math.min(particles.length, Math.floor(p.particleCount * scale))
      for (let i = 0; i < count; i++) {
        const pt = particles[i]
        pt.angle += pt.speed * p.particleSpeed * 0.01
        const r = baseR + (pt.radius - 0.6) * R * 0.5 + Math.sin(t + pt.off) * R * 0.02
        const x = cx + Math.cos(pt.angle) * r
        const y = cy + Math.sin(pt.angle) * r
        ctx.beginPath()
        ctx.arc(x, y, pt.sz * dpr, 0, Math.PI * 2)
        ctx.fillStyle = alpha(p.color, 0.4 + Math.sin(t * 2 + pt.off) * 0.3 + 0.3)
        ctx.fill()
      }

      // ---- plasma core: 3 animated blobs composited via layered radial
      // gradients on the DOM core element, cheaper than per-pixel canvas
      // noise and lets the existing glass-highlight/scan-line stay layered
      // on top untouched. Real audio amplitude pushes the blobs further
      // apart ("bulging") while speaking/listening. ----
      ampSmoothed += (live - ampSmoothed) * 0.15
      ampTickCounter++
      if (coreRef.current && ampTickCounter % 2 === 0) {
        const spread = 1 + ampSmoothed * 0.6
        const b1x = 50 + Math.cos(t * 0.6) * 24 * spread
        const b1y = 50 + Math.sin(t * 0.6) * 24 * spread
        const b2x = 50 + Math.cos(-t * 0.45 + 2.1) * 17 * spread
        const b2y = 50 + Math.sin(-t * 0.45 + 2.1) * 17 * spread
        const b3x = 50 + Math.cos(t * 0.8 + 4.2) * 13 * spread
        const b3y = 50 + Math.sin(t * 0.8 + 4.2) * 13 * spread
        coreRef.current.style.background = [
          `radial-gradient(circle at ${b1x}% ${b1y}%, ${alpha(p.color, 0.9)} 0%, transparent 55%)`,
          `radial-gradient(circle at ${b2x}% ${b2y}%, ${alpha(p.secondary, 0.55)} 0%, transparent 50%)`,
          `radial-gradient(circle at ${b3x}% ${b3y}%, ${alpha(p.color, 0.6)} 0%, transparent 45%)`,
          `radial-gradient(circle at 35% 30%, rgba(240,252,255,0.95) 0%, ${alpha(p.color, 0.85)} 28%, rgba(20,60,90,0.88) 68%, rgba(6,12,22,0.96) 100%)`,
        ].join(',')
        if (ampTickCounter % 6 === 0) setLiveAmp(ampSmoothed)
      }

      if (!reduce) t += 0.016 * (0.5 + p.ringSpeed)
      frame++
      // On low-power devices, halve the RAF cadence with setTimeout(~25ms)
      if (frameSkip && frame % 2 === 0) {
        raf = window.setTimeout(() => requestAnimationFrame(draw), 25) as unknown as number
      } else {
        raf = requestAnimationFrame(draw)
      }
    }
    draw()

    const onVis = () => {
      if (document.hidden) {
        cancelAnimationFrame(raf)
        clearTimeout(raf)
      } else {
        raf = requestAnimationFrame(draw)
      }
    }
    document.addEventListener('visibilitychange', onVis)

    return () => {
      cancelAnimationFrame(raf)
      clearTimeout(raf)
      document.removeEventListener('visibilitychange', onVis)
      ro.disconnect()
    }
    // micLevel is a stable ref; PARAMS read live via stateRef
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const params = PARAMS[state]
  const hasQuickNav = !!quickNav && quickNav.length > 0

  return (
    <div
      className="relative flex items-center justify-center"
      style={{ width: size, height: size, perspective: 1000 }}
      role="img"
      aria-label={`${name} assistant orb — ${STATE_LABEL[state]}`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* canvas: halo, waveform, particles, pulse waves */}
      <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" />

      {/* ── tilted 3D orbit rings (Saturn-style), each carrying real orbiting
          nodes riding the ring's own rotation -- no per-frame JS needed,
          pure CSS transform animation ── */}
      <div
        className="absolute inset-0 animate-orbit-a"
        style={{ transformStyle: 'preserve-3d' }}
        aria-hidden
      >
        <div
          className="absolute inset-[2%] rounded-full"
          style={{ border: `1px solid ${alpha(params.color, 0.45)}`, boxShadow: `0 0 14px ${alpha(params.color, 0.25)}` }}
        >
          <span
            className="absolute left-1/2 top-0 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full"
            style={{ background: params.color, boxShadow: `0 0 8px ${params.color}` }}
          />
        </div>
      </div>
      <div
        className="absolute inset-0 animate-orbit-b"
        style={{ transformStyle: 'preserve-3d' }}
        aria-hidden
      >
        <div
          className="absolute inset-[16%] rounded-full"
          style={{ border: `1px dashed ${alpha(params.secondary, 0.4)}` }}
        >
          <span
            className="absolute left-1/2 top-0 h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full"
            style={{ background: params.secondary, boxShadow: `0 0 6px ${params.secondary}` }}
          />
        </div>
      </div>
      <div
        className={cn('absolute inset-0', state === 'thinking' ? 'animate-orbit-c-fast' : 'animate-orbit-c')}
        style={{ transformStyle: 'preserve-3d' }}
        aria-hidden
      >
        <div
          className="absolute inset-[30%] rounded-full"
          style={{ border: `1.5px solid ${alpha(params.color, 0.55)}` }}
        >
          <span
            className="absolute left-1/2 top-0 h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full"
            style={{ background: params.color, boxShadow: `0 0 6px ${params.color}` }}
          />
          <span
            className="absolute left-1/2 bottom-0 h-1 w-1 -translate-x-1/2 translate-y-1/2 rounded-full opacity-70"
            style={{ background: params.secondary }}
          />
        </div>
      </div>

      {/* counter-rotating flat tick ring (kept flat -- reads as a HUD dial
          rather than an orbit, deliberately different from the tilted rings) */}
      <svg
        viewBox="0 0 200 200"
        className="absolute animate-hud-spin-rev"
        style={{ width: '58%', height: '58%' }}
      >
        {Array.from({ length: 48 }).map((_, i) => {
          const a = (i / 48) * Math.PI * 2
          const x1 = 100 + Math.cos(a) * 96
          const y1 = 100 + Math.sin(a) * 96
          const x2 = 100 + Math.cos(a) * (i % 4 === 0 ? 84 : 90)
          const y2 = 100 + Math.sin(a) * (i % 4 === 0 ? 84 : 90)
          return (
            <line
              key={i}
              x1={x1} y1={y1} x2={x2} y2={y2}
              stroke={HUD}
              strokeWidth={i % 4 === 0 ? 1.4 : 0.6}
              opacity={i % 4 === 0 ? 0.8 : 0.3}
            />
          )
        })}
      </svg>

      {/* ── live data readout, real amplitude, not decorative ── */}
      <div
        className="pointer-events-none absolute left-1/2 top-[6%] -translate-x-1/2 whitespace-nowrap font-mono text-[0.5rem] tracking-widest transition-opacity duration-300"
        style={{ color: alpha(params.color, 0.85), opacity: state === 'listening' || state === 'speaking' ? 1 : 0.35 }}
      >
        AMP {(liveAmp * 100).toFixed(0).padStart(2, '0')}%
      </div>

      {/* ── glass core with iris ring — click opens the radial quick-nav ── */}
      <button
        type="button"
        disabled={!hasQuickNav}
        onClick={() => hasQuickNav && setMenuOpen((v) => !v)}
        className={cn(
          'relative flex items-center justify-center rounded-full transition-transform duration-300',
          hasQuickNav && 'cursor-pointer',
          hovered && hasQuickNav && 'scale-[1.03]',
        )}
        style={{ width: '42%', height: '42%' }}
        title={hasQuickNav ? 'Open quick navigation' : undefined}
      >
        {/* iris outer ring */}
        <div
          className="absolute inset-0 rounded-full animate-hud-spin-rev"
          style={{
            border: `1px solid ${HUD_SOFT}`,
            boxShadow: `inset 0 0 12px ${alpha(params.color, 0.4)}, 0 0 24px ${alpha(params.color, 0.35)}`,
          }}
        />
        {/* iris tick marks */}
        <svg viewBox="0 0 100 100" className="absolute inset-1 animate-hud-spin" style={{ animationDuration: '22s' }}>
          {Array.from({ length: 24 }).map((_, i) => {
            const a = (i / 24) * Math.PI * 2
            const x1 = 50 + Math.cos(a) * 47
            const y1 = 50 + Math.sin(a) * 47
            const x2 = 50 + Math.cos(a) * (i % 3 === 0 ? 42 : 45)
            const y2 = 50 + Math.sin(a) * (i % 3 === 0 ? 42 : 45)
            return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke={HUD} strokeWidth={i % 3 === 0 ? 1 : 0.4} opacity={0.7} />
          })}
        </svg>

        {/* core center disk */}
        <div
          ref={coreRef}
          className="relative flex flex-col items-center justify-center rounded-full overflow-hidden"
          style={{
            width: '72%',
            height: '72%',
            marginInline: 'auto',
            boxShadow: `0 0 60px ${alpha(params.color, 0.7)}, inset 0 0 30px rgba(240,252,255,0.55), inset 0 -20px 30px ${alpha(params.color, 0.35)}`,
          }}
        >
          {/* subtle glass highlight */}
          <div
            className="pointer-events-none absolute inset-0 rounded-full"
            style={{
              background:
                'radial-gradient(ellipse at 30% 20%, rgba(255,255,255,0.5) 0%, rgba(255,255,255,0) 45%)',
            }}
          />
          {/* scanning line across core */}
          <div
            className="pointer-events-none absolute inset-x-0 h-[2px]"
            style={{
              background: `linear-gradient(90deg, transparent, ${HUD}, transparent)`,
              animation: 'orb-scan 3.2s ease-in-out infinite',
              opacity: 0.7,
            }}
          />
          <span
            className="relative font-display text-[0.68rem] font-bold tracking-[0.28em] text-background/95"
            style={{ textShadow: '0 1px 2px rgba(0,0,0,0.4)' }}
          >
            {name}
          </span>
          <span className="relative mt-0.5 text-[0.42rem] uppercase tracking-[0.35em] text-background/70">
            {STATE_LABEL[state]}
          </span>
        </div>
      </button>

      {/* ── radial quick-nav — fans real nav items out around the orb ── */}
      {hasQuickNav && (
        <div
          className={cn(
            'pointer-events-none absolute inset-0 transition-opacity duration-300',
            menuOpen ? 'opacity-100' : 'opacity-0',
          )}
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
                onClick={() => {
                  onQuickNav?.(item.key)
                  setMenuOpen(false)
                }}
                className={cn(
                  'absolute flex h-9 w-9 items-center justify-center rounded-full border backdrop-blur-sm transition-all duration-300',
                  menuOpen ? 'pointer-events-auto scale-100' : 'scale-0',
                  item.active
                    ? 'border-primary bg-primary/25 text-primary shadow-[0_0_14px_var(--hud)]'
                    : 'border-border/60 bg-background/70 text-muted-foreground hover:border-primary/60 hover:text-primary',
                )}
                style={{
                  left: '50%',
                  top: '50%',
                  transform: menuOpen
                    ? `translate(calc(-50% + ${x}px), calc(-50% + ${y}px))`
                    : 'translate(-50%, -50%)',
                  transitionDelay: menuOpen ? `${i * 35}ms` : '0ms',
                }}
              >
                <Icon className="h-4 w-4" />
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
