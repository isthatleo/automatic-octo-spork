'use client'

import React, { useEffect, useState, useCallback } from 'react'
import { cn } from '@/lib/utils'
import { Clock, Zap, AlertCircle, CheckCircle2 } from 'lucide-react'

interface GreetingData {
  persona: string
  greeting: string
  context_summary: {
    meetings: number
    build_status?: string
    market_alerts: number
    project_updates: number
    active_trades: number
    tasks_due: number
  }
  quick_actions: string[]
  next_question: string
}

type TimeOfDay = 'morning' | 'afternoon' | 'evening' | 'night'

export function PersonalizedGreetingScreen({ onComplete }: { onComplete: () => void }) {
  const [greeting, setGreeting] = useState<GreetingData | null>(null)
  const [timeOfDay, setTimeOfDay] = useState<TimeOfDay>('morning')
  const [displayText, setDisplayText] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [stage, setStage] = useState<'greeting' | 'context' | 'ready'>('greeting')

  // Determine time of day
  useEffect(() => {
    const hour = new Date().getHours()
    if (hour < 12) setTimeOfDay('morning')
    else if (hour < 17) setTimeOfDay('afternoon')
    else if (hour < 21) setTimeOfDay('evening')
    else setTimeOfDay('night')
  }, [])

  // Fetch personalized greeting
  useEffect(() => {
    const fetchGreeting = async () => {
      try {
        // In production, fetch real context from your systems
        // For now, we'll use demo data
        const demoContext = {
          meetings_today: ['10:00 - Team Standup', '14:00 - Product Review'],
          build_status: 'completed',
          market_alerts: [
            'EUR/USD approaching 1.0850 (your watched level)',
            'GBP/USD resistance broken'
          ],
          project_updates: [
            'Roxan deployment completed without errors',
            'Database migration successful'
          ],
          active_trades: ['EUR/USD LONG @ 1.0825'],
          tasks_due: ['Review PR #234', 'Update documentation']
        }

        const response = await fetch('/api/greeting/personalized', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(demoContext)
        })

        if (response.ok) {
          const data = await response.json()
          setGreeting(data)
          setIsLoading(false)
        } else {
          // Fallback
          setGreeting({
            persona: 'nancy',
            greeting: `${getTimeGreeting(timeOfDay)}. All systems ready.`,
            context_summary: {
              meetings: 0,
              market_alerts: 0,
              project_updates: 0,
              active_trades: 0,
              tasks_due: 0
            },
            quick_actions: [],
            next_question: 'What would you like to do?'
          })
          setIsLoading(false)
        }
      } catch (error) {
        console.error('Failed to fetch greeting:', error)
        setGreeting({
          persona: 'nancy',
          greeting: `${getTimeGreeting(timeOfDay)}. All systems operational.`,
          context_summary: {
            meetings: 0,
            market_alerts: 0,
            project_updates: 0,
            active_trades: 0,
            tasks_due: 0
          },
          quick_actions: [],
          next_question: 'What would you like to do?'
        })
        setIsLoading(false)
      }
    }

    fetchGreeting()
  }, [timeOfDay])

  // Type out greeting
  useEffect(() => {
    if (!greeting || stage !== 'greeting') return

    let index = 0
    const fullText = greeting.greeting
    const interval = setInterval(() => {
      if (index < fullText.length) {
        setDisplayText(fullText.substring(0, index + 1))
        index++
      } else {
        clearInterval(interval)
        setTimeout(() => setStage('context'), 1000)
      }
    }, 30)

    return () => clearInterval(interval)
  }, [greeting, stage])

  // Show context
  useEffect(() => {
    if (stage !== 'context') return

    setTimeout(() => {
      setStage('ready')
      setTimeout(() => onComplete(), 2000)
    }, 2000)
  }, [stage, onComplete])

  const getTimeGreeting = (time: TimeOfDay) => {
    switch (time) {
      case 'morning':
        return 'Good Morning'
      case 'afternoon':
        return 'Good Afternoon'
      case 'evening':
        return 'Good Evening'
      case 'night':
        return 'Good Night'
    }
  }

  return (
    <div className="min-h-screen w-full bg-gradient-to-br from-slate-950 via-blue-950 to-slate-900 flex items-center justify-center overflow-hidden">
      {/* Animated background grid */}
      <div className="absolute inset-0 bg-[linear-gradient(45deg,transparent_25%,rgba(68,68,68,.2)_25%,rgba(68,68,68,.2)_50%,transparent_50%,transparent_75%,rgba(68,68,68,.2)_75%,rgba(68,68,68,.2))] bg-[length:60px_60px] animate-pulse opacity-20" />

      {/* Holographic orb */}
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="relative w-64 h-64">
          <div className="absolute inset-0 bg-gradient-to-br from-cyan-500 to-blue-600 rounded-full blur-3xl opacity-20 animate-pulse" />
          <div className="absolute inset-8 bg-gradient-to-br from-cyan-400 to-blue-500 rounded-full blur-xl opacity-30" />
          <div className="absolute inset-16 bg-gradient-to-br from-cyan-300 to-blue-400 rounded-full blur-lg opacity-40" />
        </div>
      </div>

      {/* Content */}
      <div className="relative z-10 text-center space-y-8 px-4 max-w-2xl">
        {/* Time greeting */}
        <div className="flex items-center justify-center gap-3 text-cyan-400">
          <Clock className="w-5 h-5" />
          <span className="text-sm font-mono uppercase tracking-widest">
            {getTimeGreeting(timeOfDay)} at {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>

        {/* Main greeting */}
        <div className="space-y-4">
          <h1 className="text-5xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-cyan-300 to-blue-400">
            Nancy
          </h1>
          <div className="h-32 flex items-center justify-center">
            <p className="text-lg text-gray-200 leading-relaxed min-h-[2rem]">
              {displayText}
              {stage === 'greeting' && <span className="animate-pulse">_</span>}
            </p>
          </div>
        </div>

        {/* Context summary */}
        {stage !== 'greeting' && greeting && (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4 pt-8">
            {greeting.context_summary.meetings > 0 && (
              <div className="p-3 rounded-lg border border-cyan-500/30 bg-cyan-500/5">
                <div className="text-2xl font-bold text-cyan-400">{greeting.context_summary.meetings}</div>
                <div className="text-xs text-gray-400">Meetings</div>
              </div>
            )}
            {greeting.context_summary.market_alerts > 0 && (
              <div className="p-3 rounded-lg border border-orange-500/30 bg-orange-500/5">
                <div className="text-2xl font-bold text-orange-400">{greeting.context_summary.market_alerts}</div>
                <div className="text-xs text-gray-400">Market Alerts</div>
              </div>
            )}
            {greeting.context_summary.active_trades > 0 && (
              <div className="p-3 rounded-lg border border-green-500/30 bg-green-500/5">
                <div className="text-2xl font-bold text-green-400">{greeting.context_summary.active_trades}</div>
                <div className="text-xs text-gray-400">Open Trades</div>
              </div>
            )}
            {greeting.context_summary.project_updates > 0 && (
              <div className="p-3 rounded-lg border border-purple-500/30 bg-purple-500/5">
                <div className="text-2xl font-bold text-purple-400">{greeting.context_summary.project_updates}</div>
                <div className="text-xs text-gray-400">Projects</div>
              </div>
            )}
            {greeting.context_summary.tasks_due > 0 && (
              <div className="p-3 rounded-lg border border-yellow-500/30 bg-yellow-500/5">
                <div className="text-2xl font-bold text-yellow-400">{greeting.context_summary.tasks_due}</div>
                <div className="text-xs text-gray-400">Tasks</div>
              </div>
            )}
            {greeting.context_summary.build_status === 'completed' && (
              <div className="p-3 rounded-lg border border-green-500/30 bg-green-500/5 flex items-center justify-center">
                <CheckCircle2 className="w-6 h-6 text-green-400" />
                <span className="text-xs text-gray-400 ml-2">Build OK</span>
              </div>
            )}
          </div>
        )}

        {/* Status */}
        <div className="text-sm text-gray-400 font-mono">
          {isLoading && 'Initializing systems...'}
          {!isLoading && stage === 'greeting' && 'Analyzing context...'}
          {!isLoading && stage === 'context' && 'Processing information...'}
          {!isLoading && stage === 'ready' && 'Ready to assist'}
        </div>
      </div>

      {/* Scan line effect */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-500 to-transparent opacity-20 animate-pulse" />
      </div>
    </div>
  )
}

