'use client'

import { useEffect, useRef, useState } from 'react'
import type { NewsItem } from '@/lib/nancy/types'
import { enrichArticle } from '@/lib/nancy/nancy-client'
import { timeAgo } from '@/lib/nancy/time'
import { CornerTicks } from './hud-bits'
import { ExternalLink, Loader2, Volume2, VolumeX, X } from 'lucide-react'

/**
 * Immersive, JARVIS-style spotlight for a single story. Blurs everything
 * behind it, autoplays video (with a one-tap sound fallback), and for articles
 * surfaces a hero image plus a readout that Nancy narrates aloud.
 */
export function StoryDialog({
  item,
  isVideo,
  onClose,
  onReadout,
}: {
  item: NewsItem | null
  isVideo: boolean
  onClose: () => void
  onReadout?: (text: string) => void
}) {
  const [image, setImage] = useState<string | undefined>(undefined)
  const [body, setBody] = useState<string>('')
  const [source, setSource] = useState<string>('')
  const [link, setLink] = useState<string>('')
  const [loading, setLoading] = useState(false)
  // For video: whether audio is explicitly enabled (forces a re-mounted iframe).
  const [soundOn, setSoundOn] = useState(true)
  const readoutDone = useRef<string | null>(null)

  // Reset + enrich whenever the spotlighted item changes.
  useEffect(() => {
    if (!item) return
    setImage(item.image)
    setBody(item.summary ?? '')
    setSource(item.source)
    setLink(item.link)
    setSoundOn(true)
    readoutDone.current = null

    if (isVideo) return // videos narrate themselves

    let cancelled = false
    setLoading(true)
    enrichArticle(item.link)
      .then((meta) => {
        if (cancelled) return
        if (meta.image) setImage(meta.image)
        if (meta.url) setLink(meta.url)
        if (meta.site) setSource(meta.site)
        const richer =
          meta.description && meta.description.length > (item.summary?.length ?? 0)
            ? meta.description
            : item.summary ?? ''
        setBody(richer)
        // Nancy reads the headline + lede once the story is composed.
        if (readoutDone.current !== item.id) {
          readoutDone.current = item.id
          const script = `${item.title}. ${richer}`.trim()
          onReadout?.(script)
        }
      })
      .finally(() => !cancelled && setLoading(false))

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item?.id, isVideo])

  // Esc closes.
  useEffect(() => {
    if (!item) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [item, onClose])

  if (!item) return null

  const videoSrc = item.video
    ? `${item.video}?autoplay=1&rel=0&modestbranding=1&playsinline=1&start=0&end=180&mute=${soundOn ? 0 : 1}`
    : null

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center p-3 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-label={item.title}
    >
      {/* Background blur + dim — this is what blurs everything behind the dialog */}
      <button
        type="button"
        aria-label="Dismiss"
        onClick={onClose}
        className="absolute inset-0 cursor-default bg-background/70 backdrop-blur-xl"
      />
      {/* sweeping scan line for atmosphere */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div
          className="absolute inset-x-0 h-px bg-primary/40"
          style={{ animation: 'hud-scan 4.5s linear infinite' }}
        />
      </div>

      <div className="hud-panel relative z-10 flex max-h-[92dvh] w-full max-w-4xl flex-col overflow-hidden rounded-lg duration-300 animate-in fade-in zoom-in-95">
        <CornerTicks />

        {/* header */}
        <div className="flex items-center justify-between gap-2 border-b border-border/60 px-4 py-2.5">
          <div className="flex min-w-0 items-center gap-2">
            <span className="h-1.5 w-1.5 shrink-0 animate-hud-pulse rounded-full bg-primary" />
            <span className="truncate font-heading text-[0.6rem] tracking-[0.25em] text-primary">
              {source || 'Newsfeed'}
            </span>
            <span className="shrink-0 text-[0.55rem] text-muted-foreground">
              {timeAgo(item.published)}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded border border-border bg-secondary/30 text-muted-foreground transition-colors hover:border-destructive/60 hover:text-destructive"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* media */}
        <div className="relative aspect-video w-full shrink-0 bg-black">
          {isVideo && videoSrc ? (
            <>
              <iframe
                // re-mount on sound toggle so the mute flag takes effect
                key={`${item.id}-${soundOn ? 'on' : 'off'}`}
                src={videoSrc}
                title={item.title}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                allowFullScreen
                className="h-full w-full"
              />
              <button
                type="button"
                onClick={() => setSoundOn((s) => !s)}
                className="absolute bottom-3 right-3 z-10 flex items-center gap-1.5 rounded-full border border-primary/50 bg-background/80 px-3 py-1.5 text-[0.55rem] text-primary backdrop-blur transition-colors hover:bg-primary/15"
              >
                {soundOn ? (
                  <>
                    <Volume2 className="h-3.5 w-3.5" /> Sound on
                  </>
                ) : (
                  <>
                    <VolumeX className="h-3.5 w-3.5" /> Tap for sound
                  </>
                )}
              </button>
              {/* Notice for limited preview */}
              <p className="absolute bottom-2 left-2 text-[0.5rem] text-primary/80">
                Preview: first 3 minutes
              </p>
            </>
          ) : image ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={image || '/placeholder.svg'}
              alt={item.title}
              crossOrigin="anonymous"
              className="h-full w-full object-cover"
              onError={() => setImage(undefined)}
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center bg-secondary/20">
              {loading ? (
                <Loader2 className="h-7 w-7 animate-spin text-primary" />
              ) : (
                <span className="font-heading text-[0.6rem] tracking-[0.3em] text-muted-foreground">
                  No imagery available
                </span>
              )}
            </div>
          )}
        </div>

        {/* readout */}
        <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-4">
          <h2 className="text-balance font-heading text-sm leading-snug text-foreground sm:text-base">
            {item.title}
          </h2>
          {body && (
            <p className="text-pretty text-[0.72rem] leading-relaxed text-muted-foreground">
              {body}
            </p>
          )}
          <div className="mt-1 flex items-center gap-2">
            <a
              href={link || item.link}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded border border-primary/50 bg-primary/10 px-3 py-1.5 text-[0.55rem] text-primary transition-colors hover:bg-primary/20"
            >
              Open source <ExternalLink className="h-3 w-3" />
            </a>
            {!isVideo && body && (
              <button
                type="button"
                onClick={() => onReadout?.(`${item.title}. ${body}`)}
                className="inline-flex items-center gap-1.5 rounded border border-border bg-secondary/30 px-3 py-1.5 text-[0.55rem] text-muted-foreground transition-colors hover:border-primary/60 hover:text-primary"
              >
                <Volume2 className="h-3 w-3" /> Read again
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}