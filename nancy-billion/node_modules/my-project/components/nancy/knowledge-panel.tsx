'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import useSWR from 'swr'
import type { KnowledgeCategory, NewsItem } from '@/lib/nancy/types'
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
  Rocket,
  Search,
  Stethoscope,
  Telescope,
  X,
  type LucideIcon,
} from 'lucide-react'

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
          <Newspaper className="h-4 w-4 text-primary hud-glow" />
          <div>
            <h2 className="font-heading text-xs uppercase tracking-[0.22em] text-primary hud-glow">
              {activeLabel} {feed === 'videos' ? 'Briefings' : 'Intelligence'}
            </h2>
            <p className="text-[0.5rem] uppercase tracking-[0.25em] text-muted-foreground">
              {activeTopic ? `Topic — ${activeTopic}` : 'Trusted sources · live'}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          <div className="flex overflow-hidden rounded border border-border">
            <button
              type="button"
              onClick={() => setFeed('articles')}
              className={`flex items-center gap-1 px-2.5 py-1.5 text-[0.55rem] uppercase tracking-widest transition-colors ${
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
              className={`flex items-center gap-1 px-2.5 py-1.5 text-[0.55rem] uppercase tracking-widest transition-colors ${
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
              className={`flex items-center gap-1 px-2 py-1 text-[0.45rem] uppercase tracking-widest transition-colors ${
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
              className={`flex items-center gap-1 px-2 py-1 text-[0.45rem] uppercase tracking-widest transition-colors ${
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
              className={`flex items-center gap-1 px-2 py-1 text-[0.45rem] uppercase tracking-widest transition-colors ${
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
            className={`flex shrink-0 items-center gap-1.5 rounded border px-2.5 py-1.5 text-[0.55rem] uppercase tracking-widest transition-colors ${
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
            className="rounded border border-border px-2 py-1 text-[0.5rem] uppercase tracking-widest text-muted-foreground hover:text-foreground"
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
            <p className="font-heading text-[0.6rem] uppercase tracking-widest text-primary">
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
          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
            {items.map((it) => (
              <button
                key={it.id}
                type="button"
                onClick={() => setSpotlight(it)}
                className="group flex flex-col overflow-hidden rounded border border-border bg-secondary/20 text-left transition-colors hover:border-primary/60"
              >
                {(it.image || feed === 'videos') && (
                  <div className="relative aspect-video overflow-hidden bg-background/60">
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
                        <PlayCircle className="h-9 w-9 text-primary drop-shadow-[0_0_8px_var(--hud)]" />
                      </span>
                    )}
                  </div>
                )}
                <div className="flex flex-1 flex-col gap-1 p-2.5">
                  <div className="flex items-center justify-between text-[0.5rem] uppercase tracking-widest">
                    <span className="text-primary">{it.source}</span>
                    <span className="text-muted-foreground">{timeAgo(it.published)}</span>
                  </div>
                  <p className="line-clamp-3 text-[0.66rem] leading-snug text-foreground">
                    {it.title}
                  </p>
                  {it.summary && feed === 'articles' && (
                    <p className="line-clamp-2 text-[0.56rem] leading-relaxed text-muted-foreground">
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
          <div className="relative h-full w-full">
            {/* Timeline axis */}
            <div className="absolute left-1/2 top-0 bottom-0 w-0.5 bg-primary/20" />
            
            {/* Timeline events */}
            <div className="relative h-full w-full">
              {items
                .sort((a, b) => 
                  new Date(b.published || 0).getTime() - new Date(a.published || 0).getTime()
                )
                .map((item, index) => {
                  const isLeft = index % 2 === 0;
                  return (
                    <div
                      key={`timeline-${item.id}`}
                      className="absolute"
                      style={{
                        left: '50%',
                        top: `${(index / items.length) * 100}%`,
                        transform: `translateX(-50%)`
                      }}
                    >
                      {/* Timeline connector */}
                      <div className="absolute left-1/2 -translate-x-1/2 w-0.5 bg-primary/20" />
                      
                      {/* Event content */}
                      <div
                        className={`flex items-start gap-3 ${isLeft ? 'right-1/2' : 'left-1/2'}`}
                        style={{
                          width: '40%',
                          transform: isLeft ? 'translateX(100%)' : 'translateX(-100%)',
                        }}
                      >
                        <div className="flex-shrink-0">
                          <div className="w-2 h-2 rounded-full bg-primary" />
                        </div>
                        <div className="flex-1">
                          <div className="text-[0.5rem] font-medium text-primary">
                            {item.source}
                          </div>
                          <div className="text-[0.55rem] leading-snug text-foreground">
                            {item.title}
                          </div>
                          {item.summary && feed === 'articles' && (
                            <p className="text-[0.5rem] text-muted-foreground line-clamp-2 mt-1">
                              {item.summary}
                            </p>
                          )}
                          <div className="text-[0.45rem] text-muted-foreground mt-1">
                            {new Date(item.published || 0).toLocaleDateString()}
                          </div>
                        </div>
                      </div>
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
