'use client'

import React, { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'
import { Brain, Zap, Map, Code2, TrendingUp, MessageSquare } from 'lucide-react'

interface IntentInfo {
  intent: string
  confidence: number
  routing_hints: string[]
}

export function DashboardV2() {
  const [intents, setIntents] = useState<IntentInfo[]>([])
  const [activePanel, setActivePanel] = useState<'overview' | 'analysis' | 'memory'>('overview')

  const QUICK_ACTIONS = [
    { icon: MessageSquare, label: 'Chat', intent: 'chat', color: 'from-blue-500' },
    { icon: Map, label: 'Navigate', intent: 'map', color: 'from-green-500' },
    { icon: Code2, label: 'Code', intent: 'coding', color: 'from-purple-500' },
    { icon: TrendingUp, label: 'Trading', intent: 'trading', color: 'from-orange-500' },
  ]

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background/95 to-primary/5 p-4 md:p-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-4xl font-heading tracking-tight mb-2">
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary via-accent to-primary">
            Nancy Intelligence Center
          </span>
        </h1>
        <p className="text-muted-foreground">Context-aware AI operating system</p>
      </div>

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Main panel */}
        <div className="lg:col-span-2 space-y-6">
          {/* Quick actions */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {QUICK_ACTIONS.map((action) => {
              const Icon = action.icon
              return (
                <button
                  key={action.intent}
                  className="group relative p-4 rounded-lg border border-border/40 bg-card hover:bg-card/80 hover:border-primary/50 transition-all duration-300 overflow-hidden"
                >
                  <div className={cn(
                    'absolute inset-0 bg-gradient-to-br opacity-0 group-hover:opacity-10 transition-opacity',
                    action.color
                  )} />
                  <div className="relative z-10 flex flex-col items-center gap-2">
                    <Icon className="w-6 h-6 text-primary group-hover:text-accent transition-colors" />
                    <span className="text-sm font-medium text-foreground group-hover:text-primary transition-colors">
                      {action.label}
                    </span>
                  </div>
                </button>
              )
            })}
          </div>

          {/* Intent analysis panel */}
          <div className="p-6 rounded-lg border border-border/40 bg-card">
            <div className="flex items-center gap-2 mb-4">
              <Brain className="w-5 h-5 text-primary" />
              <h2 className="text-lg font-semibold">Intent Recognition</h2>
            </div>

            <div className="space-y-3">
              {['chat', 'map', 'trading', 'coding'].map((intent) => (
                <div
                  key={intent}
                  className="p-3 rounded border border-border/40 bg-secondary/50 hover:border-primary/50 transition-colors cursor-pointer group"
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="capitalize font-medium text-sm">{intent}</span>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <div className="w-8 h-1.5 bg-secondary rounded-full overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-primary to-accent"
                          style={{ width: `${Math.random() * 100}%` }}
                        />
                      </div>
                      <span>75%</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Context panel */}
          <div className="p-6 rounded-lg border border-border/40 bg-card">
            <div className="flex items-center gap-2 mb-4">
              <Zap className="w-5 h-5 text-accent" />
              <h2 className="text-lg font-semibold">Active Context</h2>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="p-3 rounded bg-secondary/30 border border-border/40">
                <p className="text-xs text-muted-foreground mb-1">Conversation Topics</p>
                <div className="flex flex-wrap gap-1">
                  {['chat', 'analysis'].map((topic) => (
                    <span key={topic} className="px-2 py-1 rounded text-xs bg-primary/10 text-primary border border-primary/20">
                      {topic}
                    </span>
                  ))}
                </div>
              </div>

              <div className="p-3 rounded bg-secondary/30 border border-border/40">
                <p className="text-xs text-muted-foreground mb-1">System Status</p>
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                  <span className="text-sm font-medium">All Systems Online</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right: Status & Info */}
        <div className="space-y-6">
          {/* Nancy status */}
          <div className="p-6 rounded-lg border border-border/40 bg-card">
            <div className="text-center mb-6">
              <div className="w-20 h-20 rounded-full bg-gradient-to-br from-primary to-accent mx-auto mb-3 flex items-center justify-center">
                <span className="text-2xl font-bold text-white">N</span>
              </div>
              <h3 className="font-semibold">Nancy/Billion</h3>
              <p className="text-xs text-muted-foreground">Context-Aware OS</p>
            </div>

            <div className="space-y-3">
              <div className="flex justify-between items-center text-sm">
                <span className="text-muted-foreground">Intelligence</span>
                <div className="w-16 h-1.5 bg-secondary rounded-full overflow-hidden">
                  <div className="h-full w-3/4 bg-gradient-to-r from-primary to-accent" />
                </div>
              </div>
              <div className="flex justify-between items-center text-sm">
                <span className="text-muted-foreground">Memory</span>
                <div className="w-16 h-1.5 bg-secondary rounded-full overflow-hidden">
                  <div className="h-full w-1/2 bg-gradient-to-r from-accent to-primary" />
                </div>
              </div>
              <div className="flex justify-between items-center text-sm">
                <span className="text-muted-foreground">Response Speed</span>
                <div className="w-16 h-1.5 bg-secondary rounded-full overflow-hidden">
                  <div className="h-full w-5/6 bg-gradient-to-r from-orange-500 to-red-500" />
                </div>
              </div>
            </div>
          </div>

          {/* Recent insights */}
          <div className="p-6 rounded-lg border border-border/40 bg-card">
            <h3 className="font-semibold mb-4 text-sm">System Insights</h3>
            <ul className="space-y-2 text-xs">
              <li className="flex gap-2">
                <span className="text-primary">•</span>
                <span className="text-muted-foreground">Weather queries are properly identified (not maps)</span>
              </li>
              <li className="flex gap-2">
                <span className="text-accent">•</span>
                <span className="text-muted-foreground">Context memory system is active</span>
              </li>
              <li className="flex gap-2">
                <span className="text-orange-500">•</span>
                <span className="text-muted-foreground">Trading intelligence module ready</span>
              </li>
            </ul>
          </div>

          {/* Coming soon */}
          <div className="p-6 rounded-lg border border-border/40 bg-secondary/30">
            <h3 className="font-semibold mb-3 text-sm">Coming Soon</h3>
            <ul className="space-y-1 text-xs text-muted-foreground">
              <li>✓ Memory Graph System</li>
              <li>✓ Voice UI Streaming</li>
              <li>✓ Forex Intelligence</li>
              <li>✓ Docker Deployment</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  )
}

