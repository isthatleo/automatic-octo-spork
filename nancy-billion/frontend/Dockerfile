# Nancy Frontend Dockerfile
#
# Build context: the REPO ROOT (nancy-billion/), not frontend/ alone -- see
# docker-compose.yml. This is an npm-workspaces monorepo (root package.json's
# "workspaces": ["backend", "frontend"]), so dependencies hoist to the root
# node_modules/. frontend/package-lock.json is a stale pre-workspace leftover
# missing several packages (framer-motion, recharts, @reduxjs/toolkit, ...)
# that only exist in the real, current root package-lock.json -- building
# from frontend/ in isolation (the original approach here) fails on exactly
# that mismatch.
FROM node:20-slim AS builder

WORKDIR /app

COPY package.json package-lock.json ./
COPY frontend/package.json ./frontend/package.json
RUN npm ci

COPY frontend/ ./frontend/
RUN npm run build --workspace=frontend \
    && npm prune --omit=dev \
    && mkdir -p frontend/public

# Production image
FROM node:20-slim

WORKDIR /app
ENV NODE_ENV=production

RUN apt-get update && apt-get install -y --no-install-recommends wget \
    && rm -rf /var/lib/apt/lists/*

# Both node_modules layers matter here: most deps hoist to the workspace
# root, but a handful nest inside frontend/node_modules (version conflicts,
# npm's own .bin shims) -- Node's resolution walks up from frontend/, so
# both need to be present in the same relative layout as the real repo.
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/frontend/package.json ./frontend/package.json
COPY --from=builder /app/frontend/node_modules ./frontend/node_modules
COPY --from=builder /app/frontend/.next ./frontend/.next
COPY --from=builder /app/frontend/public ./frontend/public

WORKDIR /app/frontend

# This project's own convention is port 3005, not Next's default 3000 --
# the backend's NANCY_ALLOWED_ORIGINS CORS allowlist is configured for
# localhost:3005 (see backend/.env.example), so serving on 3000 here would
# make every real API call fail CORS in the browser.
EXPOSE 3005

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:3005/ || exit 1

CMD ["npm", "run", "start", "--", "-p", "3005"]
