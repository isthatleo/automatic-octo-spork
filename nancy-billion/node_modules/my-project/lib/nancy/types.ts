export type LogLevel = 'info' | 'ok' | 'warn' | 'user' | 'nancy'

export interface LogEntry {
  id: string
  ts: number
  level: LogLevel
  text: string
}

export type PanelKey =
  | 'overview' | 'map' | 'core' | 'agents' | 'system' | 'projects' | 'market' | 'news' | 'media' | 'kanban'
  | 'sessions' | 'channels' | 'instances' | 'cron' | 'skills' | 'models' | 'keys' | 'config' | 'usage'
  | 'pairing' | 'profiles' | 'plugins' | 'mcp' | 'webhooks' | 'docs'

export interface AgentInfo {
  key: string
  id?: string
  name: string
  domain: string
  role?: string
  description?: string
  load: number
  status: 'online' | 'idle' | 'offline' | 'training' | 'error'
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
  historicalEvents?: HistoricalEvent[]
}

export interface HistoricalEvent {
  id: string
  title: string
  description: string
  date: string
  year: number
  significance: 'high' | 'medium' | 'low'
  category: 'conflict' | 'discovery' | 'culture' | 'politics' | 'science' | 'technology'
  imageUrl?: string
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
