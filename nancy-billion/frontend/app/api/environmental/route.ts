import { NextResponse } from 'next/server'
import {
  ContextPayloadSchema,
  getLatestContext,
  setLatestContext,
  validateContextPayload,
} from '@/app/lib/context-bridge'

// Local environmental endpoint that feeds the same context bridge used by /api/context.
// Best-effort forward to backend is handled by the context route (not repeated here).

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as unknown

    // Environmental route accepts either full ContextPayload or a partial environmental payload.
    // Normalize into ContextPayload for storage.
    const parsed = (() => {
      try {
        // If it already matches full schema, keep it.
        return validateContextPayload(body)
      } catch {
        // Otherwise build a minimal payload.
        const obj = body as Record<string, unknown>
        const environmental = obj?.environmental
        const payload = {
          schemaVersion: 1,
          environmental: environmental && typeof environmental === 'object' ? (environmental as any) : undefined,
          requestId: typeof obj?.requestId === 'string' ? obj.requestId : undefined,
          active_suggestions:
            typeof obj?.active_suggestions === 'number' ? Math.max(0, Math.floor(obj.active_suggestions)) : undefined,
          bridgeStatus: obj?.bridgeStatus && typeof obj.bridgeStatus === 'string' ? obj.bridgeStatus : undefined,
          extra: undefined,
        }

        // Validate final structure
        return ContextPayloadSchema.parse(payload)
      }
    })()

    const stored = setLatestContext(parsed)

    return NextResponse.json({
      success: true,
      message: 'Environmental data stored into context bridge',
      stored,
      meta: {
        storedAt: stored.storedAt,
        expiresAt: stored.expiresAt,
        ttlMs: stored.ttlMs,
      },
    })
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to process environmental data'
    return NextResponse.json({ error: message }, { status: 400 })
  }
}

export async function GET() {
  try {
    const stored = getLatestContext()

    const environmental = stored?.payload.environmental ?? {
      lighting: 'unknown',
      activity_level: 'unknown',
      obstacle_proximity: 'unknown',
    }

    return NextResponse.json({
      context: {
        ...environmental,
        timestamp: new Date().toISOString(),
      },
      meta: {
        stored: Boolean(stored),
        storedAt: stored?.storedAt,
        expiresAt: stored?.expiresAt,
      },
    })
  } catch {
    return NextResponse.json({ error: 'Failed to get environmental context' }, { status: 500 })
  }
}

