'use client'

import { useState, useEffect } from 'react'
import { Zap, Shield, Brain, Activity, Globe, TrendingUp } from 'lucide-react'

interface GodModePanelProps {
  className?: string
}

interface DivisionStats {
  name: string
  icon: string
  agentCount: number
  load: number
}

const DIVISIONS: DivisionStats[] = [
  { name: 'Research',    icon: '🔬', agentCount: 29, load: 72 },
  { name: 'Development', icon: '⚙️', agentCount: 45, load: 68 },
  { name: 'Security',   icon: '🛡️', agentCount: 25, load: 45 },
  { name: 'Analytics',  icon: '📊', agentCount: 22, load: 81 },
  { name: 'Business',   icon: '💼', agentCount: 18, load: 37 },
  { name: 'Companion',  icon: '💖', agentCount: 15, load: 29 },
  { name: 'Workflow',   icon: '🔄', agentCount: 33, load: 55 },
  { name: 'Intelligence', icon: '🧠', agentCount: 41, load: 63 },
]

function useJitter(base: number, amp = 8) {
  const [v, setV] = useState(base)
  useEffect(() => {
    const t = setInterval(() => {
      setV(Math.max(5, Math.min(99, base + (Math.random() - 0.5) * amp * 2)))
    }, 2000)
    return () => clearInterval(t)
  }, [base, amp])
  return Math.round(v)
}

export function GodModePanel({ className }: GodModePanelProps) {
  const globalLoad = useJitter(67)
  const threatLevel = useJitter(12, 4)
  const syncRate = useJitter(94, 3)

  return (
    <div className={`flex flex-col gap-4 ${className ?? ''}`}>
      {/* Header */}
      <div className="flex items-center justify-between border-b border-primary/20 pb-3">
        <h2 className="flex items-center gap-2 font-heading text-lg tracking-widest text-primary">
          <Zap className="h-4 w-4 animate-pulse" />
          GOD MODE
        </h2>
        <span className="text-[0.5rem] text-muted-foreground">
          {new Date().toLocaleTimeString()}
        </span>
      </div>

      {/* Global metrics */}
      <div className="grid grid-cols-3 gap-2 text-center">
        {[
          { label: 'LOAD', value: `${globalLoad}%`, color: 'text-primary' },
          { label: 'THREAT', value: `${threatLevel}%`, color: threatLevel > 30 ? 'text-destructive' : 'text-accent' },
          { label: 'SYNC', value: `${syncRate}%`, color: 'text-primary' },
        ].map(({ label, value, color }) => (
          <div key={label} className="rounded border border-border bg-secondary/20 py-2">
            <div className={`font-heading text-sm ${color}`}>{value}</div>
            <div className="text-[0.45rem] uppercase tracking-widest text-muted-foreground">{label}</div>
          </div>
        ))}
      </div>

      {/* Division overview */}
      <div>
        <p className="mb-2 text-[0.5rem] uppercase tracking-widest text-muted-foreground">
          Division Matrix
        </p>
        <div className="flex flex-col gap-1">
          {DIVISIONS.map(({ name, icon, agentCount, load }) => (
            <div key={name} className="flex items-center gap-2 rounded border border-border/50 bg-secondary/20 px-2 py-1.5">
              <span className="text-sm">{icon}</span>
              <span className="flex-1 text-[0.55rem] text-foreground">{name}</span>
              <span className="text-[0.45rem] text-muted-foreground">{agentCount} agents</span>
              <div className="h-1 w-16 overflow-hidden rounded-full bg-background">
                <div
                  className="h-full rounded-full bg-primary/70"
                  style={{ width: `${load}%` }}
                />
              </div>
              <span className="w-6 text-right text-[0.45rem] text-muted-foreground">{load}%</span>
            </div>
          ))}
        </div>
      </div>

      {/* Status indicators */}
      <div className="flex flex-wrap gap-1.5">
        {[
          { icon: Brain, label: 'Cognition', status: 'ACTIVE' },
          { icon: Shield, label: 'Defence', status: 'ARMED' },
          { icon: Globe, label: 'Network', status: 'ONLINE' },
          { icon: Activity, label: 'Vitals', status: 'NOMINAL' },
          { icon: TrendingUp, label: 'Learning', status: 'RUNNING' },
        ].map(({ icon: Icon, label, status }) => (
          <div key={label} className="flex items-center gap-1 rounded border border-primary/30 bg-primary/10 px-1.5 py-0.5">
            <Icon className="h-2.5 w-2.5 text-primary" />
            <span className="text-[0.45rem] text-muted-foreground">{label}</span>
            <span className="text-[0.45rem] text-primary">{status}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default GodModePanel