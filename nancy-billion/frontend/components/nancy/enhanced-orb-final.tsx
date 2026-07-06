'use client'

import { useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/utils'

export type OrbState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'executing'

const HUD = 'rgba(56, 211, 235, 1)'
const HUD_SOFT = 'rgba(56, 211, 235, 0.55)'
const AMBER = 'rgba(232, 178, 70, 1)'
const GREEN = 'rgba(34, 197, 94, 1)'

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
  listening: { ringSpeed: 0.35, particleSpeed: 0.5, particleCount: 64, waveAmp: 0.35, waveSpeed: 3, color: GREEN },
  thinking: { ringSpeed: 1.1, particleSpeed: 1.4, particleCount: 90, waveAmp: 0.18, waveSpeed: 4.5, color: HUD },
  speaking: { ringSpeed: 0.5, particleSpeed: 0.7, particleCount: 72, waveAmp: 0.45, waveSpeed: 6, color: HUD },
  executing: { ringSpeed: 0.9, particleSpeed: 1.8, particleCount: 110, waveAmp: 0.3, waveSpeed: 5, color: AMBER },
}

const STATE_LABEL: Record<OrbState, string> = {
  idle: 'Ready',
  listening: 'Listening',
  thinking: 'Analyzing',
  speaking: 'Responding',
  executing: 'Processing',
}

function useMicLevel(active: boolean) {
  const levelRef = useRef(0)
  useEffect(() => {
    if (!active || typeof navigator === 'undefined') {
      levelRef.current = 0
      return
    }
    let raf = 0
    let stream: MediaStream | null = null
    let ctx: AudioContext | null = null
    let cancelled = false

    navigator.mediaDevices
      ?.getUserMedia({ audio: true })
      .then((s) => {
        if (cancelled) {
          s.getTracks().forEach((t) => t.stop())
          return
        }
        stream = s
        const AC = (window as any).AudioContext || (window as any).webkitAudioContext
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
      ctx?.close?.()
      levelRef.current = 0
    }
  }, [active])
  return levelRef
}

export function EnhancedNancyOrb({
  state = 'idle',
  size = 280,
  showLabel = true,
}: {
  state?: OrbState
  size?: number
  showLabel?: boolean
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const micLevel = useMicLevel(state === 'listening')
  const animRef = useRef(0)
  const timeRef = useRef(0)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const params = PARAMS[state]
    const w = canvas.width
    const h = canvas.height
    const cx = w / 2
    const cy = h / 2
    const radius = Math.min(w, h) / 2 - 20

    const particles: Array<{ x: number; y: number; vx: number; vy: number; age: number }> = []

    const draw = (t: number) => {
      ctx.fillStyle = 'rgba(15, 23, 42, 0.95)'
      ctx.fillRect(0, 0, w, h)

      // Draw background glow
      const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius * 1.5)
      grad.addColorStop(0, `rgba(56, 211, 235, 0.15)`)
      grad.addColorStop(1, 'rgba(56, 211, 235, 0)')
      ctx.fillStyle = grad
      ctx.fillRect(0, 0, w, h)

      // Update and draw particles
      for (let i = particles.length - 1; i >= 0; i--) {
        const p = particles[i]
        p.x += p.vx
        p.y += p.vy
        p.age += 0.02
        p.vx *= 0.98
        p.vy *= 0.98

        const dist = Math.hypot(p.x - cx, p.y - cy)
        if (dist > radius * 1.5 || p.age > 1) {
          particles.splice(i, 1)
        }
      }

      // Spawn new particles
      if (Math.random() < params.particleCount / 100) {
        const angle = Math.random() * Math.PI * 2
        const speed = params.particleSpeed
        particles.push({
          x: cx + Math.cos(angle) * radius,
          y: cy + Math.sin(angle) * radius,
          vx: Math.cos(angle) * speed,
          vy: Math.sin(angle) * speed,
          age: 0,
        })
      }

      // Draw particles
      particles.forEach((p) => {
        const opacity = (1 - p.age) * 0.6
        ctx.fillStyle = params.color.replace('1)', `${opacity})`)
        ctx.beginPath()
        ctx.arc(p.x, p.y, 1.5, 0, Math.PI * 2)
        ctx.fill()
      })

      // Draw rings
      const ringCount = 3
      for (let i = 0; i < ringCount; i++) {
        const r = radius * (0.5 + (i / ringCount) * 0.5)
        const rotation = (t * params.ringSpeed + (i * Math.PI * 2) / ringCount) % (Math.PI * 2)
        const offsetX = Math.cos(rotation) * (r * 0.15)
        const offsetY = Math.sin(rotation) * (r * 0.15)

        ctx.strokeStyle = params.color.replace('1)', `${0.3 - i * 0.08})`)
        ctx.lineWidth = 2
        ctx.beginPath()
        ctx.arc(cx + offsetX, cy + offsetY, r, 0, Math.PI * 2)
        ctx.stroke()
      }

      // Draw wave effect
      const waveAmount = params.waveAmp
      ctx.strokeStyle = params.color.replace('1)', `0.4)`)
      ctx.lineWidth = 2.5
      ctx.beginPath()
      for (let i = 0; i < 100; i++) {
        const angle = (i / 100) * Math.PI * 2
        const baseRadius = radius * 0.7
        const wave = Math.sin(angle * 3 + t * params.waveSpeed) * baseRadius * waveAmount
        const x = cx + Math.cos(angle) * (baseRadius + wave)
        const y = cy + Math.sin(angle) * (baseRadius + wave)
        if (i === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      }
      ctx.closePath()
      ctx.stroke()

      // Draw center core
      const coreGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius * 0.3)
      coreGrad.addColorStop(0, params.color)
      coreGrad.addColorStop(1, params.color.replace('1)', `0.3)`))
      ctx.fillStyle = coreGrad
      ctx.beginPath()
      ctx.arc(cx, cy, radius * 0.3, 0, Math.PI * 2)
      ctx.fill()

      // Audio reactive
      if (state === 'listening' && micLevel.current > 0) {
        ctx.strokeStyle = GREEN.replace('1)', `${micLevel.current * 0.8})`)
        ctx.lineWidth = 3
        ctx.beginPath()
        ctx.arc(cx, cy, radius * (0.4 + micLevel.current * 0.2), 0, Math.PI * 2)
        ctx.stroke()
      }

      timeRef.current += 0.016
      animRef.current = requestAnimationFrame(draw)
    }

    animRef.current = requestAnimationFrame(draw)

    return () => cancelAnimationFrame(animRef.current)
  }, [state, micLevel])

  return (
    <div className="flex flex-col items-center gap-4">
      <div className="relative">
        <canvas
          ref={canvasRef}
          width={size}
          height={size}
          className="rounded-full shadow-2xl"
          style={{
            filter: 'drop-shadow(0 0 20px rgba(56, 211, 235, 0.4))',
          }}
        />
        {showLabel && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="text-center">
              <div className="text-xs font-mono text-cyan-400/60 uppercase tracking-widest">
                {STATE_LABEL[state]}
              </div>
            </div>
          </div>
        )}
      </div>
      {showLabel && (
        <div className="text-sm font-mono text-cyan-400">
          <span className="text-cyan-300">●</span> Nancy Active
        </div>
      )}
    </div>
  )
}

