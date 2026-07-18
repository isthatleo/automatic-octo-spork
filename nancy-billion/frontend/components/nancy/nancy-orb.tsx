'use client'

import { useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'

export type OrbState =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'speaking'
  | 'executing'

const HUD = 'rgba(56, 211, 235, 1)'
const HUD_SOFT = 'rgba(56, 211, 235, 0.55)'
const AMBER = 'rgba(232, 178, 70, 1)'
// Matches the design system's --tertiary token -- gives "thinking" its own
// identity instead of looking identical to idle/listening (both cyan).
const VIOLET = 'rgba(196, 130, 235, 1)'

// Per-state animation parameters driving the canvas.
const PARAMS: Record<
  OrbState,
  {
    ringSpeed: number
    particleSpeed: number
    particleCount: number
    waveAmp: number
    waveSpeed: number
    color: string
  }
> = {
  idle: { ringSpeed: 0.15, particleSpeed: 0.2, particleCount: 48, waveAmp: 0.05, waveSpeed: 1.2, color: HUD },
  listening: { ringSpeed: 0.35, particleSpeed: 0.5, particleCount: 64, waveAmp: 0.35, waveSpeed: 3, color: HUD },
  thinking: { ringSpeed: 1.1, particleSpeed: 1.4, particleCount: 90, waveAmp: 0.18, waveSpeed: 4.5, color: VIOLET },
  speaking: { ringSpeed: 0.5, particleSpeed: 0.7, particleCount: 72, waveAmp: 0.45, waveSpeed: 6, color: HUD },
  executing: { ringSpeed: 0.9, particleSpeed: 1.8, particleCount: 110, waveAmp: 0.3, waveSpeed: 5, color: AMBER },
}

const STATE_LABEL: Record<OrbState, string> = {
  idle: 'Standing By',
  listening: 'Listening',
  thinking: 'Processing',
  speaking: 'Responding',
  executing: 'Executing',
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

export function NancyOrb({
  state = 'idle',
  name = 'NÅNCY',
  size = 360,
  audioElement = null,
}: {
  state?: OrbState
  name?: string
  size?: number
  /** The <audio> element currently playing Nancy's real TTS output, if any
   * (see page.tsx's nancySay) -- drives real audio-reactivity while
   * speaking instead of a fixed decorative wobble. */
  audioElement?: HTMLAudioElement | null
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const stateRef = useRef<OrbState>(state)
  stateRef.current = state
  const micLevel = useMicLevel(state === 'listening')
  const speakingLevel = useElementAudioLevel(audioElement)

  // Particle + waveform engine on canvas.
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
      halo.addColorStop(0, p.color.replace(/[\d.]+\)$/, '0.18)'))
      halo.addColorStop(0.6, p.color.replace(/[\d.]+\)$/, '0.06)'))
      halo.addColorStop(1, 'rgba(0,0,0,0)')
      ctx.fillStyle = halo
      ctx.fillRect(0, 0, w, h)

      // ---- expanding pulse waves (executing) ----
      if (pulse > 0) {
        pulse += 0.012
        const pr = R * pulse
        ctx.beginPath()
        ctx.arc(cx, cy, pr, 0, Math.PI * 2)
        ctx.strokeStyle = AMBER.replace(/[\d.]+\)$/, `${Math.max(0, 0.6 - pulse * 0.6)})`)
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
        ctx.fillStyle = p.color.replace(/[\d.]+\)$/, `${0.4 + Math.sin(t * 2 + pt.off) * 0.3 + 0.3})`)
        ctx.fill()
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

  return (
    <div
      className="relative flex items-center justify-center"
      style={{ width: size, height: size }}
      role="img"
      aria-label={`${name} assistant orb — ${STATE_LABEL[state]}`}
    >
      {/* canvas: halo, waveform, particles, pulse waves */}
      <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" />

      {/* ── outer holographic arc ring (broken segments) ── */}
      <svg
        viewBox="0 0 200 200"
        className="absolute animate-hud-spin-slow"
        style={{ width: '98%', height: '98%' }}
      >
        <defs>
          <linearGradient id="arcGrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={HUD} stopOpacity="0" />
            <stop offset="50%" stopColor={HUD} stopOpacity="0.9" />
            <stop offset="100%" stopColor={HUD} stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 90, 180, 270].map((rot) => (
          <path
            key={rot}
            d="M 100 5 A 95 95 0 0 1 170 30"
            fill="none"
            stroke="url(#arcGrad)"
            strokeWidth="1.5"
            strokeLinecap="round"
            transform={`rotate(${rot} 100 100)`}
            style={{ filter: 'drop-shadow(0 0 4px var(--hud))' }}
          />
        ))}
        {/* diamond nodes */}
        {[45, 135, 225, 315].map((deg) => {
          const a = (deg * Math.PI) / 180
          const x = 100 + Math.cos(a) * 95
          const y = 100 + Math.sin(a) * 95
          return (
            <g key={deg} transform={`translate(${x} ${y}) rotate(45)`}>
              <rect x="-3" y="-3" width="6" height="6" fill={HUD} opacity="0.9" style={{ filter: 'drop-shadow(0 0 3px var(--hud))' }} />
            </g>
          )
        })}
      </svg>

      {/* ── secondary counter-rotating dashed ring ── */}
      <svg
        viewBox="0 0 200 200"
        className="absolute animate-hud-spin-rev"
        style={{ width: '84%', height: '84%' }}
      >
        <circle
          cx="100"
          cy="100"
          r="94"
          fill="none"
          stroke={HUD_SOFT}
          strokeWidth="0.6"
          strokeDasharray="2 4"
        />
      </svg>

      {/* rotating segmented inner ring */}
      <svg
        viewBox="0 0 200 200"
        className={cn('absolute', state === 'thinking' ? 'animate-hud-spin' : 'animate-hud-spin-slow')}
        style={{ width: '64%', height: '64%' }}
      >
        <circle
          cx="100"
          cy="100"
          r="92"
          fill="none"
          stroke={HUD_SOFT}
          strokeWidth="2.5"
          strokeDasharray="16 10"
          style={{ filter: 'drop-shadow(0 0 3px var(--hud))' }}
        />
      </svg>

      {/* counter-rotating tick ring */}
      <svg
        viewBox="0 0 200 200"
        className="absolute animate-hud-spin-rev"
        style={{ width: '52%', height: '52%' }}
      >
        {Array.from({ length: 60 }).map((_, i) => {
          const a = (i / 60) * Math.PI * 2
          const x1 = 100 + Math.cos(a) * 96
          const y1 = 100 + Math.sin(a) * 96
          const x2 = 100 + Math.cos(a) * (i % 5 === 0 ? 84 : 90)
          const y2 = 100 + Math.sin(a) * (i % 5 === 0 ? 84 : 90)
          return (
            <line
              key={i}
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke={HUD}
              strokeWidth={i % 5 === 0 ? 1.4 : 0.6}
              opacity={i % 5 === 0 ? 0.85 : 0.35}
            />
          )
        })}
      </svg>

      {/* ── sweeping radar beam ── */}
      <svg
        viewBox="0 0 200 200"
        className="absolute animate-hud-spin"
        style={{ width: '48%', height: '48%', animationDuration: '4s' }}
      >
        <defs>
          <linearGradient id="sweep" x1="0.5" y1="0.5" x2="1" y2="0.5">
            <stop offset="0%" stopColor={HUD} stopOpacity="0.55" />
            <stop offset="100%" stopColor={HUD} stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d="M 100 100 L 200 100 A 100 100 0 0 0 172 30 Z" fill="url(#sweep)" />
      </svg>

      {/* ── glass core with iris ring ── */}
      <div className="relative flex items-center justify-center" style={{ width: '42%', height: '42%' }}>
        {/* iris outer ring */}
        <div
          className="absolute inset-0 rounded-full animate-hud-spin-rev"
          style={{
            border: `1px solid ${HUD_SOFT}`,
            boxShadow: `inset 0 0 12px ${params.color.replace(/[\d.]+\)$/, '0.4)')}, 0 0 24px ${params.color.replace(/[\d.]+\)$/, '0.35)')}`,
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
          className="relative flex flex-col items-center justify-center rounded-full animate-hud-pulse overflow-hidden"
          style={{
            width: '72%',
            height: '72%',
            background: `radial-gradient(circle at 35% 30%, rgba(240,252,255,0.98) 0%, ${params.color.replace(/[\d.]+\)$/, '0.85)')} 28%, rgba(20,60,90,0.85) 68%, rgba(6,12,22,0.95) 100%)`,
            boxShadow: `0 0 60px ${params.color.replace(/[\d.]+\)$/, '0.7)')}, inset 0 0 30px rgba(240,252,255,0.55), inset 0 -20px 30px ${params.color.replace(/[\d.]+\)$/, '0.35)')}`,
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
            className="relative font-heading text-[0.72rem] font-semibold tracking-[0.32em] text-background/95"
            style={{ textShadow: '0 1px 2px rgba(0,0,0,0.4)' }}
          >
            {name}
          </span>
          <span className="relative mt-0.5 text-[0.42rem] uppercase tracking-[0.35em] text-background/70">
            {STATE_LABEL[state]}
          </span>
        </div>
      </div>
    </div>
  )
}
