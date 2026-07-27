'use client'

import { useEffect, useMemo, useState } from 'react'
import { cn } from '@/lib/utils'
import { BookOpen, Loader2, Bot, Brain, TerminalSquare, HelpCircle, Compass, FileText, FileCode2 } from 'lucide-react'

const QUICK_REFERENCE = [
  { title: 'What Nancy actually is', body: 'A voice-first personal assistant: real STT/TTS, a multi-provider LLM fallback chain, dozens of specialized agents, Telegram remote control, and gated file access — see AI Core and Agents for live status.', isPath: false },
  { title: 'Backend source', body: 'nancy-billion/backend/main_new.py is the FastAPI entrypoint; llm.py holds the reasoning fallback chain; agents/specialized/ holds the real agent roster.', isPath: true },
  { title: 'Frontend source', body: 'nancy-billion/frontend/app/page.tsx is the shell; components/nancy/ holds every panel in this sidebar.', isPath: true },
]

const CATEGORY_META: Record<string, { label: string; icon: typeof BookOpen }> = {
  navigation: { label: 'Navigation', icon: Compass },
  agent: { label: 'Agents', icon: Bot },
  memory: { label: 'Memory', icon: Brain },
  system: { label: 'System', icon: TerminalSquare },
  help: { label: 'Help', icon: HelpCircle },
}

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
    <div className="mx-auto flex max-w-[820px] flex-col gap-4">
      <div className="flex items-center gap-2 rounded-xl border border-border bg-card/60 px-4 py-3">
        <BookOpen className="h-4 w-4 text-primary" />
        <span className="font-heading text-xs text-foreground">Nancy Command Reference</span>
        <span className="text-[0.55rem] text-muted-foreground">
          {commands.length} real commands — slash intercepts and every panel reachable by saying &ldquo;open &lt;name&gt;&rdquo;
        </span>
      </div>

      {loading ? (
        <div className="flex items-center justify-center rounded-xl border border-border bg-card/60 py-8 text-[0.6rem] text-muted-foreground">
          <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> Loading…
        </div>
      ) : error ? (
        <p className="rounded-xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-[0.6rem] text-destructive">
          Docs unavailable: {error} — showing a minimal fallback list below.
        </p>
      ) : null}

      {!loading && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {Array.from(grouped.entries()).map(([category, items]) => {
            const meta = CATEGORY_META[category]
            const Icon = meta?.icon ?? FileText
            return (
              <div key={category} className="overflow-hidden rounded-xl border border-border bg-card/60">
                <div className="flex items-center gap-2 border-b border-border/50 bg-secondary/10 px-3.5 py-2">
                  <Icon className="h-3.5 w-3.5 text-primary" />
                  <h3 className="font-heading text-[0.65rem] text-foreground">{meta?.label ?? category}</h3>
                  <span className="ml-auto text-[0.5rem] text-muted-foreground">{items.length}</span>
                </div>
                <ul className="divide-y divide-border/30">
                  {items.map((item) => (
                    <li key={item.command} className="flex items-baseline justify-between gap-3 px-3.5 py-2">
                      <span className="shrink-0 font-mono text-[0.6rem] text-primary">{item.command}</span>
                      <span className="min-w-0 text-right text-[0.55rem] leading-relaxed text-muted-foreground">{item.description}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )
          })}
        </div>
      )}

      {modelMarkdown && (
        <div className="rounded-xl border border-border bg-card/60 p-4">
          <h3 className="mb-2 flex items-center gap-2 font-heading text-[0.68rem] text-foreground">
            <Brain className="h-3.5 w-3.5 text-primary" /> Model Reference
          </h3>
          <div className={cn('whitespace-pre-wrap font-mono text-[0.55rem] leading-relaxed text-muted-foreground')}>{modelMarkdown}</div>
        </div>
      )}

      <ol className="divide-y divide-border/40 rounded-xl border border-border bg-card/60">
        {QUICK_REFERENCE.map((e, i) => (
          <li key={e.title} className="flex gap-3 px-4 py-3.5">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-border/50 font-mono text-[0.55rem] text-muted-foreground">
              {String(i + 1).padStart(2, '0')}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                {e.isPath ? <FileCode2 className="h-3 w-3 text-tertiary" /> : <BookOpen className="h-3 w-3 text-primary" />}
                <h3 className="font-heading text-[0.68rem] text-foreground">{e.title}</h3>
              </div>
              <p className={cn('mt-1 text-[0.6rem] leading-relaxed text-muted-foreground', e.isPath && 'font-mono')}>{e.body}</p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}
