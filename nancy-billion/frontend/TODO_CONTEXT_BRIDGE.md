# TODO_CONTEXT_BRIDGE

## Context Bridge (Production-grade)
- [ ] Inspect existing Next.js API route: `frontend/app/api/context/route.ts`
- [ ] Inspect in-memory bridge helper: `frontend/app/lib/context-bridge.ts`
- [ ] Inspect current environmental route behavior: `frontend/app/api/environmental/route.ts`
- [ ] Upgrade context schema: stricter validation, correlation ids, server health info
- [ ] Add robust rate limiting and per-request id logging
- [ ] Add TTL store with explicit cleanup
- [ ] Implement GET returning latest context + metadata consistently
- [ ] Implement best-effort forwarding with structured error reporting
- [ ] Update `environmental` route to forward into context bridge (optional but recommended)
- [ ] Add `next lint` / `next build` verification

