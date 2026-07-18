'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import type { Map as LeafletMap, Marker, Circle, Popup } from 'leaflet'
import { getSunInfo, formatLocalTime, isNightAt, type SunInfo } from '@/lib/nancy/sun'
import type { Place } from '@/lib/nancy/types'
import { CornerTicks } from './hud-bits'
import { GlobeView } from './globe-view'
import {
  GlobalTrackStrip,
  LeftTelemetryRail,
  RightTelemetryRail,
} from './telemetry-rail'
import { Loader2, Crosshair, Sun, Moon, Globe2, History, Bug } from 'lucide-react'
import { cn } from '@/lib/utils'



const ESRI_SAT =
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
const ESRI_LABELS =
  'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}'
// CARTO dark-matter — perfect JARVIS night tone for cities in darkness.
const CARTO_DARK =
  'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
const CARTO_DARK_LABELS =
  'https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png'

type Phase = 'globe' | 'satellite'

export function MapPanel({
  place,
  loading,
}: {
  place: Place | null
  loading: boolean
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<LeafletMap | null>(null)
  const markerRef = useRef<Marker | null>(null)
  const ringRef = useRef<Circle | null>(null)
  // Track day/night tile layers so we can hot-swap them without rebuilding the map.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const dayLayersRef = useRef<any[]>([])
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const nightLayersRef = useRef<any[]>([])
  const currentModeRef = useRef<'day' | 'night'>('day')
  const [ready, setReady] = useState(false)
  const [sun, setSun] = useState<SunInfo | null>(null)
  const [localTime, setLocalTime] = useState('--:--:--')
  const [phase, setPhase] = useState<Phase>('globe')
  const phaseRef = useRef<Phase>('globe')
  phaseRef.current = phase

  // Day/night controls — persisted per city (name+country) in localStorage.
  const [modeOverride, setModeOverride] = useState<'auto' | 'day' | 'night'>('auto')
  const [threshold, setThreshold] = useState(0) // solar altitude (deg)
  const [debugOpen, setDebugOpen] = useState(false)

  const prefsKey = place ? `nancy.mapPrefs:${place.name}|${place.country}` : null

  // Load persisted prefs when the target city changes.
  useEffect(() => {
    if (!prefsKey || typeof window === 'undefined') {
      setModeOverride('auto')
      setThreshold(0)
      return
    }
    try {
      const raw = window.localStorage.getItem(prefsKey)
      if (raw) {
        const p = JSON.parse(raw) as { modeOverride?: 'auto' | 'day' | 'night'; threshold?: number }
        setModeOverride(p.modeOverride ?? 'auto')
        setThreshold(typeof p.threshold === 'number' ? p.threshold : 0)
        return
      }
    } catch { /* ignore corrupt entry */ }
    setModeOverride('auto')
    setThreshold(0)
  }, [prefsKey])

  // Persist on change.
  useEffect(() => {
    if (!prefsKey || typeof window === 'undefined') return
    try {
      window.localStorage.setItem(
        prefsKey,
        JSON.stringify({ modeOverride, threshold }),
      )
    } catch { /* quota / private mode — ignore */ }
  }, [prefsKey, modeOverride, threshold])



  // Zoom level at/below which the satellite view collapses back into the globe.
  const REVERT_ZOOM = 4

  // Init Leaflet once (kept mounted behind the globe, revealed on arrival)
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const L = (await import('leaflet')).default
      await import('leaflet/dist/leaflet.css')
      if (cancelled || !containerRef.current || mapRef.current) return

      const map = L.map(containerRef.current, {
        center: [20, 10],
        zoom: 5,
        zoomControl: false,
        attributionControl: true,
        worldCopyJump: true,
      })

      // Day (default): ESRI satellite imagery + boundaries — kept on the map
      // at full opacity initially so tiles preload immediately.
      const daySat = L.tileLayer(ESRI_SAT, {
        maxZoom: 18,
        className: 'hud-map-tiles hud-basemap-day',
        attribution: 'Imagery &copy; Esri',
      }).addTo(map)
      const dayLabels = L.tileLayer(ESRI_LABELS, {
        maxZoom: 18,
        className: 'hud-map-tiles hud-basemap-day',
        opacity: 0.7,
      }).addTo(map)
      dayLayersRef.current = [daySat, dayLabels]

      // Night: CARTO dark-matter — also added, but held at opacity 0 so its
      // tiles preload alongside day tiles. Swapping is a pure opacity flip
      // with no unload/reload flicker.
      const nightBase = L.tileLayer(CARTO_DARK, {
        maxZoom: 19,
        className: 'hud-map-tiles hud-basemap-night',
        attribution: '&copy; OpenStreetMap &copy; CARTO',
        opacity: 0,
      }).addTo(map)
      const nightLabels = L.tileLayer(CARTO_DARK_LABELS, {
        maxZoom: 19,
        className: 'hud-map-tiles hud-basemap-night',
        opacity: 0,
      }).addTo(map)
      nightLayersRef.current = [nightBase, nightLabels]


      map.on('zoomend', () => {
        if (phaseRef.current === 'satellite' && map.getZoom() <= REVERT_ZOOM) {
          setPhase('globe')
        }
      })

      mapRef.current = map
      setReady(true)
    })()

    return () => {
      cancelled = true
      mapRef.current?.remove()
      mapRef.current = null
    }
  }, [])

  const [descending, setDescending] = useState(false)

  // A new place restarts the cinematic from the globe
  useEffect(() => {
    if (place) {
      setPhase('globe')
      setDescending(true)
    }
  }, [place])

  // Reveal + fly the satellite map to the city. Used both by the automated
  // globe descent (street level) and by a manual zoom-in dive (city level).
  const revealSatellite = useCallback(
    async (targetZoom: number) => {
      setPhase('satellite')
      setDescending(false)
      if (!ready || !place || !mapRef.current) return
      const L = (await import('leaflet')).default
      const map = mapRef.current

      // Snap near the target so the reveal feels continuous, then zoom in.
      const start = Math.max(REVERT_ZOOM + 2, targetZoom - 7)
      map.setView([place.lat, place.lon], start, { animate: false })
      map.flyTo([place.lat, place.lon], targetZoom, { duration: 2.6 })

    if (markerRef.current) markerRef.current.remove()
    if (ringRef.current) ringRef.current.remove()

    const icon = L.divIcon({
      className: '',
      html: `<div style="
        width:18px;height:18px;border-radius:50%;
        border:2px solid oklch(0.82 0.16 210);
        box-shadow:0 0 12px oklch(0.82 0.16 210),inset 0 0 6px oklch(0.82 0.16 210);
        background:oklch(0.82 0.16 210 / 25%);
      "></div>`,
      iconSize: [18, 18],
      iconAnchor: [9, 9],
    })
    markerRef.current = L.marker([place.lat, place.lon], { icon }).addTo(map)
    ringRef.current = L.circle([place.lat, place.lon], {
      radius: 1200,
      color: 'oklch(0.8 0.15 75)',
      weight: 1,
      fillOpacity: 0.05,
      dashArray: '4 6',
    }).addTo(map)
  },
  [ready, place],
  )

  // Automated descent → street level; manual globe zoom-in dive → city level.
  const handleArrive = useCallback(() => {
    void revealSatellite(16)
  }, [revealSatellite])
  const handleDive = useCallback(() => {
    void revealSatellite(13)
  }, [revealSatellite])

  // Day/night + local time ticker
  useEffect(() => {
    if (!place) {
      setSun(null)
      return
    }
    const update = () => {
      setSun(getSunInfo(place.lat, place.lon))
      setLocalTime(formatLocalTime(place.lon))
    }
    update()
    const t = setInterval(update, 1000)
    return () => clearInterval(t)
  }, [place])

  // Resolve current night/day mode from override or solar altitude + threshold.
  const autoNight = !!(sun && isNightAt(sun.altitude, threshold))
  const nightMode =
    modeOverride === 'night' ? true : modeOverride === 'day' ? false : autoNight

  // Night rendering: keep the ESRI satellite imagery on screen (so the user
  // still sees 3D/satellite terrain of the city), but apply a heavy blue night
  // tint via CSS filter, and fade in the CARTO dark labels overlay for
  // readable place names. The flat CARTO basemap is kept hidden so we never
  // lose the satellite look.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const wantMode: 'day' | 'night' = nightMode ? 'night' : 'day'
    if (wantMode === currentModeRef.current) return
    const [daySat, dayLabels] = dayLayersRef.current
    const [nightBase, nightLabels] = nightLayersRef.current
    if (wantMode === 'night') {
      // Satellite stays fully visible — tinted by CSS class below.
      daySat?.setOpacity(1)
      dayLabels?.setOpacity(0)
      nightBase?.setOpacity(0)
      nightLabels?.setOpacity(0.85)
    } else {
      daySat?.setOpacity(1)
      dayLabels?.setOpacity(0.7)
      nightBase?.setOpacity(0)
      nightLabels?.setOpacity(0)
    }
    // Toggle the tint class on the map root so the day-layer tiles turn blue at night.
    const el = map.getContainer()
    el.classList.toggle('hud-night-mode', wantMode === 'night')
    currentModeRef.current = wantMode
  }, [nightMode, ready])


  const showSatellite = phase === 'satellite'


  return (
    <div className="hud-panel relative h-full min-h-[560px] overflow-hidden rounded-md">
      <CornerTicks />

      {/* Global Track Sys strip */}
      <div className="absolute left-0 right-0 top-0 z-[600]">
        <GlobalTrackStrip />
      </div>

      {/* Left + right telemetry rails (JARVIS-style overlay) */}
      <LeftTelemetryRail />
      <RightTelemetryRail place={place} />


      {/* 3D globe (base layer) */}
      <GlobeView
        place={place}
        active={phase === 'globe'}
        onArrive={handleArrive}
        onDive={handleDive}
      />

      {/* Satellite map, revealed once the globe descent completes */}
      <div
        className="absolute inset-0 z-[300] transition-opacity duration-1000"
        style={{
          opacity: showSatellite ? 1 : 0,
          pointerEvents: showSatellite ? 'auto' : 'none',
        }}
      >
        <div ref={containerRef} className="absolute inset-0" />
      </div>

      {/* scanline */}
      <div className="pointer-events-none absolute inset-0 z-[400] overflow-hidden">
        <div
          className="absolute left-0 h-12 w-full opacity-30"
          style={{
            background:
              'linear-gradient(180deg, transparent, oklch(0.82 0.16 210 / 40%), transparent)',
            animation: 'hud-scan 5s linear infinite',
          }}
        />
      </div>

      {/* header (sits below the Global Track Sys strip) */}
      <div className="pointer-events-none absolute left-0 right-0 top-10 z-[500] flex items-start justify-center p-3">
        <div className="hud-panel rounded px-2 py-1 mx-auto">
          <div className="flex items-center gap-1.5 font-heading text-[0.6rem] uppercase tracking-[0.22em] text-primary">
            {showSatellite ? <Crosshair className="h-3 w-3" /> : <Globe2 className="h-3 w-3" />}
            {showSatellite ? (nightMode ? 'Surface Recon · Night' : 'Surface Recon · Day') : 'Orbital View'}
          </div>
        </div>
      </div>

      {/* Day/Night debug + threshold controls */}
      <div className="absolute right-3 top-14 z-[520] flex flex-col items-end gap-1">
        <button
          type="button"
          onClick={() => setDebugOpen((v) => !v)}
          className="hud-panel flex items-center gap-1.5 rounded px-2 py-1 text-[0.55rem] uppercase tracking-widest text-primary transition-colors hover:bg-primary/10"
          title="Toggle day/night debug"
        >
          <Bug className="h-3 w-3" />
          {nightMode ? 'Night' : 'Day'} · {sun ? `${sun.altitude.toFixed(1)}°` : '—'}
        </button>
        {debugOpen && (
          <div className="hud-panel w-64 rounded p-2 text-[0.55rem]">
            <div className="mb-1 flex items-center justify-between">
              <span className="font-heading uppercase tracking-widest text-primary">Basemap Mode</span>
              <span className="text-muted-foreground">
                {modeOverride === 'auto' ? 'AUTO' : modeOverride.toUpperCase()}
              </span>
            </div>
            <div className="mb-2 grid grid-cols-3 gap-1">
              {(['auto', 'day', 'night'] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setModeOverride(m)}
                  className={cn(
                    'rounded border px-1.5 py-1 text-[0.5rem] uppercase tracking-widest transition-colors',
                    modeOverride === m
                      ? 'border-primary bg-primary/20 text-primary'
                      : 'border-border/60 text-muted-foreground hover:border-primary/50',
                  )}
                >
                  {m}
                </button>
              ))}
            </div>
            <div className="mb-1 flex items-center justify-between">
              <span className="font-heading uppercase tracking-widest text-primary">Night Threshold</span>
              <span className="text-accent">{threshold > 0 ? '+' : ''}{threshold}°</span>
            </div>
            <input
              type="range"
              min={-12}
              max={12}
              step={1}
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
              className="w-full accent-[color:var(--hud)]"
              disabled={modeOverride !== 'auto'}
            />
            <div className="mt-2 grid grid-cols-2 gap-x-2 gap-y-0.5 text-[0.5rem] text-muted-foreground">
              <span>Sun Alt</span>
              <span className="text-right text-primary">{sun ? `${sun.altitude.toFixed(2)}°` : '—'}</span>
              <span>Phase</span>
              <span className="text-right text-primary uppercase">{sun?.phase ?? '—'}</span>
              <span>Auto → Night</span>
              <span className="text-right text-accent">{autoNight ? 'YES' : 'NO'}</span>
              <span>Rendered</span>
              <span className="text-right text-accent uppercase">{nightMode ? 'night' : 'day'}</span>
            </div>
            <p className="mt-2 text-[0.5rem] leading-tight text-muted-foreground">
              Threshold sets solar altitude at which night tiles engage. −6° = civil twilight, 0° = horizon.
            </p>
          </div>
        )}
      </div>


      <div className="pointer-events-none absolute left-0 right-0 top-0 z-[499] hidden p-3">

        <div className="hud-panel rounded px-2 py-1">
          <div className="flex items-center gap-1.5 font-heading text-[0.6rem] uppercase tracking-[0.22em] text-primary">
            {showSatellite ? (
              <Crosshair className="h-3 w-3" />
            ) : (
              <Globe2 className="h-3 w-3" />
            )}
            {showSatellite ? 'Surface Recon' : 'Orbital View'}
          </div>
        </div>
        {place && (
          <>
            <div className="hud-panel max-w-[60%] rounded px-2 py-1 text-right">
              <div className="truncate font-heading text-xs text-primary hud-glow">
                {place.name}
              </div>
              <div className="truncate text-[0.55rem] text-muted-foreground">
                {place.country}
              </div>
            </div>
            
            {/* Historical Events */}
            {place.historicalEvents && place.historicalEvents.length > 0 && (
              <div className="hud-panel max-w-[60%] rounded px-2 py-1 mt-2 text-right text-[0.5rem]">
                <div className="flex items-center gap-1 mb-1">
                  <History className="h-3 w-3 text-primary" />
                  <span className="font-heading text-[0.55rem] text-primary">Historical Significance</span>
                </div>
                <div className="space-y-1">
                  {place.historicalEvents
                    .slice(0, 3) // Show top 3 events
                    .map((event) => (
                      <div
                        key={event.id}
                        className="flex items-start gap-2"
                      >
                        <div className="flex-shrink-0">
                          <span className={`text-[0.45rem] px-1.5 py-0.5 rounded ${getEventSignificanceColor(event.significance)}`}>
                            {event.category.toUpperCase()}
                          </span>
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex justify-between items-start">
                            <h4 className="font-heading text-[0.55rem] text-foreground">{event.title}</h4>
                            <span className="text-[0.45rem] text-muted-foreground">{event.year}</span>
                          </div>
                          <p className="text-[0.45rem] text-muted-foreground line-clamp-2">
                            {event.description}
                          </p>
                        </div>
                      </div>
                    ))}
                </div>
                
                {place.historicalEvents.length > 3 && (
                  <div className="mt-1 text-center">
                    <span className="text-[0.45rem] text-muted-foreground italic">
                      +{place.historicalEvents.length - 3} more events
                    </span>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>

      {/* footer telemetry */}
      {place && sun && (
        <div className="pointer-events-none absolute bottom-0 left-0 right-0 z-[500] flex flex-wrap items-end justify-between gap-2 p-3">
          <div className="hud-panel rounded px-2 py-1 text-[0.55rem] leading-relaxed text-muted-foreground">
            <div>
              LAT{' '}
              <span className="text-primary">{place.lat.toFixed(4)}</span>
            </div>
            <div>
              LON{' '}
              <span className="text-primary">{place.lon.toFixed(4)}</span>
            </div>
          </div>
          <div className="hud-panel flex items-center gap-2 rounded px-2 py-1">
            {sun.isDay ? (
              <Sun className="h-4 w-4 text-accent" />
            ) : (
              <Moon className="h-4 w-4 text-primary" />
            )}
            <div className="text-[0.55rem] leading-tight">
              <div className="font-heading uppercase tracking-widest text-foreground">
                {sun.phase}
              </div>
              <div className="text-muted-foreground">
                SUN ALT {sun.altitude.toFixed(1)}&deg;
              </div>
            </div>
          </div>
          <div className="hud-panel rounded px-2 py-1 text-right">
            <div className="font-display text-sm text-accent hud-glow-amber">
              {localTime}
            </div>
            <div className="text-[0.5rem] uppercase tracking-widest text-muted-foreground">
              Local Solar Time
            </div>
          </div>
        </div>
      )}

      {/* empty / loading state */}
      {(!place || loading) && (
        <div className="absolute inset-0 z-[450] flex flex-col items-center justify-center gap-3 bg-background/40 backdrop-blur-[1px]">
          {loading ? (
            <>
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
              <p className="font-heading text-xs uppercase tracking-widest text-primary">
                Acquiring orbital lock...
              </p>
            </>
          ) : (
            <p className="max-w-xs text-center text-xs text-muted-foreground">
              Say{' '}
              <span className="text-primary">
                &ldquo;Nancy, locate Tokyo&rdquo;
              </span>{' '}
              or type a place below to begin orbital recon.
            </p>
          )}
        </div>
      )}

      {/* descent status (while globe is flying in) */}
      {place && !loading && !showSatellite && descending && (
        <div className="pointer-events-none absolute inset-x-0 top-1/2 z-[450] flex -translate-y-1/2 justify-center">
          <div className="hud-panel rounded px-3 py-1.5">
            <p className="font-heading text-[0.6rem] uppercase tracking-[0.25em] text-primary hud-glow">
              Descending to surface...
            </p>
          </div>
        </div>
      )}

      {/* hint: scroll to dive / zoom out to return to orbit */}
      {place && !loading && !showSatellite && !descending && (
        <div className="pointer-events-none absolute inset-x-0 bottom-16 z-[450] flex justify-center">
          <div className="hud-panel rounded px-3 py-1.5">
            <p className="font-heading text-[0.55rem] uppercase tracking-[0.25em] text-primary/80">
              Scroll to dive into {place.name}
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

// Helper function to get color based on event significance
function getEventSignificanceColor(significance: 'high' | 'medium' | 'low'): string {
  const colors: Record<'high' | 'medium' | 'low', string> = {
    high: 'bg-primary/20 text-primary',
    medium: 'bg-accent/20 text-accent',
    low: 'bg-secondary/20 text-secondary'
  };
  return colors[significance];
}
