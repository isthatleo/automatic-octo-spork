# Billion — Full-Project Audit & Upgrade Roadmap (2026-07-29)

This report covers: (1) how the satellite repos are actually wired into
nancy-billion, (2) what Hermes (Nous Research) and OpenClaw do that Billion
could adopt, (3) a frontend review, (4) a JARVIS/FRIDAY-grade capability
roadmap, and (5) what was implemented this session. Findings are stated
honestly — what's real, what's simulated, what's missing.

---

## 1. Satellite-repo wiring audit

| Repo | Status | Evidence |
|---|---|---|
| `fury-main` | **WIRED (hard dependency)** | `requirements.txt` installs `-e ../../fury-main[tts]`; imported by `tools.py`, `llm.py` (FuryLLM), `neu_tts.py`, `agent_executor.py`, `computer_use_tool.py`, `main_new.py` |
| `clap-detection-main` | **WIRED (ported + honest degradation)** | `clap_detection.py` ports its mel-spectrogram preprocessing; reports unavailable until `CLAP_MODEL_PATH` points at real weights (torchvision still uninstalled by design) |
| `modules/` (workspace root) | **WIRED** | `backend/core/assistant.py` imports `modules.system.{monitor,diagnostics,recovery}` — note this only resolves when the process runs with the workspace root on `sys.path`; worth verifying inside the Docker image |
| `jarvis-mlx-main` | **NOT wired** | Zero references. It's an Apple-MLX (Mac-only) voice pipeline — reference material only on this Windows box |
| `MiroFish-main` | **NOT wired** | Zero references. Multi-agent world-simulation platform — reference material |
| `open-generative-ai-main` | **NOT wired** | Zero references. Multi-provider generative UI — its provider-registry ideas already exist in `backend/providers/` |
| `personaplex-main` | **NOT wired** | Zero references. Full-duplex speech-to-speech model (NVIDIA) — the most interesting future candidate, see §4 |

**Verdict:** nothing is *broken* — the two repos the backend claims to need
are genuinely integrated, and the four unwired ones are inspiration, not
dead links. If you want the unwired ones out of the repo, they can move to
a `reference/` folder or be deleted; if you want them wired, personaplex
(realtime voice) and MiroFish (simulation panel) are the two with a real
payoff path.

---

## 2. Hermes & OpenClaw research — what Billion can adopt

**Hermes Agent** (Nous Research, Feb 2026, MIT): self-hosted autonomous
agent; persistent cross-restart memory with FTS5 full-text session search;
cron scheduling; one agent core behind many thin surfaces (CLI, desktop
app, Telegram/Discord/Slack/WhatsApp/Signal/email); sandboxed execution
with pluggable backends (Local/Docker/SSH/Modal/Daytona); subagent
delegation where each subagent gets its own conversation + terminal; and
its signature **solve → distill → reuse skill loop** (successful solution
paths are distilled into named reusable skills automatically).

**OpenClaw** (Peter Steinberger, ~60k GitHub stars in 72h): local Node.js
gateway giving models file/shell/browser access; Slack/Discord/iMessage/
WhatsApp/Telegram channels; memory as plain local Markdown documents;
100+ shareable "AgentSkills" bundles; 24/7 proactive operation via cron +
webhooks + heartbeat; smart-home device control; optional sandboxing.
(Security caution is warranted — hardened deployment images exist for a
reason; Billion's Telegram-approval chokepoint is already ahead here.)

**What Billion already has:** most of it, genuinely — persistent memory
graph, cron + webhooks + watches, multi-channel (Telegram/Slack/WhatsApp/
Discord/ntfy/HA), skills + bundles, MCP client, sandboxing, approval
gating. The gaps worth stealing:

1. **Skill distillation loop (Hermes' best idea).** After a successful
   multi-tool chat turn, have Billion propose distilling the solution path
   into a named skill (`skill_loader` already exists — this is a new
   "distill_skill" step at the end of `_generate_response_via_hierarchy`,
   gated behind a one-tap approval). This is the single highest-leverage
   borrow: it makes Billion measurably faster/cheaper at repeated tasks.
2. **Full-text session search (FTS5).** Memory graph search is semantic;
   add a plain SQLite FTS5 index over raw conversation logs so "what did
   we decide about X in March" works verbatim, not just semantically.
3. **Memory as human-readable files.** OpenClaw's Markdown-file memory is
   auditable and hand-editable. Billion's `data/*.json` stores are close;
   a `memory/wiki` export-to-Markdown pass would give the same benefit.
4. **Thin-surface principle.** Billion's frontend is thick. Keep new
   surfaces (email channel, Signal) as thin adapters over the one WS/chat
   chokepoint — which `channels/` already does. Just don't regress.
5. **Skill sharing format.** OpenClaw skills are shareable bundles; adding
   import/export of Billion's skill JSON (plus README) makes your skills
   portable and lets you import community ideas.

---

## 3. Frontend review (Next.js 16 / React 19 control room)

What's genuinely good: voice-first hero orb with real amplitude-driven
animation, streaming sentence-level TTS with gapless audio queueing, ~25
real panels backed by real endpoints, WS domain-event live updates, real
data replacing fabricated stats (core count, uptime, activity feed), and
the new simulated/production agent badges.

Major improvement candidates, in priority order:

1. **Monolith decomposition (maintainability, not cosmetics).**
   `admin-panels.tsx` is **215KB**, `panels.tsx` 91KB, `workflow-orchestrator.tsx`
   62KB, `map-panel.tsx` 51KB, `page.tsx` 47KB. Any change risks the whole
   file; code-splitting is impossible, so first paint pays for everything.
   Split into one-file-per-panel with `next/dynamic` lazy imports — this is
   the largest single frontend win available.
2. **Type-check + lint in CI.** There is no `frontend/node_modules` on this
   machine and no automated `tsc --noEmit`/`next lint` gate. A trivial
   GitHub Action (or a `docker compose` build gate) prevents silent type
   drift in a 100+-route proxy surface.
3. **STT robustness.** Browser Web Speech API is Chrome-only and flaky
   offline. The backend already has faster-whisper: add a MediaRecorder →
   `/voice/transcribe` fallback path when `webkitSpeechRecognition` is
   absent (Firefox/Safari) — the endpoint largely exists already.
4. **Barge-in.** True JARVIS feel: speaking while Nancy is talking should
   duck/stop her audio and start listening. The orb already tracks
   speaking/listening state; wire mic VAD level (already measured) to
   cancel the audio queue.
5. **Latency surfacing.** Show time-to-first-token and which backend
   answered (data exists in `usage_analytics`) in the console bar —
   the fastest way to notice a degraded fallback chain.
6. **Error-boundary + offline states.** Panels assume the backend is up;
   a single React error boundary per panel plus a standard "backend
   unreachable" card would stop one dead route from blanking a whole view.
7. **Mobile/responsive pass.** The control room is desktop-tuned; the orb
   hero works on mobile but dense panels overflow. Even a "phone = voice +
   chat + alerts only" mode would be a big practical win.
8. **Leftover dev cruft in the tree** (`.next/` build output, `.idea/`,
   `tsconfig.tsbuildinfo`, several MB of PNGs at `frontend/` root) —
   move the images to `public/`, gitignore the rest.

---

## 4. JARVIS/FRIDAY capability roadmap (real, buildable items)

Ordered by payoff ÷ effort, all implementable with what's already in the
codebase (no simulated hardware, no consciousness claims):

1. **Realtime full-duplex voice** — `realtime_voice.py` exists (opt-in);
   the personaplex-main satellite repo is literally NVIDIA's full-duplex
   speech-to-speech model. A `providers/transcription/realtime_ws.py`-style
   adapter to a personaplex server (or a cloud realtime API) would take
   voice from "walkie-talkie" to "conversation", the single most
   JARVIS-feeling upgrade available.
2. **Skill distillation loop** (§2.1) — Billion learns her own procedures.
3. **Proactive daily ops** — the pieces (daily briefing, watches, meeting
   prep, focus mode) exist; a "chief of staff" cron that composes them
   into one morning/evening voice briefing with follow-up questions.
4. **Vision everywhere** — `AnthropicLLM.generate(images=...)` now exists
   (this session): wire webcam snapshots, screen-context captures, and
   Telegram photo messages into chat turns so "what am I looking at?"
   actually works.
5. **FTS5 conversation recall** (§2.2).
6. **Real home control depth** — Home Assistant channel exists; add scene
   learning ("movie mode" macro suggestions from observed patterns via
   `pattern_suggestions.py`).
7. **Meeting-bot auto-join** — still the most fragile lift (deliberately
   deferred in the README); keep deferred until the above land.

Explicitly *not* recommended as next steps: the TODO.md "quantum/neural
interface/holographic" items — the honesty audit already established those
agents are simulations; deepening them adds demo value, not capability.

---

## 5. Implemented this session

1. **Context bridge, end-to-end** (was dead): fixed the wrong env var
   (`BACKEND_URL`), wired the dashboard to actually POST
   panel/speaking/thinking state with a 10s heartbeat, added schema
   fields, forward timeout, limiter pruning, and a backend staleness guard
   so stale UI context can never leak into prompts.
2. **Simulated-vs-production agent badges** in the fleet roster + detail
   modal, driven by the backend's real honesty flags.
3. **Full modern Claude wiring** (`llm.py` + `main_new.py`):
   - Real **system role** for persona/context instead of user-message
     concatenation (better instruction hierarchy).
   - **Prompt caching** on the static system prompt *and* the tool-schema
     array — every tool-loop round and every chat turn was previously
     re-billed at full input price; cache reads cost a fraction and cut
     latency inside the 45s tool budget.
   - **Vision input** (`images=` on `generate()`) for real image-in-chat.
   - Applied to all three Claude paths: chat tool loop, streaming chat,
     and cron/webhook skill runs.
4. **Repo hygiene:** 13 cruft files quarantined to `_to_delete/`,
   `.gitignore` updated.
5. Both backend files compile clean on your machine (`py_compile` run on
   the device post-commit).

## 6. Honest "industry grade" assessment

Billion is unusually real for a personal JARVIS project — the chat/tool/
memory/approval core is genuine and live-tested. The gap to "industry
grade" is not more agents; it is: CI (compile + type-check + lint gates),
tests around the chat pipeline's contract, frontend decomposition (§3.1),
secrets hygiene (a real `.env` exists in `backend/` — keep it out of any
sync/backup you don't trust), and observability (surface the
usage/latency data you already collect). Recommended order: CI gate →
frontend split → skill distillation → realtime voice.
