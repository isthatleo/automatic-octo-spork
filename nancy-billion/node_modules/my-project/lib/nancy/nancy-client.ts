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

export interface ArticleMeta {
  url?: string
  image?: string | null
  title?: string | null
  description?: string | null
  site?: string | null
}

/** Resolves a story link to its publisher page and scrapes OpenGraph/meta
 * tags (hero image, description, site name) via /api/article — used by
 * StoryDialog's immersive readout. Always resolves (never rejects); on any
 * failure the caller just falls back to the feed's own summary/thumbnail. */
export async function enrichArticle(link: string): Promise<ArticleMeta> {
  if (!link) return {}
  try {
    const res = await fetch(`/api/article?url=${encodeURIComponent(link)}`)
    if (!res.ok) return {}
    return (await res.json()) as ArticleMeta
  } catch {
    return {}
  }
}
