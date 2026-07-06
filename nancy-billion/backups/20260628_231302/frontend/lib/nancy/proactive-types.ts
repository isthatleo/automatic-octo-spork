export type SuggestionType =
  | 'calendar_prep'
  | 'email_response'
  | 'information_gather'
  | 'task_reminder'
  | 'contextual_help'
  | 'routine_optimization'

export type Priority = 1 | 2 | 3 | 4 // LOW, MEDIUM, HIGH, URGENT

export interface ProactiveSuggestion {
  id: string
  type: SuggestionType
  priority: Priority
  title: string
  description: string
  actionText: string
  actionData: any
  expiresAt: string // ISO date string
  context: any
  confidence: number // 0.0 to 1.0
  createdAt: string // ISO date string
}