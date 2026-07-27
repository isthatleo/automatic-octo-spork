'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import type { Map as LeafletMap, Marker, Circle, Popup } from 'leaflet'
import { getSunInfo, formatLocalTime, isNightAt, type SunInfo } from '@/lib/nancy/sun'
import type { Place } from '@/lib/nancy/types'
import { GlobeView } from './globe-view'
import {
  Loader2, Crosshair, Sun, Moon, Globe2, BookOpen, SlidersHorizontal,
  Cloud, CloudRain, CloudSnow, CloudLightning, Wind, ExternalLink, MapPin, Search,
  LocateFixed, Navigation, Route as RouteIcon, RadioTower,
} from 'lucide-react'
import { cn } from '@/lib/utils'

/** Every client-side real-data fetch on this page goes through this --
 * bounds worst-case wait on a slow/unresponsive public API to `timeoutMs`
 * instead of letting one stalled free-tier service hold up the page
 * indefinitely. Failure still degrades gracefully (caller's .catch), this
 * just guarantees it fails *promptly*. */
function fetchWithTimeout(url: string, opts: RequestInit = {}, timeoutMs = 7000): Promise<Response> {
  const controller = new AbortController()
  const t = setTimeout(() => controller.abort(), timeoutMs)
  return fetch(url, { ...opts, signal: controller.signal }).finally(() => clearTimeout(t))
}

const WEATHER_CODES: Record<number, string> = {
  0: 'Clear sky', 1: 'Mainly clear', 2: 'Partly cloudy', 3: 'Overcast',
  45: 'Fog', 48: 'Depositing rime fog',
  51: 'Light drizzle', 53: 'Drizzle', 55: 'Dense drizzle',
  61: 'Slight rain', 63: 'Rain', 65: 'Heavy rain',
  71: 'Slight snow', 73: 'Snow', 75: 'Heavy snow',
  80: 'Rain showers', 81: 'Rain showers', 82: 'Violent rain showers',
  95: 'Thunderstorm', 96: 'Thunderstorm, hail', 99: 'Severe thunderstorm',
}

/** Real current conditions AND real elevation AND the real IANA timezone
 * name for the recon target, all from one direct Open-Meteo call
 * (`timezone=auto` resolves the actual zone at that coordinate) -- calling
 * Open-Meteo's public API directly instead of routing through our own
 * backend's weather agent, which added a real ~2s dispatch hop for the
 * same underlying data. One faster call, more real fields. */
interface PlaceWeather {
  temperature_c: number
  feelsLikeC: number
  humidityPct: number
  precipitationMm: number
  conditions: string
  windspeedKmh: number
  windDirectionDeg: number
  isDay: boolean
  elevationM: number
  timezone: string
  source: string
}
function usePlaceWeather(place: Place | null) {
  const [data, setData] = useState<PlaceWeather | null>(null)
  const [loading, setLoading] = useState(false)
  useEffect(() => {
    if (!place) {
      setData(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setData(null)
    const url =
      `https://api.open-meteo.com/v1/forecast?latitude=${place.lat}&longitude=${place.lon}` +
      `&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m,wind_direction_10m,is_day` +
      `&timezone=auto`
    fetchWithTimeout(url)
      .then((r) => (r.ok ? r.json() : null))
      .then((json) => {
        if (cancelled || !json?.current) return
        const c = json.current
        setData({
          temperature_c: c.temperature_2m,
          feelsLikeC: c.apparent_temperature,
          humidityPct: c.relative_humidity_2m,
          precipitationMm: c.precipitation,
          conditions: WEATHER_CODES[c.weather_code] ?? 'Unknown',
          windspeedKmh: c.wind_speed_10m,
          windDirectionDeg: c.wind_direction_10m,
          isDay: c.is_day === 1,
          elevationM: json.elevation,
          timezone: json.timezone,
          source: 'Open-Meteo',
        })
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [place?.lat, place?.lon])
  return { data, loading }
}

/** Real encyclopedic context for the recon target via Wikipedia's public
 * REST summary API (no key required, same "free public API, client-side"
 * pattern as the Nominatim geocoder) -- replaces the previous
 * "historicalEvents" panel, which had a full UI built for it but no code
 * path anywhere in the app ever populated that field, so it silently never
 * rendered. Degrades to nothing (not a fabricated placeholder) when no
 * article matches. */
interface PlaceSummary {
  title: string
  description?: string
  extract: string
  thumbnail?: string
  url: string
}
function usePlaceSummary(place: Place | null) {
  const [data, setData] = useState<PlaceSummary | null>(null)
  const [loading, setLoading] = useState(false)
  useEffect(() => {
    if (!place) {
      setData(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setData(null)
    fetchWithTimeout(`https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(place.name)}`, {
      headers: { Accept: 'application/json' },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((json) => {
        if (cancelled || !json || json.type === 'disambiguation') return
        if (typeof json.extract === 'string' && json.extract.length > 0) {
          setData({
            title: String(json.title ?? place.name),
            description: typeof json.description === 'string' ? json.description : undefined,
            extract: json.extract,
            thumbnail: json.thumbnail?.source,
            url: json.content_urls?.desktop?.page ?? `https://en.wikipedia.org/wiki/${encodeURIComponent(place.name)}`,
          })
        }
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [place?.name])
  return { data, loading }
}

/** Real device geolocation via the browser's native Geolocation API -- an
 * actual GPS/Wi-Fi/IP position fix, not a simulated one. `locateOnce` takes
 * a single fix; passing `tracking=true` switches to `watchPosition` for
 * genuine live position updates as the device actually moves. Heading and
 * speed are only ever real values the browser itself reports -- null
 * (shown as "N/A", never fabricated) on hardware that doesn't report them,
 * which is normal and expected on a desktop with no GPS. */
interface GeoFix {
  lat: number
  lon: number
  accuracy: number
  heading: number | null
  speed: number | null
  timestamp: number
}
function useGeolocation(tracking: boolean) {
  const [fix, setFix] = useState<GeoFix | null>(null)
  const [error, setError] = useState<string | null>(null)
  const watchId = useRef<number | null>(null)

  const toFix = (pos: GeolocationPosition): GeoFix => ({
    lat: pos.coords.latitude,
    lon: pos.coords.longitude,
    accuracy: pos.coords.accuracy,
    heading: pos.coords.heading,
    speed: pos.coords.speed,
    timestamp: pos.timestamp,
  })

  const locateOnce = useCallback(() => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setError('Geolocation is not supported by this browser')
      return
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => { setFix(toFix(pos)); setError(null) },
      (err) => setError(err.message || 'Location request failed'),
      { enableHighAccuracy: true, timeout: 10000 },
    )
  }, [])

  useEffect(() => {
    if (!tracking || typeof navigator === 'undefined' || !navigator.geolocation) return
    watchId.current = navigator.geolocation.watchPosition(
      (pos) => { setFix(toFix(pos)); setError(null) },
      (err) => setError(err.message || 'Live tracking failed'),
      { enableHighAccuracy: true },
    )
    return () => {
      if (watchId.current != null) navigator.geolocation.clearWatch(watchId.current)
      watchId.current = null
    }
  }, [tracking])

  return { fix, error, locateOnce }
}

/** Real reverse geocode of a live fix into a human place name (Nominatim,
 * same free no-key service as the forward geocoder) -- rounded to ~1km
 * before it becomes an effect dependency so continuous live-tracking
 * updates don't hammer the public API on every GPS jitter. */
function useReverseGeocode(lat: number | undefined, lon: number | undefined): string | null {
  const rLat = lat != null ? Math.round(lat * 100) / 100 : null
  const rLon = lon != null ? Math.round(lon * 100) / 100 : null
  const [label, setLabel] = useState<string | null>(null)
  useEffect(() => {
    if (rLat == null || rLon == null) {
      setLabel(null)
      return
    }
    let cancelled = false
    fetchWithTimeout(`https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${rLat}&lon=${rLon}&zoom=10&accept-language=en`, {
      headers: { Accept: 'application/json' },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((json) => {
        if (cancelled || !json) return
        const addr = json.address ?? {}
        const name = addr.city || addr.town || addr.village || addr.county || addr.state || json.display_name?.split(',')[0]
        if (name) setLabel(`${name}${addr.country ? `, ${addr.country}` : ''}`)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [rLat, rLon])
  return label
}

/** Real driving route between two points via OSRM's public routing API
 * (router.project-osrm.org -- free, no key, the same engine behind
 * Leaflet Routing Machine's default demo setup). Returns the actual road
 * geometry, distance, and duration -- never a straight-line guess. Origin
 * is rounded to ~110m before it affects the fetch, so live tracking's
 * continuous position updates don't refetch a full route on every GPS
 * jitter -- only on real movement. */
interface RouteInfo {
  distanceKm: number
  durationMin: number
  coordinates: [number, number][]
}
function useRoute(origin: { lat: number; lon: number } | null, destination: { lat: number; lon: number } | null) {
  const [route, setRoute] = useState<RouteInfo | null>(null)
  const [loading, setLoading] = useState(false)
  const oLat = origin ? Math.round(origin.lat * 1000) / 1000 : null
  const oLon = origin ? Math.round(origin.lon * 1000) / 1000 : null
  useEffect(() => {
    if (oLat == null || oLon == null || !destination) {
      setRoute(null)
      return
    }
    let cancelled = false
    setLoading(true)
    const url = `https://router.project-osrm.org/route/v1/driving/${oLon},${oLat};${destination.lon},${destination.lat}?overview=full&geometries=geojson`
    fetchWithTimeout(url)
      .then((r) => (r.ok ? r.json() : null))
      .then((json) => {
        if (cancelled || !json || json.code !== 'Ok' || !json.routes?.[0]) return
        const r = json.routes[0]
        setRoute({
          distanceKm: r.distance / 1000,
          durationMin: r.duration / 60,
          coordinates: r.geometry.coordinates.map(([lon, lat]: [number, number]) => [lat, lon] as [number, number]),
        })
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [oLat, oLon, destination?.lat, destination?.lon])
  return { route, loading }
}

/** Maps Open-Meteo's plain-text condition string to a representative icon
 * -- purely presentational, the text itself is the real data. */
function WeatherIcon({ conditions, className }: { conditions: string; className?: string }) {
  const c = conditions.toLowerCase()
  if (c.includes('thunder')) return <CloudLightning className={className} />
  if (c.includes('snow')) return <CloudSnow className={className} />
  if (c.includes('rain') || c.includes('drizzle') || c.includes('shower')) return <CloudRain className={className} />
  if (c.includes('cloud') || c.includes('overcast') || c.includes('fog')) return <Cloud className={className} />
  return <Sun className={className} />
}

/** Real search history -- every place actually resolved by the geocoder,
 * persisted locally, most recent first. Replaces the old static "say X or
 * type below" instruction with genuine, recallable content in the idle
 * state instead of a one-line caption pointing at a control that isn't
 * even on this page. */
const RECON_HISTORY_KEY = 'nancy.reconHistory'
interface ReconHistoryEntry {
  name: string
  country?: string
}
function useReconHistory(place: Place | null): ReconHistoryEntry[] {
  const [history, setHistory] = useState<ReconHistoryEntry[]>([])

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      const raw = window.localStorage.getItem(RECON_HISTORY_KEY)
      if (raw) setHistory(JSON.parse(raw))
    } catch {
      /* ignore corrupt entry */
    }
  }, [])

  useEffect(() => {
    if (!place || typeof window === 'undefined') return
    setHistory((prev) => {
      const next = [{ name: place.name, country: place.country }, ...prev.filter((h) => h.name !== place.name)].slice(0, 8)
      try {
        window.localStorage.setItem(RECON_HISTORY_KEY, JSON.stringify(next))
      } catch {
        /* quota / private mode -- ignore */
      }
      return next
    })
  }, [place?.name, place?.country])

  return history
}

/** A handful of starter suggestions shown only before any real search
 * history exists -- once the user has actually looked anything up, their
 * own real history (above) replaces these entirely. */
const RECON_STARTERS: ReconHistoryEntry[] = [
  { name: 'Tokyo' }, { name: 'New York' }, { name: 'London' }, { name: 'Sydney' }, { name: 'Reykjavík' },
]

/** Real, always-present search control -- the actionable replacement for
 * an instruction sentence that pointed at a voice/console input the user
 * might not even have open. Submits through the same real geocoder
 * (Nominatim, via page.tsx's `locate`) that voice commands use. */
function ReconSearchBar({ onLocate, loading }: { onLocate?: (query: string) => void; loading: boolean }) {
  const [query, setQuery] = useState('')
  const submit = () => {
    const q = query.trim()
    if (!q || !onLocate) return
    onLocate(q)
  }
  return (
    <div className="pointer-events-auto absolute left-1/2 top-3 z-[520] flex w-[min(92%,26rem)] -translate-x-1/2 items-center gap-2 rounded-full border border-primary/30 bg-background/75 px-3 py-1.5 backdrop-blur-sm">
      <Search className="h-3.5 w-3.5 shrink-0 text-primary" />
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') submit()
        }}
        disabled={loading}
        placeholder="Recon a place — try “Kyoto” or “Reykjavík”"
        className="w-full bg-transparent text-[0.7rem] text-foreground placeholder:text-muted-foreground/70 focus:outline-none disabled:opacity-50"
      />
      <button
        type="button"
        onClick={submit}
        disabled={loading || !query.trim()}
        className="shrink-0 rounded-full bg-primary/15 px-2.5 py-1 text-[0.55rem] text-primary transition-colors hover:bg-primary/25 disabled:opacity-40"
      >
        {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Locate'}
      </button>
    </div>
  )
}

/** Recent-recon chips (or starter suggestions before any real history
 * exists) -- one click re-runs the same real geocode as typing the name. */
function ReconHistoryRow({ history, onLocate }: { history: ReconHistoryEntry[]; onLocate?: (query: string) => void }) {
  const items = history.length > 0 ? history : RECON_STARTERS
  return (
    <div className="pointer-events-auto absolute left-0 right-0 top-14 z-[510] flex flex-wrap items-center justify-center gap-1.5 px-6">
      <span className="mr-1 text-[0.5rem] tracking-[0.2em] text-muted-foreground/70">
        {history.length > 0 ? 'RECENT RECON' : 'TRY'}
      </span>
      {items.map((h) => (
        <button
          key={h.name}
          type="button"
          onClick={() => onLocate?.(h.name)}
          className="rounded-full border border-border/60 bg-background/60 px-2.5 py-1 text-[0.55rem] text-muted-foreground backdrop-blur-sm transition-colors hover:border-primary/50 hover:text-primary"
        >
          {h.name}
        </button>
      ))}
    </div>
  )
}

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
  onLocate,
}: {
  place: Place | null
  loading: boolean
  /** Runs a real geocode + fly-to for a typed query -- the same function
   * voice commands ("Nancy, locate Tokyo") already use, threaded down from
   * page.tsx so the search bar and history chips share one real code path
   * rather than duplicating geocoding logic here. */
  onLocate?: (query: string) => void
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<LeafletMap | null>(null)
  const markerRef = useRef<Marker | null>(null)
  const ringRef = useRef<Circle | null>(null)
  // Real geolocation/routing overlays -- self-location marker, its GPS
  // accuracy circle, and the live driving-route polyline to the current
  // target, all drawn on the real Leaflet map (not the orbital globe: a
  // straight/road route only reads correctly once you're at surface level).
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const selfMarkerRef = useRef<any>(null)
  const selfAccuracyRef = useRef<Circle | null>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const routeLineRef = useRef<any>(null)
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
  const [displayOpen, setDisplayOpen] = useState(false)

  const history = useReconHistory(place)
  const { data: weather } = usePlaceWeather(place)
  const { data: summary } = usePlaceSummary(place)

  // Real geolocation + live tracking + routing -- see useGeolocation/
  // useReverseGeocode/useRoute above for exactly what's real vs. honestly
  // reported as unavailable.
  const [locateOpen, setLocateOpen] = useState(false)
  const [tracking, setTracking] = useState(false)
  const { fix: myFix, error: geoError, locateOnce } = useGeolocation(tracking)
  const myLabel = useReverseGeocode(myFix?.lat, myFix?.lon)
  const { route } = useRoute(myFix, place)

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

  // Real self-location marker + GPS accuracy circle on the surface map --
  // updates live while `tracking` is on, since myFix itself updates live.
  useEffect(() => {
    if (!ready || !mapRef.current) return
    let cancelled = false
    ;(async () => {
      const L = (await import('leaflet')).default
      if (cancelled) return
      const map = mapRef.current
      if (!map) return
      selfMarkerRef.current?.remove()
      selfAccuracyRef.current?.remove()
      selfMarkerRef.current = null
      selfAccuracyRef.current = null
      if (!myFix) return
      const icon = L.divIcon({
        className: '',
        html: `<div style="
          width:14px;height:14px;border-radius:50%;
          border:2px solid oklch(0.78 0.14 200);
          box-shadow:0 0 10px oklch(0.78 0.14 200),inset 0 0 5px oklch(0.78 0.14 200);
          background:oklch(0.78 0.14 200 / 40%);
        "></div>`,
        iconSize: [14, 14],
        iconAnchor: [7, 7],
      })
      selfMarkerRef.current = L.marker([myFix.lat, myFix.lon], { icon, zIndexOffset: 600 }).addTo(map)
      selfAccuracyRef.current = L.circle([myFix.lat, myFix.lon], {
        radius: myFix.accuracy,
        color: 'oklch(0.78 0.14 200)',
        weight: 1,
        fillOpacity: 0.06,
        dashArray: '2 6',
      }).addTo(map)
    })()
    return () => {
      cancelled = true
    }
  }, [ready, myFix?.lat, myFix?.lon, myFix?.accuracy])

  // Real OSRM driving route from your live location to the current recon
  // target, drawn as an actual road polyline (never a straight line).
  useEffect(() => {
    if (!ready || !mapRef.current) return
    let cancelled = false
    ;(async () => {
      const L = (await import('leaflet')).default
      if (cancelled) return
      const map = mapRef.current
      if (!map) return
      routeLineRef.current?.remove()
      routeLineRef.current = null
      if (!route) return
      routeLineRef.current = L.polyline(route.coordinates, {
        color: 'oklch(0.82 0.16 210)',
        weight: 3,
        opacity: 0.85,
      }).addTo(map)
    })()
    return () => {
      cancelled = true
    }
  }, [ready, route])

  const showSatellite = phase === 'satellite'


  return (
    <div className="hud-panel relative h-full min-h-[560px] overflow-hidden rounded-md">
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

      {/* Real search bar -- a genuine, always-visible affordance for
          starting a recon, replacing an instructional sentence that used to
          sit permanently in the center of the globe telling you to use a
          different, invisible control elsewhere on the page. */}
      <ReconSearchBar onLocate={onLocate} loading={loading} />

      {/* Mode readout once a target exists; while idle, the space below the
          search bar instead shows real recent-recon history (or starter
          suggestions on first use) -- an actionable list, not a caption. */}
      {place ? (
        <div className="pointer-events-none absolute left-0 right-0 top-14 z-[500] flex items-start justify-center p-3">
          <div className="hud-panel rounded px-2 py-1 mx-auto">
            <div className="flex items-center gap-1.5 font-heading text-[0.6rem] tracking-[0.22em] text-primary">
              {showSatellite ? <Crosshair className="h-3 w-3" /> : <Globe2 className="h-3 w-3" />}
              {showSatellite ? (nightMode ? 'Surface Recon · Night' : 'Surface Recon · Day') : 'Orbital View'}
            </div>
          </div>
        </div>
      ) : (
        !loading && <ReconHistoryRow history={history} onLocate={onLocate} />
      )}

      {/* Display control: real day/night layer override + solar threshold --
          previously framed as a hidden "debug" panel behind a bug icon, so
          a genuinely useful layer control (OSINT-style map tooling should
          make its layer controls discoverable, not bury them) went unseen
          by anyone who didn't already know it existed. Same functionality,
          promoted to a first-class, clearly labeled control. */}
      <div className="absolute right-3 top-14 z-[520] flex flex-col items-end gap-1">
        <button
          type="button"
          onClick={() => setDisplayOpen((v) => !v)}
          className="hud-panel flex items-center gap-1.5 rounded px-2 py-1 text-[0.55rem] text-primary transition-colors hover:bg-primary/10"
          title="Display settings — day/night layer override"
        >
          <SlidersHorizontal className="h-3 w-3" />
          {nightMode ? 'Night' : 'Day'} · {sun ? `${sun.altitude.toFixed(1)}°` : '—'}
        </button>
        {displayOpen && (
          <div className="hud-panel w-64 rounded p-2 text-[0.55rem]">
            <div className="mb-1 flex items-center justify-between">
              <span className="font-heading text-primary">Basemap Mode</span>
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
                    'rounded border px-1.5 py-1 text-[0.5rem] transition-colors',
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
              <span className="font-heading text-primary">Night Threshold</span>
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
              <span className="text-right text-primary">{sun?.phase ?? '—'}</span>
              <span>Auto → Night</span>
              <span className="text-right text-accent">{autoNight ? 'YES' : 'NO'}</span>
              <span>Rendered</span>
              <span className="text-right text-accent">{nightMode ? 'night' : 'day'}</span>
            </div>
            <p className="mt-2 text-[0.5rem] leading-tight text-muted-foreground">
              Threshold sets solar altitude at which night tiles engage. −6° = civil twilight, 0° = horizon.
            </p>
          </div>
        )}
      </div>

      {/* My Location: real browser Geolocation, live tracking via
          watchPosition, and a real OSRM driving route to the current recon
          target -- the actual "where am I / where's that / how do I get
          there" trio, not a simulated position. */}
      <div className="absolute right-3 top-24 z-[520] flex flex-col items-end gap-1">
        <button
          type="button"
          onClick={() => {
            setLocateOpen((v) => !v)
            if (!myFix) locateOnce()
          }}
          className="hud-panel flex items-center gap-1.5 rounded px-2 py-1 text-[0.55rem] text-primary transition-colors hover:bg-primary/10"
          title="My location — real device geolocation"
        >
          {tracking ? <RadioTower className="h-3 w-3 animate-pulse" /> : <LocateFixed className="h-3 w-3" />}
          {myFix ? (tracking ? 'Tracking' : 'Located') : 'My Location'}
        </button>
        {locateOpen && (
          <div className="hud-panel w-64 rounded p-2 text-[0.55rem]">
            <div className="mb-1.5 flex items-center justify-between">
              <span className="font-heading text-primary">Device Geolocation</span>
              <button
                type="button"
                onClick={locateOnce}
                className="rounded border border-border/60 px-1.5 py-0.5 text-[0.5rem] text-muted-foreground hover:border-primary/50 hover:text-primary"
              >
                Refresh
              </button>
            </div>
            {geoError ? (
              <p className="text-[0.5rem] leading-tight text-destructive">{geoError}</p>
            ) : myFix ? (
              <div className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-muted-foreground">
                <span>Near</span>
                <span className="text-right text-primary">{myLabel ?? '…'}</span>
                <span>Coords</span>
                <span className="text-right text-primary">{myFix.lat.toFixed(4)}, {myFix.lon.toFixed(4)}</span>
                <span>Accuracy</span>
                <span className="text-right text-accent">±{myFix.accuracy.toFixed(0)} m</span>
                <span>Heading</span>
                <span className="text-right text-accent">{myFix.heading != null ? `${myFix.heading.toFixed(0)}°` : 'N/A'}</span>
                <span>Speed</span>
                <span className="text-right text-accent">{myFix.speed != null ? `${(myFix.speed * 3.6).toFixed(1)} km/h` : 'N/A'}</span>
              </div>
            ) : (
              <p className="text-[0.5rem] leading-tight text-muted-foreground">Requesting a fix…</p>
            )}
            <button
              type="button"
              onClick={() => setTracking((v) => !v)}
              className={cn(
                'mt-2 flex w-full items-center justify-center gap-1.5 rounded border px-1.5 py-1 text-[0.5rem] transition-colors',
                tracking
                  ? 'border-primary bg-primary/20 text-primary'
                  : 'border-border/60 text-muted-foreground hover:border-primary/50',
              )}
            >
              <Navigation className="h-2.5 w-2.5" /> Live Tracking: {tracking ? 'ON' : 'OFF'}
            </button>
            <p className="mt-1.5 text-[0.48rem] leading-tight text-muted-foreground">
              Real GPS/Wi-Fi position from this browser. Heading/speed read N/A on hardware that doesn't report them (normal on desktop).
            </p>
          </div>
        )}
      </div>

      {/* Target lock — real place identification, source-attributed per
          OSINT sourcing conventions (a coordinate is only as trustworthy as
          its provenance, so the geocoder is named, not left implicit). */}
      {place && (
        <div className="pointer-events-none absolute left-3 top-14 z-[500] w-64">
          <div className="relative border border-primary/40 bg-background/70 px-3 py-2 backdrop-blur-sm">
            <span className="absolute -left-px -top-px h-2.5 w-2.5 border-l border-t border-primary" />
            <span className="absolute -right-px -top-px h-2.5 w-2.5 border-r border-t border-primary" />
            <span className="absolute -bottom-px -left-px h-2.5 w-2.5 border-b border-l border-primary" />
            <span className="absolute -bottom-px -right-px h-2.5 w-2.5 border-b border-r border-primary" />
            <div className="text-[0.5rem] tracking-[0.25em] text-primary/70">Target Lock</div>
            <div className="mt-0.5 truncate font-heading text-sm text-foreground">
              {place.name}
            </div>
            <div className="truncate text-[0.55rem] text-muted-foreground">
              {place.country}
            </div>
            <div className="mt-1 flex items-center gap-1 text-[0.45rem] text-muted-foreground/70">
              <MapPin className="h-2.5 w-2.5" /> Source: OpenStreetMap Nominatim
            </div>
          </div>

          {/* Environment -- real elevation + real IANA timezone + feels-like
              + humidity, all from the same single Open-Meteo call behind
              the footer's weather segment (usePlaceWeather) -- previously
              unused fields from that response now get their own real
              readout instead of being discarded. */}
          {weather && (
            <div className="relative mt-1.5 border border-border/50 bg-background/70 px-3 py-2 backdrop-blur-sm">
              <div className="mb-1.5 flex items-center gap-1.5 text-[0.5rem] tracking-[0.2em] text-primary">
                <Cloud className="h-3 w-3" /> Environment
              </div>
              <div className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-[0.55rem] text-muted-foreground">
                <span>Elevation</span>
                <span className="text-right text-primary">{weather.elevationM.toFixed(0)} m</span>
                <span>Timezone</span>
                <span className="text-right text-primary">{weather.timezone}</span>
                <span>Feels like</span>
                <span className="text-right text-accent">{weather.feelsLikeC.toFixed(0)}&deg;C</span>
                <span>Humidity</span>
                <span className="text-right text-accent">{weather.humidityPct.toFixed(0)}%</span>
              </div>
              <div className="mt-1 flex items-center gap-1 text-[0.45rem] text-muted-foreground/70">
                <MapPin className="h-2.5 w-2.5" /> Source: Open-Meteo
              </div>
            </div>
          )}

          {/* Field Notes — real Wikipedia summary of the recon target
              (usePlaceSummary), replacing a "Historical Intel" panel that
              had a full UI but no data source anywhere in the app ever
              feeding it. Hidden entirely (not a placeholder) when no
              article matches, same graceful-degrade as every other real
              data source in this app. */}
          {summary && (
            <div className="relative mt-1.5 max-h-72 overflow-y-auto border border-border/50 bg-background/70 px-3 py-2 backdrop-blur-sm">
              <div className="mb-1.5 flex items-center gap-1.5 text-[0.5rem] tracking-[0.2em] text-primary">
                <BookOpen className="h-3 w-3" /> Field Notes
              </div>
              {summary.thumbnail && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={summary.thumbnail} alt="" className="mb-1.5 h-20 w-full rounded object-cover" />
              )}
              {summary.description && (
                <p className="mb-1 text-[0.5rem] italic text-primary/80">{summary.description}</p>
              )}
              <p className="line-clamp-6 text-[0.55rem] leading-snug text-muted-foreground">
                {summary.extract}
              </p>
              <a
                href={summary.url}
                target="_blank"
                rel="noreferrer"
                className="pointer-events-auto mt-1.5 flex items-center gap-1 text-[0.45rem] text-primary/80 hover:text-primary"
              >
                <ExternalLink className="h-2.5 w-2.5" /> Source: Wikipedia
              </a>
            </div>
          )}
        </div>
      )}

      {/* footer telemetry — a single instrument-cluster strip: coordinates,
          live weather (Open-Meteo, direct), sun position, local solar time,
          and -- once a route exists -- real driving distance/duration.
          All real, source-attributed data, no fabricated readouts. */}
      {place && sun && (
        <div className="pointer-events-none absolute bottom-0 left-0 right-0 z-[500] flex justify-center p-3">
          <div className="flex items-stretch divide-x divide-border/50 border border-border/50 bg-background/70 text-[0.55rem] backdrop-blur-sm">
            <div className="flex flex-col justify-center gap-0.5 px-3 py-1.5 leading-relaxed text-muted-foreground">
              <div>
                LAT{' '}
                <span className="text-primary">{place.lat.toFixed(4)}</span>
              </div>
              <div>
                LON{' '}
                <span className="text-primary">{place.lon.toFixed(4)}</span>
              </div>
            </div>
            {weather && (
              <div className="flex items-center gap-2 px-3 py-1.5" title={`Source: ${weather.source} · feels like ${weather.feelsLikeC.toFixed(0)}°C, ${weather.humidityPct.toFixed(0)}% humidity`}>
                <WeatherIcon conditions={weather.conditions} className="h-4 w-4 text-accent" />
                <div className="leading-tight">
                  <div className="font-heading text-foreground">
                    {weather.temperature_c.toFixed(0)}&deg;C · {weather.conditions}
                  </div>
                  <div className="text-muted-foreground">
                    <Wind className="mr-1 inline h-2.5 w-2.5" />{weather.windspeedKmh.toFixed(0)} km/h
                  </div>
                </div>
              </div>
            )}
            <div className="flex items-center gap-2 px-3 py-1.5">
              {sun.isDay ? (
                <Sun className="h-4 w-4 text-accent" />
              ) : (
                <Moon className="h-4 w-4 text-primary" />
              )}
              <div className="leading-tight">
                <div className="font-heading text-foreground">
                  {sun.phase}
                </div>
                <div className="text-muted-foreground">
                  SUN ALT {sun.altitude.toFixed(1)}&deg;
                </div>
              </div>
            </div>
            <div className="flex flex-col justify-center px-3 py-1.5 text-right">
              <div className="font-display text-sm text-accent">
                {localTime}
              </div>
              <div className="text-[0.5rem] text-muted-foreground">
                Local Solar Time
              </div>
            </div>
            {route && (
              <div className="flex items-center gap-2 px-3 py-1.5" title="Source: OSRM (driving profile)">
                <RouteIcon className="h-4 w-4 text-primary" />
                <div className="leading-tight">
                  <div className="font-heading text-foreground">
                    {route.distanceKm.toFixed(0)} km · {route.durationMin < 60 ? `${route.durationMin.toFixed(0)}m` : `${(route.durationMin / 60).toFixed(1)}h`}
                  </div>
                  <div className="text-muted-foreground">Route from you</div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* loading state -- the idle "say X or type below" sentence that used
          to sit here permanently, blocking the center of the globe, is gone;
          the search bar + recent-recon row above now give the idle state a
          real, actionable affordance instead of an instruction to use a
          different, invisible control elsewhere on the page. */}
      {loading && (
        <div className="absolute inset-0 z-[450] flex flex-col items-center justify-center gap-3 bg-background/40 backdrop-blur-[1px]">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="font-heading text-xs text-primary">
            Acquiring orbital lock...
          </p>
        </div>
      )}

      {/* descent status (while globe is flying in) */}
      {place && !loading && !showSatellite && descending && (
        <div className="pointer-events-none absolute inset-x-0 top-1/2 z-[450] flex -translate-y-1/2 justify-center">
          <div className="hud-panel rounded px-3 py-1.5">
            <p className="font-heading text-[0.6rem] tracking-[0.25em] text-primary">
              Descending to surface...
            </p>
          </div>
        </div>
      )}

      {/* hint: scroll to dive / zoom out to return to orbit */}
      {place && !loading && !showSatellite && !descending && (
        <div className="pointer-events-none absolute inset-x-0 bottom-16 z-[450] flex justify-center">
          <div className="hud-panel rounded px-3 py-1.5">
            <p className="font-heading text-[0.55rem] tracking-[0.25em] text-primary/80">
              Scroll to dive into {place.name}
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
