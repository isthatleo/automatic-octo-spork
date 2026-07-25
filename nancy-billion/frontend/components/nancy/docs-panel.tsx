'use client'

import React, { useEffect, useMemo, useState } from 'react'
import { cn } from '@/lib/utils'

export function DocsHelpPanel() {
  const [commands, setCommands] = useState<{ command: string; category: string; description: string; example: string }[]>([])
  const [modelMarkdown, setModelMarkdown] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    Promise.all([
      fetch('/api/docs/commands').then((r) => r.json()),
      fetch('/api/docs/model').then((r) => r.json()),
    ])
      .then(([cmdJson, modelJson]) => {
        if (cancelled) return
        if (cmdJson?.success) {
          setCommands(Array.isArray(cmdJson.data?.commands) ? cmdJson.data.commands : [])
        }
        if (modelJson?.success && typeof modelJson.data?.markdown === 'string') {
          setModelMarkdown(modelJson.data.markdown)
        }
      })
      .catch((e) => {
        if (cancelled) return
        setError(e?.message || 'Docs unavailable')
        setCommands([
          { command: '/status', category: 'help', description: 'Show status.', example: '/status' },
          { command: '/skills', category: 'agent', description: 'Open Skills.', example: '/skills' },
          { command: '/memory', category: 'memory', description: 'Open memory.', example: '/memory' },
          { command: '/agents', category: 'agent', description: 'Open Agents.', example: '/agents' },
          { command: '/terminal', category: 'system', description: 'Open Command Layer.', example: '/terminal' },
          { command: '/help', category: 'help', description: 'List slash commands.', example: '/help' },
          { command: '/new', category: 'system', description: 'New session.', example: '/new' },
        ])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const grouped = useMemo(() => {
    const map = new Map<string, typeof commands>()
    for (const c of commands) {
      const key = c.category || 'other'
      const group = map.get(key) || []
      group.push(c)
      map.set(key, group)
    }
    return map
  }, [commands])

  return (
    <div className="space-y-4">
      <section className="rounded-lg border border-border bg-card/60 p-4">
        <h2 className="font-heading text-sm font-semibold">Nancy Command Reference</h2>
        <p className="mt-1 text-xs text-muted-foreground">Slash commands, navigations, and runtime surfaces.</p>
        {loading ? (
          <p className="mt-3 text-xs text-muted-foreground">Loading docs…</p>
        ) : error ? (
          <p className="mt-3 text-xs text-destructive">Docs unavailable: {error}</p>
        ) : (
          <div className="mt-3 grid gap-2">
            {Array.from(grouped.entries()).map(([category, items]) => (
              <div key={String(category)} className="rounded-md border border-border bg-background/60 p-2">
                <p className="text-[0.65rem] font-heading uppercase tracking-wide text-muted-foreground">{String(category)}</p>
                <ul className="mt-2 space-y-1">
                  {items.map((item) => (
                    <li key={item.command} className="flex items-baseline justify-between gap-3">
                      <span className="font-mono text-xs text-foreground">{item.command}</span>
                      <span className="text-right text-[0.65rem] text-muted-foreground">{item.description}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </section>
      <section className="rounded-lg border border-border bg-card/60 p-4">
        <h2 className="font-heading text-sm font-semibold">Model Reference</h2>
        <div className={cn('mt-2 text-xs text-muted-foreground whitespace-pre-wrap font-mono')}>{modelMarkdown}</div>
      </section>
    </div>
  )
}
