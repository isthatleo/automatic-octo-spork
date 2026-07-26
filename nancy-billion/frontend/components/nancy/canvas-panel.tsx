'use client'

import { useCallback, useEffect, useState } from 'react'
import { cn } from '@/lib/utils'
import { onDomainEvent } from '@/lib/nancy/ws-client'
import type { CanvasItem } from '@/lib/nancy/types'
import { Loader2, Pin, PinOff, Trash2, Plus, StickyNote, Link2, Code2, Image as ImageIcon } from 'lucide-react'

/* ═══════════════════════════════════════════════════════════════════════
   CANVAS — a real shared scratchpad Nancy can pin things to during a
   conversation (a note, a link, a code snippet, a screenshot), distinct
   from the chat transcript and the mission kanban. Every item is a real row
   in data/canvas.json (canvas_store.py) and every add/pin/remove broadcasts
   live to every connected tab over the same WebSocket domain-event bridge
   the mission kanban already uses — no separate real-time layer here.
   ═══════════════════════════════════════════════════════════════════════ */

const TYPE_ICON: Record<CanvasItem['type'], typeof StickyNote> = {
  note: StickyNote, link: Link2, code: Code2, image: ImageIcon,
}

export function CanvasPanel() {
  const [items, setItems] = useState<CanvasItem[]>([])
  const [loading, setLoading] = useState(true)
  const [composerOpen, setComposerOpen] = useState(false)

  const fetchItems = useCallback(async () => {
    try {
      const res = await fetch('/api/canvas', { cache: 'no-store' })
      const json = await res.json()
      if (json.success) setItems(json.items)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchItems() }, [fetchItems])

  useEffect(() => onDomainEvent((event) => {
    if (event.type === 'CANVAS_ITEM_ADDED' && event.item) {
      setItems((prev) => [event.item as CanvasItem, ...prev.filter((i) => i.id !== event.item!.id)])
    } else if (event.type === 'CANVAS_ITEM_UPDATED' && event.item) {
      setItems((prev) => prev.map((i) => (i.id === event.item!.id ? (event.item as CanvasItem) : i)))
    } else if (event.type === 'CANVAS_ITEM_REMOVED' && event.item_id) {
      setItems((prev) => prev.filter((i) => i.id !== event.item_id))
    }
  }), [])

  const togglePinned = async (item: CanvasItem) => {
    await fetch(`/api/canvas/${item.id}?pinned=${!item.pinned}`, { method: 'PATCH' })
  }
  const deleteItem = async (item: CanvasItem) => {
    await fetch(`/api/canvas/${item.id}`, { method: 'DELETE' })
  }

  const sorted = [...items].sort((a, b) => (a.pinned === b.pinned ? b.created_at - a.created_at : a.pinned ? -1 : 1))

  return (
    <div className="mx-auto flex max-w-[1100px] flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card/60 px-4 py-3">
        <div className="flex items-center gap-2">
          <StickyNote className="h-4 w-4 text-primary" />
          <span className="font-heading text-xs text-foreground">Canvas</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[0.55rem] text-muted-foreground">
            {items.length} item{items.length !== 1 ? 's' : ''} · real-time, shared across every open tab
          </span>
          <button
            type="button"
            onClick={() => setComposerOpen((v) => !v)}
            className="flex items-center gap-1.5 rounded-lg border border-primary/50 bg-primary/10 px-2.5 py-1 text-[0.6rem] text-primary transition-colors hover:bg-primary/20"
          >
            <Plus className="h-3 w-3" /> Add
          </button>
        </div>
      </div>

      {composerOpen && <CanvasComposer onDone={() => setComposerOpen(false)} />}

      {loading && items.length === 0 ? (
        <div className="flex items-center justify-center rounded-xl border border-border bg-card/60 py-10 text-[0.6rem] text-muted-foreground">
          <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> Loading…
        </div>
      ) : sorted.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border/60 bg-card/40 px-6 py-10 text-center text-[0.6rem] text-muted-foreground">
          Nothing pinned yet — add something above, or ask Nancy to pin something for you during a conversation.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {sorted.map((item) => (
            <CanvasCard key={item.id} item={item} onTogglePinned={() => togglePinned(item)} onDelete={() => deleteItem(item)} />
          ))}
        </div>
      )}
    </div>
  )
}

function CanvasCard({ item, onTogglePinned, onDelete }: { item: CanvasItem; onTogglePinned: () => void; onDelete: () => void }) {
  const Icon = TYPE_ICON[item.type]
  return (
    <div className={cn(
      'flex flex-col gap-2 rounded-xl border bg-card/60 p-3',
      item.pinned ? 'border-primary/40' : 'border-border',
    )}>
      <div className="flex items-center gap-2">
        <Icon className="h-3.5 w-3.5 shrink-0 text-primary" />
        <span className="min-w-0 flex-1 truncate text-[0.65rem] text-foreground">{item.title}</span>
        <button type="button" onClick={onTogglePinned} className="text-muted-foreground hover:text-primary" title={item.pinned ? 'Unpin' : 'Pin'} aria-label={item.pinned ? `Unpin ${item.title}` : `Pin ${item.title}`}>
          {item.pinned ? <Pin className="h-3.5 w-3.5 text-primary" /> : <PinOff className="h-3.5 w-3.5" />}
        </button>
        <button type="button" onClick={onDelete} className="text-muted-foreground hover:text-destructive" title="Remove" aria-label={`Remove ${item.title}`}>
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
      <CanvasCardBody item={item} />
    </div>
  )
}

function CanvasCardBody({ item }: { item: CanvasItem }) {
  if (item.type === 'image') {
    return <img src={`data:image/png;base64,${item.content}`} alt={item.title} className="max-h-64 w-full rounded-lg object-contain" />
  }
  if (item.type === 'link') {
    return (
      <a href={item.content} target="_blank" rel="noopener noreferrer" className="truncate text-[0.6rem] text-primary underline underline-offset-2">
        {item.content}
      </a>
    )
  }
  if (item.type === 'code') {
    return (
      <pre className="max-h-56 overflow-auto rounded-lg bg-background/60 p-2 text-[0.58rem] text-foreground">
        {item.language && <div className="mb-1 text-[0.5rem] uppercase text-muted-foreground">{item.language}</div>}
        <code>{item.content}</code>
      </pre>
    )
  }
  return <p className="whitespace-pre-wrap text-[0.62rem] leading-relaxed text-muted-foreground">{item.content}</p>
}

function CanvasComposer({ onDone }: { onDone: () => void }) {
  const [type, setType] = useState<CanvasItem['type']>('note')
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [language, setLanguage] = useState('')
  const [saving, setSaving] = useState(false)

  const submit = async () => {
    if (!title.trim() || !content.trim()) return
    setSaving(true)
    try {
      const res = await fetch('/api/canvas', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type, title: title.trim(), content: content.trim(), language: language.trim() || null }),
      })
      const json = await res.json()
      if (json.success) { setTitle(''); setContent(''); setLanguage(''); onDone() }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="rounded-xl border border-border bg-card/60 p-3">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-[110px_1fr]">
        <select value={type} onChange={(e) => setType(e.target.value as CanvasItem['type'])} className="rounded border border-border bg-background/60 px-2 py-1.5 text-[0.6rem] text-foreground outline-none focus:border-primary/60">
          <option value="note">Note</option>
          <option value="link">Link</option>
          <option value="code">Code</option>
        </select>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title" className="rounded border border-border bg-background/60 px-2 py-1.5 text-[0.6rem] text-foreground outline-none focus:border-primary/60" />
      </div>
      {type === 'code' ? (
        <textarea value={content} onChange={(e) => setContent(e.target.value)} placeholder="Code…" rows={4} className="mt-2 w-full resize-none rounded border border-border bg-background/60 px-2 py-1.5 font-mono text-[0.6rem] text-foreground outline-none focus:border-primary/60" />
      ) : type === 'link' ? (
        <input value={content} onChange={(e) => setContent(e.target.value)} placeholder="https://…" className="mt-2 w-full rounded border border-border bg-background/60 px-2 py-1.5 text-[0.6rem] text-foreground outline-none focus:border-primary/60" />
      ) : (
        <textarea value={content} onChange={(e) => setContent(e.target.value)} placeholder="Note text…" rows={3} className="mt-2 w-full resize-none rounded border border-border bg-background/60 px-2 py-1.5 text-[0.6rem] text-foreground outline-none focus:border-primary/60" />
      )}
      {type === 'code' && (
        <input value={language} onChange={(e) => setLanguage(e.target.value)} placeholder="language (optional, e.g. python)" className="mt-2 w-full rounded border border-border bg-background/60 px-2 py-1.5 text-[0.6rem] text-foreground outline-none focus:border-primary/60" />
      )}
      <div className="mt-2 flex justify-end">
        <button type="button" onClick={submit} disabled={saving || !title.trim() || !content.trim()} className="flex items-center gap-1.5 rounded-lg border border-primary bg-primary/15 px-3 py-1.5 text-[0.6rem] text-primary transition-colors hover:bg-primary/25 disabled:cursor-not-allowed disabled:opacity-40">
          {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />} Pin to canvas
        </button>
      </div>
    </div>
  )
}
