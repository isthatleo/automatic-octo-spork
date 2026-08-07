'use client'

/**
 * Mission Control -- a small, always-available surface Billion can show
 * things on (an image she generated, a note, a code snippet) WITHOUT the
 * user needing to open the full dashboard. Confirmed live as a real gap:
 * canvas content only ever rendered inside CanvasPanel, which is only
 * mounted when the dashboard's Canvas tab is open.
 *
 * This route is deliberately minimal: it only ever subscribes to the same
 * CANVAS_ITEM_ADDED/UPDATED/REMOVED domain events CanvasPanel already
 * listens for (no new backend surface, no new WS message type -- see
 * ws-client.ts's onDomainEvent), and renders the single most recent item
 * full-size with a small strip of recent history below it. In the Electron
 * shell this loads into its own frameless, always-on-top, transparent
 * BrowserWindow (see desktop/main.js's createOverlayWindow) so it floats
 * above everything else; loaded as a plain browser tab it's just a small,
 * focused page -- same component either way.
 *
 * Auth: goes through the exact same passcode-gated middleware as every
 * other route (no bypass) -- Electron's overlay window shares the main
 * window's session cookie automatically since both load the same origin.
 */

import { useEffect, useMemo, useState } from 'react'
import { onDomainEvent } from '@/lib/nancy/ws-client'
import type { CanvasItem } from '@/lib/nancy/types'
import { X, StickyNote, Link2, Code2, Image as ImageIcon, Box, MonitorPlay } from 'lucide-react'

const TYPE_ICON: Record<CanvasItem['type'], typeof StickyNote> = {
  note: StickyNote, link: Link2, code: Code2, image: ImageIcon, '3d_scene': Box, html_preview: MonitorPlay,
}

const MAX_HISTORY = 6

export default function OverlayPage() {
  const [items, setItems] = useState<CanvasItem[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [dismissed, setDismissed] = useState(false)

  // Real initial state -- without this, a fresh overlay window opened after
  // something was already posted would show nothing until the NEXT item
  // arrives, which defeats "show me what you built" if the overlay wasn't
  // already open when she built it.
  useEffect(() => {
    fetch('/api/canvas', { cache: 'no-store' })
      .then((r) => r.json())
      .then((json) => { if (json.success) setItems(json.items.slice(0, MAX_HISTORY)) })
      .catch(() => {})
  }, [])

  useEffect(() => onDomainEvent((event) => {
    if (event.type === 'CANVAS_ITEM_ADDED' && event.item) {
      const item = event.item as CanvasItem
      setItems((prev) => [item, ...prev.filter((i) => i.id !== item.id)].slice(0, MAX_HISTORY))
      setSelectedId(item.id)
      setDismissed(false)
    } else if (event.type === 'CANVAS_ITEM_UPDATED' && event.item) {
      const item = event.item as CanvasItem
      setItems((prev) => prev.map((i) => (i.id === item.id ? item : i)))
    } else if (event.type === 'CANVAS_ITEM_REMOVED' && event.item_id) {
      setItems((prev) => prev.filter((i) => i.id !== event.item_id))
      setSelectedId((cur) => (cur === event.item_id ? null : cur))
    }
  }), [])

  const active = useMemo(
    () => items.find((i) => i.id === selectedId) ?? items[0] ?? null,
    [items, selectedId],
  )

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setDismissed(true)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  if (!active || dismissed) {
    // Fully transparent, click-through-looking empty state -- an Electron
    // overlay window with nothing to show should be visually invisible,
    // not an empty dark box sitting on the desktop.
    return <div className="h-screen w-screen bg-transparent" />
  }

  return (
    <div className="flex h-screen w-screen items-start justify-center bg-transparent p-4">
      <div className="w-full max-w-md overflow-hidden rounded-2xl border border-primary/30 bg-background/95 shadow-2xl shadow-black/40 backdrop-blur">
        <div className="flex items-center gap-2 border-b border-border/60 px-3 py-2">
          <ItemIcon type={active.type} />
          <span className="min-w-0 flex-1 truncate text-[0.65rem] text-foreground">{active.title}</span>
          <button
            type="button"
            onClick={() => setDismissed(true)}
            className="text-muted-foreground hover:text-destructive"
            title="Dismiss (Esc)"
            aria-label="Dismiss"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        <div className="max-h-[60vh] overflow-auto p-3">
          <OverlayBody item={active} />
        </div>

        {items.length > 1 && (
          <div className="flex gap-1.5 overflow-x-auto border-t border-border/60 px-3 py-2">
            {items.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setSelectedId(item.id)}
                className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border ${
                  item.id === active.id ? 'border-primary bg-primary/15 text-primary' : 'border-border text-muted-foreground hover:text-foreground'
                }`}
                title={item.title}
                aria-label={`Show ${item.title}`}
              >
                <ItemIcon type={item.type} className="h-3.5 w-3.5" />
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function ItemIcon({ type, className }: { type: CanvasItem['type']; className?: string }) {
  const Icon = TYPE_ICON[type]
  return <Icon className={className ?? 'h-3.5 w-3.5 shrink-0 text-primary'} />
}

function OverlayBody({ item }: { item: CanvasItem }) {
  if (item.type === 'image') {
    return <img src={`data:image/png;base64,${item.content}`} alt={item.title} className="w-full rounded-lg object-contain" />
  }
  if (item.type === 'link') {
    return (
      <a href={item.content} target="_blank" rel="noopener noreferrer" className="break-all text-[0.65rem] text-primary underline underline-offset-2">
        {item.content}
      </a>
    )
  }
  if (item.type === 'code') {
    return (
      <pre className="overflow-auto rounded-lg bg-card/60 p-2 text-[0.6rem] text-foreground">
        {item.language && <div className="mb-1 text-[0.5rem] uppercase text-muted-foreground">{item.language}</div>}
        <code>{item.content}</code>
      </pre>
    )
  }
  if (item.type === 'html_preview') {
    return <iframe srcDoc={item.content} sandbox="allow-scripts" title={item.title} className="h-64 w-full rounded-lg border border-border bg-white" />
  }
  // note, 3d_scene (no compact 3D viewer here -- open the full dashboard's
  // Canvas tab for the real orbit-controllable version; this is a quick
  // glance surface, not a replacement for it)
  return <p className="whitespace-pre-wrap text-[0.65rem] leading-relaxed text-muted-foreground">{item.content}</p>
}
