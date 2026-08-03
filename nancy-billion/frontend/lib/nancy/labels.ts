import type { OrbState } from '@/components/nancy/nancy-orb'

export const STATE_HINT: Record<OrbState, string> = {
  idle: 'Standing By',
  listening: 'Listening',
  thinking: 'Processing',
  speaking: 'Responding',
  executing: 'Executing',
  alert: 'Degraded',
  // Book VI Ch.10's cognitive states. Each names the KIND of thought, not a
  // generic "busy" -- the point of splitting them out of `thinking` is that
  // the user can tell recall from reasoning from research at a glance.
  reasoning: 'Reasoning',
  researching: 'Researching',
  recalling: 'Recalling',
  planning: 'Planning',
  reflecting: 'Reflecting',
  learning: 'Learning',
  sleeping: 'Dormant',
}
