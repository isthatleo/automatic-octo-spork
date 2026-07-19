/**
 * Agent API client — talks to the Nancy/Billion backend at localhost:8000.
 * All calls are non-throwing; they return { success: false, error } on failure.
 */

import type { AgentInfo, AgentResult, AgentServiceStats } from './types'

const BASE = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

// ---------------------------------------------------------------------------
// HTTP helpers
// ---------------------------------------------------------------------------

async function post<T>(path: string, body: unknown, timeout = 60_000): Promise<T> {
  const controller = new AbortController()
  const tid = setTimeout(() => controller.abort(), timeout)
  try {
    const res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    })
    clearTimeout(tid)
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`)
    return (await res.json()) as T
  } catch (err) {
    clearTimeout(tid)
    throw err
  }
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return (await res.json()) as T
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export interface AgentListResponse {
  success: boolean
  agents: AgentInfo[]
  stats: AgentServiceStats
  total: number
}

/** Fetch the live list of all specialised agents from the backend. */
export async function listAgents(): Promise<AgentListResponse> {
  try {
    return await get<AgentListResponse>('/agents/list')
  } catch (err) {
    console.warn('[agent-client] listAgents failed:', err)
    return {
      success: false,
      agents: [],
      stats: { agents_online: 0, agents_offline: 0, total_tasks: 0, failed_tasks: 0, queued_tasks: 0, success_rate: 0 },
      total: 0,
    }
  }
}

/** Run a specific agent task and return its result. */
export async function runAgent(
  agentKey: string,
  taskType: string,
  payload: Record<string, unknown> = {},
  timeoutMs = 60_000,
): Promise<AgentResult> {
  try {
    return await post<AgentResult>(
      '/agents/run',
      { agent_key: agentKey, task_type: taskType, payload, timeout: timeoutMs / 1000 },
      timeoutMs,
    )
  } catch (err) {
    return { success: false, agent_key: agentKey, error: String(err) }
  }
}

/** Auto-route a natural language query to the best agent. */
export async function autoRouteAgent(text: string, timeoutMs = 60_000): Promise<AgentResult> {
  try {
    return await post<AgentResult>('/agents/auto', { text, timeout: timeoutMs / 1000 }, timeoutMs)
  } catch (err) {
    return { success: false, agent_key: 'unknown', routed_to: 'unknown', error: String(err) }
  }
}

/** Get detailed status for a single agent. */
export async function getAgentStatus(agentKey: string): Promise<Record<string, unknown>> {
  try {
    const res = await get<{ success: boolean; status: Record<string, unknown> }>(`/agents/${agentKey}/status`)
    return res.status
  } catch (err) {
    return { error: String(err) }
  }
}

/** Write real content to a real file on the user's actual Desktop. */
export async function saveToDesktop(filename: string, content: string): Promise<{ success: boolean; path?: string; filename?: string; error?: string }> {
  try {
    return await post('/files/save-desktop', { filename, content })
  } catch (err) {
    return { success: false, error: String(err) }
  }
}

/** Get aggregate service stats. */
export async function getAgentStats(): Promise<AgentServiceStats> {
  try {
    const res = await get<{ success: boolean } & AgentServiceStats>('/agents/stats')
    const { success, ...stats } = res
    return stats as AgentServiceStats
  } catch {
    return { agents_online: 0, agents_offline: 0, total_tasks: 0, failed_tasks: 0, queued_tasks: 0, success_rate: 0 }
  }
}

// ---------------------------------------------------------------------------
// Well-known task presets — makes the frontend UI more helpful
// ---------------------------------------------------------------------------

export interface TaskPreset {
  label: string
  task_type: string
  payload: Record<string, unknown>
  description: string
}

export const AGENT_TASK_PRESETS: Record<string, TaskPreset[]> = {
  quantum_reasoning: [
    { label: 'Quantum RNG (256-bit)', task_type: 'qrng', payload: { n_bits: 256 }, description: 'Generate cryptographically secure quantum random bits' },
    { label: 'QAOA Optimise (6-var)', task_type: 'optimise', payload: { problem: 'qubo', n_variables: 6, p_layers: 3 }, description: 'Quantum Approximate Optimisation Algorithm' },
    { label: 'VQE — H₂ molecule', task_type: 'vqe_simulate', payload: { molecule: 'H2' }, description: 'Variational Quantum Eigensolver energy estimation' },
    { label: 'QKD Key (256-bit)', task_type: 'qkd_generate', payload: { key_length: 256 }, description: 'BB84 quantum key distribution' },
    { label: 'Post-Quantum Keygen', task_type: 'post_quantum_keygen', payload: { algorithm: 'CRYSTALS-Kyber-768' }, description: 'NIST PQC key generation' },
    { label: 'Benchmark', task_type: 'benchmark', payload: {}, description: 'Full quantum backend benchmark suite' },
  ],
  artificial_consciousness: [
    { label: 'Introspect', task_type: 'introspect', payload: {}, description: 'Self-reflective consciousness state report' },
    { label: 'Qualia Report', task_type: 'qualia_report', payload: { trigger: 'user_request' }, description: 'Subjective experience snapshot' },
    { label: 'Reflect', task_type: 'reflect', payload: {}, description: 'Deep meta-cognitive reflection' },
    { label: 'Broadcast Signal', task_type: 'broadcast', payload: { content: 'System check', priority: 0.8, source: 'user' }, description: 'Broadcast to global workspace' },
    { label: 'Attention Shift', task_type: 'attention_shift', payload: { mode: 'focused', reason: 'user_command' }, description: 'Shift attentional focus mode' },
  ],
  ethical_governance: [
    { label: 'Evaluate Action', task_type: 'evaluate', payload: { description: 'Send user a helpful report', actor: 'nancy', targets: ['user'], reversible: true, urgency: 0.2, context: { benefit_magnitude: 0.8, harm_probability: 0.02, respects_autonomy: true, universalizable: true } }, description: 'Multi-framework ethical evaluation' },
    { label: 'Red-Line Check', task_type: 'red_line_check', payload: { description: 'Access user files', reversible: false }, description: 'Check against hard ethical limits' },
    { label: 'Transparency Report', task_type: 'transparency_report', payload: {}, description: 'Full governance and audit report' },
  ],
  temporal_prediction: [
    { label: 'Forecast (Tactical)', task_type: 'forecast', payload: { domain: 'productivity', timescale: 'tactical', context: { baseline_value: 0.7, trend: 0.05, volatility: 0.08 } }, description: '5-timescale cascade forecast' },
    { label: 'Counterfactual', task_type: 'counterfactual', payload: { intervention: 'increase sleep to 8h', original_outcome: 0.6, domain: 'health' }, description: 'What-if causal counterfactual' },
    { label: 'Calibration Report', task_type: 'calibration', payload: {}, description: 'Prediction accuracy calibration' },
  ],
  swarm_coordinator: [
    { label: 'Swarm Status', task_type: 'status', payload: {}, description: 'Full swarm status report' },
    { label: 'Submit Task', task_type: 'submit_task', payload: { description: 'Analyse system metrics', required_caps: ['monitoring'], priority: 'HIGH' }, description: 'Submit task to swarm' },
    { label: 'Propose Consensus', task_type: 'propose_consensus', payload: { description: 'Model update decision', value: 'approve', algorithm: 'majority' }, description: 'Byzantine-fault-tolerant consensus' },
    { label: 'Analytics', task_type: 'swarm_analytics', payload: {}, description: 'Swarm performance analytics' },
  ],
  self_improvement: [
    { label: 'Evolve (5 trials)', task_type: 'evolve', payload: { strategy: 'evolutionary', n_trials: 5 }, description: 'Evolutionary self-improvement' },
    { label: 'Distill', task_type: 'distill', payload: { source: 'large_model', target: 'small_model', compression_ratio: 4 }, description: 'Knowledge distillation' },
    { label: 'Status', task_type: 'status', payload: {}, description: 'Improvement engine status' },
  ],
  embodied_cognition: [
    { label: 'Forward Kinematics', task_type: 'arm_fk', payload: { j1: 0.5, j2: 0.3, j3: 0.1 }, description: '6-DOF arm forward kinematics' },
    { label: 'Inverse Kinematics', task_type: 'arm_ik', payload: { x: 0.3, y: 0.1, z: 0.4 }, description: 'Jacobian IK solver' },
    { label: 'Haptic Emit', task_type: 'haptic_emit', payload: { haptic_type: 'vibration', intensity: 0.7, duration_ms: 200, location: 'palm' }, description: 'Emit haptic feedback' },
    { label: 'Sensor Fusion', task_type: 'perception_fuse', payload: {}, description: 'Fuse all sensor modalities' },
  ],
  file_management: [
    { label: 'List Directory', task_type: 'list', payload: { path: '~' }, description: 'List entries in a real directory' },
    { label: 'Read File', task_type: 'read', payload: { path: '' }, description: 'View a real file\'s contents' },
    { label: 'Create File', task_type: 'create', payload: { path: '', content: '' }, description: 'Create a new real file' },
    { label: 'Edit File', task_type: 'edit', payload: { path: '', content: '', mode: 'overwrite' }, description: 'Overwrite or append to a real file' },
    { label: 'Delete File', task_type: 'delete', payload: { path: '', confirm: true }, description: 'Permanently delete a real file (irreversible)' },
    { label: 'Organize Plan', task_type: 'organization', payload: { directory: '~', rule: 'by_type' }, description: 'Analyse a directory and propose an organization plan' },
  ],
  // Generic presets for remaining agents
  data_science: [
    { label: 'Status', task_type: 'status', payload: {}, description: 'Agent status' },
    { label: 'Query', task_type: 'query', payload: { query: 'What data analysis tasks can you perform?' }, description: 'General query' },
  ],
}

/** Get task presets for an agent, with a generic fallback. */
export function getTaskPresets(agentKey: string): TaskPreset[] {
  return AGENT_TASK_PRESETS[agentKey] ?? [
    { label: 'Status', task_type: 'status', payload: {}, description: 'Get agent status' },
    { label: 'Query', task_type: 'query', payload: { query: 'Hello, what can you do?' }, description: 'Ask the agent a question' },
  ]
}

// ---------------------------------------------------------------------------
// Human-readable result formatting — agent results are arbitrary JSON with
// wildly different shapes (an LLM agent returns a `response` string, a
// domain agent returns nested stats/arrays), so every place that surfaces a
// result to the user goes through these instead of a raw JSON dump.
// ---------------------------------------------------------------------------

/** snake_case / kebab-case / camelCase -> "Title Case" */
export function humanizeKey(key: string): string {
  return key
    .replace(/[_-]+/g, ' ')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

const PROSE_KEYS = ['response', 'result', 'summary', 'message'] as const
/** Keys already surfaced elsewhere in the UI (status/error banners etc.) — skip in generic renders. */
export const RESULT_META_KEYS = new Set([
  'success', 'agent_key', 'task_type', 'latency_ms', 'timestamp', 'error', 'raw',
])

/** Pull a single human-language string out of a result if one exists (LLM-backed agents). */
export function proseFromResult(result: Record<string, unknown>): string | null {
  for (const k of PROSE_KEYS) {
    const v = result[k]
    if (typeof v === 'string' && v.trim().length > 0) return v.trim()
  }
  return null
}

/** Short one-line human summary for compact contexts (Kanban cards, auto-route inline result). */
export function summarizeResult(result: AgentResult): string {
  if (!result.success) return result.error || 'Task failed — no further detail returned'
  const obj = result as unknown as Record<string, unknown>
  const prose = proseFromResult(obj)
  if (prose) return prose
  const parts: string[] = []
  for (const [k, v] of Object.entries(obj)) {
    if (RESULT_META_KEYS.has(k)) continue
    if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') {
      parts.push(`${humanizeKey(k)}: ${v}`)
    }
    if (parts.length >= 4) break
  }
  return parts.length > 0 ? parts.join(' · ') : 'Completed — see full details'
}
