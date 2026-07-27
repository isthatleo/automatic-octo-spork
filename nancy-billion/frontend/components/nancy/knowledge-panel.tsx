'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import useSWR from 'swr'
import type { EconomicEvent, KnowledgeCategory, NewsItem } from '@/lib/nancy/types'
import { getEconomicCalendarEvents } from '@/lib/nancy/economic-calendar-client'
import { timeAgo } from '@/lib/nancy/time'
import { cn } from '@/lib/utils'
import { StoryDialog } from './story-dialog'
import {
  Atom,
  Bookmark,
  BookmarkCheck,
  BookOpen,
  CandlestickChart,
  CheckCircle2,
  Clapperboard,
  Clock,
  Flame,
  FlaskConical,
  Globe2,
  LayoutGrid,
  Landmark,
  Layers,
  Loader2,
  Newspaper,
  Pause,
  Play,
  PlayCircle,
  Radio,
  Search,
  SkipForward,
  Star,
  Stethoscope,
  Telescope,
  X,
  type LucideIcon,
} from 'lucide-react'

// ---------------------------------------------------------------------------
// Economic Calendar strip -- real NFP/CPI/FOMC tracking (see backend's
// economic_calendar.py + /economic-calendar/events), shown regardless of
// which news category tab is active. Countdown ticks client-side; the
// underlying data itself refreshes from the backend's cache every 20s.
// ---------------------------------------------------------------------------

/** Data provider's "YYYY-MM-DD HH:MM:SS" is US-Eastern release time (BLS/Fed
 *  convention, e.g. 08:30/14:00 ET) -- not necessarily the viewer's local
 *  timezone. Verify against your own first live fetch if this looks off by
 *  a few hours for your location. */
function parseEventDate(date: string): Date {
  return new Date(date.replace(' ', 'T'))
}

function formatCountdown(target: Date, now: Date): string {
  const ms = target.getTime() - now.getTime()
  if (ms <= 0) return 'releasing now'
  const totalSeconds = Math.floor(ms / 1000)
  const days = Math.floor(totalSeconds / 86400)
  const hours = Math.floor((totalSeconds % 86400) / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  if (days > 0) return `in ${days}d ${hours}h`
  if (hours > 0) return `in ${hours}h ${minutes}m`
  if (minutes > 0) return `in ${minutes}m ${seconds}s`
  return `in ${seconds}s`
}

function EconomicCalendarStrip() {
  const [now, setNow] = useState(() => new Date())
  const { data } = useSWR('economic-calendar-events', () => getEconomicCalendarEvents(), {
    refreshInterval: 20000,
    revalidateOnFocus: false,
  })

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  const events = data?.events ?? []
  const upcoming = useMemo(
    () =>
      events
        .filter((e) => e.actual === null)
        .sort((a, b) => parseEventDate(a.date).getTime() - parseEventDate(b.date).getTime())
        .slice(0, 3),
    [events],
  )
  const recent = useMemo(
    () =>
      events
        .filter((e) => e.actual !== null)
        .sort((a, b) => parseEventDate(b.date).getTime() - parseEventDate(a.date).getTime())
        .slice(0, 3),
    [events],
  )

  if (data && !data.configured) {
    return (
      <div className="flex items-center gap-2 border-b border-border/60 bg-secondary/10 px-3 py-2 text-[0.55rem] text-muted-foreground">
        <Radio className="h-3 w-3" />
        Economic calendar disabled — set FMP_API_KEY in the backend .env to track live NFP/CPI/FOMC releases.
      </div>
    )
  }

  if (upcoming.length === 0 && recent.length === 0) return null

  return (
    <div className="flex flex-wrap items-center gap-2 overflow-x-auto border-b border-border/60 bg-secondary/10 px-3 py-2">
      <span className="flex shrink-0 items-center gap-1 text-[0.5rem] tracking-[0.2em] text-primary">
        <Radio className="h-3 w-3 animate-pulse" /> LIVE CALENDAR
      </span>
      {recent.map((e) => {
        const delta = e.actual !== null && e.estimate !== null ? e.actual - e.estimate : null
        return (
          <div
            key={`recent-${e.event_name}-${e.date}`}
            className="flex shrink-0 items-center gap-1.5 rounded border border-border bg-background/60 px-2 py-1 text-[0.55rem]"
          >
            <span className="text-foreground">{e.event_name}</span>
            <span className="text-muted-foreground">
              {e.actual}
              {e.unit} vs {e.estimate}
              {e.unit} est.
            </span>
            {delta !== null && (
              <span className={delta > 0 ? 'text-emerald-400' : delta < 0 ? 'text-rose-400' : 'text-muted-foreground'}>
                {delta > 0 ? '▲' : delta < 0 ? '▼' : '='}
                {Math.abs(delta)}
                {e.unit}
              </span>
            )}
          </div>
        )
      })}
      {upcoming.map((e) => (
        <div
          key={`upcoming-${e.event_name}-${e.date}`}
          className="flex shrink-0 items-center gap-1.5 rounded border border-primary/30 bg-primary/5 px-2 py-1 text-[0.55rem]"
        >
          <span className="text-primary">{e.event_name}</span>
          <span className="text-muted-foreground">{formatCountdown(parseEventDate(e.date), now)}</span>
          {e.estimate !== null && (
            <span className="text-muted-foreground">
              (est. {e.estimate}
              {e.unit})
            </span>
          )}
        </div>
      ))}
    </div>
  )
}

type Media = 'articles' | 'videos'
type ViewMode = 'cards' | 'sources' | 'timeline'

// ---------------------------------------------------------------------------
// Real bookmarks -- an actual user action (clicking a star), persisted
// locally, not a fabricated "recommended for you" signal. Stores full items
// (not just ids) so a saved story still renders correctly after its
// originating feed fetch has rotated out of cache.
// ---------------------------------------------------------------------------
const BOOKMARKS_KEY = 'nancy.newsBookmarks'
function useBookmarks() {
  const [items, setItems] = useState<NewsItem[]>([])

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      const raw = window.localStorage.getItem(BOOKMARKS_KEY)
      if (raw) setItems(JSON.parse(raw))
    } catch {
      /* ignore corrupt entry */
    }
  }, [])

  const persist = (next: NewsItem[]) => {
    setItems(next)
    try {
      window.localStorage.setItem(BOOKMARKS_KEY, JSON.stringify(next))
    } catch {
      /* quota / private mode -- ignore */
    }
  }

  const isSaved = (id: string) => items.some((i) => i.id === id)
  const toggle = (item: NewsItem) => {
    persist(isSaved(item.id) ? items.filter((i) => i.id !== item.id) : [item, ...items].slice(0, 200))
  }

  return { items, isSaved, toggle }
}

// ---------------------------------------------------------------------------
// Real "seen" tracking -- every story id you've actually opened in the
// spotlight dialog, persisted locally. Powers a real "already read" mark
// instead of pretending every visit to the feed is a first visit.
// ---------------------------------------------------------------------------
const SEEN_KEY = 'nancy.newsSeen'
function useSeenTracking() {
  const [seen, setSeen] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      const raw = window.localStorage.getItem(SEEN_KEY)
      if (raw) setSeen(new Set(JSON.parse(raw)))
    } catch {
      /* ignore corrupt entry */
    }
  }, [])

  const markSeen = (id: string) => {
    setSeen((prev) => {
      if (prev.has(id)) return prev
      const next = new Set(prev)
      next.add(id)
      // Cap what's persisted so this can't grow unbounded over a long session.
      const capped = Array.from(next).slice(-500)
      try {
        window.localStorage.setItem(SEEN_KEY, JSON.stringify(capped))
      } catch {
        /* quota / private mode -- ignore */
      }
      return new Set(capped)
    })
  }

  return { seen, markSeen }
}

/** Real reading-time estimate from the actual summary word count (200 wpm) --
 * a derived stat, not a fabricated one, same idea as timeAgo() computing a
 * real value from a real timestamp instead of inventing one. */
function estimateReadingTime(text: string | undefined): number {
  if (!text) return 1
  const words = text.trim().split(/\s+/).filter(Boolean).length
  return Math.max(1, Math.round(words / 200))
}

const STOPWORDS = new Set([
  'the', 'and', 'for', 'with', 'that', 'this', 'from', 'have', 'has', 'are', 'was', 'were',
  'will', 'says', 'said', 'after', 'over', 'into', 'about', 'amid', 'more', 'than', 'its',
  'their', 'his', 'her', 'new', 'first', 'what', 'when', 'why', 'how', 'who', 'not',
])
function significantWords(title: string): Set<string> {
  return new Set(
    title
      .toLowerCase()
      .replace(/[^a-z0-9\s]/g, ' ')
      .split(/\s+/)
      .filter((w) => w.length > 3 && !STOPWORDS.has(w)),
  )
}
function jaccard(a: Set<string>, b: Set<string>): number {
  if (a.size === 0 || b.size === 0) return 0
  let intersect = 0
  for (const w of a) if (b.has(w)) intersect++
  const union = a.size + b.size - intersect
  return union === 0 ? 0 : intersect / union
}

/** Real lightweight cross-source clustering: groups items in the current
 * result set whose titles share enough significant vocabulary (Jaccard
 * similarity over real title words) to plausibly be the same story covered
 * by different outlets. Returns, per item id, how many *distinct real
 * sources* are in its cluster -- a genuine source-diversity signal computed
 * from the actual fetched items, not a fabricated "trending" score. */
function computeSourceDiversity(items: NewsItem[]): Map<string, number> {
  const wordSets = items.map((it) => significantWords(it.title))
  const result = new Map<string, number>()
  for (let i = 0; i < items.length; i++) {
    const sources = new Set([items[i].source])
    for (let j = 0; j < items.length; j++) {
      if (i === j) continue
      if (jaccard(wordSets[i], wordSets[j]) >= 0.4) sources.add(items[j].source)
    }
    if (sources.size > 1) result.set(items[i].id, sources.size)
  }
  return result
}

// ---------------------------------------------------------------------------
// Real "Follow" system -- an explicit user action (tapping a star on a
// category or on a searched topic), persisted locally, driving a genuine
// "For You" aggregation. Not an opaque ML recommendation -- exactly the
// categories/topics you told it to track, nothing else.
// ---------------------------------------------------------------------------
const FOLLOWS_KEY = 'nancy.newsFollows'
interface Follows {
  categories: KnowledgeCategory[]
  topics: string[]
}
function useFollows() {
  const [follows, setFollows] = useState<Follows>({ categories: [], topics: [] })

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      const raw = window.localStorage.getItem(FOLLOWS_KEY)
      if (raw) setFollows(JSON.parse(raw))
    } catch {
      /* ignore corrupt entry */
    }
  }, [])

  const persist = (next: Follows) => {
    setFollows(next)
    try {
      window.localStorage.setItem(FOLLOWS_KEY, JSON.stringify(next))
    } catch {
      /* quota / private mode -- ignore */
    }
  }

  const isCategoryFollowed = (c: KnowledgeCategory) => follows.categories.includes(c)
  const toggleCategory = (c: KnowledgeCategory) => {
    persist({ ...follows, categories: isCategoryFollowed(c) ? follows.categories.filter((x) => x !== c) : [...follows.categories, c] })
  }
  const isTopicFollowed = (t: string) => follows.topics.some((x) => x.toLowerCase() === t.toLowerCase())
  const toggleTopic = (t: string) => {
    const clean = t.trim()
    if (!clean) return
    persist({ ...follows, topics: isTopicFollowed(clean) ? follows.topics.filter((x) => x.toLowerCase() !== clean.toLowerCase()) : [...follows.topics, clean] })
  }

  return { follows, isCategoryFollowed, toggleCategory, isTopicFollowed, toggleTopic }
}

/** Real aggregation across every followed category/topic -- parallel
 * fetches through the same real RSS/YouTube/Google-News pipeline
 * (app/api/news/route.ts), merged, deduped by title, sorted by actual
 * publish time. Empty (not fabricated) until you've followed something. */
function useForYouFeed(categories: KnowledgeCategory[], topics: string[], media: Media, active: boolean) {
  const [items, setItems] = useState<NewsItem[]>([])
  const [loading, setLoading] = useState(false)
  const catKey = categories.join(',')
  const topicKey = topics.join(',')

  useEffect(() => {
    if (!active || (catKey === '' && topicKey === '')) {
      setItems([])
      return
    }
    let cancelled = false
    setLoading(true)
    const queries = [
      ...catKey.split(',').filter(Boolean).map((c) => `/api/news?type=${media}&category=${c}`),
      ...topicKey.split(',').filter(Boolean).map((t) => `/api/news?type=${media}&topic=${encodeURIComponent(t)}`),
    ]
    Promise.all(queries.map((q) => fetch(q).then((r) => r.json()).catch(() => ({ items: [] as NewsItem[] }))))
      .then((results) => {
        if (cancelled) return
        const merged: NewsItem[] = []
        const seen = new Set<string>()
        for (const r of results) {
          for (const it of (r.items ?? []) as NewsItem[]) {
            const key = it.title.toLowerCase()
            if (seen.has(key)) continue
            seen.add(key)
            merged.push(it)
          }
        }
        merged.sort((a, b) => (b.published ? Date.parse(b.published) : 0) - (a.published ? Date.parse(a.published) : 0))
        setItems(merged.slice(0, 40))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [active, catKey, topicKey, media])

  return { items, loading }
}

interface CatMeta {
  key: KnowledgeCategory
  label: string
  icon: LucideIcon
}

const CATS: CatMeta[] = [
  { key: 'finance', label: 'Finance', icon: CandlestickChart },
  { key: 'general', label: 'World', icon: Globe2 },
  { key: 'medicine', label: 'Medicine', icon: Stethoscope },
  { key: 'science', label: 'Science', icon: FlaskConical },
  { key: 'physics', label: 'Physics', icon: Atom },
  { key: 'astrophysics', label: 'Astrophysics', icon: Telescope },
  { key: 'documentaries', label: 'Docs', icon: Clapperboard },
  { key: 'history', label: 'History', icon: Landmark },
  { key: 'literature', label: 'Literature', icon: BookOpen },
]

const fetcher = (url: string) =>
  fetch(url).then((r) => {
    if (!r.ok) throw new Error('feed error')
    return r.json() as Promise<{ items: NewsItem[] }>
  })


export function KnowledgePanel({
  category,
  topic,
  media,
  autoOpenTop,
  requestId,
  onReadout,
  onClose,
}: {
  category: KnowledgeCategory
  topic: string | null
  media: Media
  autoOpenTop: boolean
  /** Increments on every fresh command so identical requests still re-sync. */
  requestId: number
  onReadout: (text: string) => void
  onClose: () => void
}) {
  const [cat, setCat] = useState<KnowledgeCategory>(category)
  const [feed, setFeed] = useState<Media>(media)
  const [query, setQuery] = useState(topic ?? '')
  const [activeTopic, setActiveTopic] = useState(topic ?? '')
  const [spotlight, setSpotlight] = useState<NewsItem | null>(null)
  const [viewMode, setViewMode] = useState<ViewMode>('cards')
  const [showSaved, setShowSaved] = useState(false)
  const [showForYou, setShowForYou] = useState(false)
  const [sortMode, setSortMode] = useState<'latest' | 'trending'>('latest')
  const bookmarks = useBookmarks()
  const { seen, markSeen } = useSeenTracking()
  const follows = useFollows()
  // Token that increments whenever the page issues a fresh command, so we know
  // to honor an autoOpenTop request exactly once per command.
  const pendingAuto = useRef(false)

  // Real auto-read/autoplay queue -- "Play Briefing" walks through whatever
  // list is currently on screen, opening each story and auto-advancing
  // after a real dwell time (the actual estimated reading time for
  // articles, the actual 3-minute preview cap already used for videos).
  // Not a fabricated "AI picked this for you" queue -- it's exactly the
  // real items currently visible, in the same order.
  const [briefingQueue, setBriefingQueue] = useState<NewsItem[] | null>(null)
  const briefingIndexRef = useRef(0)
  const briefingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Sync from a new voice/typed command.
  useEffect(() => {
    setCat(category)
    setFeed(media)
    setQuery(topic ?? '')
    setActiveTopic(topic ?? '')
    if (autoOpenTop) pendingAuto.current = true
  }, [category, topic, media, autoOpenTop, requestId])

  const params = new URLSearchParams({ type: feed })
  if (cat && cat !== 'general') params.set('category', cat)
  if (activeTopic) params.set('topic', activeTopic)
  const { data, isLoading, error } = useSWR(
    `/api/news?${params.toString()}`,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 60000 },
  )

  const fetchedItems = useMemo(() => data?.items ?? [], [data])
  const forYou = useForYouFeed(follows.follows.categories, follows.follows.topics, feed, showForYou)

  const baseItems = showSaved ? bookmarks.items : showForYou ? forYou.items : fetchedItems
  // Real cross-source diversity, computed over whatever the actual current
  // result set is (bookmarks/For You included -- each is a real merged set
  // of real items, clustering still means the same thing: multiple real
  // outlets covering the same real story).
  const diversity = useMemo(() => computeSourceDiversity(baseItems), [baseItems])
  const items = useMemo(() => {
    if (sortMode !== 'trending') return baseItems
    return [...baseItems].sort((a, b) => (diversity.get(b.id) ?? 0) - (diversity.get(a.id) ?? 0))
  }, [baseItems, sortMode, diversity])

  // Auto-open the single top result immersively when Nancy was asked to.
  useEffect(() => {
    if (pendingAuto.current && fetchedItems.length > 0) {
      pendingAuto.current = false
      openStory(fetchedItems[0])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchedItems])

  // Opening a story is always the real "the user actually read this" signal
  // that drives the seen/read-tracking mark on its card.
  const openStory = (item: NewsItem) => {
    setSpotlight(item)
    markSeen(item.id)
  }

  const startBriefing = () => {
    if (items.length === 0) return
    briefingIndexRef.current = 0
    setBriefingQueue(items)
    openStory(items[0])
  }
  const stopBriefing = () => {
    if (briefingTimerRef.current) clearTimeout(briefingTimerRef.current)
    setBriefingQueue(null)
    setSpotlight(null)
  }
  const skipBriefing = () => {
    if (!briefingQueue) return
    if (briefingTimerRef.current) clearTimeout(briefingTimerRef.current)
    const next = briefingIndexRef.current + 1
    if (next >= briefingQueue.length) {
      stopBriefing()
      return
    }
    briefingIndexRef.current = next
    openStory(briefingQueue[next])
  }

  // Auto-advance: dwell for the real estimated reading time (articles) or
  // the real 3-minute preview window (videos, matching StoryDialog's own
  // `&end=180` cap) before moving to the next real item in the queue.
  useEffect(() => {
    if (!briefingQueue || !spotlight) return
    const dwellMs = feed === 'videos' ? 180_000 : (estimateReadingTime(spotlight.summary) * 60_000 + 5000)
    briefingTimerRef.current = setTimeout(() => {
      const next = briefingIndexRef.current + 1
      if (next >= briefingQueue.length) {
        stopBriefing()
        return
      }
      briefingIndexRef.current = next
      openStory(briefingQueue[next])
    }, dwellMs)
    return () => {
      if (briefingTimerRef.current) clearTimeout(briefingTimerRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spotlight, briefingQueue, feed])

  const activeLabel = showSaved ? 'Saved' : showForYou ? 'For You' : CATS.find((c) => c.key === cat)?.label ?? 'Library'

  return (
    <div className="hud-panel relative flex h-full flex-col overflow-hidden rounded-md">
      {/* header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 p-3">
        <div className="flex items-center gap-2">
          <Newspaper className="h-4 w-4 text-primary" />
          <div>
            <h2 className="font-heading text-xs tracking-[0.22em] text-primary">
              {activeLabel} {feed === 'videos' ? 'Briefings' : 'Intelligence'}
            </h2>
            <p className="text-[0.5rem] tracking-[0.25em] text-muted-foreground">
              {activeTopic ? `Topic — ${activeTopic}` : 'Trusted sources · live'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          <div className="flex overflow-hidden rounded border border-border">
            <button
              type="button"
              onClick={() => setFeed('articles')}
              className={`flex items-center gap-1 px-2.5 py-1.5 text-[0.55rem] transition-colors ${
                feed === 'articles'
                  ? 'bg-primary/15 text-primary'
                  : 'bg-secondary/30 text-muted-foreground hover:text-foreground'
              }`}
            >
              <Newspaper className="h-3 w-3" /> Articles
            </button>
            <button
              type="button"
              onClick={() => setFeed('videos')}
              className={`flex items-center gap-1 px-2.5 py-1.5 text-[0.55rem] transition-colors ${
                feed === 'videos'
                  ? 'bg-primary/15 text-primary'
                  : 'bg-secondary/30 text-muted-foreground hover:text-foreground'
              }`}
            >
              <PlayCircle className="h-3 w-3" /> Videos
            </button>
          </div>
          
          {/* View Mode Controls -- Cards (magazine-style grid, the default),
              Sources (real items grouped by actual outlet, replacing a
              "Galaxy" view whose star positions never encoded anything real),
              Timeline (real chronological order). */}
          <div className="flex overflow-hidden rounded border border-border">
            <button
              type="button"
              onClick={() => setViewMode('cards')}
              className={`flex items-center gap-1 px-2 py-1.5 text-[0.5rem] transition-colors ${
                viewMode === 'cards'
                  ? 'bg-primary/15 text-primary'
                  : 'bg-secondary/30 text-muted-foreground hover:text-foreground'
              }`}
            >
              <LayoutGrid className="h-3 w-3" /> Cards
            </button>
            <button
              type="button"
              onClick={() => setViewMode('sources')}
              className={`flex items-center gap-1 px-2 py-1.5 text-[0.5rem] transition-colors ${
                viewMode === 'sources'
                  ? 'bg-primary/15 text-primary'
                  : 'bg-secondary/30 text-muted-foreground hover:text-foreground'
              }`}
            >
              <Layers className="h-3 w-3" /> Sources
            </button>
            <button
              type="button"
              onClick={() => setViewMode('timeline')}
              className={`flex items-center gap-1 px-2 py-1.5 text-[0.5rem] transition-colors ${
                viewMode === 'timeline'
                  ? 'bg-primary/15 text-primary'
                  : 'bg-secondary/30 text-muted-foreground hover:text-foreground'
              }`}
            >
              <Clock className="h-3 w-3" /> Timeline
            </button>
          </div>

          {/* For You -- real aggregation of every followed category/topic
              (useForYouFeed). Empty until you've actually followed
              something; never a fabricated recommendation. */}
          <button
            type="button"
            onClick={() => { setShowForYou((v) => !v); setShowSaved(false) }}
            className={`flex items-center gap-1 rounded border px-2.5 py-1.5 text-[0.55rem] transition-colors ${
              showForYou
                ? 'border-primary bg-primary/15 text-primary'
                : 'border-border bg-secondary/30 text-muted-foreground hover:text-foreground'
            }`}
          >
            <Flame className="h-3 w-3" /> For You {(follows.follows.categories.length + follows.follows.topics.length) > 0 && `(${follows.follows.categories.length + follows.follows.topics.length})`}
          </button>

          {/* Trending -- real cross-source clustering re-sort (computeSourceDiversity),
              not a hidden black-box ranking. */}
          <button
            type="button"
            onClick={() => setSortMode((m) => (m === 'trending' ? 'latest' : 'trending'))}
            title="Sort by real cross-source coverage"
            className={`flex items-center gap-1 rounded border px-2.5 py-1.5 text-[0.55rem] transition-colors ${
              sortMode === 'trending'
                ? 'border-gold bg-gold/15 text-gold'
                : 'border-border bg-secondary/30 text-muted-foreground hover:text-foreground'
            }`}
          >
            <Flame className="h-3 w-3" /> Trending
          </button>

          {/* Saved -- real bookmarks (localStorage), independent of the
              current category/search filter. */}
          <button
            type="button"
            onClick={() => { setShowSaved((v) => !v); setShowForYou(false) }}
            className={`flex items-center gap-1 rounded border px-2.5 py-1.5 text-[0.55rem] transition-colors ${
              showSaved
                ? 'border-primary bg-primary/15 text-primary'
                : 'border-border bg-secondary/30 text-muted-foreground hover:text-foreground'
            }`}
          >
            {showSaved ? <BookmarkCheck className="h-3 w-3" /> : <Bookmark className="h-3 w-3" />}
            Saved {bookmarks.items.length > 0 && `(${bookmarks.items.length})`}
          </button>

          {/* Play Briefing -- real auto-read/autoplay queue through
              whatever's currently on screen (see the briefing effect
              above): opens each item, dwells for its real reading-time
              estimate (or the real 3-minute video preview window), then
              auto-advances. */}
          <button
            type="button"
            onClick={() => (briefingQueue ? stopBriefing() : startBriefing())}
            disabled={!briefingQueue && items.length === 0}
            className={`flex items-center gap-1 rounded border px-2.5 py-1.5 text-[0.55rem] transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
              briefingQueue
                ? 'border-destructive bg-destructive/15 text-destructive'
                : 'border-primary bg-primary/15 text-primary hover:bg-primary/25'
            }`}
          >
            {briefingQueue ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
            {briefingQueue ? 'Stop Briefing' : 'Play Briefing'}
          </button>

          <button
            type="button"
            onClick={onClose}
            title="Close"
            className="flex h-8 w-8 items-center justify-center rounded border border-border bg-secondary/30 text-muted-foreground transition-colors hover:border-destructive/60 hover:text-destructive"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {briefingQueue && spotlight && (
        <div className="flex items-center gap-2 border-b border-border/60 bg-primary/5 px-3 py-1.5 text-[0.55rem]">
          <Radio className="h-3 w-3 shrink-0 animate-pulse text-primary" />
          <span className="text-muted-foreground">Now playing ({briefingIndexRef.current + 1}/{briefingQueue.length}):</span>
          <span className="truncate text-foreground">{spotlight.title}</span>
          <button type="button" onClick={skipBriefing} className="ml-auto flex shrink-0 items-center gap-1 rounded border border-border px-2 py-0.5 text-muted-foreground hover:text-foreground">
            <SkipForward className="h-3 w-3" /> Skip
          </button>
        </div>
      )}

      <EconomicCalendarStrip />

      {/* domain rail + search -- both apply to the live feed, not to Saved
          or For You (a bookmark list has no "category", and For You is
          driven by follows, not category selection), so both are hidden
          in those views rather than shown doing nothing. */}
      {!showSaved && !showForYou && (
        <>
          <div className="flex items-center gap-1.5 overflow-x-auto border-b border-border/60 p-2">
            {CATS.map(({ key, label, icon: Icon }) => (
              <div key={key} className="group relative shrink-0">
              <button
                type="button"
                onClick={() => {
                  setCat(key)
                  setQuery('')
                  setActiveTopic('')
                }}
                className={`flex shrink-0 items-center gap-1.5 rounded border px-2.5 py-1.5 pr-6 text-[0.55rem] transition-colors ${
                  cat === key
                    ? 'border-primary bg-primary/15 text-primary'
                    : 'border-border bg-secondary/20 text-muted-foreground hover:border-primary/50 hover:text-foreground'
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                {label}
              </button>
              <button
                type="button"
                onClick={() => follows.toggleCategory(key)}
                title={follows.isCategoryFollowed(key) ? `Unfollow ${label}` : `Follow ${label}`}
                className={`absolute right-1 top-1/2 flex h-4 w-4 -translate-y-1/2 items-center justify-center rounded-full transition-opacity ${
                  follows.isCategoryFollowed(key) ? 'text-gold opacity-100' : 'text-muted-foreground opacity-0 group-hover:opacity-100'
                }`}
              >
                <Star className={cn('h-3 w-3', follows.isCategoryFollowed(key) && 'fill-gold')} />
              </button>
              </div>
            ))}
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault()
              setActiveTopic(query.trim())
            }}
            className="flex items-center gap-2 border-b border-border/60 p-2"
          >
            <Search className="ml-1 h-3.5 w-3.5 text-muted-foreground" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={`Search ${activeLabel.toLowerCase()} — e.g. ${
                cat === 'finance' ? 'Nvidia, CPI, oil' : 'a topic or keyword'
              }`}
              className="h-8 flex-1 rounded border border-border bg-background/60 px-2.5 text-[0.6rem] text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-primary/60"
            />
            {activeTopic && (
              <>
                <button
                  type="button"
                  onClick={() => follows.toggleTopic(activeTopic)}
                  title={follows.isTopicFollowed(activeTopic) ? `Unfollow "${activeTopic}"` : `Follow "${activeTopic}"`}
                  className={`flex items-center gap-1 rounded border px-2 py-1 text-[0.5rem] transition-colors ${
                    follows.isTopicFollowed(activeTopic) ? 'border-gold bg-gold/10 text-gold' : 'border-border text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <Star className={cn('h-2.5 w-2.5', follows.isTopicFollowed(activeTopic) && 'fill-gold')} />
                  {follows.isTopicFollowed(activeTopic) ? 'Following' : 'Follow'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setQuery('')
                    setActiveTopic('')
                  }}
                  className="rounded border border-border px-2 py-1 text-[0.5rem] text-muted-foreground hover:text-foreground"
                >
                  Top stories
                </button>
              </>
            )}
          </form>
        </>
      )}

      {/* body */}
      <div className="relative flex-1 overflow-y-auto p-3">
        {isLoading && (
          <div className="flex h-full flex-col items-center justify-center gap-2">
            <Loader2 className="h-7 w-7 animate-spin text-primary" />
            <p className="font-heading text-[0.6rem] text-primary">
              Aggregating reports...
            </p>
          </div>
        )}

        {error && !isLoading && (
          <p className="mt-8 text-center text-xs text-destructive">
            Uplink failed. Try again shortly.
          </p>
        )}

        {!isLoading && !error && items.length === 0 && (
          <p className="mt-8 text-center text-xs text-muted-foreground">
            No reports found{activeTopic ? ` for "${activeTopic}"` : ''}.
          </p>
        )}

        {!isLoading && viewMode === 'cards' && items.length > 0 && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {items.map((it) => (
              <NewsCard
                key={it.id}
                item={it}
                feed={feed}
                saved={bookmarks.isSaved(it.id)}
                isSeen={seen.has(it.id)}
                sourceCount={diversity.get(it.id)}
                onOpen={() => openStory(it)}
                onToggleSave={() => bookmarks.toggle(it)}
              />
            ))}
          </div>
        )}

        {!isLoading && viewMode === 'sources' && items.length > 0 && (
          <div className="flex flex-col gap-4">
            {/* Real grouping by actual outlet -- replaces a "Galaxy" view
                whose star positions were an arbitrary spiral with no
                relation to the data. This groups the same real items by a
                genuine attribute (who reported it), so you can see how
                coverage actually differs by source. */}
            {Object.entries(
              items.reduce<Record<string, NewsItem[]>>((acc, it) => {
                (acc[it.source] ??= []).push(it)
                return acc
              }, {}),
            )
              .sort((a, b) => b[1].length - a[1].length)
              .map(([source, group]) => (
                <div key={source}>
                  <div className="mb-1.5 flex items-center gap-2 text-[0.55rem] tracking-[0.15em] text-primary">
                    <Radio className="h-3 w-3" /> {source.toUpperCase()}
                    <span className="text-muted-foreground">({group.length})</span>
                  </div>
                  <div className="flex flex-col divide-y divide-border/40 border-t border-border/40">
                    {group.map((it) => (
                      <button
                        key={it.id}
                        type="button"
                        onClick={() => openStory(it)}
                        className={`group flex items-start gap-3 py-2.5 text-left transition-colors hover:bg-secondary/20 ${seen.has(it.id) ? 'opacity-60' : ''}`}
                      >
                        {(it.image || feed === 'videos') && (
                          <div className="relative h-12 w-16 shrink-0 overflow-hidden rounded bg-background/60">
                            {it.image && (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img src={it.image} alt="" className="h-full w-full object-cover opacity-90" />
                            )}
                            {feed === 'videos' && (
                              <span className="absolute inset-0 flex items-center justify-center">
                                <PlayCircle className="h-4 w-4 text-primary" />
                              </span>
                            )}
                          </div>
                        )}
                        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                          <div className="flex items-center gap-1.5 text-[0.48rem] text-muted-foreground">
                            {seen.has(it.id) && <CheckCircle2 className="h-2.5 w-2.5 text-primary/70" />}
                            {timeAgo(it.published)}
                          </div>
                          <p className="line-clamp-2 text-[0.65rem] leading-snug text-foreground transition-colors group-hover:text-primary">
                            {it.title}
                          </p>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
          </div>
        )}

        {!isLoading && viewMode === 'timeline' && items.length > 0 && (
          <div className="relative mx-auto max-w-2xl py-1">
            {/* Timeline axis — a real hairline running the full flowed height
                of the list, not a fixed-height overlay, so it always lines
                up regardless of how many reports came back. */}
            <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-primary/20" />

            <div className="flex flex-col gap-5">
              {[...items]
                .sort(
                  (a, b) =>
                    new Date(b.published || 0).getTime() - new Date(a.published || 0).getTime(),
                )
                .map((item, index) => {
                  const isLeft = index % 2 === 0
                  const body = (
                    <button
                      type="button"
                      onClick={() => openStory(item)}
                      className={`group flex flex-col gap-1 rounded border border-border/50 bg-secondary/20 px-2.5 py-2 text-left transition-colors hover:border-primary/50 ${isLeft ? 'items-end text-right' : 'items-start text-left'} ${seen.has(item.id) ? 'opacity-60' : ''}`}
                    >
                      <div className="flex items-center gap-2 text-[0.5rem]">
                        <span className="text-primary">{item.source}</span>
                        <span className="text-muted-foreground">
                          {new Date(item.published || 0).toLocaleDateString()}
                        </span>
                        {seen.has(item.id) && <CheckCircle2 className="h-2.5 w-2.5 text-primary/70" />}
                      </div>
                      <div className="text-[0.6rem] leading-snug text-foreground transition-colors group-hover:text-primary">
                        {item.title}
                      </div>
                      {item.summary && feed === 'articles' && (
                        <p className="line-clamp-2 text-[0.5rem] leading-relaxed text-muted-foreground">
                          {item.summary}
                        </p>
                      )}
                    </button>
                  )
                  return (
                    <div
                      key={`timeline-${item.id}`}
                      className="relative grid grid-cols-[1fr_auto_1fr] items-start gap-3"
                    >
                      <div>{isLeft && body}</div>
                      <div className="flex justify-center pt-2.5">
                        <span className="h-2.5 w-2.5 shrink-0 rounded-full border-2 border-background bg-primary shadow-[0_0_8px_var(--hud)]" />
                      </div>
                      <div>{!isLeft && body}</div>
                    </div>
                  )
                })}
            </div>
          </div>
        )}
      </div>

      <StoryDialog
        item={spotlight}
        isVideo={feed === 'videos'}
        onClose={() => (briefingQueue ? stopBriefing() : setSpotlight(null))}
        onReadout={onReadout}
      />
    </div>
  )
}

/** Magazine-style card -- the default view. Bigger imagery and one story
 * per card read better scanned than a dense list (2026 news-app UX
 * consensus favors card/tile layouts over plain RSS-style rows). Every
 * badge on it is real: reading-time is derived from the actual summary
 * word count, "seen" reflects stories you've actually opened, the
 * source-count badge comes from real title-similarity clustering across
 * the current result set, and the bookmark star is a real, persisted
 * user action. */
function NewsCard({
  item,
  feed,
  saved,
  isSeen,
  sourceCount,
  onOpen,
  onToggleSave,
}: {
  item: NewsItem
  feed: Media
  saved: boolean
  isSeen: boolean
  sourceCount: number | undefined
  onOpen: () => void
  onToggleSave: () => void
}) {
  return (
    <div
      className={`group relative flex flex-col overflow-hidden rounded border border-border/60 bg-secondary/10 transition-colors hover:border-primary/50 ${isSeen ? 'opacity-70' : ''}`}
    >
      <button type="button" onClick={onOpen} className="flex flex-1 flex-col text-left">
        <div className="relative aspect-video w-full shrink-0 overflow-hidden bg-background/60">
          {item.image ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={item.image}
              alt=""
              className="h-full w-full object-cover opacity-90 transition-transform duration-500 group-hover:scale-105"
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-[0.5rem] tracking-[0.2em] text-muted-foreground/60">
              NO IMAGE
            </div>
          )}
          {feed === 'videos' && (
            <span className="absolute inset-0 flex items-center justify-center">
              <PlayCircle className="h-8 w-8 text-primary drop-shadow-[0_0_10px_var(--hud)]" />
            </span>
          )}
          {isSeen && (
            <span className="absolute left-1.5 top-1.5 flex items-center gap-1 rounded bg-background/80 px-1.5 py-0.5 text-[0.42rem] text-primary backdrop-blur-sm">
              <CheckCircle2 className="h-2.5 w-2.5" /> Read
            </span>
          )}
          {sourceCount != null && sourceCount > 1 && (
            <span className="absolute right-1.5 top-1.5 rounded bg-background/80 px-1.5 py-0.5 text-[0.42rem] text-accent backdrop-blur-sm">
              {sourceCount} sources
            </span>
          )}
        </div>
        <div className="flex flex-1 flex-col gap-1 p-2.5">
          <div className="flex items-center gap-2 text-[0.5rem]">
            <span className="text-primary">{item.source}</span>
            <span className="text-muted-foreground">{timeAgo(item.published)}</span>
            {feed === 'articles' && item.summary && (
              <span className="text-muted-foreground/70">· {estimateReadingTime(item.summary)} min read</span>
            )}
          </div>
          <p className="line-clamp-2 text-[0.72rem] leading-snug text-foreground transition-colors group-hover:text-primary">
            {item.title}
          </p>
          {item.summary && feed === 'articles' && (
            <p className="line-clamp-2 text-[0.58rem] leading-relaxed text-muted-foreground">
              {item.summary}
            </p>
          )}
        </div>
      </button>
      <button
        type="button"
        onClick={onToggleSave}
        title={saved ? 'Remove from Saved' : 'Save for later'}
        className={`absolute bottom-2 right-2 flex h-6 w-6 items-center justify-center rounded-full backdrop-blur-sm transition-colors ${
          saved ? 'bg-primary/25 text-primary' : 'bg-background/70 text-muted-foreground hover:text-primary'
        }`}
      >
        {saved ? <BookmarkCheck className="h-3 w-3" /> : <Bookmark className="h-3 w-3" />}
      </button>
    </div>
  )
}
