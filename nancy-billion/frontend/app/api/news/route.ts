import type { NextRequest } from 'next/server'
import type { NewsItem } from '@/lib/nancy/types'

// Cache upstream feeds briefly so repeated requests stay snappy and polite.
export const revalidate = 300

// --- Trusted source feeds -------------------------------------------------

// Reputable outlet RSS feeds (include thumbnails) used for general headlines.
const OUTLET_FEEDS: { source: string; url: string }[] = [
  { source: 'BBC News', url: 'https://feeds.bbci.co.uk/news/world/rss.xml' },
  { source: 'The Guardian', url: 'https://www.theguardian.com/world/rss' },
  { source: 'NPR', url: 'https://feeds.npr.org/1001/rss.xml' },
  {
    source: 'Al Jazeera',
    url: 'https://www.aljazeera.com/xml/rss/all.xml',
  },
]

// Trusted news YouTube channels (public Atom feeds, no key required).
const VIDEO_FEEDS: { source: string; channelId: string }[] = [
  { source: 'BBC News', channelId: 'UC16niRr50-MSBwiO3YDb3RA' },
  { source: 'Al Jazeera English', channelId: 'UCNye-wNBqNL5ZzHSJj3l8Bg' },
  { source: 'Bloomberg', channelId: 'UCIALMKvObZNtJ6AmdCLP7Lg' },
  { source: 'Sky News', channelId: 'UCoMdktPbSTixAyNGwb-UYkQ' },
  { source: 'DW News', channelId: 'UCknLrEdhRCp1aegoMqRaCZg' },
]

// Per-domain channel pools for the knowledge library. Unknown/old IDs simply
// return empty feeds and are skipped, so the experience degrades gracefully.
const CATEGORY_CHANNELS: Record<string, { source: string; channelId: string }[]> = {
  finance: [
    { source: 'Bloomberg', channelId: 'UCIALMKvObZNtJ6AmdCLP7Lg' },
    { source: 'CNBC', channelId: 'UCvJJ_dzjViJCoLf5uKUTwoA' },
    { source: 'Yahoo Finance', channelId: 'UCEAZeUIeJs0IjQiqTCdVSIg' },
  ],
  medicine: [
    { source: 'DW News', channelId: 'UCknLrEdhRCp1aegoMqRaCZg' },
    { source: 'TED-Ed', channelId: 'UCsooa4yRKGN_zEE8iknghZA' },
  ],
  science: [
    { source: 'Veritasium', channelId: 'UCHnyfMqiRRG1u-2MsSQLbXA' },
    { source: 'Kurzgesagt', channelId: 'UCsXVk37bltHxD1rDPwtNM8Q' },
    { source: 'SciShow', channelId: 'UCZYTClx2T1of7BRZ86-8fow' },
  ],
  physics: [
    { source: 'minutephysics', channelId: 'UCUHW94eEFW7hkUMVaZz4eDg' },
    { source: 'PBS Space Time', channelId: 'UC7_gcs09iThXybpVgjHZ_7g' },
    { source: 'Veritasium', channelId: 'UCHnyfMqiRRG1u-2MsSQLbXA' },
  ],
  astrophysics: [
    { source: 'PBS Space Time', channelId: 'UC7_gcs09iThXybpVgjHZ_7g' },
    { source: 'NASA', channelId: 'UCLA_DiR1FfKNvjuUpBHmylQ' },
    { source: 'Kurzgesagt', channelId: 'UCsXVk37bltHxD1rDPwtNM8Q' },
  ],
  documentaries: [
    { source: 'DW Documentary', channelId: 'UCW39zufHfsuGgpLviKh297Q' },
    { source: 'Free Documentary', channelId: 'UCYwVxWpjeKFWwu8TML-Te9A' },
  ],
  history: [
    { source: 'Kings and Generals', channelId: 'UCMmaBzfCCwZ2KqaBJ322FUQ' },
    { source: 'TED-Ed', channelId: 'UCsooa4yRKGN_zEE8iknghZA' },
  ],
  literature: [
    { source: 'TED-Ed', channelId: 'UCsooa4yRKGN_zEE8iknghZA' },
    { source: 'CrashCourse', channelId: 'UCX6b17PVsYBQ0ip5gyeme-Q' },
  ],
}

// Search query used when a knowledge domain is requested without a specific topic.
const CATEGORY_QUERIES: Record<string, string> = {
  finance: 'stock market markets economy finance earnings rates',
  medicine: 'medicine health medical research clinical',
  science: 'science research discovery breakthrough',
  physics: 'physics quantum particle experiment',
  astrophysics: 'astrophysics astronomy space cosmos telescope',
  documentaries: 'documentary feature investigation',
  history: 'history historical archaeology',
  literature: 'literature books authors novel writing',
}

// A topic typed/spoken for a domain gets scoped to that domain for relevance.
function categoryScopedQuery(category: string | null, topic: string | null): string | null {
  if (topic && category && category !== 'general') {
    return `${topic} ${CATEGORY_QUERIES[category]?.split(' ').slice(0, 2).join(' ') ?? ''}`.trim()
  }
  if (topic) return topic
  if (category && category !== 'general') return CATEGORY_QUERIES[category] ?? null
  return null
}

// --- Tiny XML helpers (no dependencies) -----------------------------------

function decode(s: string): string {
  return s
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'")
    .replace(/&#x27;/g, "'")
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/<[^>]+>/g, '') // strip any leftover tags
    .replace(/\s+/g, ' ')
    .trim()
}

function tag(block: string, name: string): string | null {
  const m = block.match(new RegExp(`<${name}[^>]*>([\\s\\S]*?)</${name}>`, 'i'))
  return m ? m[1] : null
}

function attr(block: string, tagName: string, attrName: string): string | null {
  const m = block.match(
    new RegExp(`<${tagName}[^>]*\\b${attrName}=["']([^"']+)["']`, 'i'),
  )
  return m ? m[1] : null
}

async function fetchFeed(url: string): Promise<string | null> {
  try {
    const res = await fetch(url, {
      headers: { 'User-Agent': 'NancyOS/1.0 (news aggregator)' },
      next: { revalidate },
    })
    if (!res.ok) return null
    return await res.text()
  } catch {
    return null
  }
}

// --- Parsers --------------------------------------------------------------

function parseRssItems(xml: string, source: string): NewsItem[] {
  const items: NewsItem[] = []
  const blocks = xml.match(/<item[\s\S]*?<\/item>/gi) || []
  for (const b of blocks) {
    const title = decode(tag(b, 'title') || '')
    const link = decode(tag(b, 'link') || '')
    if (!title || !link) continue
    const desc = decode(tag(b, 'description') || tag(b, 'summary') || '')
    const image =
      attr(b, 'media:thumbnail', 'url') ||
      attr(b, 'media:content', 'url') ||
      attr(b, 'enclosure', 'url') ||
      undefined
    const published = tag(b, 'pubDate') || tag(b, 'dc:date') || undefined
    items.push({
      id: link,
      title,
      source,
      link,
      summary: desc.slice(0, 220),
      image: image || undefined,
      published: published || undefined,
    })
  }
  return items
}

function parseYoutubeEntries(xml: string, source: string): NewsItem[] {
  const items: NewsItem[] = []
  const blocks = xml.match(/<entry[\s\S]*?<\/entry>/gi) || []
  for (const b of blocks) {
    const title = decode(tag(b, 'title') || '')
    const link =
      attr(b, 'link', 'href') ||
      `https://www.youtube.com/watch?v=${tag(b, 'yt:videoId') || ''}`
    const vid = tag(b, 'yt:videoId')
    if (!title || !vid) continue
    const image = attr(b, 'media:thumbnail', 'url') || undefined
    const desc = decode(tag(b, 'media:description') || '')
    const published = tag(b, 'published') || undefined
    items.push({
      id: vid,
      title,
      source,
      link,
      summary: desc.slice(0, 200),
      image,
      published: published || undefined,
      video: `https://www.youtube-nocookie.com/embed/${vid}`,
    })
  }
  return items
}

function googleNewsUrl(topic: string | null): string {
  const base = 'https://news.google.com/rss'
  const locale = 'hl=en-US&gl=US&ceid=US:en'
  if (topic) {
    return `${base}/search?q=${encodeURIComponent(topic)}&${locale}`
  }
  return `${base}?${locale}`
}

function parseGoogleNews(xml: string): NewsItem[] {
  const items: NewsItem[] = []
  const blocks = xml.match(/<item[\s\S]*?<\/item>/gi) || []
  for (const b of blocks) {
    const rawTitle = decode(tag(b, 'title') || '')
    const link = decode(tag(b, 'link') || '')
    if (!rawTitle || !link) continue
    // Google titles look like "Headline - Source"
    const sourceTag = decode(tag(b, 'source') || '')
    let title = rawTitle
    let source = sourceTag
    const dashIdx = rawTitle.lastIndexOf(' - ')
    if (!source && dashIdx > 0) {
      source = rawTitle.slice(dashIdx + 3)
      title = rawTitle.slice(0, dashIdx)
    } else if (source && rawTitle.endsWith(` - ${source}`)) {
      title = rawTitle.slice(0, rawTitle.length - source.length - 3)
    }
    const published = tag(b, 'pubDate') || undefined
    items.push({
      id: link,
      title: title.trim(),
      source: source || 'Google News',
      link,
      published: published || undefined,
    })
  }
  return items
}

function dedupeSort(items: NewsItem[], limit: number): NewsItem[] {
  const seen = new Set<string>()
  const out: NewsItem[] = []
  for (const it of items) {
    const key = it.title.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push(it)
  }
  out.sort((a, b) => {
    const ta = a.published ? Date.parse(a.published) : 0
    const tb = b.published ? Date.parse(b.published) : 0
    return tb - ta
  })
  return out.slice(0, limit)
}

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const type = searchParams.get('type') === 'videos' ? 'videos' : 'articles'
  const topic = searchParams.get('topic')?.trim() || null
  const category = searchParams.get('category')?.trim() || null
  const scoped = categoryScopedQuery(category, topic)

  if (type === 'videos') {
    // Use the domain's channel pool when a category is set, else the news pool.
    const pool =
      (category && CATEGORY_CHANNELS[category]) || VIDEO_FEEDS
    const results = await Promise.all(
      pool.map(async ({ source, channelId }) => {
        const xml = await fetchFeed(
          `https://www.youtube.com/feeds/videos.xml?channel_id=${channelId}`,
        )
        return xml ? parseYoutubeEntries(xml, source) : []
      }),
    )
    let items = results.flat()
    if (topic) {
      const t = topic.toLowerCase()
      const filtered = items.filter((i) => i.title.toLowerCase().includes(t))
      if (filtered.length >= 3) items = filtered
    }
    // Fallback to the broad news pool if a domain pool came back thin.
    if (items.length < 3 && category) {
      const fb = await Promise.all(
        VIDEO_FEEDS.map(async ({ source, channelId }) => {
          const xml = await fetchFeed(
            `https://www.youtube.com/feeds/videos.xml?channel_id=${channelId}`,
          )
          return xml ? parseYoutubeEntries(xml, source) : []
        }),
      )
      items = items.concat(fb.flat())
    }
    return Response.json({ items: dedupeSort(items, 16) })
  }

  // Articles: a scoped query (topic and/or category) uses Google News search;
  // a bare general request uses the curated trusted outlets.
  if (scoped) {
    const xml = await fetchFeed(googleNewsUrl(scoped))
    const items = xml ? parseGoogleNews(xml) : []
    return Response.json({ items: dedupeSort(items, 18) })
  }

  const results = await Promise.all(
    OUTLET_FEEDS.map(async ({ source, url }) => {
      const xml = await fetchFeed(url)
      return xml ? parseRssItems(xml, source) : []
    }),
  )
  return Response.json({ items: dedupeSort(results.flat(), 18) })
}
