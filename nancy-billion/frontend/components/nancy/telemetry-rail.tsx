'use client'

/**
 * JARVIS "Global Track Sys"-style telemetry rail — matches the reference
 * screenshot: NETWORK TRAFFIC waveform, RADAR ROUTER satellite table,
 * CONTINENTAL SCANNING sub-globes.
 */

import { useEffect, useState } from 'react'

const CYAN = 'oklch(0.82 0.16 210)'

function useTick(ms = 900) {
  const [n, setN] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setN((v) => v + 1), ms)
    return () => clearInterval(t)
  }, [ms])
  return n
}

/* ─── Top strip: multi-city clocks + status pills ────────────────── */
export function GlobalTrackStrip() {
  useTick(1000)
  const now = Date.now()
  const cities: [string, number][] = [
    ['LOCAL', 0],
    ['LOS ANGELES', -7],
    ['NEW YORK', -4],
    ['LONDON', 1],
    ['PARIS', 2],
    ['BEIJING', 8],
  ]
  const fmt = (offset: number) => {
    const d = new Date(now + offset * 3600_000)
    return d.toUTCString().slice(17, 25)
  }
  return (
    <div className="hud-panel flex items-stretch gap-0 rounded-none border-x-0 border-t-0 px-3 py-1.5">
      <div className="flex items-center gap-2 pr-4 border-r border-primary/20">
        <span className="font-heading text-[0.6rem] tracking-[0.32em] text-primary hud-glow">
          GLOBAL <span className="text-foreground/80">TRACK SYS</span>
        </span>
      </div>
      <div className="flex flex-1 items-center gap-4 px-4 overflow-hidden">
        {cities.map(([c, off]) => (
          <div key={c} className="flex flex-col leading-tight">
            <span className="text-[0.42rem] uppercase tracking-widest text-muted-foreground">
              {c}
            </span>
            <span className="font-heading text-[0.6rem] text-primary tabular-nums">
              {fmt(off)}
            </span>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-1">
        {['SCANNING', 'TELEMETRY', 'MONITOR', 'DATA', 'TARGETS', 'ISOLATE', 'AM'].map(
          (p, i) => (
            <span
              key={p}
              className={`rounded-sm border px-1.5 py-0.5 text-[0.42rem] tracking-widest ${
                i === 2
                  ? 'border-destructive/60 bg-destructive/15 text-destructive animate-hud-flicker'
                  : 'border-primary/40 bg-primary/10 text-primary'
              }`}
            >
              {p}
            </span>
          ),
        )}
      </div>
    </div>
  )
}

/* ─── Left rail widgets ─────────────────────────────────────────── */

function NetworkTraffic() {
  useTick(700)
  const bars = Array.from({ length: 48 }, () => Math.random())
  return (
    <div className="hud-panel rounded-sm p-2">
      <div className="mb-1.5 flex items-center justify-between">
        <span className="font-heading text-[0.55rem] tracking-[0.22em] text-primary">
          NETWORK TRAFFIC
        </span>
        <span className="text-[0.42rem] text-muted-foreground">SYS LOG</span>
      </div>
      <div className="text-[0.42rem] text-muted-foreground/80 mb-1">SN-GA/3 · R2</div>
      <div className="flex h-10 items-end gap-[2px]">
        {bars.map((v, i) => (
          <div
            key={i}
            className="w-full bg-primary/80"
            style={{
              height: `${20 + v * 80}%`,
              boxShadow: v > 0.7 ? `0 0 4px ${CYAN}` : 'none',
              opacity: 0.4 + v * 0.6,
            }}
          />
        ))}
      </div>
    </div>
  )
}

function RadarRouter() {
  useTick(1500)
  const rows = [
    ['32', '2585N', 'DIRECT AS', '-125.9', '0.5'],
    ['34', '9302N', 'ECHOSTAR 09', '-369.5', '0.2'],
    ['35', '7446N', 'ECHOSTAR 12', '-389.6', '1.0'],
    ['1', '5423A', 'ANK 5', '-260.4', '0.3'],
    ['87', '5289C', 'GALAXY 23', '-355.2', '0.0'],
    ['1', '5286C', 'NORAD C4', '-874.1', '0.2'],
  ]
  return (
    <div className="hud-panel rounded-sm p-2">
      <div className="mb-1.5 flex items-center justify-between">
        <span className="font-heading text-[0.55rem] tracking-[0.22em] text-primary">
          RADAR ROUTER
        </span>
        <span className="rounded-sm bg-primary/20 px-1 text-[0.42rem] text-primary">
          SECURE
        </span>
      </div>
      <div className="mb-1 flex items-center gap-2 text-[0.5rem]">
        <span className="font-heading text-primary">ANK 5</span>
        <span className="text-muted-foreground">LAT -20.45845</span>
        <span className="text-muted-foreground">LON 245.630</span>
      </div>
      <table className="w-full border-collapse text-[0.42rem]">
        <thead>
          <tr className="text-muted-foreground">
            {['SAT ID', 'COM', 'NAME', 'ORBIT', 'INC'].map((h) => (
              <th key={h} className="border-b border-primary/20 py-0.5 text-left font-normal">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="text-foreground/85">
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-border/40">
              {r.map((c, j) => (
                <td
                  key={j}
                  className={`py-0.5 tabular-nums ${
                    i === 3 ? 'text-primary' : ''
                  } ${c === '5423A' ? 'text-destructive' : ''}`}
                >
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function MiniGlobe({ label, pct }: { label: string; pct: number }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative h-10 w-10">
        <div
          className="absolute inset-0 rounded-full border border-primary/40"
          style={{
            background:
              'radial-gradient(circle at 30% 30%, oklch(0.4 0.12 220 / 60%), transparent 70%), radial-gradient(circle at 70% 70%, oklch(0.6 0.14 210 / 40%), transparent 60%)',
            boxShadow: `inset 0 0 6px ${CYAN}, 0 0 4px ${CYAN}`,
          }}
        />
        <div
          className="absolute inset-1 rounded-full border border-primary/20 animate-hud-spin-slow"
          style={{ borderStyle: 'dashed' }}
        />
        <div
          className="absolute inset-0 flex items-center justify-center font-heading text-[0.5rem] text-primary"
          style={{ textShadow: `0 0 4px ${CYAN}` }}
        >
          {pct}%
        </div>
      </div>
      <span className="text-[0.42rem] uppercase tracking-widest text-muted-foreground">
        {label}
      </span>
    </div>
  )
}

function ContinentalScan() {
  useTick(1800)
  return (
    <div className="hud-panel rounded-sm p-2">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-heading text-[0.55rem] tracking-[0.22em] text-primary">
          CONTINENTAL SCANNING
        </span>
        <span className="text-[0.42rem] text-primary/80 animate-hud-pulse">LIVE</span>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <MiniGlobe label="S. USA" pct={40 + Math.floor(Math.random() * 20)} />
        <MiniGlobe label="N. USA" pct={40 + Math.floor(Math.random() * 20)} />
        <MiniGlobe label="AFRICA" pct={40 + Math.floor(Math.random() * 20)} />
        <MiniGlobe label="AUS" pct={40 + Math.floor(Math.random() * 20)} />
        <MiniGlobe label="ASIA" pct={40 + Math.floor(Math.random() * 20)} />
        <MiniGlobe label="EUROPE" pct={40 + Math.floor(Math.random() * 20)} />
      </div>
    </div>
  )
}

export function LeftTelemetryRail() {
  return (
    <aside className="pointer-events-none absolute left-2 top-14 bottom-14 z-[500] hidden w-[220px] flex-col gap-2 lg:flex">
      <div className="pointer-events-auto flex flex-col gap-2 opacity-95">
        <NetworkTraffic />
        <RadarRouter />
        <ContinentalScan />
      </div>
    </aside>
  )
}

/* ─── Right rail: tracking monitor / global position / target ────── */

function TrackingMonitor() {
  useTick(600)
  const wave = Array.from({ length: 24 }, () => Math.random())
  return (
    <div className="hud-panel rounded-sm p-2">
      <div className="mb-1 flex items-center justify-between">
        <span className="font-heading text-[0.55rem] tracking-[0.22em] text-primary">
          TRACKING MONITOR
        </span>
        <span className="text-[0.42rem] text-primary/70">CX1</span>
      </div>
      <div className="text-[0.42rem] text-muted-foreground">CONNECTED · PRIVATE SATELLITE</div>
      <div className="mt-1 flex h-6 items-end gap-[2px]">
        {wave.map((v, i) => (
          <div
            key={i}
            className="w-full bg-accent/80"
            style={{ height: `${30 + v * 70}%`, opacity: 0.5 + v * 0.5 }}
          />
        ))}
      </div>
    </div>
  )
}

function GlobalPosition({ lat, lon }: { lat?: number; lon?: number }) {
  return (
    <div className="hud-panel rounded-sm p-2">
      <div className="mb-1 font-heading text-[0.55rem] tracking-[0.22em] text-primary">
        GLOBAL POSITION
      </div>
      <div className="text-[0.42rem] text-muted-foreground mb-1">DATA STREAM</div>
      <div className="grid grid-cols-6 gap-[2px]">
        {Array.from({ length: 24 }, (_, i) => (
          <div
            key={i}
            className="h-1.5 bg-primary/60"
            style={{ opacity: 0.3 + Math.random() * 0.7 }}
          />
        ))}
      </div>
      <div className="mt-1.5 grid grid-cols-2 gap-1 text-[0.5rem] tabular-nums">
        <div>
          <div className="text-muted-foreground text-[0.42rem]">LONGITUDE</div>
          <div className="text-primary">{(lon ?? 0).toFixed(4)}</div>
        </div>
        <div>
          <div className="text-muted-foreground text-[0.42rem]">LATITUDE</div>
          <div className="text-primary">{(lat ?? 0).toFixed(4)}</div>
        </div>
      </div>
    </div>
  )
}

function TargetData({ name }: { name?: string }) {
  return (
    <div className="hud-panel rounded-sm p-2">
      <div className="mb-1 font-heading text-[0.55rem] tracking-[0.22em] text-primary">
        TARGET DATA
      </div>
      <div className="text-[0.42rem] text-muted-foreground">
        GLOBAL POSITION MONITORING · SPECIFIC AREA CLASSIFIED
      </div>
      <div className="mt-1 font-heading text-sm text-accent hud-glow-amber">
        {name?.toUpperCase() ?? '— — —'}
      </div>
      <div className="mt-1 flex flex-wrap gap-1 text-[0.4rem]">
        {['DRAG COEFFICIENT', 'SOLAR FLUX', 'REFRACTIVE INDEX'].map((k) => (
          <span key={k} className="rounded-sm bg-secondary/40 px-1 py-0.5 text-muted-foreground">
            {k}
          </span>
        ))}
      </div>
      <div className="mt-1 flex items-center gap-1">
        <span className="rounded-sm border border-primary/50 bg-primary/10 px-1 py-0.5 font-heading text-[0.5rem] text-primary">
          T-RB0
        </span>
        <span className="text-[0.42rem] text-muted-foreground">SAT-LINK 01</span>
      </div>
    </div>
  )
}

export function RightTelemetryRail({
  place,
}: {
  place?: { lat: number; lon: number; name: string } | null
}) {
  return (
    <aside className="pointer-events-none absolute right-2 top-14 z-[500] hidden w-[220px] flex-col gap-2 md:flex">
      <div className="pointer-events-auto flex flex-col gap-2 opacity-95">
        <TrackingMonitor />
        <GlobalPosition lat={place?.lat} lon={place?.lon} />
        <TargetData name={place?.name} />
      </div>
    </aside>
  )
}
