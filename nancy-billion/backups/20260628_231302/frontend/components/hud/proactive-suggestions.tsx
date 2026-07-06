'use client'

import { useEffect, useState } from 'react'
import type { ProactiveSuggestion, SuggestionType, Priority } from '@/lib/nancy/proactive-types'

export function ProactiveSuggestions() {
  const [suggestions, setSuggestions] = useState<Array<{
    id: string
    type: SuggestionType
    priority: Priority
    title: string
    description: string
    actionText: string
    actionData: any
    expiresAt: string
    context: any
    confidence: number
    createdAt: string
  }>>([])

  useEffect(() => {
    const fetchSuggestions = async () => {
      try {
        const response = await fetch('/api/proactive/suggestions')
        if (response.ok) {
          const data = await response.json()
          setSuggestions(data)
        }
      } catch (error) {
        console.error('Failed to fetch proactive suggestions:', error)
      }
    }

    const interval = setInterval(fetchSuggestions, 5000) // Update every 5 seconds
    fetchSuggestions() // Initial load
    
    return () => clearInterval(interval)
  }, [])

  const handleAccept = async (id: string) => {
    try {
      const response = await fetch(`/api/proactive/suggestions/${id}/accept`, {
        method: 'POST'
      })
      if (response.ok) {
        // Refresh suggestions
        fetchSuggestions()
      }
    } catch (error) {
      console.error('Failed to accept suggestion:', error)
    }
  }

  const handleDismiss = async (id: string) => {
    try {
      const response = await fetch(`/api/proactive/suggestions/${id}/dismiss`, {
        method: 'DELETE'
      })
      if (response.ok) {
        // Refresh suggestions
        fetchSuggestions()
      }
    } catch (error) {
      console.error('Failed to dismiss suggestion:', error)
    }
  }

  const getPriorityClass = (priority: Priority) => {
    switch (priority) {
      case Priority.URGENT: return 'border-l-4 border-hud/100 bg-hud/5'
      case Priority.HIGH: return 'border-l-4 border-hud/80 bg-hud/3'
      case Priority.MEDIUM: return 'border-l-4 border-hud/60 bg-hud/2'
      case Priority.LOW: return 'border-l-4 border-hud/40 bg-hud/1'
      default: return 'border-l-4 border-hud/20'
    }
  }

  const getTypeIcon = (type: SuggestionType) => {
    switch (type) {
      case SuggestionType.CALENDAR_PREP: return '📅'
      case SuggestionType.EMAIL_RESPONSE: return '📧'
      case SuggestionType.INFORMATION_GATHER: return '📋'
      case SuggestionType.TASK_REMINDER: return '⏰'
      case SuggestionType.CONTEXTUAL_HELP: return '💡'
      case SuggestionType.ROUTINE_OPTIMIZATION: return '🔄'
      // Environmental suggestion types
      case 'environmental_lighting': return '💡'
      case 'environmental_activity': return '🏃'
      case 'environmental_proximity': return '📏'
      default: return '✨'
    }
  }
  
  // Environmental suggestion type mapper
  const mapEnvironmentalType = (type: string): SuggestionType => {
    switch (type) {
      case 'environmental_lighting': return SuggestionType.CONTEXTUAL_HELP
      case 'environmental_activity': return SuggestionType.CONTEXTUAL_HELP
      case 'environmental_proximity': return SuggestionType.ROUTINE_OPTIMIZATION
      default: return SuggestionType.CONTEXTUAL_HELP
    }
  }

  if (suggestions.length === 0) {
    return null
  }

  return (
    <div className="fixed bottom-4 right-4 max-w-xs z-50 pointer-auto">
      <div className="space-y-3">
        {suggestions.map((suggestion) => (
          <div key={suggestion.id} className={`${getPriorityClass(suggestion.priority)} rounded-lg p-4 backdrop-blur-sm border border-hud/20 shadow-lg transition-all duration-300 hover:shadow-hud/20 hover:bg-hud/10`}>
            <div className="flex items-start justify-between mb-2">
              <div className="flex items-center space-x-2">
                <span className="text-hud/100 text-lg">{getTypeIcon(suggestion.type)}</span>
                <div>
                  <h3 className="font-semibold text-hud/100">{suggestion.title}</h3>
                  <p className="text-sm text-hud/60 line-clamp-2">{suggestion.description}</p>
                </div>
              </div>
              <div className="text-xs text-hud/40">
                {Math.round(suggestion.confidence * 100)}% confidence
              </div>
            </div>
            <div className="flex items-center justify-between">
              <button
                onClick={() => handleAccept(suggestion.id)}
                className="flex items-center space-x-1 px-3 py-1.5 text-sm font-medium bg-hud/10 border border-hud/30 rounded hover:bg-hud/20 hover:text-hud/100 transition-colors"
              >
                {suggestion.actionText}
                <span className="ml-1">→</span>
              </button>
              <button
                onClick={() => handleDismiss(suggestion.id)}
                className="text-hud/40 hover:text-hud/60 text-sm"
              >
                ×
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}