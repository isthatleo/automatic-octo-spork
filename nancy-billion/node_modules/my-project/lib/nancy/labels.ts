import type { OrbState } from '@/components/nancy/nancy-orb'

export const STATE_HINT: Record<OrbState, string> = {
  idle: 'Standing By',
  listening: 'Listening',
  thinking: 'Processing',
  speaking: 'Responding',
  executing: 'Executing',
  alert: 'Degraded',
}
