'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { cn } from '@/lib/utils'
import { onDomainEvent } from '@/lib/nancy/ws-client'
import type { CanvasItem } from '@/lib/nancy/types'
import {
  Loader2, Pin, PinOff, Trash2, Plus, StickyNote, Link2, Code2, Image as ImageIcon,
  Search, Copy, Check, Pencil, Save, X, Maximize2,
} from 'lucide-react'

/* ═══════════════════════════════════════════════════════════════════════
   CANVAS — a real shared scratchpad Nancy can pin things to during a
   conversation (a note, a link, a code snippet, a screenshot), distinct
   from the chat transcript and the mission kanban. Every item is a real row
   in data/canvas.json (canvas_store.py) and every add/pin/edit/remove
   broadcasts live to every connected tab over the same WebSocket
   domain-event bridge the mission kanban already uses — no separate
   real-time layer here.
   ═══════════════════════════════════════════════════════════════════════ */

const TYPE_ICON: Record<CanvasItem['type'], typeof StickyNote> = {
  note: StickyNote, link: Link2, code: Code2, image: ImageIcon,
}

type TypeFilter = CanvasItem['type'] | 'all'

export function CanvasPanel() {
  const [items, setItems] = useState<CanvasItem[]>([])
  const [loading, setLoading] = useState(true)
  const [composerOpen, setComposerOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all')
  const [preview, setPreview] = useState<CanvasItem | null>(null)

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
  const editItem = async (item: CanvasItem, patch: { title: string; content: string; language?: string | null }) => {
    await fetch(`/api/canvas/${item.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    })
  }

  // Real client-side search/filter over the real item list -- no separate
  // search index, just the same data already on screen.
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return items.filter((i) => {
      if (typeFilter !== 'all' && i.type !== typeFilter) return false
      if (!q) return true
      return i.title.toLowerCase().includes(q) || i.content.toLowerCase().includes(q)
    })
  }, [items, query, typeFilter])

  const sorted = [...filtered].sort((a, b) => (a.pinned === b.pinned ? b.created_at - a.created_at : a.pinned ? -1 : 1))
  const counts = useMemo(() => {
    const c: Record<TypeFilter, number> = { all: items.length, note: 0, link: 0, code: 0, image: 0 }
    for (const i of items) c[i.type]++
    return c
  }, [items])

  return (
    <div className="mx-auto flex max-w-[1300px] flex-col gap-4">
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

      {/* real search + type filter over the real item list */}
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card/60 px-3 py-2">
        <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search titles and content…"
          className="h-7 min-w-[140px] flex-1 bg-transparent text-[0.6rem] text-foreground outline-none placeholder:text-muted-foreground/60"
        />
        <div className="flex flex-wrap gap-1.5">
          {(['all', 'note', 'link', 'code', 'image'] as TypeFilter[]).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTypeFilter(t)}
              className={cn(
                'rounded-full border px-2 py-0.5 text-[0.5rem] capitalize transition-colors',
                typeFilter === t ? 'border-primary bg-primary/15 text-primary' : 'border-border text-muted-foreground hover:text-foreground',
              )}
            >
              {t} {t !== 'all' && `(${counts[t]})`}
            </button>
          ))}
        </div>
      </div>

      {loading && items.length === 0 ? (
        <div className="flex items-center justify-center rounded-xl border border-border bg-card/60 py-10 text-[0.6rem] text-muted-foreground">
          <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> Loading…
        </div>
      ) : sorted.length === 0 && items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border/60 bg-card/40 px-6 py-10 text-center text-[0.6rem] text-muted-foreground">
          Nothing pinned yet — add something above, or ask Nancy to pin something for you during a conversation.
        </div>
      ) : sorted.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border/60 bg-card/40 px-6 py-10 text-center text-[0.6rem] text-muted-foreground">
          No items match {query ? `"${query}"` : 'this filter'}.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {sorted.map((item) => (
            <CanvasCard
              key={item.id}
              item={item}
              onTogglePinned={() => togglePinned(item)}
              onDelete={() => deleteItem(item)}
              onEdit={(patch) => editItem(item, patch)}
              onPreview={() => setPreview(item)}
            />
          ))}
        </div>
      )}

      {preview && preview.type === 'image' && (
        <ImagePreviewModal item={preview} onClose={() => setPreview(null)} />
      )}
    </div>
  )
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard permission denied -- silently no-op, nothing to fabricate here */
    }
  }
  return (
    <button type="button" onClick={copy} className="text-muted-foreground hover:text-primary" title="Copy" aria-label="Copy content">
      {copied ? <Check className="h-3.5 w-3.5 text-primary" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  )
}

function CanvasCard({
  item,
  onTogglePinned,
  onDelete,
  onEdit,
  onPreview,
}: {
  item: CanvasItem
  onTogglePinned: () => void
  onDelete: () => void
  onEdit: (patch: { title: string; content: string; language?: string | null }) => void
  onPreview: () => void
}) {
  const Icon = TYPE_ICON[item.type]
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(item.title)
  const [content, setContent] = useState(item.content)
  const [language, setLanguage] = useState(item.language ?? '')

  const startEdit = () => {
    setTitle(item.title); setContent(item.content); setLanguage(item.language ?? '')
    setEditing(true)
  }
  const save = () => {
    if (!title.trim() || !content.trim()) return
    onEdit({ title: title.trim(), content: content.trim(), language: item.type === 'code' ? (language.trim() || null) : undefined })
    setEditing(false)
  }

  return (
    <div className={cn(
      'flex flex-col gap-2 rounded-xl border bg-card/60 p-3',
      item.pinned ? 'border-primary/40' : 'border-border',
    )}>
      <div className="flex items-center gap-2">
        <Icon className="h-3.5 w-3.5 shrink-0 text-primary" />
        {editing ? (
          <input value={title} onChange={(e) => setTitle(e.target.value)} className="min-w-0 flex-1 rounded border border-border bg-background/60 px-1.5 py-0.5 text-[0.65rem] text-foreground outline-none focus:border-primary/60" />
        ) : (
          <span className="min-w-0 flex-1 truncate text-[0.65rem] text-foreground">{item.title}</span>
        )}
        {!editing && item.type !== 'image' && <CopyButton text={item.content} />}
        {!editing && (
          <button type="button" onClick={startEdit} className="text-muted-foreground hover:text-primary" title="Edit" aria-label={`Edit ${item.title}`}>
            <Pencil className="h-3.5 w-3.5" />
          </button>
        )}
        <button type="button" onClick={onTogglePinned} className="text-muted-foreground hover:text-primary" title={item.pinned ? 'Unpin' : 'Pin'} aria-label={item.pinned ? `Unpin ${item.title}` : `Pin ${item.title}`}>
          {item.pinned ? <Pin className="h-3.5 w-3.5 text-primary" /> : <PinOff className="h-3.5 w-3.5" />}
        </button>
        <button type="button" onClick={onDelete} className="text-muted-foreground hover:text-destructive" title="Remove" aria-label={`Remove ${item.title}`}>
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>

      {editing ? (
        <div className="flex flex-col gap-2">
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={item.type === 'code' ? 6 : 3}
            className={cn('w-full resize-none rounded border border-border bg-background/60 px-2 py-1.5 text-[0.6rem] text-foreground outline-none focus:border-primary/60', item.type === 'code' && 'font-mono')}
          />
          {item.type === 'code' && (
            <input value={language} onChange={(e) => setLanguage(e.target.value)} placeholder="language (optional)" className="w-full rounded border border-border bg-background/60 px-2 py-1 text-[0.55rem] text-foreground outline-none focus:border-primary/60" />
          )}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={save} disabled={!title.trim() || !content.trim()} className="flex items-center gap-1 rounded border border-primary bg-primary/15 px-2 py-1 text-[0.55rem] text-primary hover:bg-primary/25 disabled:cursor-not-allowed disabled:opacity-40">
              <Save className="h-3 w-3" /> Save
            </button>
            <button type="button" onClick={() => setEditing(false)} className="flex items-center gap-1 rounded border border-border px-2 py-1 text-[0.55rem] text-muted-foreground hover:text-foreground">
              <X className="h-3 w-3" /> Cancel
            </button>
          </div>
        </div>
      ) : (
        <CanvasCardBody item={item} onPreview={onPreview} />
      )}
    </div>
  )
}

function CanvasCardBody({ item, onPreview }: { item: CanvasItem; onPreview: () => void }) {
  if (item.type === 'image') {
    return (
      <button type="button" onClick={onPreview} className="group relative overflow-hidden rounded-lg">
        <img src={`data:image/png;base64,${item.content}`} alt={item.title} className="max-h-64 w-full object-contain transition-opacity group-hover:opacity-80" />
        <span className="absolute right-1.5 top-1.5 flex h-6 w-6 items-center justify-center rounded-full bg-background/80 text-muted-foreground opacity-0 backdrop-blur-sm transition-opacity group-hover:opacity-100">
          <Maximize2 className="h-3 w-3" />
        </span>
      </button>
    )
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

function ImagePreviewModal({ item, onClose }: { item: CanvasItem; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label={item.title}>
      <button type="button" aria-label="Dismiss" onClick={onClose} className="absolute inset-0 cursor-default bg-background/80 backdrop-blur-sm" />
      <div className="relative z-10 flex max-h-[90dvh] max-w-4xl flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-foreground">{item.title}</span>
          <button type="button" onClick={onClose} className="flex h-7 w-7 items-center justify-center rounded border border-border bg-card/80 text-muted-foreground hover:text-destructive">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
        <img src={`data:image/png;base64,${item.content}`} alt={item.title} className="max-h-[80dvh] rounded-lg object-contain" />
      </div>
    </div>
  )
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
