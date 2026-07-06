import { z } from 'zod'

export const ContextPayloadSchema = z
  .object({
    // Client-provided correlation
    requestId: z.string().min(1).optional(),

    // Versioning for forward compatibility
    schemaVersion: z.number().int().positive().default(1),

    // Optional top-level status
    bridgeStatus: z
      .enum(['connected', 'degraded', 'disconnected', 'unknown'])
      .optional(),

    // Arbitrary contextual signals
    environmental: z
      .object({
        lighting: z.string().optional(),
        activity_level: z.string().optional(),
        obstacle_proximity: z.string().optional(),
      })
      .partial()
      .optional(),

    active_suggestions: z.number().int().nonnegative().optional(),

    // Client can attach any other structured state
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

// In-memory store (production note: swap with Redis/Postgres in multi-instance)
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


