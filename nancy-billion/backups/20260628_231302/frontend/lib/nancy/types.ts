export type LogLevel = 'info' | 'ok' | 'warn' | 'user' | 'nancy'

export interface LogEntry {
  id: string
  ts: number
  level: LogLevel
  text: string
}

export type PanelKey = 'overview' | 'map' | 'core' | 'agents' | 'system' | 'projects' | 'market' | 'news' | 'media'

export interface AgentInfo {
  id: string
  name: string
  role: string
  load: number
  status: 'online' | 'idle' | 'training'
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
  date: string // ISO date string
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

export type KnowledgeCategory = 'finance' | 'medicine' | 'science' | 'physics' | 'astrophysics' | 'history' | 'literature'

export interface MarketAnalysis {
  symbol: string
  summary: string
  recommendation: 'buy' | 'sell' | 'hold'
  confidence: number
  timestamp: number
}
