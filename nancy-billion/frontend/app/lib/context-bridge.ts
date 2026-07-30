import { z } from 'zod'

export const ContextPayloadSchema = z
  .object({
    requestId: z.string().min(1).optional(),
    schemaVersion: z.number().int().positive().default(1),
    bridgeStatus: z
      .enum(['connected', 'degraded', 'disconnected', 'unknown'])
      .optional(),
    /** Where this context event came from (e.g. 'dashboard'). The backend's
     * _live_context_bridge_context() reads this key by name. */
    source: z.string().max(64).optional(),
    /** The panel currently open in the control room ('voice-hero' when the
     * user is in the panel-less voice-first mode). Read by name by the
     * backend and injected into the live system prompt. */
    active_panel: z.string().max(64).nullable().optional(),
    /** Live voice-loop state so Nancy knows mid-conversation whether she is
     * currently speaking or thinking when a background channel pings her. */
    speaking: z.boolean().optional(),
    thinking: z.boolean().optional(),
    environmental: z
      .object({
        lighting: z.string().optional(),
        activity_level: z.string().optional(),
        obstacle_proximity: z.string().optional(),
      })
      .partial()
      .optional(),
    active_suggestions: z.number().int().nonnegative().optional(),
    extra: z.record(z.unknown()).optional(),
  })
  .strict()

export type ContextPayload = z.infer<typeof ContextPayloadSchema>

export type StoredContext = {
  payload: ContextPayload
  storedAt: string
  storedBy: 'frontend-api'
  ttlMs: number
  expiresAt: string
}

export type ContextMeta = {
  stored: boolean
  storedAt?: string
  expiresAt?: string
  ttlMs?: number
}

const DEFAULT_TTL_MS = 15_000

let latest: StoredContext | null = null

export function setLatestContext(payload: ContextPayload, ttlMs: number = DEFAULT_TTL_MS): StoredContext {
  const now = new Date()
  const expires = new Date(now.getTime() + ttlMs)

  latest = {
    payload,
    storedAt: now.toISOString(),
    storedBy: 'frontend-api',
    ttlMs,
    expiresAt: expires.toISOString(),
  }

  return latest
}

export function getLatestContext(): StoredContext | null {
  if (!latest) return null
  const now = Date.now()
  if (now > new Date(latest.expiresAt).getTime()) {
    latest = null
    return null
  }
  return latest
}

export function getContextMeta(): ContextMeta {
  const stored = getLatestContext()
  if (!stored) return { stored: false }
  return {
    stored: true,
    storedAt: stored.storedAt,
    expiresAt: stored.expiresAt,
    ttlMs: stored.ttlMs,
  }
}

export function validateContextPayload(input: unknown): ContextPayload {
  return ContextPayloadSchema.parse(input)
}

