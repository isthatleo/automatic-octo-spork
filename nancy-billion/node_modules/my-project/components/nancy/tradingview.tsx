'use client'

import { useEffect, useRef } from 'react'

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
