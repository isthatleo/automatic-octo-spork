'use strict'

/**
 * Proactive Assistant - Anticipates user needs and provides contextual assistance
 * Inspired by JARVIS's proactive capabilities
 */

export interface ContextEvent {
  type: string
  data: Record<string, any>
  timestamp: string
}

export interface ProactiveSuggestion {
  id: string
  type: 'info' | 'warning' | 'opportunity' | 'reminder'
  title: string
  description: string
  action?: () => void
  priority: number // 1-5, 5 being highest
  timestamp: string
}

export class ProactiveAssistant {
  private contextEvents: ContextEvent[] = []
  private suggestions: ProactiveSuggestion[] = []
  private readonly maxContextEvents = 1000
  private readonly maxSuggestions = 50
  private initialized = false

  constructor() {
    // Initialize with empty state
  }

  /**
   * Initialize the proactive assistant
   */
  public initialize(): void {
    if (this.initialized) return
    this.initialized = true
    console.log('Proactive Assistant initialized')
    
    // Start background monitoring
    this.startContextMonitoring()
  }

  /**
   * Add a context event for pattern learning
   */
  public addContextEvent(type: string, data: Record<string, any> = {}): void {
    const event: ContextEvent = {
      type,
      data: { ...data, timestamp: new Date().toISOString() },
      timestamp: new Date().toISOString()
    }

    this.contextEvents.push(event)
    
    // Keep only recent events
    if (this.contextEvents.length > this.maxContextEvents) {
      this.contextEvents = this.contextEvents.slice(-this.maxContextEvents)
    }

    // Process for insights
    this.processContextInsights()
  }

  /**
   * Get proactive suggestions based on context
   */
  public getSuggestions(): ProactiveSuggestion[] {
    return [...this.suggestions].sort((a, b) => b.priority - a.priority)
  }

  /**
   * Clear all suggestions
   */
  public clearSuggestions(): void {
    this.suggestions = []
  }

  /**
   * Start background context monitoring
   */
  private startContextMonitoring(): void {
    // Monitor time-based events
    setInterval(() => {
      this.checkTimeBasedEvents()
    }, 60000) // Check every minute

    // Monitor for patterns every 5 minutes
    setInterval(() => {
      this.detectPatterns()
    }, 300000)
  }

  /**
   * Check for time-based events and reminders
   */
  private checkTimeBasedEvents(): void {
    const now = new Date()
    const hour = now.getHours()
    const minute = now.getMinutes()

    // Morning briefing (7:30 AM)
    if (hour === 7 && minute === 30) {
      this.addSuggestion({
        id: `morning-briefing-${now.toDateString()}`,
        type: 'opportunity',
        title: 'Good morning',
        description: 'Shall I provide your daily briefing?',
        priority: 4,
        timestamp: now.toISOString()
      })
    }

    // Evening wind-down (9:00 PM)
    if (hour === 21 && minute === 0) {
      this.addSuggestion({
        id: `evening-checkin-${now.toDateString()}`,
        type: 'info',
        title: 'Evening check-in',
        description: 'Would you like me to secure the house and set tomorrow\'s agenda?',
        priority: 3,
        timestamp: now.toISOString()
      })
    }
  }

  /**
   * Detect patterns in user behavior
   */
  private detectPatterns(): void {
    // Analyze recent commands for patterns
    const recentEvents = this.contextEvents.slice(-20) // Last 20 events
    
    // Look for common command sequences
    const commandTypes = recentEvents
      .filter(e => e.type === 'command_executed')
      .map(e => e.data.action)
      .filter((action): action is string => typeof action === 'string')

    // If user frequently checks news in the morning, suggest it proactively
    const morningNewsChecks = commandTypes.filter(action => 
      action === 'navigate' && 
      new Date().getHours() >= 6 && 
      new Date().getHours() <= 9
    ).length

    if (morningNewsChecks >= 3) {
      // Check if we already have a similar suggestion
      const existing = this.suggestions.some(s => 
        s.id.startsWith('news-suggestion')
      )

      if (!existing) {
        this.addSuggestion({
          id: `news-suggestion-${Date.now()}`,
          type: 'opportunity',
          title: 'News briefing available',
          description: 'I\'ve compiled the latest developments in technology and finance.',
          priority: 3,
          timestamp: new Date().toISOString()
        })
      }
    }
  }

  /**
   * Process context events for insights
   */
  private processContextInsights(): void {
    // This would typically involve more sophisticated ML pattern recognition
    // For now, we'll implement basic heuristics
    
    // Check for signs of user being busy or stressed
    const recentCommands = this.contextEvents.slice(-10)
      .filter(e => e.type === 'command_executed')
      .length

    if (recentCommands > 8) { // High command frequency might indicate stress
      const existing = this.suggestions.some(s => 
        s.id === 'wellness-check'
      )

      if (!existing) {
        this.addSuggestion({
          id: 'wellness-check',
          type: 'info',
          title: 'You\'ve been active',
          description: 'Would you like me to handle some routine tasks so you can focus?',
          priority: 2,
          timestamp: new Date().toISOString()
        })
      }
    }
  }

  /**
   * Add a suggestion to the queue
   */
  private addSuggestion(suggestion: Omit<ProactiveSuggestion, 'id' | 'timestamp'> & Partial<Pick<ProactiveSuggestion, 'id' | 'timestamp'>>): void {
    const sug: ProactiveSuggestion = {
      id: suggestion.id ?? `sug-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
      type: suggestion.type,
      title: suggestion.title,
      description: suggestion.description,
      action: suggestion.action,
      priority: suggestion.priority ?? 1,
      timestamp: suggestion.timestamp ?? new Date().toISOString()
    }

    // Avoid duplicates
    const exists = this.suggestions.some(s => s.title === sug.title && s.type === sug.type)
    if (!exists) {
      this.suggestions.push(sug)
      
      // Keep only recent suggestions
      if (this.suggestions.length > this.maxSuggestions) {
        this.suggestions = this.suggestions.slice(-this.maxSuggestions)
      }
    }
  }
}

// Export singleton instance
export const proactiveAssistant = new ProactiveAssistant()

// Auto-initialize when imported if in browser
if (typeof window !== 'undefined') {
  // Initialize on load
  window.addEventListener('load', () => {
    proactiveAssistant.initialize()
  })
}