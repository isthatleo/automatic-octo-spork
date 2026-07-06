import type { KnowledgeCategory, MarketAnalysis, PanelKey } from './types'
import { localBrain } from './local-brain'

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
  category: KnowledgeCategory | null
  topic: string | null
  symbol: string | null
  panel: PanelKey | null
  target: string | null
  media: 'articles' | 'videos' | null
  autoOpenTop: boolean
}

export interface ChatTurn {
  role: 'user' | 'assistant'
  content: string
}

/** Ask Nancy's AI brain what to do with a spoken/typed line. */
export async function askNancy(
  text: string,
  history: ChatTurn[],
): Promise<NancyDecision> {
  try {
    const res = await fetch('http://localhost:8000/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, history }),
    })
    if (!res.ok) throw new Error(`nancy route ${res.status}`)
    return (await res.json()) as NancyDecision
  } catch {
    // Network/route failure — keep Nancy responsive with the local core.
    return localBrain(text)
  }
}

/** Pull a structured market analysis for a TradingView symbol. */
export async function analyzeSymbol(symbol: string): Promise<MarketAnalysis> {
  const res = await fetch('http://localhost:8000/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol }),
  })
  if (!res.ok) throw new Error('analysis failed')
  return (await res.json()) as MarketAnalysis
}

export interface ArticleMeta {
  url?: string
  image?: string | null
  title?: string | null
  description?: string | null
  site?: string | null
}

/** Resolve a hero image + fuller text for an article URL (best effort). */
export async function enrichArticle(url: string): Promise<ArticleMeta> {
  try {
    const res = await fetch(`http://localhost:8000/article?url=${encodeURIComponent(url)}`)
    return (await res.json()) as ArticleMeta
  } catch {
    return {}
  }
}
