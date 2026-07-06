'use client'

import React, { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'
import {
  Activity,
  Brain,
  TrendingUp,
  Clock,
  AlertTriangle,
  CheckCircle2,
  Zap,
  Navigation2,
  MessageSquare,
  Database,
  Globe
} from 'lucide-react'

interface DashboardMetrics {
  systemStatus: 'online' | 'operational' | 'optimizing'
  responseTime: number
  memoryUsage: number
  contextItems: number
  activeThreads: number
  lastUpdate: string
}

interface MarketData {
  pair: string
  price: number
  change: number
  trend: 'up' | 'down' | 'neutral'
}

export function JarvisLikeDashboard() {
  const [metrics, setMetrics] = useState<DashboardMetrics>({
    systemStatus: 'online',
    responseTime: 145,
    memoryUsage: 68,
    contextItems: 24,
    activeThreads: 5,
    lastUpdate: new Date().toLocaleTimeString()
  })

  const [marketData, setMarketData] = useState<MarketData[]>([
    { pair: 'EUR/USD', price: 1.0872, change: 0.25, trend: 'up' },
    { pair: 'GBP/USD', price: 1.2745, change: -0.15, trend: 'down' },
    { pair: 'USD/JPY', price: 149.5, change: 0.5, trend: 'up' }
  ])

  const [time, setTime] = useState(new Date())

  // Update time every second
  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  // Update metrics
  useEffect(() => {
    const interval = setInterval(() => {
      setMetrics(prev => ({
        ...prev,
        responseTime: Math.floor(Math.random() * 200) + 50,
        memoryUsage: Math.floor(Math.random() * 30) + 50,
        contextItems: Math.floor(Math.random() * 10) + 20,
        lastUpdate: new Date().toLocaleTimeString()
      }))
    }, 3000)

    return () => clearInterval(interval)
  }, [])

  return (
    <div className="min-h-screen w-full bg-gradient-to-br from-slate-950 via-blue-950 to-slate-900 p-4 md:p-8 overflow-hidden">
      {/* Animated background */}
      <div className="absolute inset-0 -z-10 opacity-30">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_50%,rgba(0,200,255,0.1),transparent_50%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_80%_80%,rgba(100,200,255,0.1),transparent_50%)]" />
      </div>

      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-cyan-300 to-blue-400">
              NANCY INTELLIGENCE CENTER
            </h1>
            <p className="text-cyan-400/60 mt-2 text-sm font-mono">
              Status: {metrics.systemStatus.toUpperCase()} | Last Updated: {metrics.lastUpdate}
            </p>
          </div>
          <div className="text-right">
            <div className="text-4xl font-mono font-bold text-cyan-300">
              {time.toLocaleTimeString()}
            </div>
            <div className="text-cyan-400/60 text-sm">
              {time.toLocaleDateString()}
            </div>
          </div>
        </div>

        {/* Status bar */}
        <div className="h-1 bg-gradient-to-r from-cyan-500 via-blue-500 to-purple-500 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-green-400 to-cyan-400 transition-all duration-300"
            style={{ width: `${metrics.responseTime}%` }}
          />
        </div>
      </div>

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 mb-8">
        {/* System Status Card */}
        <StatusCard
          icon={Activity}
          label="System Status"
          value={metrics.systemStatus.toUpperCase()}
          color="cyan"
        />

        {/* Response Time */}
        <StatusCard
          icon={Zap}
          label="Response Time"
          value={`${metrics.responseTime}ms`}
          color="blue"
        />

        {/* Memory Usage */}
        <StatusCard
          icon={Database}
          label="Memory Usage"
          value={`${metrics.memoryUsage}%`}
          color="purple"
        />

        {/* Context Items */}
        <StatusCard
          icon={Brain}
          label="Context Items"
          value={`${metrics.contextItems}`}
          color="green"
        />
      </div>

      {/* Main content grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-8">
        {/* Market Data Panel */}
        <div className="lg:col-span-2 border border-cyan-500/20 rounded-lg p-6 bg-gradient-to-br from-cyan-950/30 to-blue-950/30 backdrop-blur-sm">
          <h2 className="text-xl font-bold text-cyan-300 mb-6 flex items-center gap-2">
            <TrendingUp className="w-5 h-5" />
            Market Intelligence
          </h2>

          <div className="space-y-4">
            {marketData.map((market, i) => (
              <MarketTicker key={i} market={market} />
            ))}
          </div>
        </div>

        {/* Alerts Panel */}
        <div className="border border-orange-500/20 rounded-lg p-6 bg-gradient-to-br from-orange-950/30 to-red-950/30 backdrop-blur-sm">
          <h2 className="text-xl font-bold text-orange-300 mb-6 flex items-center gap-2">
            <AlertTriangle className="w-5 h-5" />
            Active Alerts
          </h2>

          <div className="space-y-3">
            <AlertItem
              severity="info"
              message="EUR/USD approaching watched level 1.0850"
            />
            <AlertItem
              severity="success"
              message="Docker build completed successfully"
            />
            <AlertItem
              severity="warning"
              message="High market volatility detected"
            />
            <AlertItem
              severity="info"
              message="Roxan deployment in progress"
            />
          </div>
        </div>
      </div>

      {/* Bottom panels */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Recent Activity */}
        <div className="border border-blue-500/20 rounded-lg p-6 bg-gradient-to-br from-blue-950/30 to-slate-950/30 backdrop-blur-sm">
          <h2 className="text-lg font-bold text-blue-300 mb-4 flex items-center gap-2">
            <MessageSquare className="w-5 h-5" />
            Recent Activity
          </h2>

          <div className="space-y-3 text-sm">
            <ActivityLine time="14:32" message="Chat: Analyzed EUR/USD momentum" />
            <ActivityLine time="14:15" message="Memory: Added project context" />
            <ActivityLine time="14:08" message="Trading: Recorded new position" />
            <ActivityLine time="13:52" message="System: Context rebuilt" />
          </div>
        </div>

        {/* AI Status */}
        <div className="border border-purple-500/20 rounded-lg p-6 bg-gradient-to-br from-purple-950/30 to-slate-950/30 backdrop-blur-sm">
          <h2 className="text-lg font-bold text-purple-300 mb-4 flex items-center gap-2">
            <Brain className="w-5 h-5" />
            AI Status
          </h2>

          <div className="space-y-4">
            <ProgressBar label="Intelligence" value={92} color="cyan" />
            <ProgressBar label="Context Awareness" value={88} color="blue" />
            <ProgressBar label="Memory Efficiency" value={75} color="purple" />
            <ProgressBar label="System Load" value={45} color="green" />
          </div>
        </div>
      </div>

      {/* Recon/Map Section */}
      <div className="mt-8 border border-green-500/20 rounded-lg p-6 bg-gradient-to-br from-green-950/30 to-slate-950/30 backdrop-blur-sm">
        <h2 className="text-lg font-bold text-green-300 mb-4 flex items-center gap-2">
          <Navigation2 className="w-5 h-5" />
          Reconnaissance & Navigation
        </h2>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <ReconCard title="Global View" icon="🌍" color="blue" />
          <ReconCard title="Market Analysis" icon="📊" color="cyan" />
          <ReconCard title="Trade Routes" icon="🛤️" color="green" />
        </div>
      </div>
    </div>
  )
}

function StatusCard({
  icon: Icon,
  label,
  value,
  color
}: {
  icon: any
  label: string
  value: string
  color: 'cyan' | 'blue' | 'purple' | 'green'
}) {
  const borderColor = {
    cyan: 'border-cyan-500/20',
    blue: 'border-blue-500/20',
    purple: 'border-purple-500/20',
    green: 'border-green-500/20'
  }[color]

  const bgColor = {
    cyan: 'from-cyan-950/30 to-blue-950/30',
    blue: 'from-blue-950/30 to-slate-950/30',
    purple: 'from-purple-950/30 to-slate-950/30',
    green: 'from-green-950/30 to-slate-950/30'
  }[color]

  const textColor = {
    cyan: 'text-cyan-300',
    blue: 'text-blue-300',
    purple: 'text-purple-300',
    green: 'text-green-300'
  }[color]

  const valueColor = {
    cyan: 'text-cyan-400',
    blue: 'text-blue-400',
    purple: 'text-purple-400',
    green: 'text-green-400'
  }[color]

  return (
    <div
      className={`border ${borderColor} rounded-lg p-4 bg-gradient-to-br ${bgColor} backdrop-blur-sm`}
    >
      <div className="flex items-center justify-between mb-3">
        <Icon className={cn('w-5 h-5', textColor)} />
        <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
      </div>
      <p className={cn('text-sm font-mono', textColor)}>{label}</p>
      <p className={cn('text-2xl font-bold mt-2', valueColor)}>{value}</p>
    </div>
  )
}

function MarketTicker({ market }: { market: MarketData }) {
  const isUp = market.trend === 'up'
  const arrow = isUp ? '▲' : '▼'
  const color = isUp ? 'text-green-400' : 'text-red-400'

  return (
    <div className="flex items-center justify-between p-3 rounded-lg border border-cyan-500/10 bg-cyan-950/20 hover:bg-cyan-950/40 transition-colors">
      <div>
        <p className="font-mono font-bold text-cyan-300">{market.pair}</p>
        <p className="text-sm text-cyan-400/60">{market.price.toFixed(4)}</p>
      </div>
      <div className={cn('text-right', color)}>
        <p className="font-bold flex items-center justify-end gap-1">
          {arrow} {Math.abs(market.change).toFixed(2)}%
        </p>
      </div>
    </div>
  )
}

function AlertItem({ severity, message }: { severity: 'info' | 'success' | 'warning'; message: string }) {
  const colors = {
    info: 'text-blue-300 border-blue-500/30 bg-blue-950/20',
    success: 'text-green-300 border-green-500/30 bg-green-950/20',
    warning: 'text-yellow-300 border-yellow-500/30 bg-yellow-950/20'
  }

  const icons = {
    info: Activity,
    success: CheckCircle2,
    warning: AlertTriangle
  }

  const Icon = icons[severity]

  return (
    <div className={cn('border rounded-lg p-3 flex items-start gap-3', colors[severity])}>
      <Icon className="w-4 h-4 mt-1 flex-shrink-0" />
      <p className="text-sm">{message}</p>
    </div>
  )
}

function ActivityLine({ time, message }: { time: string; message: string }) {
  return (
    <div className="flex gap-3 text-gray-400">
      <span className="font-mono text-blue-400 flex-shrink-0 w-12">{time}</span>
      <span className="text-sm">{message}</span>
    </div>
  )
}

function ProgressBar({ label, value, color }: { label: string; value: number; color: string }) {
  const colorClass = {
    cyan: 'bg-gradient-to-r from-cyan-500 to-blue-500',
    blue: 'bg-gradient-to-r from-blue-500 to-purple-500',
    purple: 'bg-gradient-to-r from-purple-500 to-pink-500',
    green: 'bg-gradient-to-r from-green-500 to-emerald-500'
  }[color]

  return (
    <div>
      <div className="flex justify-between items-center mb-2">
        <p className="text-sm text-gray-300">{label}</p>
        <p className="text-sm font-mono text-gray-400">{value}%</p>
      </div>
      <div className="h-1 bg-gray-800 rounded-full overflow-hidden">
        <div
          className={cn('h-full transition-all duration-300', colorClass)}
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  )
}

function ReconCard({ title, icon, color }: { title: string; icon: string; color: string }) {
  const borderColor = {
    cyan: 'border-cyan-500/20 hover:border-cyan-500/50',
    blue: 'border-blue-500/20 hover:border-blue-500/50',
    green: 'border-green-500/20 hover:border-green-500/50'
  }[color]

  const bgColor = {
    cyan: 'hover:bg-cyan-950/20',
    blue: 'hover:bg-blue-950/20',
    green: 'hover:bg-green-950/20'
  }[color]

  return (
    <div
      className={cn(
        'border rounded-lg p-6 text-center cursor-pointer transition-all',
        borderColor,
        bgColor
      )}
    >
      <div className="text-4xl mb-3">{icon}</div>
      <p className="font-semibold text-gray-300">{title}</p>
    </div>
  )
}

