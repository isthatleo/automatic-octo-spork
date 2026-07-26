'use client'

import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'

/**
 * Generic TradingView embed. Injects the given widget script with a JSON config
 * into a fresh container and re-mounts whenever the config changes (e.g. a new
 * symbol). No API key required.
 */
export function TradingViewWidget({
  scriptSrc,
  config,
  className,
}: {
  scriptSrc: string
  config: Record<string, unknown>
  className?: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  const json = JSON.stringify(config)

  useEffect(() => {
    const host = ref.current
    if (!host) return
    host.innerHTML = ''

    const container = document.createElement('div')
    container.className = 'tradingview-widget-container'
    container.style.height = '100%'
    container.style.width = '100%'

    const widget = document.createElement('div')
    widget.className = 'tradingview-widget-container__widget'
    widget.style.height = '100%'
    widget.style.width = '100%'
    container.appendChild(widget)

    const script = document.createElement('script')
    script.src = scriptSrc
    script.type = 'text/javascript'
    script.async = true
    script.innerHTML = json
    container.appendChild(script)

    host.appendChild(container)

    return () => {
      host.innerHTML = ''
    }
  }, [scriptSrc, json])

  return <div ref={ref} className={className} style={{ height: '100%', width: '100%' }} />
}

/**
 * On-demand TradingView chart window -- only ever rendered when explicitly
 * requested ("open the chart for gold"), never shown proactively alongside
 * a regular price mention. Real Advanced Chart widget, no API key, dark
 * theme to match the rest of the app.
 */
export function TradingViewDialog({ symbol, onClose }: { symbol: string | null; onClose: () => void }) {
  if (!symbol) return null
  return (
    <div className="fixed inset-0 z-[95] flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label={`TradingView chart for ${symbol}`}>
      <button type="button" aria-label="Dismiss" onClick={onClose} className="absolute inset-0 cursor-default bg-background/80 backdrop-blur-md" />
      <div className="relative z-10 flex h-[85vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
          <span className="font-heading text-xs text-foreground">{symbol}</span>
          <button type="button" onClick={onClose} className="text-muted-foreground hover:text-foreground" aria-label="Close chart">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1">
          <TradingViewWidget
            scriptSrc="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js"
            config={{
              autosize: true,
              symbol,
              interval: 'D',
              timezone: 'Etc/UTC',
              theme: 'dark',
              style: '1',
              locale: 'en',
              enable_publishing: false,
              allow_symbol_change: true,
              hide_top_toolbar: false,
              hide_legend: false,
            }}
          />
        </div>
      </div>
    </div>
  )
}
