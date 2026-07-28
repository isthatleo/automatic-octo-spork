export type LogLevel = 'info' | 'ok' | 'warn' | 'user' | 'nancy'

export interface LogEntry {
  id: string
  ts: number
  level: LogLevel
  text: string
  /** A real image pushed alongside this entry (a Telegram map snapshot, or
   *  a screenshot/canvas image a tool call produced) -- base64 PNG data,
   *  no data: URI prefix. */
  imageBase64?: string
}

export type PanelKey =
  | 'overview' | 'map' | 'core' | 'agents' | 'system' | 'market' | 'news' | 'kanban'
  | 'sessions' | 'channels' | 'instances' | 'cron' | 'skills' | 'models' | 'keys' | 'config' | 'usage'
  | 'pairing' | 'profiles' | 'plugins' | 'webhooks' | 'docs' | 'canvas' | 'memory-insights'
  | 'achievements' | 'theming'

export interface AgentInfo {
  key: string
  id?: string
  name: string
  domain: string
  role?: string
  description?: string
  load: number
  status: 'online' | 'idle' | 'offline' | 'training' | 'error' | 'executing'
  /** Real task_type currently in flight (see base_specialized_agent.py's
   * run_task) -- only non-null while status === 'executing'. */
  current_task_type?: string | null
  confidence: number
  specializations: string[]
  total_tasks: number
  error?: string
  /** Honesty flags from the backend (see base_specialized_agent.get_info):
   *  'production' unless the agent runs on simulated data or unattached hardware. */
  mode?: string
  hardware_connected?: boolean | null
}

export interface AgentTask {
  agent_key: string
  task_type: string
  payload: Record<string, unknown>
}

export interface AgentResult {
  success: boolean
  agent_key: string
  latency_ms?: number
  routed_to?: string
  error?: string
  [key: string]: unknown
}

export interface AgentServiceStats {
  agents_online: number
  agents_offline: number
  total_tasks: number
  failed_tasks: number
  queued_tasks: number
  success_rate: number
}

export interface Place {
  name: string
  lat: number
  lon: number
  country?: string
  timezone?: string
}

export interface ProjectInfo {
  name: string
  path: string
  type: string
}

export interface MarketData {
  symbol: string
  name: string
  price: number
  change: number
  changePercent: number
}

export interface NewsItem {
  id: string
  title: string
  source: string
  link: string
  summary?: string
  image?: string
  published?: string
  /** Embeddable video URL, present only for video-feed items. */
  video?: string
}

export type KnowledgeCategory =
  | 'general'
  | 'finance'
  | 'medicine'
  | 'science'
  | 'physics'
  | 'astrophysics'
  | 'documentaries'
  | 'history'
  | 'literature'

export interface EconomicEvent {
  key_prefix: 'nfp' | 'cpi' | 'fomc'
  event_name: string
  raw_event_name: string
  /** "YYYY-MM-DD HH:MM:SS" as returned by the data provider (US Eastern release time). */
  date: string
  country: string
  previous: number | null
  estimate: number | null
  actual: number | null
  change: number | null
  change_percent: number | null
  unit: string
  impact: string
}

export interface MarketAnalysis {
  symbol: string
  summary: string
  recommendation: 'buy' | 'sell' | 'hold'
  confidence: number
  timestamp: number
}

/* ── Missions (AI Workflow Orchestrator) — mirrors backend/missions_store.py.
   Backend timestamps are Unix seconds (Python time.time()), NOT the
   milliseconds the rest of this frontend uses (Date.now()) -- callers must
   multiply by 1000 before handing one to timeAgo()/Date. ── */
export type MissionStage =
  | 'mission_created' | 'planning' | 'reasoning' | 'dependency_resolution' | 'agent_assignment'
  | 'execution' | 'validation' | 'human_approval' | 'deployment' | 'archive'

export interface MissionSubtask {
  id: string
  text: string
  done: boolean
}

export interface MissionResult {
  success: boolean
  text: string
  at: number
  savedFile?: string | null
}

export interface MissionHistoryEntry {
  stage: MissionStage
  at: number
}

export interface Mission {
  id: string
  title: string
  description: string
  stage: MissionStage
  assigned_agent: string | null
  // Explicit multi-agent execution -- when non-empty, the backend runs every
  // one of these agents in real parallel and synthesizes their outputs,
  // instead of the single assigned_agent path.
  assigned_agents: string[]
  owner: string
  priority: 'low' | 'medium' | 'high' | 'critical'
  risk: 'low' | 'medium' | 'high'
  estimated_cost: number | null
  due_date: string | null
  tags: string[]
  dependencies: string[]
  subtasks: MissionSubtask[]
  order: number
  created_at: number
  updated_at: number
  dispatched_at: number | null
  result: MissionResult | null
  cancelled: boolean
  history: MissionHistoryEntry[]
}

/** The real domain events published over the /ws socket (see
 * backend/event_bus.py + main_new.py's _broadcast_domain_event). */
export type DomainEventType =
  | 'MISSION_CREATED' | 'MISSION_UPDATED' | 'MISSION_ASSIGNED' | 'MISSION_STARTED'
  | 'MISSION_COMPLETED' | 'MISSION_CANCELLED' | 'MISSION_DELETED'
  | 'AGENT_ONLINE' | 'AGENT_OFFLINE' | 'AGENT_TASK_STARTED' | 'AGENT_TASK_FINISHED'
  | 'CANVAS_ITEM_ADDED' | 'CANVAS_ITEM_UPDATED' | 'CANVAS_ITEM_REMOVED'

export interface CanvasItem {
  id: string
  type: 'note' | 'link' | 'code' | 'image' | '3d_scene' | 'html_preview'
  title: string
  content: string
  language: string | null
  pinned: boolean
  created_at: number
}

// content for type === '3d_scene' is a JSON string matching this shape --
// see backend/main_new.py's create_3d_scene tool and canvas_store.py's
// VALID_TYPES comment: simplified illustrative primitives, not CAD-accurate.
export interface Scene3DObject {
  type: 'box' | 'sphere' | 'cylinder' | 'cone' | 'torus'
  position: [number, number, number]
  size?: number[]
  color?: string
  label?: string
}

export interface Scene3DData {
  description?: string
  objects: Scene3DObject[]
}

export interface DomainEvent {
  type: DomainEventType
  at: number
  mission?: Mission
  mission_id?: string
  agent_key?: string
  task_type?: string
  success?: boolean
  error?: string
  item?: CanvasItem
  item_id?: string
  [key: string]: unknown
}
