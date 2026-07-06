'use client'

import React, { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'

type Persona = 'nancy' | 'billion' | 'jarvis'

interface GreetingData {
  persona: Persona
  boot_message: string
  ready_message: string
  context_aware_greeting: string
}

export function NancyStartupGreeting({ onComplete }: { onComplete: () => void }) {
  const [greeting, setGreeting] = useState<GreetingData | null>(null)
  const [displayText, setDisplayText] = useState('')
  const [stage, setStage] = useState<'boot' | 'ready' | 'complete'>('boot')
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    // Fetch greeting from backend
    fetch('/api/greeting')
      .then((res) => res.json())
      .then((data) => {
        setGreeting(data)
        setIsLoading(false)
      })
      .catch((err) => {
        console.error('Failed to fetch greeting:', err)
        // Fallback to default
        setGreeting({
          persona: 'nancy',
          boot_message: "✨ Nancy initializing... All systems coming online.",
          ready_message: "Hello! I'm Nancy. Ready to assist with whatever you need. What's on your mind?",
          context_aware_greeting: "What can I help you with today?"
        })
        setIsLoading(false)
      })
  }, [])

  useEffect(() => {
    if (!greeting) return

    if (stage === 'boot') {
      // Type boot message
      let index = 0
      const bootMessage = greeting.boot_message
      const interval = setInterval(() => {
        if (index < bootMessage.length) {
          setDisplayText(bootMessage.substring(0, index + 1))
          index++
        } else {
          clearInterval(interval)
          setTimeout(() => {
            setStage('ready')
            setDisplayText('')
          }, 1000)
        }
      }, 30)

      return () => clearInterval(interval)
    } else if (stage === 'ready') {
      // Type ready message
      let index = 0
      const readyMessage = greeting.ready_message
      const interval = setInterval(() => {
        if (index < readyMessage.length) {
          setDisplayText(readyMessage.substring(0, index + 1))
          index++
        } else {
          clearInterval(interval)
          setTimeout(() => {
            setStage('complete')
            onComplete()
          }, 2000)
        }
      }, 20)

      return () => clearInterval(interval)
    }
  }, [greeting, stage, onComplete])

  const getPersonaColor = (persona: Persona) => {
    switch (persona) {
      case 'nancy':
        return 'from-blue-500 to-cyan-500'
      case 'billion':
        return 'from-purple-500 to-pink-500'
      case 'jarvis':
        return 'from-gray-600 to-blue-600'
      default:
        return 'from-blue-500 to-cyan-500'
    }
  }

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-gradient-to-br from-background to-background/95">
      {/* Background effects */}
      <div className="absolute inset-0 -z-10">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_50%,rgba(56,211,235,0.1),transparent_50%)] animate-pulse" />
      </div>

      {/* Main content */}
      <div className="text-center space-y-8 px-4">
        {/* Logo orb */}
        {greeting && (
          <div
            className={cn(
              'w-32 h-32 rounded-full mx-auto',
              'bg-gradient-to-br',
              getPersonaColor(greeting.persona),
              'shadow-2xl flex items-center justify-center',
              'animate-pulse'
            )}
          >
            <span className="text-4xl font-bold text-white">
              {greeting.persona === 'nancy' && '✨'}
              {greeting.persona === 'billion' && '💰'}
              {greeting.persona === 'jarvis' && '🎩'}
            </span>
          </div>
        )}

        {/* Persona name */}
        {greeting && (
          <h1 className="text-3xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-primary to-accent">
            {greeting.persona.toUpperCase()}
          </h1>
        )}

        {/* Typing text */}
        <div className="h-20 flex items-center justify-center">
          <p className="text-lg text-foreground/90 whitespace-pre-wrap max-w-md">
            {displayText}
            <span className="animate-pulse">_</span>
          </p>
        </div>

        {/* Loading indicator */}
        {isLoading && (
          <div className="flex justify-center gap-2">
            <div className="w-2 h-2 rounded-full bg-primary animate-bounce" />
            <div className="w-2 h-2 rounded-full bg-primary animate-bounce" style={{ animationDelay: '0.2s' }} />
            <div className="w-2 h-2 rounded-full bg-primary animate-bounce" style={{ animationDelay: '0.4s' }} />
          </div>
        )}

        {/* Status indicator */}
        <div className="text-sm text-muted-foreground">
          {stage === 'boot' && 'Systems initializing...'}
          {stage === 'ready' && 'Coming online...'}
          {stage === 'complete' && 'Ready to assist'}
        </div>
      </div>
    </div>
  )
}

export function PersonaSelector({ onSelectPersona }: { onSelectPersona: (persona: Persona) => void }) {
  const personas: Array<{ name: Persona; emoji: string; description: string }> = [
    { name: 'nancy', emoji: '✨', description: 'Friendly & helpful' },
    { name: 'billion', emoji: '💰', description: 'Ambitious & driven' },
    { name: 'jarvis', emoji: '🎩', description: 'Formal & precise' },
  ]

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold text-center">Choose your Nancy</h2>

      <div className="grid grid-cols-3 gap-4">
        {personas.map((persona) => (
          <button
            key={persona.name}
            onClick={() => onSelectPersona(persona.name)}
            className="p-4 rounded-lg border border-border/40 hover:border-primary/80 hover:bg-primary/10 transition-all"
          >
            <div className="text-3xl mb-2">{persona.emoji}</div>
            <div className="font-semibold capitalize">{persona.name}</div>
            <div className="text-xs text-muted-foreground">{persona.description}</div>
          </button>
        ))}
      </div>
    </div>
  )
}

