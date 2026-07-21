/**
 * Economic calendar API client — talks to the Nancy/Billion backend's real
 * NFP/CPI/FOMC tracking (see backend/economic_calendar.py). Non-throwing,
 * same convention as agent-client.ts.
 */

import type { EconomicEvent } from './types'

const BASE = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000'

export interface EconomicCalendarResponse {
  success: boolean
  events: EconomicEvent[]
  tracked_releases: Record<string, string>
  configured: boolean
}

/** Fetch the live cached NFP/CPI/FOMC calendar (upcoming + recently released). */
export async function getEconomicCalendarEvents(): Promise<EconomicCalendarResponse> {
  try {
    const res = await fetch(`${BASE}/economic-calendar/events`, { cache: 'no-store' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return (await res.json()) as EconomicCalendarResponse
  } catch (err) {
    console.warn('[economic-calendar-client] fetch failed:', err)
    return { success: false, events: [], tracked_releases: {}, configured: false }
  }
}
