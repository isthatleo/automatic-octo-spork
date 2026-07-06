// Lightweight solar position math for day/night determination.
// Based on standard NOAA solar position approximations.

function toRad(d: number) {
  return (d * Math.PI) / 180
}
function toDeg(r: number) {
  return (r * 180) / Math.PI
}

export interface SunInfo {
  altitudeDeg: number
  isDay: boolean
  phase: 'day' | 'golden' | 'twilight' | 'night'
  localHour: number
}

/**
 * Compute the sun altitude (degrees above horizon) for a lat/lon at a given UTC date.
 */
export function getSunInfo(lat: number, lon: number, date = new Date()): SunInfo {
  const rad = Math.PI / 180

  const start = Date.UTC(date.getUTCFullYear(), 0, 0)
  const diff = date.getTime() - start
  const dayOfYear = Math.floor(diff / 86400000)

  const hoursUTC =
    date.getUTCHours() +
    date.getUTCMinutes() / 60 +
    date.getUTCSeconds() / 3600

  // Fractional year (radians)
  const gamma =
    ((2 * Math.PI) / 365) * (dayOfYear - 1 + (hoursUTC - 12) / 24)

  // Equation of time (minutes)
  const eqTime =
    229.18 *
    (0.000075 +
      0.001868 * Math.cos(gamma) -
      0.032077 * Math.sin(gamma) -
      0.014615 * Math.cos(2 * gamma) -
      0.040849 * Math.sin(2 * gamma))

  // Solar declination (radians)
  const decl =
    0.006918 -
    0.399912 * Math.cos(gamma) +
    0.070257 * Math.sin(gamma) -
    0.006758 * Math.cos(2 * gamma) +
    0.000907 * Math.sin(2 * gamma) -
    0.002697 * Math.cos(3 * gamma) +
    0.00148 * Math.sin(3 * gamma)

  const timeOffset = eqTime + 4 * lon
  const trueSolarTime = (hoursUTC * 60 + timeOffset) % 1440
  let ha = trueSolarTime / 4 - 180
  if (ha < -180) ha += 360

  const latR = lat * rad
  const haR = ha * rad

  const cosZenith =
    Math.sin(latR) * Math.sin(decl) +
    Math.cos(latR) * Math.cos(decl) * Math.cos(haR)
  const zenith = Math.acos(Math.max(-1, Math.min(1, cosZenith)))
  const altitude = 90 - toDeg(zenith)

  const localHour = ((lon / 15 + date.getUTCHours() + date.getUTCMinutes() / 60) % 24 + 24) % 24

  let phase: SunInfo['phase']
  if (altitude > 6) phase = 'day'
  else if (altitude > 0) phase = 'golden'
  else if (altitude > -6) phase = 'twilight'
  else phase = 'night'

  return {
    altitudeDeg: altitude,
    isDay: altitude > 0,
    phase,
    localHour,
  }
}

export function formatLocalTime(lon: number, date = new Date()): string {
  // Approximate local solar time from longitude (no DST/timezone db needed).
  const offsetHours = lon / 15
  const local = new Date(date.getTime() + offsetHours * 3600 * 1000)
  const h = local.getUTCHours().toString().padStart(2, '0')
  const m = local.getUTCMinutes().toString().padStart(2, '0')
  const s = local.getUTCSeconds().toString().padStart(2, '0')
  return `${h}:${m}:${s}`
}

export { toRad, toDeg }
