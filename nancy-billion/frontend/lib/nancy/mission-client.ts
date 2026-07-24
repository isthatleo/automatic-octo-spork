/**
 * Mission API client — talks to the backend's real /missions REST routes
 * (via the app/api/missions/* Next.js proxy, same pattern as cron/skills/
 * webhooks) instead of localStorage. Every call is non-throwing; failures
 * come back as { success: false }.
 */
import type { Mission } from './types'

export interface MissionListResponse {
  success: boolean
  missions: Mission[]
}

export interface MissionResponse {
  success: boolean
  mission?: Mission
  detail?: string
}

export interface MissionCreateInput {
  title: string
  description?: string
  owner?: string
  priority?: Mission['priority']
  risk?: Mission['risk']
  estimated_cost?: number | null
  due_date?: string | null
  tags?: string[]
  dependencies?: string[]
  subtasks?: Mission['subtasks']
  assigned_agent?: string | null
}

export type MissionUpdateInput = Partial<MissionCreateInput> & { order?: number }

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: 'no-store' })
  return (await res.json()) as T
}

async function sendJson<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  return (await res.json()) as T
}

export async function listMissions(): Promise<MissionListResponse> {
  try {
    return await getJson<MissionListResponse>('/api/missions')
  } catch (err) {
    console.warn('[mission-client] listMissions failed:', err)
    return { success: false, missions: [] }
  }
}

export async function createMission(input: MissionCreateInput): Promise<MissionResponse> {
  try {
    return await sendJson<MissionResponse>('/api/missions', 'POST', input)
  } catch (err) {
    return { success: false, detail: String(err) }
  }
}

export async function updateMission(id: string, patch: MissionUpdateInput): Promise<MissionResponse> {
  try {
    return await sendJson<MissionResponse>(`/api/missions/${id}`, 'PATCH', patch)
  } catch (err) {
    return { success: false, detail: String(err) }
  }
}

export async function assignMission(id: string, agentKey: string | null): Promise<MissionResponse> {
  try {
    return await sendJson<MissionResponse>(`/api/missions/${id}/assign`, 'POST', { agent_key: agentKey })
  } catch (err) {
    return { success: false, detail: String(err) }
  }
}

export async function transitionMission(id: string, stage: Mission['stage']): Promise<MissionResponse> {
  try {
    return await sendJson<MissionResponse>(`/api/missions/${id}/transition`, 'POST', { stage })
  } catch (err) {
    return { success: false, detail: String(err) }
  }
}

export async function cancelMission(id: string): Promise<MissionResponse> {
  try {
    return await sendJson<MissionResponse>(`/api/missions/${id}/cancel`, 'POST')
  } catch (err) {
    return { success: false, detail: String(err) }
  }
}

export async function deleteMission(id: string): Promise<{ success: boolean; detail?: string }> {
  try {
    return await sendJson<{ success: boolean; detail?: string }>(`/api/missions/${id}`, 'DELETE')
  } catch (err) {
    return { success: false, detail: String(err) }
  }
}
