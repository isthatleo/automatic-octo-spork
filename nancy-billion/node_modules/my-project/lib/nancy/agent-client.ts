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
  science_research: [
    { label: 'Physical Constant', task_type: 'constant-lookup', payload: { name: 'speed_of_light' }, description: 'Look up a real CODATA physical constant' },
    { label: 'Unit Conversion', task_type: 'unit-conversion', payload: { value: 100, from_unit: 'km', to_unit: 'mile' }, description: 'Exact SI/derived-unit conversion' },
    { label: 'Sample Size', task_type: 'sample-size', payload: { effect_size: 0.5, alpha: 0.05, power: 0.8 }, description: 'Statistical power analysis for experiment design' },
    { label: 'Literature Synthesis', task_type: 'literature-synthesis', payload: { topic: 'CRISPR gene editing' }, description: 'Real Wikipedia-sourced science topic synthesis' },
  ],
  general_research: [
    { label: 'Research Brief', task_type: 'brief', payload: { topic: 'renewable energy storage' }, description: 'Source-grounded overview, key terms, related topics' },
    { label: 'Compare Topics', task_type: 'compare', payload: { topic_a: 'solar power', topic_b: 'wind power' }, description: 'Side-by-side comparison with similarity score' },
    { label: 'Related Topics', task_type: 'related-topics', payload: { topic: 'artificial intelligence' }, description: 'Discover related topics from a real source' },
  ],
  nuclear_research: [
    { label: 'Decay Calculation', task_type: 'decay-calculation', payload: { isotope: 'co-60', elapsed_seconds: 157788000 }, description: 'Real radioactive decay law for a common isotope' },
    { label: 'Binding Energy', task_type: 'binding-energy', payload: { mass_number: 56, atomic_number: 26 }, description: 'Semi-empirical mass formula (iron-56)' },
    { label: 'Dose Estimate', task_type: 'dose-estimate', payload: { isotope: 'cs-137', activity_mbq: 100, distance_m: 1 }, description: 'Point-source gamma dose-rate approximation' },
    { label: 'Fuel Cycle Overview', task_type: 'fuel-cycle-overview', payload: {}, description: 'Civilian fuel cycle and IAEA non-proliferation safeguards' },
    { label: 'Fusion Overview', task_type: 'fusion-overview', payload: {}, description: 'Lawson criterion and leading fusion energy approaches' },
  ],
  agent_creator: [
    { label: 'List Registry', task_type: 'list_registry', payload: {}, description: 'List curated and dynamically-created agents' },
    { label: 'Scaffold Agent', task_type: 'scaffold', payload: { key: 'weather_forecaster', class_name: 'WeatherForecasterAgent', domain: 'weather-forecasting', description: 'Forecasts weather conditions' }, description: 'Generate a valid new agent module (does not write to disk)' },
    { label: 'Deploy Agent', task_type: 'deploy', payload: { key: 'weather_forecaster', class_name: 'WeatherForecasterAgent', domain: 'weather-forecasting', description: 'Forecasts weather conditions' }, description: 'Validate and write a new agent file to agents/specialized/dynamic/' },
  ],
  weather_climate: [
    { label: 'Current Weather', task_type: 'current-weather', payload: { location: 'London' }, description: 'Real current conditions for a location (Open-Meteo)' },
    { label: '5-Day Forecast', task_type: 'forecast', payload: { location: 'Tokyo', days: 5 }, description: 'Real multi-day forecast' },
    { label: 'Climate Trend', task_type: 'climate-stats', payload: { location: 'Berlin', start_date: '2015-01-01', end_date: '2024-12-31' }, description: 'Real historical daily-temperature trend analysis' },
    { label: 'Heat Index', task_type: 'heat-index', payload: { temperature_c: 32, relative_humidity_pct: 70 }, description: 'NWS heat index formula' },
  ],
  economics: [
    { label: 'GDP Lookup', task_type: 'indicator-lookup', payload: { country: 'US', indicator: 'gdp_per_capita_usd' }, description: 'Real World Bank indicator series' },
    { label: 'Growth Analysis', task_type: 'growth-analysis', payload: { country: 'IN', indicator: 'gdp_per_capita_usd' }, description: 'Real CAGR, doubling time, and trend' },
    { label: 'Inflation Adjust', task_type: 'inflation-adjust', payload: { country: 'US', amount: 100, from_year: '2000', to_year: '2023' }, description: 'Real CPI-based amount adjustment' },
    { label: 'List Indicators', task_type: 'list-indicators', payload: {}, description: 'See all supported macro indicators' },
  ],
  materials_science: [
    { label: 'Material Lookup', task_type: 'material-lookup', payload: { material: 'titanium_ti6al4v' }, description: 'Real handbook material properties' },
    { label: 'Stress-Strain', task_type: 'stress-strain', payload: { material: 'aluminum_6061', applied_stress_mpa: 150, original_length_m: 1 }, description: "Hooke's law elongation + factor of safety" },
    { label: 'Thermal Expansion', task_type: 'thermal-expansion', payload: { material: 'steel_1020', length_m: 10, delta_temperature_c: 50 }, description: 'Real linear thermal expansion' },
    { label: 'Material Selection', task_type: 'material-selection', payload: { candidates: ['aluminum_6061', 'titanium_ti6al4v', 'stainless_304'] }, description: 'Weighted multi-criteria ranking' },
  ],
  personal_finance: [
    { label: 'Savings Projection', task_type: 'savings-projection', payload: { current_savings: 5000, monthly_contribution: 300, annual_rate_pct: 6, years: 10 }, description: 'Compound-interest future value' },
    { label: 'Retirement Projection', task_type: 'retirement-projection', payload: { current_age: 30, retirement_age: 65, current_savings: 20000, monthly_contribution: 500 }, description: 'Nominal + inflation-adjusted retirement balance' },
    { label: 'Debt Payoff', task_type: 'debt-payoff', payload: { debts: [{ name: 'Card A', balance: 5000, apr: 22, min_payment: 100 }, { name: 'Card B', balance: 2000, apr: 15, min_payment: 50 }], extra_monthly_payment: 200 }, description: 'Real avalanche vs. snowball simulation' },
    { label: 'Net Worth', task_type: 'net-worth', payload: { assets: { savings: 10000, home: 250000 }, liabilities: { mortgage: 180000 } }, description: 'Assets minus liabilities' },
  ],
  energy_grid: [
    { label: 'Solar Output', task_type: 'solar-output', payload: { location: 'Phoenix', panel_area_m2: 20 }, description: 'Real irradiance-grounded PV output estimate' },
    { label: 'Wind Output', task_type: 'wind-output', payload: { location: 'Amsterdam', rotor_diameter_m: 100 }, description: 'Real wind-speed-grounded turbine output estimate' },
    { label: 'LCOE', task_type: 'lcoe', payload: { capex_usd: 1000000, opex_annual_usd: 20000, annual_output_kwh: 2000000 }, description: 'Levelized Cost of Energy' },
    { label: 'Carbon Intensity', task_type: 'carbon-intensity', payload: { generation_mix_pct: { coal: 20, gas: 30, wind: 25, solar_pv: 15, nuclear: 10 } }, description: 'Weighted grid carbon intensity' },
  ],
  mathematics: [
    { label: 'Factorize', task_type: 'number-theory', payload: { operation: 'factorize', n: 360 }, description: 'Real prime factorization' },
    { label: 'Combinations', task_type: 'combinatorics', payload: { operation: 'combinations', n: 10, r: 3 }, description: 'nCr calculation' },
    { label: 'Polynomial Roots', task_type: 'polynomial-roots', payload: { coefficients: [1, -3, 2] }, description: 'Exact roots via numpy' },
    { label: 'Linear Algebra', task_type: 'linear-algebra', payload: { operation: 'determinant', matrix: [[1, 2], [3, 4]] }, description: 'Determinant/inverse/eigenvalues/solve' },
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
