'use client'

import React, { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'
import { Globe, MapPin, TrendingUp, Navigation2, Radar, Eye } from 'lucide-react'

interface Location {
  name: string
  lat: number
  lng: number
  type: 'market' | 'project' | 'alert' | 'trade'
  intensity: number
  label: string
}

export function EnhancedReconMap() {
  const [locations, setLocations] = useState<Location[]>([
    {
      name: 'EUR/USD Market',
      lat: 0,
      lng: 0,
      type: 'market',
      intensity: 0.95,
      label: 'EUR/USD @ 1.0872'
    },
    {
      name: 'Roxan Project',
      lat: 40.7128,
      lng: -74.006,
      type: 'project',
      intensity: 0.85,
      label: 'Deployment Success'
    },
    {
      name: 'Trading Alert',
      lat: 51.5074,
      lng: -0.1278,
      type: 'alert',
      intensity: 0.9,
      label: 'EUR Resistance'
    },
    {
      name: 'Active Trade',
      lat: 35.6762,
      lng: 139.6503,
      type: 'trade',
      intensity: 0.75,
      label: 'EUR Long Position'
    }
  ])

  const [scanAngle, setScanAngle] = useState(0)

  // Animate radar scan
  useEffect(() => {
    const interval = setInterval(() => {
      setScanAngle((prev) => (prev + 2) % 360)
    }, 50)
    return () => clearInterval(interval)
  }, [])

  // Normalize coordinates to grid (0-100)
  const normalizeCoord = (value: number, isLng: boolean) => {
    if (isLng) {
      return ((value + 180) / 360) * 100
    } else {
      return ((value + 90) / 180) * 100
    }
  }

  return (
    <div className="w-full h-screen bg-gradient-to-br from-slate-950 via-blue-950 to-slate-900 p-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-cyan-300 to-blue-400 flex items-center gap-3">
          <Radar className="w-8 h-8 text-cyan-400" />
          TACTICAL RECONNAISSANCE SYSTEM
        </h1>
        <p className="text-cyan-400/60 mt-2 text-sm font-mono">
          Real-time surveillance and market intelligence
        </p>
      </div>

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-[calc(100vh-150px)]">
        {/* Holographic map */}
        <div className="lg:col-span-2 border border-cyan-500/30 rounded-lg p-6 bg-gradient-to-br from-cyan-950/20 to-blue-950/20 backdrop-blur-sm relative overflow-hidden">
          {/* Grid background */}
          <svg className="absolute inset-0 w-full h-full opacity-10" preserveAspectRatio="none">
            <defs>
              <pattern id="grid" width="50" height="50" patternUnits="userSpaceOnUse">
                <path
                  d="M 50 0 L 0 0 0 50"
                  fill="none"
                  stroke="cyan"
                  strokeWidth="0.5"
                />
              </pattern>
            </defs>
            <rect width="100%" height="100%" fill="url(#grid)" />
          </svg>

          {/* Radar sweep */}
          <svg className="absolute inset-0 w-full h-full" preserveAspectRatio="none">
            <g opacity="0.2">
              <circle cx="50%" cy="50%" r="25%" fill="none" stroke="cyan" strokeWidth="1" />
              <circle cx="50%" cy="50%" r="50%" fill="none" stroke="cyan" strokeWidth="1" />
              <circle cx="50%" cy="50%" r="75%" fill="none" stroke="cyan" strokeWidth="1" />
              <line x1="50%" y1="0%" x2="50%" y2="100%" stroke="cyan" strokeWidth="1" />
              <line x1="0%" y1="50%" x2="100%" y2="50%" stroke="cyan" strokeWidth="1" />
            </g>

            {/* Scan line */}
            <g opacity="0.5">
              <line
                x1="50%"
                y1="50%"
                x2={`calc(50% + ${50 * Math.cos((scanAngle * Math.PI) / 180)}%)`}
                y2={`calc(50% + ${50 * Math.sin((scanAngle * Math.PI) / 180)}%)`}
                stroke="lime"
                strokeWidth="2"
                filter="drop-shadow(0 0 5px lime)"
              />
            </g>
          </svg>

          {/* Locations */}
          <div className="absolute inset-0 flex items-center justify-center">
            {locations.map((location, i) => (
              <MapLocation key={i} location={location} normalizeCoord={normalizeCoord} />
            ))}
          </div>

          {/* Center marker */}
          <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-4 h-4">
            <div className="absolute inset-0 bg-cyan-400 rounded-full animate-pulse" />
            <div className="absolute inset-1 border border-cyan-400 rounded-full" />
          </div>

          {/* Legend */}
          <div className="absolute bottom-4 left-4 space-y-2 bg-slate-950/80 backdrop-blur-sm border border-cyan-500/30 rounded-lg p-4">
            <p className="text-cyan-300 font-mono text-xs font-bold mb-3">Legend</p>
            <LegendItem color="cyan" label="Market Data" />
            <LegendItem color="green" label="Projects" />
            <LegendItem color="orange" label="Alerts" />
            <LegendItem color="purple" label="Trades" />
          </div>
        </div>

        {/* Right sidebar */}
        <div className="space-y-4">
          {/* Active locations list */}
          <div className="border border-blue-500/30 rounded-lg p-6 bg-gradient-to-br from-blue-950/20 to-slate-950/20 backdrop-blur-sm">
            <h2 className="text-lg font-bold text-blue-300 mb-4 flex items-center gap-2">
              <Eye className="w-5 h-5" />
              Active Locations
            </h2>

            <div className="space-y-3 max-h-64 overflow-y-auto">
              {locations.map((location, i) => (
                <div key={i} className="p-3 rounded-lg border border-blue-500/20 bg-blue-950/20 hover:bg-blue-950/40 transition-colors">
                  <div className="flex items-center justify-between mb-2">
                    <p className="font-semibold text-blue-300">{location.label}</p>
                    <TypeBadge type={location.type} />
                  </div>
                  <p className="text-xs text-blue-400/60 font-mono">
                    {location.lat.toFixed(2)}° {location.lng.toFixed(2)}°
                  </p>
                  <div className="mt-2 h-1 bg-slate-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-cyan-400 to-blue-400"
                      style={{ width: `${location.intensity * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Intelligence Summary */}
          <div className="border border-green-500/30 rounded-lg p-6 bg-gradient-to-br from-green-950/20 to-slate-950/20 backdrop-blur-sm">
            <h2 className="text-lg font-bold text-green-300 mb-4 flex items-center gap-2">
              <TrendingUp className="w-5 h-5" />
              Intelligence Summary
            </h2>

            <div className="space-y-3 text-sm">
              <SummaryItem label="Markets Active" value="3" color="cyan" />
              <SummaryItem label="Threats Detected" value="1" color="orange" />
              <SummaryItem label="Projects Tracked" value="2" color="green" />
              <SummaryItem label="Positions Open" value="2" color="purple" />
            </div>
          </div>

          {/* System Status */}
          <div className="border border-purple-500/30 rounded-lg p-6 bg-gradient-to-br from-purple-950/20 to-slate-950/20 backdrop-blur-sm">
            <h2 className="text-lg font-bold text-purple-300 mb-4 flex items-center gap-2">
              <Navigation2 className="w-5 h-5" />
              Coverage Map
            </h2>

            <div className="grid grid-cols-3 gap-2">
              <MiniGrid title="Global" active={true} />
              <MiniGrid title="Markets" active={true} />
              <MiniGrid title="Projects" active={true} />
              <MiniGrid title="Trades" active={true} />
              <MiniGrid title="Alerts" active={true} />
              <MiniGrid title="Analysis" active={false} />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function MapLocation({
  location,
  normalizeCoord
}: {
  location: Location
  normalizeCoord: (value: number, isLng: boolean) => number
}) {
  const x = normalizeCoord(location.lng, true)
  const y = normalizeCoord(location.lat, false)

  const colors = {
    market: 'cyan',
    project: 'green',
    alert: 'orange',
    trade: 'purple'
  }

  const color = colors[location.type]

  const bgColor = {
    cyan: 'from-cyan-500 to-blue-500',
    green: 'from-green-500 to-emerald-500',
    orange: 'from-orange-500 to-red-500',
    purple: 'from-purple-500 to-pink-500'
  }[color]

  const shadowColor = {
    cyan: 'drop-shadow(0 0 10px cyan)',
    green: 'drop-shadow(0 0 10px #22c55e)',
    orange: 'drop-shadow(0 0 10px #f97316)',
    purple: 'drop-shadow(0 0 10px #a855f7)'
  }[color]

  return (
    <div
      className="absolute w-4 h-4 transform -translate-x-1/2 -translate-y-1/2 group cursor-pointer"
      style={{
        left: `${x}%`,
        top: `${y}%`,
        filter: shadowColor
      }}
    >
      {/* Outer pulse */}
      <div
        className={cn('absolute inset-0 rounded-full animate-pulse opacity-50 bg-gradient-to-br', bgColor)}
      />

      {/* Inner dot */}
      <div
        className={cn('absolute inset-1 rounded-full bg-gradient-to-br', bgColor)}
      />

      {/* Tooltip on hover */}
      <div className="absolute left-full ml-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-slate-950 border border-gray-400 rounded px-3 py-2 text-xs text-white whitespace-nowrap pointer-events-none">
        <p className="font-semibold">{location.label}</p>
        <p className="text-gray-400">{location.name}</p>
      </div>
    </div>
  )
}

function TypeBadge({ type }: { type: string }) {
  const colors = {
    market: 'bg-cyan-500/20 text-cyan-300',
    project: 'bg-green-500/20 text-green-300',
    alert: 'bg-orange-500/20 text-orange-300',
    trade: 'bg-purple-500/20 text-purple-300'
  }

  return (
    <span className={cn('px-2 py-1 rounded text-xs font-mono capitalize', colors[type as keyof typeof colors])}>
      {type}
    </span>
  )
}

function SummaryItem({ label, value, color }: { label: string; value: string; color: string }) {
  const textColor = {
    cyan: 'text-cyan-400',
    orange: 'text-orange-400',
    green: 'text-green-400',
    purple: 'text-purple-400'
  }[color]

  return (
    <div className="flex justify-between items-center">
      <span className="text-gray-400">{label}</span>
      <span className={cn('font-bold', textColor)}>{value}</span>
    </div>
  )
}

function MiniGrid({ title, active }: { title: string; active: boolean }) {
  return (
    <div
      className={cn(
        'p-2 rounded border text-xs text-center cursor-pointer transition-colors',
        active
          ? 'border-green-500/50 bg-green-950/30 text-green-300 hover:bg-green-950/50'
          : 'border-gray-600/30 bg-gray-950/30 text-gray-500 hover:bg-gray-950/50'
      )}
    >
      {title}
    </div>
  )
}

