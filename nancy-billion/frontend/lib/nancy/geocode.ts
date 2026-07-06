import type { Place } from './types'

/**
 * Free geocoding via OpenStreetMap Nominatim. No API key required.
 * Uses structured address details so cities, towns, villages and countries
 * all resolve to the correct, human-readable name + parent country.
 */
export async function geocode(query: string): Promise<Place | null> {
  const q = query.trim()
  if (!q) return null

  const url =
    `https://nominatim.openstreetmap.org/search` +
    `?format=jsonv2&addressdetails=1&accept-language=en&limit=1` +
    `&q=${encodeURIComponent(q)}`

  try {
    const res = await fetch(url, { headers: { Accept: 'application/json' } })
    if (!res.ok) return null

    const data = (await res.json()) as Array<{
      lat: string
      lon: string
      name?: string
      display_name: string
      address?: Record<string, string>
    }>
    if (!Array.isArray(data) || data.length === 0) return null

    const top = data[0]
    const addr = top.address ?? {}

    // Prefer the most specific populated-place label available.
    const name =
      top.name ||
      addr.city ||
      addr.town ||
      addr.village ||
      addr.municipality ||
      addr.county ||
      addr.state ||
      addr.country ||
      top.display_name.split(',')[0].trim()

    const country =
      addr.country || top.display_name.split(',').pop()?.trim() || undefined

    const lat = Number.parseFloat(top.lat)
    const lon = Number.parseFloat(top.lon)
    if (Number.isNaN(lat) || Number.isNaN(lon)) return null

    return { name, country, lat, lon }
  } catch {
    return null
  }
}
