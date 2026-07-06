// Minimal shape used by Nancy's local brain and API route.
export interface NancyDecision {
  reply: string
  action:
    | 'none'
    | 'knowledge'
    | 'news'
    | 'market'
    | 'locate'
    | 'navigate'
    | 'launch'
    | 'close'
  category:
    | 'finance'
    | 'medicine'
    | 'science'
    | 'physics'
    | 'astrophysics'
    | 'documentaries'
    | 'history'
    | 'literature'
    | 'general'
    | null
  topic: string | null
  symbol: string | null
  panel: 'overview' | 'map' | 'core' | 'agents' | 'system' | null
  target: string | null
  media: 'articles' | 'videos' | null
  autoOpenTop: boolean
}
