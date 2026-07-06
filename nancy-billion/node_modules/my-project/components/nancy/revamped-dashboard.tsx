'use client'

import React, { useState, useEffect } from 'react'
import { cn } from '@/lib/utils'
import {
  TrendingUp,
  AlertCircle,
  CheckCircle2,
  Clock,
  Activity,
  Brain,
  PieChart,
  Zap,
  Target,
  DollarSign
} from 'lucide-react'
import { EnhancedNancyOrb } from './enhanced-orb-final'
import {
  useMemorySummary,
  useProjects,
  useTradingPerformance,
  useTradeHistory,
  useRiskAssessment,
  useGreeting
} from '@/hooks/useSystemData'

export function RevampedDashboard() {
  const [orbState, setOrbState] = useState<'idle' | 'listening' | 'thinking' | 'speaking' | 'executing'>('idle')
  const [time, setTime] = useState(new Date())

  const memory = useMemorySummary()
  const projects = useProjects()
  const trading = useTradingPerformance()
  const trades = useTradeHistory(5)
  const risk = useRiskAssessment()
  const greeting = useGreeting()

  // Update time
  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  return (
    <div className="min-h-screen w-full bg-gradient-to-br from-slate-950 via-blue-950 to-slate-900 p-6 md:p-8">
      {/* Animated background */}
      <div className="absolute inset-0 -z-10 opacity-30">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_50%,rgba(0,200,255,0.1),transparent_50%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_80%_80%,rgba(100,200,255,0.1),transparent_50%)]" />
      </div>

      {/* Header with Greeting */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-cyan-300 to-blue-400">
              NANCY COMMAND CENTER
            </h1>
            {greeting.data && (
              <p className="text-cyan-400/80 mt-2 text-sm max-w-2xl">
                {greeting.data.greeting}
              </p>
            )}
          </div>
          <div className="text-right">
            <div className="text-3xl font-mono font-bold text-cyan-300">
              {time.toLocaleTimeString()}
            </div>
            <div className="text-cyan-400/60 text-sm">{time.toDateString()}</div>
          </div>
        </div>

        {/* Status bar */}
        <div className="h-1 bg-gradient-to-r from-cyan-500 via-blue-500 to-purple-500 rounded-full" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 mb-8">
        {/* Nancy Orb & Status */}
        <div className="lg:col-span-1 flex flex-col items-center gap-4">
          <EnhancedNancyOrb state={orbState} size={240} showLabel={true} />
          <div className="w-full space-y-2 text-center">
            <div className="text-xs font-mono text-cyan-400 uppercase">System Status</div>
            <div className="flex justify-center gap-2">
              <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
              <span className="text-sm text-cyan-300">Operational</span>
            </div>
          </div>
        </div>

        {/* Key Metrics */}
        <div className="lg:col-span-3 grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Memory Metrics */}
          <MetricCard
            icon={Brain}
            label="Memories Stored"
            value={memory.data?.total_nodes || 0}
            color="cyan"
            loading={memory.loading}
          />

          {/* Projects */}
          <MetricCard
            icon={Activity}
            label="Active Projects"
            value={projects.data?.length || 0}
            color="green"
            loading={projects.loading}
          />

          {/* Trading Metrics */}
          <MetricCard
            icon={TrendingUp}
            label="Open Trades"
            value={trading.data?.closed_trades || 0}
            color="purple"
            loading={trading.loading}
          />
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* Trading Performance */}
        <div className="lg:col-span-2 border border-cyan-500/20 rounded-lg p-6 bg-gradient-to-br from-cyan-950/30 to-blue-950/30 backdrop-blur-sm">
          <h2 className="text-xl font-bold text-cyan-300 mb-4 flex items-center gap-2">
            <DollarSign className="w-5 h-5" />
            Trading Performance
          </h2>

          {trading.loading ? (
            <div className="animate-pulse space-y-2">
              <div className="h-4 bg-cyan-500/20 rounded w-3/4" />
              <div className="h-4 bg-cyan-500/20 rounded w-1/2" />
            </div>
          ) : trading.data ? (
            <div className="space-y-3">
              <PerformanceRow
                label="Win Rate"
                value={`${(trading.data.win_rate || 0).toFixed(1)}%`}
                color="green"
              />
              <PerformanceRow
                label="Total P&L"
                value={`$${(trading.data.total_pnl || 0).toFixed(2)}`}
                color={trading.data.total_pnl >= 0 ? 'green' : 'red'}
              />
              <PerformanceRow
                label="Closed Trades"
                value={trading.data.closed_trades || 0}
                color="cyan"
              />
              <PerformanceRow
                label="Current Equity"
                value={`$${(trading.data.current_equity || 0).toFixed(2)}`}
                color="blue"
              />
            </div>
          ) : (
            <p className="text-gray-400">No trading data</p>
          )}
        </div>

        {/* Risk Assessment */}
        <div className="border border-orange-500/20 rounded-lg p-6 bg-gradient-to-br from-orange-950/30 to-red-950/30 backdrop-blur-sm">
          <h2 className="text-xl font-bold text-orange-300 mb-4 flex items-center gap-2">
            <AlertCircle className="w-5 h-5" />
            Risk Assessment
          </h2>

          {risk.loading ? (
            <div className="animate-pulse space-y-2">
              <div className="h-4 bg-orange-500/20 rounded" />
              <div className="h-4 bg-orange-500/20 rounded w-3/4" />
            </div>
          ) : risk.data ? (
            <div className="space-y-3">
              <RiskMetric
                label="Risk Level"
                value={risk.data.risk_level?.toUpperCase() || 'UNKNOWN'}
                color={
                  risk.data.risk_level === 'low'
                    ? 'green'
                    : risk.data.risk_level === 'moderate'
                      ? 'yellow'
                      : risk.data.risk_level === 'high'
                        ? 'orange'
                        : 'red'
                }
              />
              <RiskMetric
                label="Drawdown"
                value={`${(risk.data.drawdown_pct || 0).toFixed(2)}%`}
                color="cyan"
              />
              <div className="mt-4 p-3 rounded-lg border border-orange-500/30 bg-orange-950/20">
                <p className="text-xs text-orange-300">
                  {risk.data.recommendations?.[0] || 'No recommendations at this time'}
                </p>
              </div>
            </div>
          ) : (
            <p className="text-gray-400">No risk data</p>
          )}
        </div>
      </div>

      {/* Projects & Recent Trades */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Projects Panel */}
        <div className="border border-green-500/20 rounded-lg p-6 bg-gradient-to-br from-green-950/30 to-slate-950/30 backdrop-blur-sm">
          <h2 className="text-lg font-bold text-green-300 mb-4 flex items-center gap-2">
            <Target className="w-5 h-5" />
            Active Projects
          </h2>

          {projects.loading ? (
            <div className="space-y-2">
              {[1, 2, 3].map(i => (
                <div key={i} className="h-4 bg-green-500/20 rounded animate-pulse" />
              ))}
            </div>
          ) : projects.data && projects.data.length > 0 ? (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {projects.data.slice(0, 5).map((project: any, i: number) => (
                <ProjectItem key={i} project={project} />
              ))}
            </div>
          ) : (
            <p className="text-gray-400 text-sm">No projects tracked</p>
          )}
        </div>

        {/* Recent Trades */}
        <div className="border border-purple-500/20 rounded-lg p-6 bg-gradient-to-br from-purple-950/30 to-slate-950/30 backdrop-blur-sm">
          <h2 className="text-lg font-bold text-purple-300 mb-4 flex items-center gap-2">
            <TrendingUp className="w-5 h-5" />
            Recent Trades
          </h2>

          {trades.loading ? (
            <div className="space-y-2">
              {[1, 2, 3].map(i => (
                <div key={i} className="h-4 bg-purple-500/20 rounded animate-pulse" />
              ))}
            </div>
          ) : trades.data && trades.data.length > 0 ? (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {trades.data.map((trade: any, i: number) => (
                <TradeItem key={i} trade={trade} />
              ))}
            </div>
          ) : (
            <p className="text-gray-400 text-sm">No recent trades</p>
          )}
        </div>
      </div>
    </div>
  )
}

function MetricCard({
  icon: Icon,
  label,
  value,
  color,
  loading
}: {
  icon: any
  label: string
  value: number | string
  color: 'cyan' | 'green' | 'purple'
  loading?: boolean
}) {
  const colors = {
    cyan: 'from-cyan-950/30 to-blue-950/30 border-cyan-500/20 text-cyan-300',
    green: 'from-green-950/30 to-slate-950/30 border-green-500/20 text-green-300',
    purple: 'from-purple-950/30 to-slate-950/30 border-purple-500/20 text-purple-300'
  }

  return (
    <div
      className={cn(
        'border rounded-lg p-4 bg-gradient-to-br backdrop-blur-sm',
        colors[color]
      )}
    >
      <div className="flex items-center justify-between mb-2">
        <Icon className="w-5 h-5" />
      </div>
      <p className="text-sm font-mono text-gray-400">{label}</p>
      {loading ? (
        <div className="h-6 bg-gray-500/20 rounded animate-pulse mt-2" />
      ) : (
        <p className="text-2xl font-bold mt-2">{value}</p>
      )}
    </div>
  )
}

function PerformanceRow({
  label,
  value,
  color
}: {
  label: string
  value: string | number
  color: 'green' | 'red' | 'cyan' | 'blue'
}) {
  const colorClass = {
    green: 'text-green-400',
    red: 'text-red-400',
    cyan: 'text-cyan-400',
    blue: 'text-blue-400'
  }[color]

  return (
    <div className="flex justify-between items-center p-2 rounded border border-gray-500/10 hover:border-gray-500/30 transition">
      <span className="text-sm text-gray-400">{label}</span>
      <span className={cn('font-mono font-bold', colorClass)}>{value}</span>
    </div>
  )
}

function RiskMetric({
  label,
  value,
  color
}: {
  label: string
  value: string
  color: 'green' | 'yellow' | 'orange' | 'red' | 'cyan'
}) {
  const colorClass = {
    green: 'text-green-400',
    yellow: 'text-yellow-400',
    orange: 'text-orange-400',
    red: 'text-red-400',
    cyan: 'text-cyan-400'
  }[color]

  return (
    <div className="flex justify-between items-center">
      <span className="text-sm text-gray-400">{label}</span>
      <span className={cn('font-mono font-bold', colorClass)}>{value}</span>
    </div>
  )
}

function ProjectItem({ project }: { project: any }) {
  return (
    <div className="p-3 rounded border border-green-500/20 hover:border-green-500/50 transition-colors bg-green-950/10">
      <div className="flex items-start justify-between">
        <div>
          <p className="font-semibold text-green-300 text-sm">{project.name || 'Untitled'}</p>
          <p className="text-xs text-gray-400 mt-1">{project.status || 'In progress'}</p>
        </div>
        <CheckCircle2 className="w-4 h-4 text-green-400" />
      </div>
    </div>
  )
}

function TradeItem({ trade }: { trade: any }) {
  const isProfit = (trade.profit_loss || 0) >= 0

  return (
    <div className="p-3 rounded border border-purple-500/20 hover:border-purple-500/50 transition-colors bg-purple-950/10">
      <div className="flex items-center justify-between">
        <div className="flex-1">
          <p className="font-mono font-semibold text-purple-300 text-sm">
            {trade.pair} {trade.direction}
          </p>
          <p className="text-xs text-gray-400">@ {trade.entry_price}</p>
        </div>
        <div className="text-right">
          <p className={cn('font-mono font-bold text-sm', isProfit ? 'text-green-400' : 'text-red-400')}>
            ${trade.profit_loss?.toFixed(2) || 0}
          </p>
          <p className="text-xs text-gray-400">{trade.status}</p>
        </div>
      </div>
    </div>
  )
}

