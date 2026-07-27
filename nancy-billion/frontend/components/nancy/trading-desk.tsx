'use client'

import { useEffect, useMemo, useState } from 'react'
import { HudPanel } from './hud-bits'
import { timeAgo } from '@/lib/nancy/time'
import { onEconomicAlert, type EconomicAlertPayload } from '@/lib/nancy/ws-client'
import { getEconomicCalendarEvents } from '@/lib/nancy/economic-calendar-client'
import {
  useTradingQuotes, useWatchedPairs, useTradingPerformance, useRiskAssessment, useTradeHistory,
} from '@/hooks/useSystemData'
import useSWR from 'swr'
import type { NewsItem } from '@/lib/nancy/types'
import { TrendingUp, TrendingDown, Radio, AlertTriangle, Newspaper, X, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

/** Real, live-polled countdown to a scheduled economic release -- ticks
 * client-side, the underlying date is the real FRED/Fed-published schedule. */
function formatCountdown(target: Date, now: Date): string {
  const ms = target.getTime() - now.getTime()
  if (ms <= 0) return 'releasing now'
  const s = Math.floor(ms / 1000)
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (d > 0) return `in ${d}d ${h}h`
  if (h > 0) return `in ${h}h ${m}m`
  return `in ${m}m ${s % 60}s`
}
function parseEventDate(date: string): Date {
  return new Date(date.replace(' ', 'T'))
}

const newsFetcher = (url: string) => fetch(url).then((r) => r.json() as Promise<{ items: NewsItem[] }>)

/* ═══════════════════════════════════════════════════════════════
   TRADING DESK — live NFP/CPI/FOMC calendar, real quotes, real
   performance/risk, and a live finance news feed, all in one view
   meant to stay open while actually trading.
   ═══════════════════════════════════════════════════════════════ */
export function TradingDeskPanel() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  // Real cached NFP/CPI/FOMC state (FRED-backed, see economic_calendar.py).
  const { data: calendar } = useSWR('trading-desk-economic-calendar', () => getEconomicCalendarEvents(), {
    refreshInterval: 20000,
    revalidateOnFocus: false,
  })
  const events = calendar?.events ?? []
  const upcoming = useMemo(
    () => events.filter((e) => e.actual === null).sort((a, b) => parseEventDate(a.date).getTime() - parseEventDate(b.date).getTime()),
    [events],
  )
  const recent = useMemo(
    () => events.filter((e) => e.actual !== null).sort((a, b) => parseEventDate(b.date).getTime() - parseEventDate(a.date).getTime()),
    [events],
  )

  // Live alerts received *while this page is open*, on top of the cached
  // history above -- a real running feed, not a fabricated ticker.
  const [liveAlerts, setLiveAlerts] = useState<EconomicAlertPayload[]>([])
  useEffect(() => onEconomicAlert((payload) => setLiveAlerts((prev) => [payload, ...prev].slice(0, 5))), [])

  const { data: watched } = useWatchedPairs()
  const pairs = watched?.relevant_pairs ?? []
  const { data: quotesData, loading: quotesLoading } = useTradingQuotes(pairs.length > 0 ? pairs : undefined)
  const quotes = quotesData?.quotes ?? []

  const { data: perf } = useTradingPerformance()
  const { data: risk } = useRiskAssessment()
  const { data: trades, loading: tradesLoading } = useTradeHistory(8)

  const { data: newsData, isLoading: newsLoading } = useSWR('/api/news?type=articles&category=finance', newsFetcher, {
    refreshInterval: 120000,
    revalidateOnFocus: false,
  })
  const newsItems = newsData?.items ?? []

  return (
    <div className="mx-auto flex max-w-[1680px] flex-col gap-4">
      {liveAlerts.length > 0 && (
        <div className="flex flex-col gap-1.5">
          {liveAlerts.map((a, i) => (
            <div key={`${a.event_name}-${i}`} className="flex items-center gap-2 rounded-xl border border-gold/40 bg-gold/10 px-4 py-2.5 text-[0.65rem]">
              <Radio className="h-3.5 w-3.5 shrink-0 animate-pulse text-gold" />
              <span className="text-foreground">{a.text}</span>
              <button type="button" onClick={() => setLiveAlerts((prev) => prev.filter((_, idx) => idx !== i))} className="ml-auto text-muted-foreground hover:text-foreground">
                <X className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Live quotes ticker -- real forex/metal prices for whatever the
          user has actually told Nancy they trade (or real trade-history
          pairs), never a hardcoded default list. */}
      <div className="flex items-center gap-3 overflow-x-auto rounded-xl border border-border bg-card/60 px-4 py-3">
        <span className="flex shrink-0 items-center gap-1.5 text-[0.55rem] tracking-[0.2em] text-primary">
          <Radio className="h-3 w-3 animate-pulse" /> LIVE
        </span>
        {quotesLoading && quotes.length === 0 && <span className="text-[0.6rem] text-muted-foreground">Loading quotes…</span>}
        {!quotesLoading && quotes.length === 0 && (
          <span className="text-[0.6rem] text-muted-foreground">
            No pairs tracked yet — tell Nancy which pairs you trade (e.g. &ldquo;I trade EUR/USD and XAU/USD&rdquo;).
          </span>
        )}
        {quotes.map((q) => (
          <div key={q.pair} className="flex shrink-0 items-center gap-2 rounded border border-border/60 bg-secondary/20 px-2.5 py-1.5 text-[0.6rem]">
            <span className="font-heading text-foreground">{q.pair}</span>
            <span className="text-primary">{q.price.toFixed(q.price < 10 ? 4 : 2)}</span>
            <span className={cn('flex items-center gap-0.5', q.change_24h >= 0 ? 'text-emerald-400' : 'text-rose-400')}>
              {q.change_24h >= 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
              {q.change_24h >= 0 ? '+' : ''}{q.change_24h.toFixed(2)}%
            </span>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <HudPanel title="Economic Calendar · NFP / CPI / FOMC" accent="amber">
          {!calendar?.configured ? (
            <p className="py-4 text-center text-[0.6rem] text-muted-foreground">
              Economic calendar disabled — set FRED_API_KEY in the backend .env to track live NFP/CPI/FOMC releases.
            </p>
          ) : (
            <div className="flex flex-col gap-3">
              <div>
                <div className="mb-1.5 text-[0.5rem] tracking-[0.2em] text-muted-foreground">UPCOMING</div>
                <div className="flex flex-col gap-1.5">
                  {upcoming.length === 0 && <p className="text-[0.6rem] text-muted-foreground">Nothing scheduled in the tracked window.</p>}
                  {upcoming.map((e) => (
                    <div key={`up-${e.event_name}-${e.date}`} className="flex items-center justify-between rounded border border-primary/30 bg-primary/5 px-2.5 py-1.5 text-[0.6rem]">
                      <span className="text-primary">{e.event_name}</span>
                      <span className="text-muted-foreground">{formatCountdown(parseEventDate(e.date), now)}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <div className="mb-1.5 text-[0.5rem] tracking-[0.2em] text-muted-foreground">RECENT PRINTS</div>
                <div className="flex flex-col gap-1.5">
                  {recent.length === 0 && <p className="text-[0.6rem] text-muted-foreground">No prints yet in the tracked window.</p>}
                  {recent.map((e) => {
                    const delta = e.actual !== null && e.previous !== null ? e.actual - e.previous : null
                    return (
                      <div key={`re-${e.event_name}-${e.date}`} className="flex items-center justify-between rounded border border-border/50 bg-secondary/20 px-2.5 py-1.5 text-[0.6rem]">
                        <span className="text-foreground">{e.event_name}</span>
                        <span className="text-muted-foreground">
                          {e.actual}{e.unit} {e.previous != null && `(prev ${e.previous}${e.unit})`}
                        </span>
                        {delta !== null && (
                          <span className={delta > 0 ? 'text-emerald-400' : delta < 0 ? 'text-rose-400' : 'text-muted-foreground'}>
                            {delta > 0 ? '▲' : delta < 0 ? '▼' : '='}{Math.abs(delta)}{e.unit}
                          </span>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          )}
        </HudPanel>

        <HudPanel title="Performance & Risk" accent="violet">
          <div className="flex flex-col gap-3">
            {perf?.metrics ? (
              <div className="grid grid-cols-2 gap-2 text-center">
                {[
                  { label: 'Total trades', v: perf.metrics.total_trades ?? 0 },
                  { label: 'Win rate', v: perf.metrics.win_rate != null ? `${(perf.metrics.win_rate * 100).toFixed(0)}%` : '—' },
                  { label: 'Net P/L', v: perf.metrics.total_profit_loss != null ? perf.metrics.total_profit_loss.toFixed(1) : '—' },
                  { label: 'Avg P/L', v: perf.metrics.average_profit_loss != null ? perf.metrics.average_profit_loss.toFixed(2) : '—' },
                ].map((s) => (
                  <div key={s.label} className="rounded border border-border/60 bg-secondary/20 py-2">
                    <div className="font-display text-sm text-foreground">{s.v}</div>
                    <div className="text-[0.45rem] text-muted-foreground">{s.label}</div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-[0.6rem] text-muted-foreground">No closed trades recorded yet.</p>
            )}
            {risk?.risk_assessment && (
              <div className="flex items-center gap-2 rounded border border-border/50 bg-secondary/20 px-2.5 py-2 text-[0.6rem]">
                <AlertTriangle className={cn('h-3.5 w-3.5', risk.risk_assessment.risk_level === 'high' || risk.risk_assessment.risk_level === 'extreme' ? 'text-destructive' : 'text-primary')} />
                <span className="text-foreground">Risk level: {String(risk.risk_assessment.risk_level ?? 'unknown')}</span>
              </div>
            )}
          </div>
        </HudPanel>
      </div>

      <HudPanel title="Recent Trades">
        {tradesLoading && trades.length === 0 ? (
          <div className="flex items-center justify-center py-4 text-[0.6rem] text-muted-foreground"><Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> Loading…</div>
        ) : trades.length === 0 ? (
          <p className="py-2 text-center text-[0.6rem] text-muted-foreground">No trades recorded yet.</p>
        ) : (
          <div className="flex flex-col divide-y divide-border/40">
            {trades.map((t: Record<string, unknown>, i: number) => {
              const pl = typeof t.profit_loss === 'number' ? t.profit_loss : null
              return (
                <div key={i} className="flex items-center justify-between py-1.5 text-[0.6rem]">
                  <span className="text-foreground">{String(t.pair)}</span>
                  <span className="text-muted-foreground">{String(t.direction)} @ {String(t.entry_price)}</span>
                  <span className={pl == null ? 'text-muted-foreground' : pl >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                    {pl == null ? String(t.status) : `${pl >= 0 ? '+' : ''}${pl.toFixed(1)}`}
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </HudPanel>

      {/* Live finance news -- the real RSS/Google-News pipeline
          (see app/api/news/route.ts), scoped to finance, refreshed every
          2 minutes while this page is open. */}
      <div className="rounded-xl border border-border bg-card/60 p-4">
        <div className="mb-3 flex items-center gap-2">
          <Newspaper className="h-4 w-4 text-primary" />
          <h2 className="font-heading text-[0.72rem] font-medium text-foreground/90">Market News</h2>
          <span className="ml-auto text-[0.55rem] text-primary">Live</span>
        </div>
        {newsLoading && newsItems.length === 0 ? (
          <div className="flex items-center justify-center py-4 text-[0.6rem] text-muted-foreground"><Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> Aggregating…</div>
        ) : (
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {newsItems.slice(0, 9).map((it) => (
              <a
                key={it.id}
                href={it.link}
                target="_blank"
                rel="noreferrer"
                className="flex flex-col gap-1 rounded border border-border/50 bg-secondary/10 px-2.5 py-2 text-left transition-colors hover:border-primary/50"
              >
                <div className="flex items-center gap-2 text-[0.48rem]">
                  <span className="text-primary">{it.source}</span>
                  <span className="text-muted-foreground">{timeAgo(it.published)}</span>
                </div>
                <p className="line-clamp-2 text-[0.62rem] leading-snug text-foreground">{it.title}</p>
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
