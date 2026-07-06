'use client'

import { useEffect, useRef } from 'react'
import type { Place } from '@/lib/nancy/types'

const EARTH_TEXTURE =
  'https://unpkg.com/three-globe/example/img/earth-blue-marble.jpg'
const EARTH_BUMP =
  'https://unpkg.com/three-globe/example/img/earth-topology.png'
const NIGHT_BACKGROUND =
  'https://unpkg.com/three-globe/example/img/night-sky.png'

const HUD_CYAN = 'rgb(56, 211, 235)'
const HUD_AMBER = 'rgb(232, 178, 70)'

// Altitude (globe.gl POV units) at which a manual zoom-in "dives" into the
// satellite surface view.
const DIVE_ALTITUDE = 0.55
// Wide orbital altitude used when returning to the globe via zoom-out.
const ORBIT_ALTITUDE = 2.2

export function GlobeView({
  place,
  active,
  onArrive,
  onDive,
}: {
  /** Target place to fly to. */
  place: Place | null
  /** Whether the globe phase is currently visible/animating. */
  active: boolean
  /** Fired once the automated descent toward the city completes. */
  onArrive?: () => void
  /** Fired when the user manually zooms the globe in past the dive threshold. */
  onDive?: () => void
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const globeRef = useRef<any>(null)
  const arriveTimers = useRef<number[]>([])
  const lastPlaceKey = useRef<string | null>(null)
  const prevActive = useRef(false)
  const reducedMotion = useRef(false)
  const dived = useRef(false)

  // Keep the latest props reachable from the persistent onZoom handler.
  const placeRef = useRef<Place | null>(place)
  const activeRef = useRef(active)
  const onDiveRef = useRef(onDive)
  placeRef.current = place
  activeRef.current = active
  onDiveRef.current = onDive

  // Init globe once
  useEffect(() => {
    let cancelled = false
    reducedMotion.current =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches

    ;(async () => {
      const Globe = (await import('globe.gl')).default
      if (cancelled || !containerRef.current || globeRef.current) return

      const el = containerRef.current
      const globe = new Globe(el, { animateIn: true })
        .globeImageUrl(EARTH_TEXTURE)
        .bumpImageUrl(EARTH_BUMP)
        .backgroundImageUrl(NIGHT_BACKGROUND)
        .showAtmosphere(true)
        .atmosphereColor(HUD_CYAN)
        .atmosphereAltitude(0.22)
        .pointOfView({ lat: 20, lng: 10, altitude: 2.6 }, 0)

      // rings for the pulsing target marker
      globe
        .ringColor(() => HUD_CYAN)
        .ringMaxRadius(5)
        .ringPropagationSpeed(3)
        .ringRepeatPeriod(900)

      // glowing point marker
      globe
        .pointColor(() => HUD_AMBER)
        .pointAltitude(0.01)
        .pointRadius(0.4)

      const controls = globe.controls()
      controls.enableZoom = true
      controls.autoRotate = !reducedMotion.current
      controls.autoRotateSpeed = 0.35

      // Detect a manual zoom-in past the dive threshold → hand off to satellite.
      globe.onZoom((pov: { lat: number; lng: number; altitude: number }) => {
        if (
          activeRef.current &&
          placeRef.current &&
          !dived.current &&
          pov.altitude < DIVE_ALTITUDE
        ) {
          dived.current = true
          onDiveRef.current?.()
        }
      })

      const resize = () => {
        if (!el) return
        globe.width(el.clientWidth)
        globe.height(el.clientHeight)
      }
      resize()
      const ro = new ResizeObserver(resize)
      ro.observe(el)

      globeRef.current = { globe, controls, ro }
    })()

    return () => {
      cancelled = true
      arriveTimers.current.forEach((t) => clearTimeout(t))
      arriveTimers.current = []
      const ref = globeRef.current
      if (ref) {
        try {
          ref.ro?.disconnect()
          ref.globe?._destructor?.()
        } catch {
          /* ignore */
        }
        if (containerRef.current) containerRef.current.innerHTML = ''
        globeRef.current = null
      }
    }
  }, [])

  // Choreography: new place → rotate + descend; zoom-out re-entry → ascend.
  useEffect(() => {
    const ref = globeRef.current
    if (!ref) return

    if (!active) {
      prevActive.current = false
      return
    }

    const { globe, controls } = ref
    const key = place
      ? `${place.lat.toFixed(3)},${place.lon.toFixed(3)}`
      : null
    const placeChanged = key !== null && key !== lastPlaceKey.current
    const reentered = !prevActive.current
    prevActive.current = true
    dived.current = false

    arriveTimers.current.forEach((t) => clearTimeout(t))
    arriveTimers.current = []

    // Brand-new target: run the full rotate → descend cinematic.
    if (placeChanged && place) {
      lastPlaceKey.current = key

      globe.ringsData([{ lat: place.lat, lng: place.lon }])
      globe.pointsData([{ lat: place.lat, lng: place.lon }])
      controls.autoRotate = false

      if (reducedMotion.current) {
        globe.pointOfView(
          { lat: place.lat, lng: place.lon, altitude: 0.35 },
          0,
        )
        onArrive?.()
        return
      }

      // Phase 1: rotate to bring the country into view.
      const rotateMs = 1800
      globe.pointOfView(
        { lat: place.lat, lng: place.lon, altitude: ORBIT_ALTITUDE },
        rotateMs,
      )

      // Phase 2: descend toward the city surface.
      const descendMs = 1700
      const t1 = window.setTimeout(() => {
        globe.pointOfView(
          { lat: place.lat, lng: place.lon, altitude: 0.25 },
          descendMs,
        )
      }, rotateMs + 250)

      const t2 = window.setTimeout(() => {
        onArrive?.()
      }, rotateMs + 250 + descendMs)

      arriveTimers.current.push(t1, t2)
      return
    }

    // Returned to the globe via zoom-out: ascend smoothly to orbital view.
    if (reentered && place) {
      controls.autoRotate = !reducedMotion.current
      globe.pointOfView(
        { lat: place.lat, lng: place.lon, altitude: ORBIT_ALTITUDE },
        1200,
      )
    }
  }, [place, active, onArrive])

  return <div ref={containerRef} className="absolute inset-0 z-0" />
}
