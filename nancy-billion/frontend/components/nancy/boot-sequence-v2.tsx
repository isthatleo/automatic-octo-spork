'use client'

import React, { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'

type Stage = 'systems' | 'memory' | 'context' | 'ready'

const STAGES: Array<{ name: Stage; label: string; description: string; duration: number }> = [
  { name: 'systems', label: 'Initializing Systems', description: 'Bringing core modules online', duration: 1200 },
  { name: 'memory', label: 'Loading Memory', description: 'Accessing knowledge graph', duration: 1200 },
  { name: 'context', label: 'Building Context', description: 'Understanding environment', duration: 1200 },
  { name: 'ready', label: 'Ready', description: 'All systems operational', duration: 800 },
]

export function BootSequenceV2({ onDone }: { onDone: () => void }) {
  const [stage, setStage] = useState<Stage>('systems')
  const [progress, setProgress] = useState(0)
  const [isComplete, setIsComplete] = useState(false)
  const [stageIndex, setStageIndex] = useState(0)

  useEffect(() => {
    if (isComplete) {
      const timer = setTimeout(onDone, 1000)
      return () => clearTimeout(timer)
    }

    const currentStage = STAGES[stageIndex]
    let progressInterval: NodeJS.Timeout
    let stageTimer: NodeJS.Timeout

    const progressInterval_ = setInterval(() => {
      setProgress((p) => {
        const newProgress = p + (100 / (currentStage.duration / 50))
        if (newProgress >= 100) {
          clearInterval(progressInterval_)
          return 100
        }
        return newProgress
      })
    }, 50)

    stageTimer = setTimeout(() => {
      if (stageIndex < STAGES.length - 1) {
        setStageIndex(stageIndex + 1)
        setProgress(0)
      } else {
        setIsComplete(true)
      }
    }, currentStage.duration)

    return () => {
      clearInterval(progressInterval_)
      clearTimeout(stageTimer)
    }
  }, [stageIndex, isComplete, onDone])

  const currentStageInfo = STAGES[stageIndex]
  const displayStage = currentStageInfo.name

  return (
    <div className="relative min-h-screen w-full overflow-hidden bg-gradient-to-br from-background via-background to-primary/5 flex items-center justify-center">
      {/* Animated background gradient */}
      <div className="absolute inset-0 -z-10">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_50%,rgba(56,211,235,0.1),transparent_50%)] animate-pulse" />
        <div className="absolute top-0 right-0 w-96 h-96 bg-primary/10 rounded-full blur-3xl animate-blob" />
        <div className="absolute bottom-0 left-0 w-96 h-96 bg-accent/10 rounded-full blur-3xl animate-blob animation-delay-2000" />
      </div>

      {/* Main content */}
      <div className="relative z-10 flex flex-col items-center gap-12 px-4">
        {/* Logo orb */}
        <div className="relative">
          <div className={cn(
            'w-48 h-48 rounded-full bg-gradient-to-br from-primary to-primary/50 shadow-2xl',
            'flex items-center justify-center font-heading text-5xl text-white transition-all duration-500',
            isComplete ? 'scale-100 opacity-100' : 'scale-95 opacity-75'
          )}>
            <div className="absolute inset-0 rounded-full border-2 border-primary/30 animate-spin" style={{ animationDuration: '3s' }} />
            <div className="absolute inset-3 rounded-full border border-primary/20 animate-spin" style={{ animationDuration: '5s', animationDirection: 'reverse' }} />
            <span className="relative z-10">N</span>
          </div>

          {/* Pulsing aura */}
          <div className="absolute inset-0 rounded-full bg-primary/20 blur-2xl animate-pulse" />
        </div>

        {/* Status display */}
        <div className="text-center space-y-4">
          <h1 className="font-heading text-4xl tracking-tight">
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary to-accent">
              Nancy/Billion
            </span>
          </h1>
          <p className="text-muted-foreground text-lg">Sovereign AI Operating System</p>
        </div>

        {/* Stage display */}
        <div className="w-full max-w-md space-y-6">
          {STAGES.map((s, i) => (
            <div
              key={s.name}
              className={cn(
                'p-4 rounded-lg border transition-all duration-500',
                i === stageIndex
                  ? 'border-primary bg-primary/10 shadow-lg shadow-primary/20'
                  : i < stageIndex
                    ? 'border-primary/50 bg-primary/5'
                    : 'border-border/40 bg-secondary/5'
              )}
            >
              <div className="flex items-center gap-3 mb-2">
                <div
                  className={cn(
                    'w-6 h-6 rounded-full border-2 flex items-center justify-center transition-all',
                    i < stageIndex
                      ? 'border-primary bg-primary'
                      : i === stageIndex
                        ? 'border-primary bg-transparent'
                        : 'border-border/40'
                  )}
                >
                  {i < stageIndex && <span className="text-white text-sm">✓</span>}
                  {i === stageIndex && (
                    <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
                  )}
                </div>
                <div>
                  <p className={cn(
                    'font-semibold text-sm',
                    i === stageIndex ? 'text-primary' : i < stageIndex ? 'text-foreground' : 'text-muted-foreground'
                  )}>
                    {s.label}
                  </p>
                  <p className="text-xs text-muted-foreground">{s.description}</p>
                </div>
              </div>

              {i === stageIndex && (
                <div className="w-full h-1 bg-secondary rounded-full overflow-hidden mt-2">
                  <div
                    className="h-full bg-gradient-to-r from-primary to-accent transition-all duration-100"
                    style={{ width: `${Math.min(progress, 100)}%` }}
                  />
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Ready indicator */}
        {isComplete && (
          <div className="text-center space-y-2 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="inline-flex items-center gap-2 text-primary">
              <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
              <span className="text-sm font-medium">All systems operational</span>
            </div>
            <p className="text-xs text-muted-foreground">Initializing command interface...</p>
          </div>
        )}
      </div>

      {/* Bottom info */}
      <div className="absolute bottom-6 text-center text-xs text-muted-foreground/60">
        <p>Version 2.0 • Intelligent Context-Aware Operating System</p>
      </div>
    </div>
  )
}

