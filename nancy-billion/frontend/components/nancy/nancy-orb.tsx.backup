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
  thinking: { ringSpeed: 1.1, particleSpeed: 1.4, particleCount: 90, waveAmp: 0.18, waveSpeed: 4.5, color: HUD },
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

export function NancyOrb({
  state = 'idle',
  name = 'NÅNCY',
  size = 360,
}: {
  state?: OrbState
  name?: string
  size?: number
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const stateRef = useRef<OrbState>(state)
  stateRef.current = state
  const micLevel = useMicLevel(state === 'listening')

  // Particle + waveform engine on canvas.
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = Math.min(2, window.devicePixelRatio || 1)
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let raf = 0
    let t = 0

    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      canvas.width = rect.width * dpr
      canvas.height = rect.height * dpr
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(canvas)

    type P = { angle: number; radius: number; speed: number; sz: number; off: number }
    const particles: P[] = Array.from({ length: 120 }).map(() => ({
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
        stateRef.current === 'listening' ? micLevel.current : 0
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

      // ---- orbiting particle system ----
      const count = Math.floor(p.particleCount)
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
      raf = requestAnimationFrame(draw)
    }
    draw()

    return () => {
      cancelAnimationFrame(raf)
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

      {/* core center disk */}
      <div
        className="relative flex flex-col items-center justify-center rounded-full animate-hud-pulse"
        style={{
          width: '34%',
          height: '34%',
          background: `radial-gradient(circle, rgba(225,250,255,0.95) 0%, ${params.color.replace(/[\d.]+\)$/, '0.9)')} 30%, rgba(20,60,80,0.85) 72%, rgba(8,16,28,0.9) 100%)`,
          boxShadow: `0 0 40px ${params.color.replace(/[\d.]+\)$/, '0.75)')}, inset 0 0 22px rgba(225,250,255,0.55)`,
        }}
      >
        <span className="font-heading text-sm font-semibold tracking-[0.28em] text-background drop-shadow">
          {name}
        </span>
        <span className="mt-0.5 text-[0.5rem] uppercase tracking-[0.3em] text-background/80">
          {STATE_LABEL[state]}
        </span>
      </div>
    </div>
  )
}
