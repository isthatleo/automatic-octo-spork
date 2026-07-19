'use client'

import { useState, useEffect, useCallback } from 'react'
import { X, Play, Loader2, ChevronDown, ChevronRight, CheckCircle2, AlertCircle, Zap } from 'lucide-react'
import { runAgent, getTaskPresets, humanizeKey, proseFromResult, RESULT_META_KEYS, type TaskPreset } from '@/lib/nancy/agent-client'
import type { AgentInfo, AgentResult } from '@/lib/nancy/types'
import { cn } from '@/lib/utils'

interface AgentTaskModalProps {
  agent: AgentInfo
  onClose: () => void
}

function JsonView({ data }: { data: unknown }) {
  const [expanded, setExpanded] = useState(false)
  const str = JSON.stringify(data, null, 2)
  const lines = str.split('\n').length

  return (
    <div className="rounded border border-border bg-background/80">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-1.5 px-3 py-1.5 text-[0.55rem] text-muted-foreground hover:text-foreground"
      >
        {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        Raw JSON ({lines} lines)
      </button>
      {expanded && (
        <pre className="max-h-72 overflow-y-auto px-3 pb-3 text-[0.6rem] leading-relaxed text-primary">
          {str}
        </pre>
      )}
    </div>
  )
}

/** Recursively renders an arbitrary JSON value as readable, labelled UI instead of raw braces/quotes. */
function ValueNode({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value === null || value === undefined || value === '') {
    return <span className="italic text-muted-foreground/60">—</span>
  }
  if (typeof value === 'boolean') {
    return <span className={value ? 'text-primary' : 'text-destructive'}>{value ? 'Yes' : 'No'}</span>
  }
  if (typeof value === 'number') {
    return <span className="text-accent">{value.toLocaleString()}</span>
  }
  if (typeof value === 'string') {
    return <span className="whitespace-pre-wrap text-foreground">{value}</span>
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="italic text-muted-foreground/60">None</span>
    const allPrimitive = value.every((v) => v === null || typeof v !== 'object')
    if (allPrimitive) {
      return (
        <ul className="flex flex-col gap-1">
          {value.map((v, i) => (
            <li key={i} className="flex items-start gap-1.5 text-[0.62rem]">
              <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-primary/60" />
              <ValueNode value={v} depth={depth + 1} />
            </li>
          ))}
        </ul>
      )
    }
    return (
      <div className="flex flex-col gap-1.5">
        {value.map((v, i) => (
          <div key={i} className="rounded border border-border/40 bg-secondary/20 px-2 py-1.5">
            <ValueNode value={v} depth={depth + 1} />
          </div>
        ))}
      </div>
    )
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
    if (entries.length === 0) return <span className="italic text-muted-foreground/60">Empty</span>
    return (
      <div className={cn('flex flex-col gap-2', depth > 0 && 'border-l border-border/40 pl-3')}>
        {entries.map(([k, v]) => (
          <div key={k}>
            <span className="text-[0.55rem] uppercase tracking-wide text-muted-foreground">{humanizeKey(k)}</span>
            <div className="mt-0.5">
              <ValueNode value={v} depth={depth + 1} />
            </div>
          </div>
        ))}
      </div>
    )
  }
  return <span>{String(value)}</span>
}

const PROSE_DISPLAY_KEYS = new Set(['response', 'result', 'summary', 'message'])

/** Human-readable presentation of an agent result: prose response up top (if the
 * agent returned one), then every other field laid out as labelled sections —
 * a raw JSON dump is still available below, collapsed, for anyone who wants it. */
function ResultView({ result }: { result: AgentResult }) {
  const obj = result as unknown as Record<string, unknown>
  const prose = proseFromResult(obj)
  const rest = Object.entries(obj).filter(([k]) => !RESULT_META_KEYS.has(k) && !(prose !== null && PROSE_DISPLAY_KEYS.has(k)))

  return (
    <div className="flex flex-col gap-2.5">
      {prose && (
        <div className="whitespace-pre-wrap rounded border border-primary/30 bg-primary/5 px-3 py-2.5 text-[0.68rem] leading-relaxed text-foreground">
          {prose}
        </div>
      )}
      {rest.length > 0 && (
        <div className="flex flex-col gap-3 rounded border border-border/50 bg-background/40 px-3 py-2.5">
          {rest.map(([k, v]) => (
            <div key={k}>
              <span className="font-heading text-[0.55rem] tracking-wide text-primary/80">{humanizeKey(k)}</span>
              <div className="mt-1 text-[0.62rem]">
                <ValueNode value={v} />
              </div>
            </div>
          ))}
        </div>
      )}
      <JsonView data={result} />
    </div>
  )
}

export function AgentTaskModal({ agent, onClose }: AgentTaskModalProps) {
  const presets = getTaskPresets(agent.key)
  const [selectedPreset, setSelectedPreset] = useState<TaskPreset>(presets[0])
  const [customPayload, setCustomPayload] = useState(JSON.stringify(presets[0].payload, null, 2))
  const [payloadError, setPayloadError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<AgentResult | null>(null)
  const [elapsed, setElapsed] = useState<number | null>(null)

  // Sync payload editor when preset changes
  useEffect(() => {
    setCustomPayload(JSON.stringify(selectedPreset.payload, null, 2))
    setPayloadError(null)
    setResult(null)
  }, [selectedPreset])

  const validatePayload = useCallback((): Record<string, unknown> | null => {
    try {
      const parsed = JSON.parse(customPayload)
      setPayloadError(null)
      return parsed
    } catch (e) {
      setPayloadError(`Invalid JSON: ${(e as Error).message}`)
      return null
    }
  }, [customPayload])

  const handleRun = useCallback(async () => {
    const payload = validatePayload()
    if (!payload) return

    setRunning(true)
    setResult(null)
    const start = Date.now()

    try {
      const res = await runAgent(agent.key, selectedPreset.task_type, payload)
      setElapsed(Date.now() - start)
      setResult(res)
    } finally {
      setRunning(false)
    }
  }, [agent.key, selectedPreset.task_type, validatePayload])

  const statusColor = agent.status === 'online'
    ? 'text-primary' : agent.status === 'offline'
    ? 'text-destructive' : 'text-accent'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-sm bg-background/60"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="hud-panel relative flex w-full max-w-2xl flex-col gap-4 rounded-lg border border-primary/40 bg-background p-5 shadow-[0_0_60px_rgba(var(--hud-rgb),0.2)]"
        style={{ maxHeight: '90vh', overflowY: 'auto' }}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <Zap className="h-4 w-4 text-primary" />
              <h2 className="font-heading text-base text-primary">
                {agent.name}
              </h2>
              <span className={cn('text-[0.5rem]', statusColor)}>
                {agent.status}
              </span>
            </div>
            <p className="mt-0.5 text-[0.55rem] text-muted-foreground">{agent.domain} · {agent.description}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-border p-1 text-muted-foreground hover:border-primary/60 hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Specializations */}
        {agent.specializations.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {agent.specializations.slice(0, 8).map((s) => (
              <span key={s} className="rounded border border-border bg-secondary/30 px-1.5 py-0.5 text-[0.45rem] text-muted-foreground">
                {s}
              </span>
            ))}
            {agent.specializations.length > 8 && (
              <span className="text-[0.45rem] text-muted-foreground self-center">+{agent.specializations.length - 8} more</span>
            )}
          </div>
        )}

        {/* Task preset selector */}
        <div>
          <label className="mb-1.5 block text-[0.55rem] text-muted-foreground">
            Task Preset
          </label>
          <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
            {presets.map((preset) => (
              <button
                key={preset.task_type + preset.label}
                type="button"
                onClick={() => setSelectedPreset(preset)}
                className={cn(
                  'flex flex-col items-start rounded border p-2 text-left transition-colors',
                  selectedPreset === preset
                    ? 'border-primary bg-primary/15 text-primary'
                    : 'border-border bg-secondary/30 text-muted-foreground hover:border-primary/50 hover:text-foreground',
                )}
              >
                <span className="font-heading text-[0.6rem] tracking-wide">{preset.label}</span>
                <span className="mt-0.5 text-[0.5rem] opacity-70">{preset.description}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Payload editor */}
        <div>
          <label className="mb-1.5 block text-[0.55rem] text-muted-foreground">
            Payload JSON
          </label>
          <textarea
            value={customPayload}
            onChange={(e) => { setCustomPayload(e.target.value); setPayloadError(null) }}
            rows={6}
            spellCheck={false}
            className={cn(
              'w-full rounded border bg-background/60 px-3 py-2 font-mono text-[0.6rem] text-foreground outline-none resize-y',
              payloadError ? 'border-destructive' : 'border-border focus:border-primary/60',
            )}
          />
          {payloadError && (
            <p className="mt-1 text-[0.5rem] text-destructive">{payloadError}</p>
          )}
        </div>

        {/* Run button */}
        <button
          type="button"
          onClick={handleRun}
          disabled={running || agent.status === 'offline'}
          className={cn(
            'flex items-center justify-center gap-2 rounded border py-2.5 font-heading text-[0.65rem] transition-all',
            running || agent.status === 'offline'
              ? 'cursor-not-allowed border-border text-muted-foreground opacity-50'
              : 'border-primary bg-primary/15 text-primary hover:bg-primary/25',
          )}
        >
          {running ? (
            <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Executing…</>
          ) : (
            <><Play className="h-3.5 w-3.5" /> Execute {selectedPreset.task_type}</>
          )}
        </button>

        {/* Result */}
        {result && (
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              {result.success ? (
                <CheckCircle2 className="h-3.5 w-3.5 text-primary" />
              ) : (
                <AlertCircle className="h-3.5 w-3.5 text-destructive" />
              )}
              <span className={cn('text-[0.6rem]', result.success ? 'text-primary' : 'text-destructive')}>
                {result.success ? 'Success' : 'Failed'}
              </span>
              {elapsed !== null && (
                <span className="ml-auto text-[0.5rem] text-muted-foreground">{elapsed}ms</span>
              )}
              {result.latency_ms !== undefined && (
                <span className="text-[0.5rem] text-muted-foreground">agent: {result.latency_ms}ms</span>
              )}
            </div>
            {result.error && (
              <p className="rounded border border-destructive/30 bg-destructive/10 px-3 py-2 text-[0.6rem] text-destructive">
                {result.error}
              </p>
            )}
            <ResultView result={result} />
          </div>
        )}

        {/* Stats footer */}
        <div className="flex items-center gap-3 border-t border-border pt-2 text-[0.5rem] text-muted-foreground">
          <span>Confidence: <span className="text-primary">{(agent.confidence * 100).toFixed(0)}%</span></span>
          <span>Tasks: <span className="text-foreground">{agent.total_tasks}</span></span>
          <span>Load: <span className="text-accent">{agent.load}%</span></span>
        </div>
      </div>
    </div>
  )
}
