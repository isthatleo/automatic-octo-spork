'use client'

import React, { useEffect, useState, useCallback, useRef } from 'react'
import { cn } from '@/lib/utils'

type VoiceState = 'idle' | 'listening' | 'processing' | 'speaking'

interface AnimationConfig {
  orb: {
    scale: number
    opacity: number
    glow: number
  }
  pulse?: {
    enabled: boolean
    frequency: number
  }
  rotation?: number | { speed: number; direction: 'cw' | 'ccw' }
  audio_sync?: boolean
}

export function VoiceOrbV2({ state, audioLevel = 0 }: { state: VoiceState; audioLevel?: number }) {
  const [scale, setScale] = useState(1)
  const [glow, setGlow] = useState(0.5)
  const [rotation, setRotation] = useState(0)
  const animationRef = useRef<NodeJS.Timeout | null>(null)

  const animationConfigs: Record<VoiceState, AnimationConfig> = {
    idle: {
      orb: { scale: 1.0, opacity: 0.8, glow: 0.5 },
    },
    listening: {
      orb: { scale: 1.1, opacity: 1.0, glow: 1.0 },
      pulse: { enabled: true, frequency: 2 },
      rotation: { speed: 360, direction: 'cw' },
    },
    processing: {
      orb: { scale: 0.95, opacity: 0.9, glow: 0.8 },
      pulse: { enabled: true, frequency: 3 },
      rotation: { speed: 180, direction: 'ccw' },
    },
    speaking: {
      orb: { scale: 1.05, opacity: 1.0, glow: 1.2 },
      pulse: { enabled: true, frequency: 1.5 },
      audio_sync: true,
    },
  }

  const config = animationConfigs[state]

  useEffect(() => {
    if (animationRef.current) {
      clearInterval(animationRef.current)
    }

    // Handle rotation
    if (config.rotation && typeof config.rotation === 'object') {
      const direction = config.rotation.direction === 'cw' ? 1 : -1
      const speed = config.rotation.speed
      let currentRotation = 0

      animationRef.current = setInterval(() => {
        currentRotation += (speed * direction) / 60 // 60fps
        setRotation(currentRotation % 360)
      }, 1000 / 60)
    }

    // Handle scale/glow pulse
    if (config.pulse?.enabled) {
      const frequency = config.pulse.frequency
      let time = 0
      const pulseInterval = setInterval(() => {
        time += 0.016 * frequency // 60fps
        const pulse = 0.5 + Math.sin(time * Math.PI * 2) * 0.5

        if (config.audio_sync && audioLevel > 0) {
          setScale(config.orb.scale + audioLevel * 0.1)
          setGlow(config.orb.glow + audioLevel * 0.5)
        } else {
          setScale(config.orb.scale + pulse * 0.15)
          setGlow(config.orb.glow + pulse * 0.3)
        }
      }, 1000 / 60)

      return () => clearInterval(pulseInterval)
    } else {
      setScale(config.orb.scale)
      setGlow(config.orb.glow)
    }

    return () => {
      if (animationRef.current) {
        clearInterval(animationRef.current)
      }
    }
  }, [state, config, audioLevel])

  return (
    <div className="relative w-64 h-64 flex items-center justify-center">
      {/* Outer glow */}
      <div
        className="absolute inset-0 rounded-full transition-all duration-300"
        style={{
          background: `radial-gradient(circle, rgba(56, 211, 235, ${glow * 0.3}), transparent)`,
          transform: `scale(${scale + glow * 0.3})`,
        }}
      />

      {/* Main orb */}
      <div
        className={cn(
          'absolute w-56 h-56 rounded-full transition-all duration-300',
          'bg-gradient-to-br from-primary to-primary/70',
          'shadow-2xl flex items-center justify-center',
          'border-2 border-primary/50'
        )}
        style={{
          transform: `scale(${scale}) rotate(${rotation}deg)`,
          opacity: config.orb.opacity,
        }}
      >
        {/* Inner core */}
        <div className="absolute inset-4 rounded-full bg-gradient-to-b from-primary/50 to-transparent opacity-50" />

        {/* State indicator */}
        <div className="relative z-10 text-center">
          <div className="text-white text-2xl font-bold">N</div>
          <div className="text-primary/60 text-xs mt-1 uppercase tracking-widest">{state}</div>
        </div>
      </div>

      {/* Pulse rings (for listening/speaking) */}
      {(state === 'listening' || state === 'speaking') && (
        <>
          <div
            className="absolute rounded-full border-2 border-primary/50 animate-pulse"
            style={{
              width: '280px',
              height: '280px',
              animationDuration: `${1 / (config.pulse?.frequency || 1)}s`,
            }}
          />
          <div
            className="absolute rounded-full border border-primary/30 animate-pulse"
            style={{
              width: '320px',
              height: '320px',
              animationDuration: `${2 / (config.pulse?.frequency || 1)}s`,
              animationDelay: `${0.2 / (config.pulse?.frequency || 1)}s`,
            }}
          />
        </>
      )}
    </div>
  )
}

export function VoiceTranscript({ transcript, interim }: { transcript: string; interim: string }) {
  return (
    <div className="w-full max-w-2xl">
      <div className="p-4 rounded-lg border border-border/40 bg-card/50 backdrop-blur-sm">
        <p className="text-sm text-foreground/90 leading-relaxed">
          {transcript}
          {interim && <span className="text-muted-foreground italic">{interim}</span>}
          {!transcript && !interim && (
            <span className="text-muted-foreground">Listening...</span>
          )}
        </p>
      </div>
    </div>
  )
}

export function VoiceControls({
  state,
  onToggle,
  onStop,
}: {
  state: VoiceState
  onToggle: () => void
  onStop: () => void
}) {
  const isActive = state !== 'idle'

  return (
    <div className="flex gap-3">
      <button
        onClick={onToggle}
        className={cn(
          'px-6 py-2 rounded-lg font-semibold transition-all',
          isActive
            ? 'bg-destructive hover:bg-destructive/90 text-white'
            : 'bg-primary hover:bg-primary/90 text-white'
        )}
      >
        {isActive ? '◼ Stop' : '● Record'}
      </button>

      {isActive && (
        <button
          onClick={onStop}
          className="px-6 py-2 rounded-lg bg-secondary hover:bg-secondary/90 text-foreground font-semibold transition-all"
        >
          ⏸ Pause
        </button>
      )}
    </div>
  )
}

export function VoiceStatusIndicator({ state }: { state: VoiceState }) {
  const statusConfig = {
    idle: { label: 'Ready', color: 'text-muted-foreground', dot: 'bg-gray-500' },
    listening: { label: 'Listening...', color: 'text-primary', dot: 'bg-primary animate-pulse' },
    processing: { label: 'Processing...', color: 'text-accent', dot: 'bg-accent animate-pulse' },
    speaking: { label: 'Speaking...', color: 'text-primary', dot: 'bg-primary animate-pulse' },
  }

  const config = statusConfig[state]

  return (
    <div className="flex items-center gap-2">
      <div className={cn('w-2 h-2 rounded-full', config.dot)} />
      <span className={cn('text-sm font-medium', config.color)}>{config.label}</span>
    </div>
  )
}

