'use client'

import { useEffect, useRef, useState } from 'react'
import type { LogEntry } from '@/lib/nancy/types'
import { Mic, MicOff, Send, Volume2 } from 'lucide-react'
import { cn } from '@/lib/utils'

export function ConsoleBar({
  logs,
  listening,
  awake,
  supported,
  interim,
  onToggleMic,
  onSubmit,
}: {
  logs: LogEntry[]
  listening: boolean
  awake: boolean
  supported: boolean
  interim: string
  onToggleMic: () => void
  onSubmit: (text: string) => void
}) {
  const [value, setValue] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [logs])

  return (
    <div className="hud-panel mx-auto flex w-full max-w-md flex-col gap-1.5 rounded-xl p-2.5 shadow-lg">
      <div className="flex items-center justify-between">
        <h2 className="text-[0.65rem] font-medium text-foreground">Console</h2>
        <span
          className={cn(
            'flex items-center gap-1.5 text-[0.65rem]',
            awake ? 'text-primary' : listening ? 'text-foreground' : 'text-muted-foreground',
          )}
        >
          <span className={cn('h-1.5 w-1.5 rounded-full', awake ? 'bg-primary' : listening ? 'bg-foreground' : 'bg-muted-foreground')} />
          {awake ? 'Listening for a command' : listening ? 'Standby — say "Nancy"' : 'Mic off'}
        </span>
      </div>

      <div
        ref={scrollRef}
        className="h-12 overflow-y-auto rounded-lg border border-border bg-background/60 p-1.5 text-[0.68rem] leading-snug"
      >
        {logs.map((l) => (
          <div key={l.id} className="flex gap-1.5">
            <span className="shrink-0 text-muted-foreground/60">
              {new Date(l.ts).toLocaleTimeString('en-GB')}
            </span>
            <span
              className={cn(
                l.level === 'nancy' && 'text-primary',
                l.level === 'user' && 'text-foreground',
                l.level === 'ok' && 'text-primary/80',
                l.level === 'warn' && 'text-destructive',
                l.level === 'info' && 'text-muted-foreground',
              )}
            >
              {l.level === 'nancy' && 'Nancy: '}
              {l.level === 'user' && 'You: '}
              {l.text}
            </span>
          </div>
        ))}
        {interim && (
          <div className="flex gap-1.5 opacity-60">
            <span className="text-foreground">You: {interim}</span>
          </div>
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (!value.trim()) return
          onSubmit(value.trim())
          setValue('')
        }}
        className="flex items-center gap-2"
      >
        <button
          type="button"
          onClick={onToggleMic}
          disabled={!supported}
          title={supported ? 'Toggle microphone' : 'Speech recognition not supported in this browser'}
          className={cn(
            'flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border transition-colors',
            !supported && 'cursor-not-allowed opacity-40',
            listening
              ? 'border-primary bg-primary/15 text-primary'
              : 'border-border bg-secondary/40 text-foreground hover:border-primary/40',
          )}
        >
          {listening ? <Mic className="h-3.5 w-3.5" /> : <MicOff className="h-3.5 w-3.5" />}
        </button>
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Type a command…"
          className="h-7 flex-1 rounded-lg border border-border bg-background/60 px-2.5 text-[0.68rem] text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-primary/50"
        />
        <button
          type="submit"
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-border bg-secondary/40 text-primary transition-colors hover:border-primary/40"
        >
          <Send className="h-3.5 w-3.5" />
        </button>
      </form>
      {!supported && (
        <p className="flex items-center gap-1 text-[0.6rem] text-muted-foreground">
          <Volume2 className="h-2.5 w-2.5" />
          Voice input needs Chrome/Edge. Typed commands work everywhere.
        </p>
      )}
    </div>
  )
}
