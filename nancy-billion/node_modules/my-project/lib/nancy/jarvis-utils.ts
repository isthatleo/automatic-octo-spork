/**
 * JARVIS-inspired utility functions for enhanced Nancy/Billion orb interactions
 * These utilities provide advanced features while maintaining compatibility with existing code
 */

import type { OrbState } from '@/components/nancy/nancy-orb'

/**
 * Enhanced state definitions for JARVIS-like behavior
 */
export interface EnhancedOrbState extends OrbState {
  // Additional states for more nuanced interactions
  awakening?: boolean
  processingDeep?: boolean
  communicatingSecure?: boolean
  learningActive?: boolean
  evolving?: boolean
  anticipating?: boolean
}

/**
 * Maps traditional orb states to enhanced JARVIS states with smooth transitions
 */
export const enhanceOrbState = (baseState: OrbState, context?: Record<string, unknown>): EnhancedOrbState => {
  const enhanced: EnhancedOrbState = {
    ...baseState,
    awakening: baseState === 'idle' && !!context?.userApproach,
    processingDeep: baseState === 'thinking' && !!context?.complexReasoning,
    communicatingSecure: baseState === 'speaking' && !!context?.secureChannel,
    learningActive: baseState === 'thinking' && !!context?.knowledgeAcquisition,
    evolving: baseState === 'thinking' && !!context?.selfOptimization,
    anticipating: !!context?.userIntentPrediction && context.userIntentPrediction > 0.7
  }
  
  return enhanced
}

/**
 * Calculate appropriate visual intensity based on state and context
 */
export const calculateVisualIntensity = (state: EnhancedOrbState, ambientLight: number = 1): number => {
  let baseIntensity = 0.5
  
  switch (true) {
    case state.awakening:
      baseIntensity = 0.3 + Math.sin(Date.now() * 0.005) * 0.2
      break
    case state.processingDeep:
      baseIntensity = 0.7 + Math.sin(Date.now() * 0.01) * 0.2
      break
    case state.communicatingSecure:
      baseIntensity = 0.6 + (Date.now() % 1000) / 1000 * 0.3
      break
    case state.learningActive:
      baseIntensity = 0.5 + Math.sin(Date.now() * 0.008) * 0.3
      break
    case state.evolving:
      baseIntensity = 0.4 + Math.sin(Date.now() * 0.003) * 0.4
      break
    case state.anticipating:
      baseIntensity = 0.8 + Math.sin(Date.now() * 0.015) * 0.15
      break
    default:
      baseIntensity = state === 'listening' ? 0.8 : state === 'speaking' ? 0.7 : 0.5
  }
  
  // Adjust for ambient light conditions
  return Math.min(1.0, Math.max(0.1, baseIntensity * (0.5 + ambientLight * 0.5)))
}

/**
 * Generate JARVIS-inspired audio feedback patterns
 */
export const getAudioFeedbackPattern = (action: string, intensity: number = 0.5): {
  frequency: number
  duration: number
  waveform: 'sine' | 'square' | 'triangle' | 'sawtooth'
} => {
  const patterns: Record<string, { frequency: number; duration: number; waveform: 'sine' | 'square' | 'triangle' | 'sawtooth' }> = {
    wake: { frequency: 800, duration: 150, waveform: 'sine' },
    think: { frequency: 400, duration: 300, waveform: 'triangle' },
    speak: { frequency: 600, duration: 200, waveform: 'sine' },
    alert: { frequency: 1000, duration: 100, waveform: 'square' },
    success: { frequency: [600, 800, 1000], duration: 100, waveform: 'sine' },
    error: { frequency: [400, 200], duration: 150, waveform: 'sawtooth' },
    orbit: { frequency: 200, duration: 500, waveform: 'sine' }
  }
  
  const pattern = patterns[action] || patterns.orbit
  return {
    ...pattern,
    intensity: Math.min(1.0, Math.max(0.0, intensity))
  }
}

/**
 * Create smooth transition values for orb animations
 */
export const createSmoothTransition = (start: number, end: number, progress: number, easing: 'linear' | 'ease-in' | 'ease-out' | 'ease-in-out' = 'ease-in-out'): number => {
  const clampedProgress = Math.min(1, Math.max(0, progress))
  
  switch (easing) {
    case 'ease-in':
      return start + (end - start) * (clampedProgress * clampedProgress)
    case 'ease-out':
      return start + (end - start) * (1 - (1 - clampedProgress) * (1 - clampedProgress))
    case 'ease-in-out':
      return start + (end - start) * (3 * clampedProgress * clampedProgress - 2 * clampedProgress * clampedProgress * clampedProgress)
    default: // linear
      return start + (end - start) * clampedProgress
  }
}

/**
 * Calculate orbital parameters for advanced particle systems
 */
export const calculateOrbitalParameters = (baseRadius: number, particleIndex: number, totalParticles: number, time: number, state: OrbState) => {
  const phase = (particleIndex / totalParticles) * Math.PI * 2
  const orbitSpeed = 0.1 + (state === 'thinking' ? 0.5 : state === 'executing' ? 0.8 : 0.2)
  
  return {
    angle: phase + time * orbitSpeed,
    radius: baseRadius + Math.sin(time * 0.3 + phase) * 0.1,
    elevation: Math.sin(time * 0.2 + phase * 0.7) * 0.05,
    size: 0.5 + Math.sin(time * 0.1 + phase) * 0.3,
    opacity: 0.3 + Math.sin(time * 0.4 + phase) * 0.4
  }
}

/**
 * Generate contextual hints based on system state and user behavior
 */
export const generateContextualHint = (state: OrbState, recentActivity: string[] = [], timeOfDay: number = new Date().getHours()): string => {
  const timeBasedHints = [
    [5, 9, "Good morning. Systems operating at optimal efficiency."],
    [9, 12, "Morning briefing ready. Shall I review today's priorities?"],
    [12, 14, "Afternoon systems check. All divisions functioning nominally."],
    [14, 18, "Productive period detected. Would you like to schedule a break?"],
    [18, 22, "Evening mode engaged. Reduced power consumption active."],
    [22, 5, "Night watch maintaining. Systems running on minimal power."]
  ]
  
  // Check time-based hints first
  for (const [start, end, hint] of timeBasedHints) {
    if (timeOfDay >= start && timeOfDay < end) {
      return hint
    }
  }
  
  // State-based hints
  const stateHints: Record<OrbState, string> = {
    idle: "Awaiting your command, sir.",
    listening: "I'm listening. How may I assist you?",
    thinking: "Processing complex variables...",
    speaking: "Communicating response...",
    executing: "Executing directive..."
  }
  
  return stateHints[state] || "Systems online and ready."
}

/**
 * Detect user intent from interaction patterns (simplified)
 */
export const detectUserIntent = (recentCommands: string[], timeSinceLastInteraction: number): {
  confidence: number
  likelyAction: string
  suggestedResponse: string
} => {
  if (timeSinceLastInteraction > 300000) { // 5 minutes
    return {
      confidence: 0.8,
      likelyAction: 'greeting',
      suggestedResponse: "Welcome back. Systems have been maintaining optimal performance during your absence."
    }
  }
  
  if (recentCommands.length === 0) {
    return {
      confidence: 0.6,
      likelyAction: 'initial_engagement',
      suggestedResponse: "Good day. I am Nancy/Billion, at your service. What would you like to accomplish today?"
    }
  }
  
  const lastCommand = recentCommands[recentCommands.length - 1].toLowerCase()
  
  if (lastCommand.includes('help') || lastCommand.includes('what')) {
    return {
      confidence: 0.9,
      likelyAction: 'explanation_request',
      suggestedResponse: "I can assist with system management, information analysis, strategic planning, and various operational tasks. What specific area would you like to explore?"
    }
  }
  
  if (lastCommand.includes('status') || lastCommand.includes('report')) {
    return {
      confidence: 0.85,
      likelyAction: 'status_request',
      suggestedResponse: "All systems operational. Would you like a detailed report on any particular division?"
    }
  }
  
  return {
    confidence: 0.5,
    likelyAction: 'general_inquiry',
    suggestedResponse: "I'm ready to assist. What would you like to work on?"
  }
}

export default {
  enhanceOrbState,
  calculateVisualIntensity,
  getAudioFeedbackPattern,
  createSmoothTransition,
  calculateOrbitalParameters,
  generateContextualHint,
  detectUserIntent
}