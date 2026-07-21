'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import useSWR from 'swr'
import type { EconomicEvent, KnowledgeCategory, NewsItem } from '@/lib/nancy/types'
import { getEconomicCalendarEvents } from '@/lib/nancy/economic-calendar-client'
import { CornerTicks } from './hud-bits'
import { StoryDialog } from './story-dialog'
import {
  Atom,
  BookOpen,
  CandlestickChart,
  Clapperboard,
  Clock,
  FlaskConical,
  Globe2,
  Landmark,
  List,
  Loader2,
  Newspaper,
  Orbit,
  PlayCircle,
  Radio,
  Rocket,
  Search,
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
type ViewMode = 'list' | 'galaxy' | 'timeline'

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

function timeAgo(iso?: string): string {
  if (!iso) return ''
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return ''
  const m = Math.round((Date.now() - t) / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.round(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.round(h / 24)}d ago`
}

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
  const [viewMode, setViewMode] = useState<ViewMode>('list')
  // Token that increments whenever the page issues a fresh command, so we know
  // to honor an autoOpenTop request exactly once per command.
  const pendingAuto = useRef(false)

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

  const items = useMemo(() => data?.items ?? [], [data])

  // Auto-open the single top result immersively when Nancy was asked to.
  useEffect(() => {
    if (pendingAuto.current && items.length > 0) {
      pendingAuto.current = false
      setSpotlight(items[0])
    }
  }, [items])

  const activeLabel = CATS.find((c) => c.key === cat)?.label ?? 'Library'

  return (
    <div className="hud-panel relative flex h-full flex-col overflow-hidden rounded-md">
      <CornerTicks />

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
          
          {/* View Mode Controls */}
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setViewMode('list')}
              className={`flex items-center gap-1 px-2 py-1 text-[0.45rem] transition-colors ${
                viewMode === 'list'
                  ? 'bg-primary/15 text-primary'
                  : 'bg-secondary/30 text-muted-foreground hover:text-foreground'
              }`}
            >
              <List className="h-3 w-3" /> List
            </button>
            <button
              type="button"
              onClick={() => setViewMode('galaxy')}
              className={`flex items-center gap-1 px-2 py-1 text-[0.45rem] transition-colors ${
                viewMode === 'galaxy'
                  ? 'bg-primary/15 text-primary'
                  : 'bg-secondary/30 text-muted-foreground hover:text-foreground'
              }`}
            >
              <Orbit className="h-3 w-3" /> Galaxy
            </button>
            <button
              type="button"
              onClick={() => setViewMode('timeline')}
              className={`flex items-center gap-1 px-2 py-1 text-[0.45rem] transition-colors ${
                viewMode === 'timeline'
                  ? 'bg-primary/15 text-primary'
                  : 'bg-secondary/30 text-muted-foreground hover:text-foreground'
              }`}
            >
              <Clock className="h-3 w-3" /> Timeline
            </button>
          </div>
          
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

      <EconomicCalendarStrip />

      {/* domain rail */}
      <div className="flex items-center gap-1.5 overflow-x-auto border-b border-border/60 p-2">
        {CATS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            type="button"
            onClick={() => {
              setCat(key)
              setQuery('')
              setActiveTopic('')
            }}
            className={`flex shrink-0 items-center gap-1.5 rounded border px-2.5 py-1.5 text-[0.55rem] transition-colors ${
              cat === key
                ? 'border-primary bg-primary/15 text-primary'
                : 'border-border bg-secondary/20 text-muted-foreground hover:border-primary/50 hover:text-foreground'
            }`}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </button>
        ))}
      </div>

      {/* search */}
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
        )}
      </form>

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

        {!isLoading && viewMode === 'list' && items.length > 0 && (
          <div className="flex flex-col divide-y divide-border/50 border-t border-border/50">
            {items.map((it, i) => (
              <button
                key={it.id}
                type="button"
                onClick={() => setSpotlight(it)}
                className="group flex items-start gap-3 py-3 text-left transition-colors hover:bg-secondary/20"
              >
                <span className="mt-0.5 w-6 shrink-0 text-right font-display text-[0.7rem] text-muted-foreground/50">
                  {String(i + 1).padStart(2, '0')}
                </span>
                {(it.image || feed === 'videos') && (
                  <div className="relative h-14 w-20 shrink-0 overflow-hidden rounded bg-background/60">
                    {it.image && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={it.image || '/placeholder.svg'}
                        alt=""
                        className="h-full w-full object-cover opacity-90 transition-transform duration-500 group-hover:scale-105"
                      />
                    )}
                    {feed === 'videos' && (
                      <span className="absolute inset-0 flex items-center justify-center">
                        <PlayCircle className="h-5 w-5 text-primary drop-shadow-[0_0_8px_var(--hud)]" />
                      </span>
                    )}
                  </div>
                )}
                <div className="flex min-w-0 flex-1 flex-col gap-1">
                  <div className="flex items-center gap-2 text-[0.5rem]">
                    <span className="text-primary">{it.source}</span>
                    <span className="text-muted-foreground">{timeAgo(it.published)}</span>
                  </div>
                  <p className="line-clamp-2 text-[0.7rem] leading-snug text-foreground transition-colors group-hover:text-primary">
                    {it.title}
                  </p>
                  {it.summary && feed === 'articles' && (
                    <p className="line-clamp-1 text-[0.56rem] leading-relaxed text-muted-foreground">
                      {it.summary}
                    </p>
                  )}
                </div>
              </button>
            ))}
          </div>
        )}
        
        {!isLoading && viewMode === 'galaxy' && items.length > 0 && (
          <div className="relative h-full w-full">
            {/* Galaxy background */}
            <div
              className="absolute inset-0 -z-10"
              style={{
                background:
                  'radial-gradient(circle at center, transparent 0%, oklch(0.1 0 0 / 0.8) 70%, oklch(0.05 0 0 / 0.9) 100%)',
              }}
            />

            {(() => {
              // Golden-angle spiral scatter -- deterministic (same items always
              // land in the same spots), not a fabricated data layout, just a
              // real algorithm for spreading N nodes without overlap.
              const GOLDEN_ANGLE = 137.508 * (Math.PI / 180)
              const n = items.length
              const nodes = items.map((item, i) => {
                const angle = i * GOLDEN_ANGLE
                const radius = 6 + (Math.sqrt(i + 1) / Math.sqrt(n)) * 40
                return {
                  item,
                  x: 50 + radius * Math.cos(angle),
                  y: 50 + radius * Math.sin(angle),
                }
              })

              return (
                <>
                  {/* Constellation lines -- real SVG segments between
                      consecutive nodes in spiral order, not overlapping divs. */}
                  <svg
                    viewBox="0 0 100 100"
                    preserveAspectRatio="none"
                    className="pointer-events-none absolute inset-0 h-full w-full"
                  >
                    {nodes.slice(1).map((n0, i) => {
                      const prev = nodes[i]
                      return (
                        <line
                          key={`line-${n0.item.id}`}
                          x1={prev.x}
                          y1={prev.y}
                          x2={n0.x}
                          y2={n0.y}
                          stroke="oklch(0.6 0.15 240 / 0.35)"
                          strokeWidth={0.15}
                        />
                      )
                    })}
                  </svg>

                  {/* Knowledge nodes (stars) */}
                  {nodes.map(({ item, x, y }) => (
                    <button
                      key={`star-${item.id}`}
                      type="button"
                      onClick={() => setSpotlight(item)}
                      title={item.title}
                      className="group absolute flex flex-col items-center"
                      style={{ left: `${x}%`, top: `${y}%`, transform: 'translate(-50%, -50%)' }}
                    >
                      <span className="flex h-8 w-8 items-center justify-center rounded-full border border-primary/40 bg-primary/15 text-primary shadow-[0_0_10px_rgba(56,211,235,0.35)] transition-all duration-300 group-hover:scale-125 group-hover:bg-primary/30">
                        <span className="h-1.5 w-1.5 rounded-full bg-primary" />
                      </span>
                      <span className="mt-1 max-w-[6rem] truncate rounded bg-background/80 px-1.5 py-0.5 text-[0.45rem] text-primary opacity-0 backdrop-blur-sm transition-opacity group-hover:opacity-100">
                        {item.title}
                      </span>
                    </button>
                  ))}
                </>
              )
            })()}
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
                      onClick={() => setSpotlight(item)}
                      className={`group flex flex-col gap-1 rounded border border-border/50 bg-secondary/20 px-2.5 py-2 text-left transition-colors hover:border-primary/50 ${isLeft ? 'items-end text-right' : 'items-start text-left'}`}
                    >
                      <div className="flex items-center gap-2 text-[0.5rem]">
                        <span className="text-primary">{item.source}</span>
                        <span className="text-muted-foreground">
                          {new Date(item.published || 0).toLocaleDateString()}
                        </span>
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
        onClose={() => setSpotlight(null)}
        onReadout={onReadout}
      />
    </div>
  )
}
