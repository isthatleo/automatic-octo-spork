'use client'

import { useEffect, useState } from 'react'
import { HudPanel } from './hud-bits'
import { CandlestickChart, TrendingUp, TrendingDown, DollarSign, RefreshCw } from 'lucide-react'

interface MarketData {
  symbol: string
  name: string
  price: number
  change: number
  changePercent: number
}

/** Market Panel – shows watchlist and basic financial data. */
export function MarketPanel({
  watchlist,
  onAddSymbol,
  onRemoveSymbol,
}: {
  watchlist: MarketData[]
  onAddSymbol: (symbol: string) => void
  onRemoveSymbol: (symbol: string) => void
}) {
  const [refreshing, setRefreshing] = useState(false)

  const handleRefresh = async () => {
    setRefreshing(true)
    // In a real app, we'd fetch fresh quotes here
    await new Promise(resolve => setTimeout(resolve, 1500))
    setRefreshing(false)
  }

  const handleAdd = () => {
    // Simple popup for demo; in reality would be a proper input
    const symbol = window.prompt('Enter symbol to add (e.g. AAPL, BTCUSD):')
    if (symbol) {
      onAddSymbol(symbol.toUpperCase())
    }
  }

  return (
    <HudPanel title="Markets Watchlist" right={<span className="text-primary">{watchlist.length} SYMBOLS</span>}>
      <div className="flex flex-col gap-3">
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-2">
            <DollarSign className="h-4 w-4 text-primary" />
            <span className="font-heading text-[0.6rem] text-foreground">Markets Overview</span>
          </div>
          <button
            type="button"
            onClick={handleRefresh}
            className={`flex h-8 w-8 items-center justify-center rounded border border-border bg-secondary/30 text-muted-foreground transition-colors ${refreshing ? 'border-primary bg-primary/15' : ''} hover:border-primary/60`}
            disabled={refreshing}
          >
            {refreshing ? (
              <RefreshCw className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
          </button>
          <button
            type="button"
            onClick={handleAdd}
            className="flex h-8 w-8 items-center justify-center rounded border border-border bg-secondary/30 text-muted-foreground transition-colors hover:border-primary/60"
          >
            <span className="text-[0.5rem] uppercase tracking-widest">+</span>
          </button>
        </div>

        {watchlist.length === 0 ? (
          <p className="text-center text-[0.55rem] text-muted-foreground">
            No symbols in watchlist. Add some to get started.
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {watchlist.map((data) => (
              <div key={data.symbol} className="flex items-center justify-between p-2 rounded border border-border bg-secondary/20">
                <div className="flex items-center gap-2">
                  <span className="font-heading text-[0.6rem] text-foreground">{data.symbol}</span>
                  <p className="text-[0.5rem] text-muted-foreground">{data.name}</p>
                </div>
                <div className="flex items-center gap-2">
                  <span className={data.change >= 0 ? 'text-primary' : 'text-destructive'}>
                    {data.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                  <span className={data.change >= 0 ? 'text-primary' : 'text-destructive'}>
                    ({data.change >= 0 ? '+' : ''}{data.change.toFixed(2)} ({data.changePercent >= 0 ? '+' : ''}{data.changePercent.toFixed(2)}%)
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => onRemoveSymbol(data.symbol)}
                  className="flex h-6 w-6 items-center justify-center rounded border border-destructive/50 bg-destructive/10 text-destructive transition-colors hover:bg-destructive/20"
                >
                  <TrendingDown className="h-3 w-3 text-destructive" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </HudPanel>
  )
}