'use client'

import { useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'

export type OrbState =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'speaking'
  | 'executing'

const HUD_PRIMARY = 'rgba(0, 255, 255, 1)' // Cyan
const HUD_SECONDARY = 'rgba(255, 0, 255, 1)' // Magenta
const HUD_ACCENT = 'rgba(0, 255, 128, 1)' // Spring green
const HUD_WARNING = 'rgba(255, 255, 0, 1)' // Yellow
const HUD_ERROR = 'rgba(255, 0, 64, 1)' // Red-pink
const HUD_SOFT = 'rgba(0, 255, 255, 0.15)'
const DEPTH_FOG = 'rgba(0, 10, 20, 0.3)'

// Enhanced per-state animation parameters with fluid dynamics
const ENHANCED_PARAMS: Record<
  OrbState,
  {
    ringSpeed: number
    particleSpeed: number
    particleCount: number
    waveAmp: number
    waveSpeed: number
    fluidViscosity: number
    colorPrimary: string
    colorSecondary: string
    turbulence: number
    glowIntensity: number
  }
> = {
  idle: {
    ringSpeed: 0.1,
    particleSpeed: 0.15,
    particleCount: 60,
    waveAmp: 0.03,
    waveSpeed: 0.8,
    fluidViscosity: 0.95,
    colorPrimary: HUD_PRIMARY,
    colorSecondary: HUD_SECONDARY,
    turbulence: 0.1,
    glowIntensity: 0.6
  },
  listening: {
    ringSpeed: 0.25,
    particleSpeed: 0.4,
    particleCount: 80,
    waveAmp: 0.4,
    waveSpeed: 2.5,
    fluidViscosity: 0.85,
    colorPrimary: HUD_PRIMARY,
    colorSecondary: HUD_ACCENT,
    turbulence: 0.3,
    glowIntensity: 0.8
  },
  thinking: {
    ringSpeed: 0.8,
    particleSpeed: 1.2,
    particleCount: 120,
    waveAmp: 0.2,
    waveSpeed: 4.0,
    fluidViscosity: 0.7,
    colorPrimary: HUD_SECONDARY,
    colorSecondary: HUD_PRIMARY,
    turbulence: 0.5,
    glowIntensity: 1.0
  },
  speaking: {
    ringSpeed: 0.4,
    particleSpeed: 0.6,
    particleCount: 90,
    waveAmp: 0.5,
    waveSpeed: 5.0,
    fluidViscosity: 0.8,
    colorPrimary: HUD_ACCENT,
    colorSecondary: HUD_PRIMARY,
    turbulence: 0.4,
    glowIntensity: 0.9
  },
  executing: {
    ringSpeed: 0.6,
    particleSpeed: 1.5,
    particleCount: 140,
    waveAmp: 0.35,
    waveSpeed: 4.5,
    fluidViscosity: 0.6,
    colorPrimary: HUD_WARNING,
    colorSecondary: HUD_ERROR,
    turbulence: 0.6,
    glowIntensity: 1.2
  }
}

const STATE_LABEL: Record<OrbState, string> = {
  idle: 'Standing By',
  listening: 'Listening',
  thinking: 'Processing',
  speaking: 'Responding',
  executing: 'Executing'
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
        analyser.fftSize = 2048 // Increased for better frequency resolution
        src.connect(analyser)
        const data = new Uint8Array(analyser.frequencyBinCount)
        const tick = () => {
          analyser.getByteTimeDomainData(data)
          let sum = 0
          let sumHigh = 0
          let sumMid = 0
          let sumLow = 0
          
          // Split frequency bands for more reactive visualization
          const third = Math.floor(data.length / 3)
          for (let i = 0; i < data.length; i++) {
            const v = (data[i] - 128) / 128
            const magnitude = v * v
            sum += magnitude
            
            if (i < third) {
              sumLow += magnitude * 0.5 // Low frequencies
            } else if (i < 2 * third) {
              sumMid += magnitude * 1.0 // Mid frequencies
            } else {
              sumHigh += magnitude * 1.5 // High frequencies (more sensitive to voice)
            }
          }
          
          const rms = Math.sqrt(sum / data.length)
          const rmsLow = Math.sqrt(sumLow / third)
          const rmsMid = Math.sqrt(sumMid / third)
          const rmsHigh = Math.sqrt(sumHigh / third)
          
          // Weighted combination emphasizing voice frequencies
          levelRef.current = Math.min(1.0, (rms * 2.0 + rmsMid * 1.5 + rmsHigh * 2.0) / 2.0)
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

export function EnhancedNancyOrb({
  state = 'idle',
  name = 'JÄRVIS',
  size = 400,
  enableHolographic = true,
  enableFluidSimulation = true,
}: {
  state?: OrbState
  name?: string
  size?: number
  enableHolographic?: boolean
  enableFluidSimulation?: boolean
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const stateRef = useRef<OrbState>(state)
  stateRef.current = state
  const micLevel = useMicLevel(state === 'listening')
  const timeRef = useRef(0)

  // Particle system with fluid-like behavior
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

    // Fluid particles with interconnected behavior
    type FluidParticle = {
      x: number
      y: number
      vx: number
      vy: number
      ax: number
      ay: number
      mass: number
      radius: number
      hue: number
      life: number
      maxLife: number
    }

    const particles: FluidParticle[] = Array.from({ 
      length: ENHANCED_PARAMS[stateRef.current].particleCount 
    }).map(() => ({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      vx: (Math.random() - 0.5) * 0.5,
      vy: (Math.random() - 0.5) * 0.5,
      ax: 0,
      ay: 0,
      mass: 0.5 + Math.random() * 1.5,
      radius: 1.0 + Math.random() * 2.0,
      hue: Math.random() * 60 + 180, // Cyan to blue range
      life: Math.random() * 100,
      maxLife: 50 + Math.random() * 100
    }))

    // Vortex points for fluid dynamics
    const vortices = Array.from({ length: 3 }).map(() => ({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      strength: 0.5 + Math.random() * 1.5,
      rotation: (Math.random() - 0.5) * 0.1,
      life: Math.random() * 200
    }))

    let pulse = 0
    let prevState: OrbState = stateRef.current

    const drawFluid = () => {
      const w = canvas.width
      const h = canvas.height
      const cx = w / 2
      const cy = h / 2
      const R = Math.min(w, h) * 0.45
      const p = ENHANCED_PARAMS[stateRef.current]

      ctx.clearRect(0, 0, w, h)

      // Update time
      timeRef.current += 0.016 * (0.5 + p.ringSpeed)
      t = timeRef.current

      // Trigger shockwave effects
      if (stateRef.current === 'executing' && prevState !== 'executing') {
        pulse = 0.002
      } else if (stateRef.current === 'alert' && prevState !== 'alert') {
        pulse = 0.003
      }
      prevState = stateRef.current

      // Depth fog background
      ctx.fillStyle = DEPTH_FOG
      ctx.fillRect(0, 0, w, h)

      // Outer luminous haze with chromatic aberration
      if (enableHolographic) {
        const breathe = 1 + Math.sin(t * 0.8) * 0.1
        const hazeR = R * 1.3 * breathe
        
        // Red channel offset
        ctx.save()
        ctx.filter = 'blur(24px)'
        ctx.fillStyle = p.colorPrimary.replace(/[\d.]+\)$/, '0.08)')
        ctx.beginPath()
        ctx.ellipse(cx - 2, cy, hazeR * 1.02, hazeR * 1.02, 0, 0, Math.PI * 2)
        ctx.fill()
        ctx.restore()
        
        // Blue channel offset
        ctx.save()
        ctx.filter = 'blur(20px)'
        ctx.fillStyle = p.colorSecondary.replace(/[\d.]+\)$/, '0.06)')
        ctx.beginPath()
        ctx.ellipse(cx + 1, cy - 1, hazeR * 0.98, hazeR * 0.98, 0, 0, Math.PI * 2)
        ctx.fill()
        ctx.restore()
        
        // Green channel center
        ctx.save()
        ctx.filter = 'blur(16px)'
        ctx.fillStyle = p.colorPrimary.replace(/[\d.]+\)$/, '0.12)')
        ctx.beginPath()
        ctx.ellipse(cx, cy, hazeR, hazeR, 0, 0, Math.PI * 2)
        ctx.fill()
        ctx.restore()
      }

      // Fluid dynamics simulation
      if (enableFluidSimulation) {
        // Apply forces between particles
        for (let i = 0; i < particles.length; i++) {
          const p1 = particles[i]
          p1.ax = 0
          p1.ay = 0
          
          // Mouse/touch repulsion (simplified)
          const mouseInfluence = 0
          
          // Vortex influences
          for (const vortex of vortices) {
            const dx = vortex.x - p1.x
            const dy = vortex.y - p1.y
            const dist = Math.sqrt(dx * dx + dy * dy)
            const force = vortex.strength / (dist * dist + 0.01)
            
            p1.ax += (force * dx / dist) * vortex.rotation
            p1.ay += (force * dy / dist) * vortex.rotation
          }
          
          // Center attraction with fluid resistance
          const dxToCenter = cx - p1.x
          const dyToCenter = cy - p1.y
          const distToCenter = Math.sqrt(dxToCenter * dxToCenter + dyToCenter * dyToCenter)
          
          if (distToCenter > R * 0.8) {
            // Pull back toward center with fluid resistance
            const centerForce = (distToCenter - R * 0.8) * 0.0005 * p.fluidViscosity
            p1.ax += (centerForce * dxToCenter / distToCenter)
            p1.ay += (centerForce * dyToCenter / distToCenter)
          } else {
            // Fluid flow around center
            const flowAngle = Math.atan2(dyToCenter, dxToCenter) + Math.PI / 2
            const flowStrength = Math.sin(t * p.waveSpeed + distToCenter * 0.01) * p.waveAmp * 0.0003
            p1.ax += Math.cos(flowAngle) * flowStrength * (1 - distToCenter / (R * 0.8))
            p1.ay += Math.sin(flowStrength) * flowStrength * (1 - distToCenter / (R * 0.8))
          }
          
          // Audio reactivity
          if (stateRef.current === 'listening') {
            const audioForce = micLevel.current * 0.002
            const angleToCenter = Math.atan2(p1.y - cy, p1.x - cx)
            p1.ax += Math.cos(angleToCenter) * audioForce
            p1.ay += Math.sin(angleToCenter) * audioForce
          }
          
          // Apply viscosity (damping)
          p1.vx += p1.ax
          p1.vy += p1.ay
          p1.vx *= p.fluidViscosity
          p1.vy *= p.fluidViscosity
          
          // Update position
          p1.x += p1.vx
          p1.y += p1.vy
          
          // Boundary conditions with soft edges
          if (p1.x < 0) { p1.x = 0; p1.vx *= -0.5 }
          if (p1.x > w) { p1.x = w; p1.vx *= -0.5 }
          if (p1.y < 0) { p1.y = 0; p1.vy *= -0.5 }
          if (p1.y > h) { p1.y = h; p1.vy *= -0.5 }
          
          // Age and lifecycle
          p1.life++
          if (p1.life > p1.maxLife) {
            p1.x = Math.random() * w
            p1.y = Math.random() * h
            p1.vx = (Math.random() - 0.5) * 0.2
            p1.vy = (Math.random() - 0.5) * 0.2
            p1.life = 0
            p1.hue = Math.random() * 60 + 180 + Math.sin(t) * 10
          }
        }
        
        // Update vortices
        for (const vortex of vortices) {
          vortex.life++
          if (vortex.life > 200) {
            vortex.x = Math.random() * w
            vortex.y = Math.random() * h
            vortex.strength = 0.5 + Math.random() * 1.5
            vortex.rotation = (Math.random() - 0.5) * 0.1
            vortex.life = 0
          }
          
          // Slow drift
          vortex.x += Math.sin(t * 0.1 + vortex.life * 0.01) * 0.2
          vortex.y += Math.cos(t * 0.1 + vortex.life * 0.01) * 0.2
        }
        
        // Draw fluid particles with trails
        for (let i = 0; i < particles.length; i++) {
          const p = particles[i]
          const lifeFactor = p.life / p.maxLife
          
          // Main particle glow
          ctx.save()
          ctx.shadowBlur = p.radius * 2 * p.glowIntensity
          ctx.shadowColor = `hsla(${p.hue}, 80%, 60%, ${0.3 * lifeFactor * p.glowIntensity})`
          
          // Gradient for particle
          const gradient = ctx.createRadialGradient(
            p.x, p.y, 0,
            p.x, p.y, p.radius
          )
          gradient.addColorStop(0, `hsla(${p.hue}, 80%, 70%, ${0.8 * lifeFactor})`)
          gradient.addColorStop(1, `hsla(${p.hue}, 80%, 40%, ${0.4 * lifeFactor})`)
          
          ctx.fillStyle = gradient
          ctx.beginPath()
          ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2)
          ctx.fill()
          ctx.restore()
          
          // Trail effect
          if (lifeFactor > 0.3) {
            ctx.save()
            ctx.globalAlpha = 0.2 * lifeFactor
            ctx.fillStyle = `hsla(${p.hue}, 80%, 50%, 0.1)`
            ctx.beginPath()
            ctx.arc(p.x - p.vx * 2, p.y - p.vy * 2, p.radius * 0.6, 0, Math.PI * 2)
            ctx.fill()
            ctx.restore()
          }
        }
      }

      // Standing wave interference patterns
      if (enableHolographic) {
        const waveDetail = 80
        const baseRadius = R * 0.6
        
        // Multiple interfering wave patterns
        for (let wave = 0; wave < 3; wave++) {
          ctx.beginPath()
          for (let i = 0; i <= waveDetail; i++) {
            const angle = (i / waveDetail) * Math.PI * 2
            
            // Complex wave interference
            let radius = baseRadius
            
            // Primary standing wave
            radius += Math.sin(angle * 4 + t * p.waveSpeed) * p.waveAmp * R * 0.12
            
            // Secondary wave for complexity
            radius += Math.sin(angle * 7 - t * p.waveSpeed * 0.7) * p.waveAmp * R * 0.06
            
            // Tertiary wave for richness
            radius += Math.sin(angle * 11 + t * p.waveSpeed * 1.3) * p.waveAmp * R * 0.04
            
            // Audio modulation
            if (stateRef.current === 'listening') {
              radius += micLevel.current * R * 0.08 * Math.sin(angle * 6 + t * 10)
            }
            
            const x = cx + Math.cos(angle) * radius
            const y = cy + Math.sin(angle) * radius
            
            if (i === 0) ctx.moveTo(x, y)
            else ctx.lineTo(x, y)
          }
          ctx.closePath()
          
          // Wave stroke with glow
          ctx.strokeStyle = `hsla(${(p.hue + wave * 40) % 360}, 80%, 60%, ${0.4 * p.glowIntensity})`
          ctx.lineWidth = 1.8 * dpr
          ctx.shadowBlur = 8 * dpr
          ctx.shadowColor = `hsla(${(p.hue + wave * 40) % 360}, 80%, 60%, ${0.3 * p.glowIntensity})`
          ctx.stroke()
          ctx.shadowBlur = 0
        }
      }

      // Expanding consciousness waves (executing/alert states)
      if (pulse > 0 && (stateRef.current === 'executing' || stateRef.current === 'alert')) {
        pulse += stateRef.current === 'executing' ? 0.015 : 0.025
        
        // Multiple expanding rings
        for (let ring = 0; ring < 3; ring++) {
          const ringPulse = pulse - ring * 0.2
          if (ringPulse > 0) {
            const radius = R * ringPulse * 1.5
            const alpha = Math.max(0, 0.6 - ringPulse * 0.8 + ring * 0.1)
            
            ctx.beginPath()
            ctx.arc(cx, cy, radius, 0, Math.PI * 2)
            ctx.strokeStyle = `hsla(${p.hue}, 80%, 70%, ${alpha * 0.4})`
            ctx.lineWidth = 2.5 * dpr - ring * 0.5
            ctx.setLineDash([10 * dpr, 5 * dpr])
            ctx.stroke()
            ctx.setLineDash([])
          }
        }
        
        if ((stateRef.current === 'executing' && pulse >= 1.2) || 
            (stateRef.current === 'alert' && pulse >= 1.5)) {
          pulse = stateRef.current === 'executing' ? 0.002 : 0.003
        }
      }

      // Central core with depth and refraction
      ctx.save()
      ctx.translate(cx, cy)
      
      // Outer refraction ring
      ctx.beginPath()
      ctx.ellipse(0, 0, R * 0.35, R * 0.3, t * 0.3, 0, Math.PI * 2)
      ctx.strokeStyle = `hsla(${p.hue}, 70%, 80%, ${0.2 * p.glowIntensity})`
      ctx.lineWidth = 1.5 * dpr
      ctx.stroke()
      
      // Inner core with gradient
      const coreGradient = ctx.createRadialGradient(0, 0, 0, 0, 0, R * 0.25)
      coreGradient.addColorStop(0, `hsla(${p.hue}, 60%, 90%, ${0.9 * p.glowIntensity})`)
      coreGradient.addColorStop(0.5, `hsla(${p.hue}, 70%, 70%, ${0.7 * p.glowIntensity})`)
      coreGradient.addColorStop(1, `hsla(${p.hue}, 60%, 50%, ${0.4 * p.glowIntensity})`)
      
      ctx.fillStyle = coreGradient
      ctx.beginPath()
      ctx.arc(0, 0, R * 0.25, 0, Math.PI * 2)
      ctx.fill()
      
      // Central nucleus
      ctx.fillStyle = `hsla(${p.hue}, 50%, 30%, ${0.6 * p.glowIntensity})`
      ctx.beginPath()
      ctx.arc(0, 0, R * 0.08, 0, Math.PI * 2)
      ctx.fill()
      
      ctx.restore()

      // Name and state label with holographic effect
      ctx.save()
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.font = `bold ${Math.max(12, R * 0.08)}px 'Orbitron', 'Courier New', monospace`
      
      // Name with glow and slight offset for depth
      ctx.shadowColor = `hsla(${p.hue}, 80%, 70%, ${0.4 * p.glowIntensity})`
      ctx.shadowBlur = 4 * dpr
      ctx.fillStyle = `hsla(${p.hue}, 80%, 90%, ${0.8 * p.glowIntensity})`
      ctx.fillText(name, 0, R * 0.1)
      
      // State label
      ctx.font = `italic ${Math.max(10, R * 0.05)}px 'Orbitron', 'Courier New', monospace`
      ctx.shadowBlur = 2 * dpr
      ctx.fillStyle = `hsla(${p.hue}, 70%, 80%, ${0.6 * p.glowIntensity})`
      ctx.fillText(STATE_LABEL[state], 0, R * 0.25)
      ctx.restore()
    }

    drawFluid()

    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
    }
    // Dependencies: stateRef (read via .current), micLevel (stable ref)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const params = ENHANCED_PARAMS[state]

  return (
    <div
      className="relative flex items-center justify-center"
      style={{ width: size, height: size }}
      role="img"
      aria-label={`${name} assistant orb — ${STATE_LABEL[state]}`}
    >
      {/* Canvas: fluid dynamics, holographic effects, standing waves */}
      <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" />
      
      {/* Optional: Holographic projection elements */}
      {enableHolographic && (
        <>
          {/* Scan lines */}
          <div className="absolute inset-0 pointer-events-none">
            <div className="absolute inset-0 bg-[repeating-linear-gradient(0deg,transparent,transparent_1px,rgba(0,255,255,0.03)_1px,rgba(0,255,255,0.03)_2px)]" 
                 className="animate-scan"
                 style={{ pointerEvents: 'none' }}></div>
          </div>
          
          {/* Chromatic aberration overlay */}
          <div className="absolute inset-0 pointer-events-none
                        animate-chromaticShift"
               style={{ pointerEvents: 'none' }}></div>
        </>
      )}
      
      {/* Optional: Depth indicators */}
      {enableFluidSimulation && (
        <div className="absolute inset-0 pointer-events-none"
             style={{
               pointerEvents: 'none',
               background: `radial-gradient(circle at 50% 50%, transparent 0%, rgba(0,10,20,0.1) 70%, rgba(0,10,20,0.2) 100%)`,
               pointerEvents: 'none'
             }}></div>
      )}
    </div>
  )
}