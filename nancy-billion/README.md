# Nancy / Billion — A Real, Self-Hosted AI Operating System

Nancy (also addressed as "Billion") is a JARVIS/FRIDAY-style personal AI assistant: a FastAPI backend with real tool-use, real background automation, and a real multi-agent architecture, paired with a Next.js control-room frontend. It runs entirely on your own machine via Docker Compose — no vendor lock-in beyond whichever LLM/provider keys you choose to configure, and every "capability" listed below is a real, live-tested code path, not a mock or a plan.

## What she can actually do

**Coding & files** — real filesystem read/write/edit/multi-edit/search/glob, a real terminal (allowlisted-safe or approval-gated), Jupyter notebook cell editing, an LSP client for live diagnostics, a unified-diff viewer, Python syntax-checking on every write, and a real local Monaco code editor in the UI.

**Browser & computer control** — real headless-Chromium browser automation (navigate/click/fill/screenshot, SSRF-checked), real screenshot/mouse/keyboard control, real on-demand webcam capture, real clipboard read/write, real GUI app launching — all dispatched through a paired host-node bridge when the backend runs in a container with no display of its own.

**Voice & presence** — real STT (faster-whisper) and TTS (neural NeuTTS with a Pyttsx3 fallback), a browser-native wake-word/voice command pipeline, real Twilio phone calls and SMS, an opt-in lower-latency realtime voice mode, and **real speaker verification** (MFCC + cosine similarity): once you enroll your voice, Billion checks it against sensitive commands and escalates approval on a mismatch — never a hard lockout, always a louder ask.

**Memory** — a real embedding-backed knowledge graph that actually grows from every real conversation (WS chat, voice, Telegram, background tasks, cron/webhook skills all populate it through one shared chokepoint), with same-topic mentions **merged** into one node over time (not one node per raw message) while every individual mention's own text and timestamp is preserved. Billion can proactively search her own memory (`search_memory`) beyond whatever's auto-injected into context, plus holographic/symbolic fact storage, a memory wiki, commitment tracking, and dream-cycle consolidation.

**Proactive & scheduled** — real cron jobs and reusable automation blueprints, a daily briefing (now calendar-aware), recurring "watch and alert" monitoring (a webpage, a price, a GitHub release, or an open-ended news topic), unprompted meeting prep (auto-researches an upcoming real calendar event and posts notes before it starts), and a self-healing loop that watches her own resource usage and primary LLM backend health.

**Security & modes** — Telegram-approval gating on every sensitive action, an arm/disarm window for batches of trusted actions, **lockdown mode** (raises the bar to "real voice match required" for everything), **focus mode** (queues non-urgent pushes into one digest instead of pinging you all day), a real SOS/emergency-contact alert, a security-lint pass on generated code, an evidence ledger, and a self-maintenance check that audits her own dependencies against the OSV vulnerability database.

**Real-world tools** — calculator, unit/currency conversion, weather, password/QR generation, URL shortening, zip/unzip, PDF merge/split, image resize, notes, expense tracking, ping/port-check, and scene macros (chain existing tools under one named voice command, e.g. "movie mode").

**Integrations** — Google Calendar, Spotify, Home Assistant, Slack/Telegram/ntfy/WhatsApp/Discord/other channels, a pluggable web-search/image/video/TTS/transcription provider registry, MCP plugin support, real multi-device pairing (a "node" is any second machine running the lightweight node-agent stub), mDNS discovery on the LAN, and a real Docker-backed multi-tenant fleet manager.

**Illustrative research & live artifacts** — Billion can post a real, orbit-controllable 3D scene (Three.js) or a real self-contained, sandboxed HTML/JS live demo to the shared canvas — genuinely rendered and interactive, not a text description of one.

Every one of these is wired into the *actual* WebSocket chat pipeline the frontend uses (not just an unused legacy REST endpoint — that distinction mattered enough to be a real bug fixed this session; see `CHANGELOG` notes below if present), gated behind Telegram approval where the action is sensitive, and callable by natural language, not just a fixed command syntax.

## Architecture

```
automatic-octo-spork/
├── fury-main/              # sibling package the backend depends on (tools.py needs it unconditionally)
└── nancy-billion/
    ├── backend/            # FastAPI app, WebSocket manager, ~90 top-level modules + subpackages
    │   ├── main_new.py     #   the actual entry point — chat pipeline, tool dispatch, all REST/WS routes
    │   ├── llm.py           #   multi-backend LLM fallback chain (Anthropic → Groq → OpenRouter → ...)
    │   ├── memory/          #   knowledge graph, holographic store, wiki, dreaming, external providers
    │   ├── channels/        #   Telegram, Slack, ntfy, Home Assistant, WhatsApp, Discord, ...
    │   ├── providers/       #   pluggable web-search/image/video/TTS/transcription/telephony vendors
    │   ├── agents/          #   ~46 specialized agent implementations
    │   ├── fleet/, sandbox/ #   multi-tenant Docker cells, Windows process-container sandboxing
    │   └── data/            #   bind-mounted JSON stores — real state, survives a container rebuild
    └── frontend/            # Next.js control room
        ├── app/api/**       #   server-side proxy routes to the backend (see BACKEND_URL below)
        └── components/nancy #   ~25 panels: Overview, Recon, Canvas, Memory Insights, Cron, ...
```

Two containers, one Docker network: `nancy-backend` (port 8000) and `nancy-frontend` (port 3005). The frontend's own Next.js API routes run *inside* the frontend container and reach the backend over the Compose network via `BACKEND_URL=http://backend:8000` — a separate, server-only env var from `NEXT_PUBLIC_BACKEND_URL` (which stays `http://localhost:8000`, correct for your browser, which runs on the host). Getting this distinction wrong silently 502s every REST-proxied feature while leaving the WebSocket chat path completely unaffected — a real bug this project hit and fixed; worth knowing if you ever see a panel come up empty that the backend swears it has data for.

## Quickstart

Prerequisites: Docker Desktop (or Docker Engine + Compose v2).

```bash
cd nancy-billion
cp backend/.env.example backend/.env    # fill in whichever provider keys you actually have
docker compose up -d --build
```

- Frontend: http://localhost:3005
- Backend: http://localhost:8000 (health: `/system/health`)

Everything degrades gracefully with no keys configured at all — Billion just won't offer whichever capability needs the missing credential. See `backend/.env.example` for every real integration point, grouped and commented with exactly what each one unlocks.

### Local (non-Docker) development

```bash
# Backend
cd nancy-billion/backend
python -m venv .venv && .venv\Scripts\Activate.ps1   # Windows PowerShell
pip install -r requirements.txt
python main_new.py

# Frontend
cd nancy-billion/frontend
npm install
npm run dev
```

## Configuration

All real configuration lives in `backend/.env.example` — copy it to `backend/.env` and fill in what you have. Nothing is required to boot; each section is independently optional and the relevant tool/channel/provider simply isn't offered to Billion until its key is set. Notable ones:

- `ANTHROPIC_API_KEY` — primary LLM backend. Falls back through Groq → OpenRouter → OpenCode → local Ollama/llama.cpp if unset or rate-limited/out-of-credit.
- `GOOGLE_CALENDAR_CLIENT_ID` / `_SECRET` / `_REFRESH_TOKEN` — real calendar integration (list/create/delete events, calendar-aware daily briefing, proactive meeting prep).
- `TWILIO_ACCOUNT_SID` / `_AUTH_TOKEN` / `_FROM_NUMBER` — real phone calls and SMS.
- `EMERGENCY_CONTACT_NUMBER` — who the SOS tool alerts.
- `BRAVE_API_KEY` (or another configured web-search provider) — real web search, used by watch-topic alerts, meeting prep, and general research.
- `HOST_NODE_ID` / `NODE_SHARED_SECRET` — pair a native host machine for real display/camera/clipboard/app-launch access from inside the container.

## Known limitations (stated honestly, not hidden)

- Meeting-bot auto-join (Google Meet/Teams/Zoom) is deliberately deferred — the single most fragile lift in the whole roadmap (live browser automation joining real calls), backlogged rather than half-built.
- Voice-match enforcement covers every sensitive tool call, but capturing a fresh audio sample happens at the wake-word command layer specifically — a typed command never has audio to check, by design (there's nothing to verify).
- The container itself has no real audio/display/camera hardware — those actions dispatch to a paired host node when one's registered, or degrade to "not available" otherwise. Real voice input to the actual frontend goes through the browser's own microphone (Web Speech API), not the container.
- Self-maintenance's dependency-vulnerability check only covers exact-pinned (`==`) requirements — an unpinned/ranged line has no single version to check against the vulnerability database, so it's skipped rather than guessed.

## Contributing

- Compile-check every touched Python file (`python -m py_compile`) and type-check the frontend (`npx tsc --noEmit`) before considering a change done.
- Every new sensitive tool should go through the same `_request_approval` chokepoint in `main_new.py` (Telegram approval, voice-match-aware) rather than inventing a new gating pattern.
- New persisted state follows the existing JSON-store dataclass pattern (see `missions_store.py` or `watch_store.py` for the reference shape) unless there's a specific reason for something heavier.
