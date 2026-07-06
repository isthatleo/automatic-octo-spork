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
    <div className="hud-panel flex flex-col gap-2 rounded-md p-3">
      <div className="flex items-center justify-between">
        <h2 className="font-heading text-[0.62rem] uppercase tracking-[0.22em] text-primary hud-glow">
          Command Console
        </h2>
        <span
          className={cn(
            'flex items-center gap-1.5 text-[0.55rem] uppercase tracking-widest',
            awake ? 'text-accent' : listening ? 'text-primary' : 'text-muted-foreground',
          )}
        >
          <span
            className={cn(
              'h-1.5 w-1.5 rounded-full',
              awake
                ? 'animate-hud-pulse bg-accent'
                : listening
                  ? 'animate-hud-pulse bg-primary'
                  : 'bg-muted-foreground',
            )}
          />
          {awake ? 'Listening for command' : listening ? 'Standby — say "Nancy"' : 'Mic off'}
        </span>
      </div>

      <div
        ref={scrollRef}
        className="h-24 overflow-y-auto rounded border border-border/60 bg-background/50 p-2 text-[0.58rem] leading-relaxed"
      >
        {logs.map((l) => (
          <div key={l.id} className="flex gap-1.5">
            <span className="shrink-0 text-muted-foreground/50">
              {new Date(l.ts).toLocaleTimeString('en-GB')}
            </span>
            <span
              className={cn(
                l.level === 'nancy' && 'text-primary',
                l.level === 'user' && 'text-accent',
                l.level === 'ok' && 'text-primary/80',
                l.level === 'warn' && 'text-destructive',
                l.level === 'info' && 'text-muted-foreground',
              )}
            >
              {l.level === 'nancy' && 'NÅNCY: '}
              {l.level === 'user' && 'YOU: '}
              {l.text}
            </span>
          </div>
        ))}
        {interim && (
          <div className="flex gap-1.5 opacity-60">
            <span className="text-accent">YOU: {interim}</span>
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
            'flex h-9 w-9 shrink-0 items-center justify-center rounded border transition-colors',
            !supported && 'cursor-not-allowed opacity-40',
            listening
              ? 'border-primary bg-primary/20 text-primary'
              : 'border-border bg-secondary/40 text-foreground hover:border-primary/60',
          )}
        >
          {listening ? <Mic className="h-4 w-4" /> : <MicOff className="h-4 w-4" />}
        </button>
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Type a command — e.g. locate Reykjavik, open terminal, system status"
          className="h-9 flex-1 rounded border border-border bg-background/60 px-3 text-[0.62rem] text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-primary/60"
        />
        <button
          type="submit"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded border border-border bg-secondary/40 text-primary transition-colors hover:border-primary/60"
        >
          <Send className="h-4 w-4" />
        </button>
      </form>
      {!supported && (
        <p className="flex items-center gap-1 text-[0.52rem] text-muted-foreground">
          <Volume2 className="h-3 w-3" />
          Voice input needs Chrome/Edge. Typed commands work everywhere.
        </p>
      )}
    </div>
  )
}
