// Lightweight sun position + local time helpers for the map panel.
export interface SunInfo {
  altitude: number
  azimuth: number
  isDay: boolean
  phase: 'night' | 'dawn' | 'day' | 'dusk'
}

/** Rough solar altitude/azimuth using NOAA approximation. Good enough for HUD. */
export function getSunInfo(lat: number, lon: number, date = new Date()): SunInfo {
  const rad = Math.PI / 180
  const dayOfYear = Math.floor(
    (date.getTime() - Date.UTC(date.getUTCFullYear(), 0, 0)) / 86400000,
  )
  const decl = 23.44 * Math.sin(((360 / 365) * (dayOfYear - 81)) * rad)
  const utcHours =
    date.getUTCHours() + date.getUTCMinutes() / 60 + date.getUTCSeconds() / 3600
  const solarTime = utcHours + lon / 15
  const hourAngle = (solarTime - 12) * 15
  const altitude =
    Math.asin(
      Math.sin(lat * rad) * Math.sin(decl * rad) +
        Math.cos(lat * rad) * Math.cos(decl * rad) * Math.cos(hourAngle * rad),
    ) / rad
  const azimuth =
    (Math.atan2(
      Math.sin(hourAngle * rad),
      Math.cos(hourAngle * rad) * Math.sin(lat * rad) -
        Math.tan(decl * rad) * Math.cos(lat * rad),
    ) /
      rad +
      180) %
    360
  const isDay = altitude > 0
  let phase: SunInfo['phase'] = 'night'
  if (altitude > 6) phase = 'day'
  else if (altitude > -6 && altitude <= 6) phase = altitude >= 0 ? 'dusk' : 'dawn'
  return { altitude, azimuth, isDay, phase }
}

/**
 * Decide whether a location should render its night basemap given a solar-
 * altitude threshold (in degrees). Positive = above horizon.
 * Threshold of 0 = strict horizon. Values like -3 keep the night map on
 * during civil twilight; +3 flips to day slightly before sunrise.
 */
export function isNightAt(altitudeDeg: number, thresholdDeg = 0): boolean {
  return altitudeDeg <= thresholdDeg
}


/** Format local time at a given longitude. */
export function formatLocalTime(lon: number, date = new Date()): string {
  const offsetHours = Math.round(lon / 15)
  const local = new Date(date.getTime() + offsetHours * 3600 * 1000)
  return local.toUTCString().slice(17, 22)
}
