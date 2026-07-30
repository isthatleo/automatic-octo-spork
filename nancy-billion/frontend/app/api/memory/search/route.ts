import { NextResponse } from 'next/server'
import { BACKEND_URL as BACKEND, backendHeaders } from '@/lib/nancy/backend-server'


// Real semantic search over the whole memory graph (memory/extensions.py's
// search_memories, itself a thin wrapper over MemoryGraph's real embedding
// query). Previously this proxy called a POST route the backend never had
// and never forwarded the query string on GET either -- fixed to match the
// real backend contract: GET /memory/search?q=&top_k=.
export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const q = searchParams.get('q') ?? ''
  const topK = searchParams.get('top_k') ?? '10'
  try {
    const url = new URL(`${BACKEND}/memory/search`)
    url.searchParams.set('q', q)
    url.searchParams.set('top_k', topK)
    const res = await fetch(url.toString(), { headers: backendHeaders(), cache: 'no-store' })
    if (!res.ok) return NextResponse.json({ success: false, results: [] }, { status: res.status })
    return NextResponse.json(await res.json())
  } catch {
    return NextResponse.json({ success: false, results: [] }, { status: 502 })
  }
}
