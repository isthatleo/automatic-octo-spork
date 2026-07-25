'use client'

const DEFAULT_BASE = typeof window !== 'undefined' ? '' : 'http://localhost:8000'

export interface MemorySearchHit {
  id?: string
  title?: string
  summary?: string
  score?: number
  [key: string]: unknown
}

async function _json(path: string, base = DEFAULT_BASE): Promise<any> {
  const res = await fetch(`${base}${path}`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

async function _postJson(
  path: string,
  payload: Record<string, any>,
  base = DEFAULT_BASE,
): Promise<any> {
  const res = await fetch(`${base}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(payload || {}),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function memorySearch(
  text: string,
  topK = 10,
): Promise<MemorySearchHit[]> {
  try {
    const json = await _postJson('/memory/search', { text, top_k: topK })
    if (!Array.isArray(json?.results)) return []
    return json.results.map((item: any) => ({
      id: item.id,
      title: item.title,
      summary: item.summary,
      score: item.score,
      ...item,
    }))
  } catch {
    return []
  }
}

export async function memoryStatus() {
  try {
    return await _json('/memory/search')
  } catch (e) {
    return { available: false, error: (e as Error).message }
  }
}
