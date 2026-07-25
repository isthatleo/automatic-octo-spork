/**
 * Docs/meta client for Nancy's frontend help surfaces.
 * Provides structured metadata for slash commands, skills,
 * memory search, agent roster, and tools so UI shells can render
 * honest docs instead of hardcoded strings.
 */

const DEFAULT_BASE = typeof window !== 'undefined' ? '' : 'http://localhost:8000'

export interface DocsCommand {
  command: string
  category: 'navigation' | 'agent' | 'memory' | 'system' | 'help'
  description: string
  example: string
}

export interface DocsSkill {
  id?: string
  name: string
  description: string
  category: string
  agent_count?: number
}

export interface DocsAgent {
  key: string
  name?: string
  domain?: string
  status?: string
  mode?: string
}

export interface DocsMemoryHint {
  label: string
  query: string
  note: string
}

const SLASH_COMMANDS: DocsCommand[] = [
  { command: '/skills', category: 'agent', description: 'Open Skills and view attached agents.', example: '/skills' },
  { command: '/memory', category: 'memory', description: 'Open memory, session history, and recall tools.', example: '/memory' },
  { command: '/agents', category: 'agent', description: 'Open agent command and specialist roster.', example: '/agents' },
  { command: '/terminal', category: 'system', description: 'Open Command Layer terminal and runtime control.', example: '/terminal' },
  { command: '/status', category: 'help', description: 'Show current system status summary.', example: '/status' },
  { command: '/help', category: 'help', description: 'List available slash commands.', example: '/help' },
  { command: '/new', category: 'system', description: 'Start a fresh session/chat.', example: '/new' },
]

export function listSlashCommands() {
  return SLASH_COMMANDS
}

export interface DocsFetchResult<T> {
  success: boolean
  data?: T
  error?: string
}

async function _json(path: string, base = DEFAULT_BASE): Promise<any> {
  const url = `${base}${path}`
  const res = await fetch(url, { method: 'GET', headers: { Accept: 'application/json' } })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`HTTP ${res.status}: ${text.slice(0, 180)}`)
  }
  return res.json()
}

async function _postJson(path: string, payload: Record<string, any>, base = DEFAULT_BASE): Promise<any> {
  const url = `${base}${path}`
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(payload || {}),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`HTTP ${res.status}: ${text.slice(0, 180)}`)
  }
  return res.json()
}

export async function fetchSkillList(): Promise<DocsFetchResult<DocsSkill[]>> {
  try {
    const json = await _json('/skills')
    const skills = Array.isArray(json?.skills) ? json.skills : []
    const out: DocsSkill[] = skills.map((s: any) => ({
      id: s.id,
      name: s.name,
      description: s.description,
      category: s.category,
      agent_count: Array.isArray(s.agent_keys) ? s.agent_keys.length : undefined,
    }))
    return { success: true, data: out }
  } catch (e: any) {
    return { success: false, error: e?.message || 'skills fetch failed' }
  }
}

export async function fetchMemorySuggestions(): Promise<DocsMemoryHint[]> {
  return [
    { label: 'Recent topics', query: 'latest conversation topics', note: 'Queries stored memory entries by recency and relevance.' },
    { label: 'Facts about user', query: 'user preferences facts', note: 'Retrieves asserted long-term facts extracted from chat.' },
    { label: 'Open decisions', query: 'pending decisions outages', note: 'Memory search has no dedicated status endpoint; use /memory/search.' },
  ]
}

export async function fetchAgentRoster(): Promise<DocsFetchResult<DocsAgent[]>> {
  try {
    const json = await _json('/agents/list')
    const agents = Array.isArray(json?.agents) ? json.agents : []
    const out: DocsAgent[] = agents.map((a: any) => ({
      key: a.key,
      name: a.name,
      domain: a.domain,
      status: a.status,
      mode: a.mode,
    }))
    return { success: true, data: out }
  } catch (e: any) {
    return { success: false, error: e?.message || 'agent roster fetch failed' }
  }
}

export async function sendChatSlash(message: string, history: unknown[] = []): Promise<DocsFetchResult<{ reply: string }>> {
  try {
    const json = await _postJson('/chat', { text: message, history, task_hint: null })
    if (!json?.reply) {
      return { success: false, error: 'backend returned no reply field' }
    }
    return { success: true, data: { reply: String(json.reply) } }
  } catch (e: any) {
    return { success: false, error: e?.message || 'slash chat failed' }
  }
}

export async function fetchSystemStatus(): Promise<DocsFetchResult<Record<string, any>>> {
  try {
    const json = await _json('/status')
    return { success: true, data: json || {} }
  } catch (e: any) {
    return { success: false, error: e?.message || 'status fetch failed' }
  }
}
