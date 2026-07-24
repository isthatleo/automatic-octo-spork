/**
 * Human-readable descriptions of real backend domain events (see
 * backend/event_bus.py) -- shared between Mission Control's Live Activity
 * feed and the Workflow Orchestrator's Live Feed so the two pages narrate
 * the same real events identically instead of drifting.
 */
import type { DomainEvent, MissionStage } from './types'

export const STAGE_LABELS: Record<MissionStage, string> = {
  mission_created: 'Mission Created',
  planning: 'Planning',
  reasoning: 'Reasoning',
  dependency_resolution: 'Dependency Resolution',
  agent_assignment: 'Agent Assignment',
  execution: 'Execution',
  validation: 'Validation',
  human_approval: 'Human Approval',
  deployment: 'Deployment',
  archive: 'Archive',
}

export interface DescribedEvent {
  text: string
  tone: 'ok' | 'error' | 'info'
}

export function describeDomainEvent(evt: DomainEvent): DescribedEvent | null {
  switch (evt.type) {
    case 'MISSION_CREATED': return { text: `Mission created: "${evt.mission?.title}"`, tone: 'info' }
    case 'MISSION_ASSIGNED': return { text: `"${evt.mission?.title}" assigned to ${evt.mission?.assigned_agent ?? 'nobody'}`, tone: 'info' }
    case 'MISSION_STARTED': return { text: `Executing "${evt.mission?.title}" via ${evt.mission?.assigned_agent}…`, tone: 'info' }
    case 'MISSION_COMPLETED': return { text: `"${evt.mission?.title}" completed by ${evt.mission?.assigned_agent}`, tone: 'ok' }
    case 'MISSION_CANCELLED': return { text: `"${evt.mission?.title}" cancelled`, tone: 'error' }
    case 'MISSION_DELETED': return { text: 'Mission deleted', tone: 'info' }
    case 'MISSION_UPDATED': {
      if (!evt.mission) return null
      if (evt.mission.result && evt.mission.result.success === false) {
        return { text: `"${evt.mission.title}" failed: ${evt.mission.result.text}`, tone: 'error' }
      }
      return { text: `"${evt.mission.title}" → ${STAGE_LABELS[evt.mission.stage]}`, tone: 'info' }
    }
    case 'AGENT_ONLINE': return { text: `${evt.agent_key} came online`, tone: 'ok' }
    case 'AGENT_OFFLINE': return { text: `${evt.agent_key} failed to initialise`, tone: 'error' }
    case 'AGENT_TASK_STARTED': return { text: `${evt.agent_key} started ${evt.task_type}`, tone: 'info' }
    case 'AGENT_TASK_FINISHED': return { text: `${evt.agent_key} finished ${evt.task_type} (${evt.success ? 'ok' : 'failed'})`, tone: evt.success ? 'ok' : 'error' }
    default: return null
  }
}
