# Nancy / Billion — Sovereign AI Assistant

Nancy/Billion is a modular, sovereign AI operating system that combines a Python backend (FastAPI + optional Fury integration), a Next.js dashboard frontend, and a registry-driven multi-agent architecture with learning and orchestration capabilities.

This repository contains runtime components, agent & tool registries, utilities for generating agent definitions from design documents, and a set of learning and reasoning tools used by specialized agents.

Key capabilities
- Multi-agent orchestration and hierarchical roles (sovereign core, councils, divisions)
- Pluggable LLM backends with fallbacks (Ollama, OpenAI, Anthropic, local LlamaCpp, Groq, OpenRouter)
- Tool registry pattern: tools implemented in Python and registered for agents to call
- STT / TTS integration (Faster-Whisper, pyttsx3, optional cloud providers)
- Frontend dashboard (Next.js + Tailwind) for monitoring and interaction
- Utilities to generate or update `data/agent_registry.json` from design docs

Table of contents
- Purpose
- Quickstart (developer)
- Development notes
- Important file map
- Contribution
- License & contact

Purpose
-------
Provide a flexible platform for building a sovereign AI assistant with:

- Clear separation of concerns: backend orchestration, tool implementations, agent registry and frontend UI
- Easy experimentation with multiple LLMs and runtime fallbacks
- A registry-driven approach to create and manage dozens of specialized agents

Quickstart (developer)
----------------------
These steps assume Windows PowerShell (see repo for platform-specific notes).

Prerequisites
- Python 3.10+ (recommended)
- Node.js 16+ (for frontend)
- pip, virtualenv (or venv)
- Optional: Docker, Ollama or other local LLM runtime

Backend (Python)
1. Create and activate a virtual environment:

   python -m venv .venv
   .\.venv\Scripts\Activate.ps1   # PowerShell on Windows

2. Install dependencies:

   pip install -r backend/requirements.txt

3. Configure environment variables:

- Create `.env` (or set env vars) with keys you need, for example:
  - OPENAI_API_KEY, ANTHROPIC_API_KEY, OLLAMA_BASE_URL, HOST, PORT, etc.

4. Run the backend in development:

   python backend/main_new.py

   or with uvicorn (recommended for FastAPI deployments):

   python -m uvicorn backend.main_new:app --host 0.0.0.0 --port 8000

5. Regenerate the agent registry (optional):

   python backend/generate_agent_registry.py --design "../NÅNCY-BILLION OS Sovereign AI  Design.md" --out data/agent_registry.json

Frontend (Next.js)
1. Install dependencies and run dev server:

   cd frontend
   npm install
   npm run dev

2. Open http://localhost:3000

Development notes
-----------------
- Entry points:
  - Backend FastAPI app: `backend/main_new.py` (primary)
  - Legacy/alternate: `backend/main.py`, `backend/main_backup.py`
  - Agent registry generator: `backend/generate_agent_registry.py`
- LLM backend factory: `backend/llm.py` — configure providers via environment variables and select preferred providers.
- Tools: `backend/tools.py` contains many tool implementations and registration blocks. Use `rebuild_tools.py` to compose tools from modular parts when needed.
- Learning tools: `learning_tool_functions.py`, `learning_section.py` and `learning_registrations_section.py` implement learning, hypothesis and invention tools used by specialized agents.
- Agent registry: `data/agent_registry.json` — the runtime agent definitions and prompts. Use the generator script to keep this in sync with design docs.

Important file map
------------------
- backend/
  - main_new.py        — FastAPI app & WebSocket manager (recommended entrypoint)
  - main.py / main_backup.py — legacy entrypoints
  - llm.py             — LLM backend factory and fallback chains
  - tools.py           — Central tool implementations & registrations
  - generate_agent_registry.py — Create `data/agent_registry.json` from design docs
  - orchestration/     — Orchestrator, hierarchy definitions and integration helpers
  - system_monitor.py  — System health utilities
  - stt.py / tts.py    — STT/TTS backend factories
  - requirements.txt   — Python dependencies

- frontend/
  - package.json       — Next.js app and scripts
  - README.md          — Frontend-specific notes

- data/
  - agent_registry.json — Agent definitions used by runtime

- utilities & scripts
  - rebuild_tools.py, fix_tools.py — helpers to patch or rebuild `backend/tools.py`
  - add_agent.py, add_learning_division.py — registry helpers
  - TODO*.md, PHASE_*.md, IMPLEMENTATION_SUMMARY.md — project planning and phase notes

Contribution
------------
- Branch from `main` into feature branches and open pull requests with clear descriptions and tests where applicable.
- Code style:
  - Python: follow PEP8; use black/isort for formatting where possible.
  - JavaScript: follow ESLint/Prettier rules in the frontend.
- Tests: add pytest unit tests for orchestration and tool behavior. Consider adding a dummy LLM backend for deterministic tests.

License
-------
Add a LICENSE file at the repository root and update this section with the chosen license (e.g. MIT).

Maintainers / Contact
---------------------
- Project lead: <name> — <email@example.com>
- Maintainer: <name> — <email@example.com>
- Security contact: <security@example.com>

Troubleshooting & next steps
----------------------------
- If the backend fails to start, check `backend/requirements.txt` and confirm the virtual environment is active.
- If LLM backends are unavailable, the system will fall back to the DummyLLM present in `backend/llm.py` — use that for local development.
- To add a new specialized agent:
  1. Edit or generate `data/agent_registry.json` (use `backend/generate_agent_registry.py` to help bootstrap from design docs).
  2. Confirm required tools are registered in `backend/tools.py`.
  3. Restart the backend.

If you'd like, I can now:
1. Add run examples (Docker / docker-compose) if you have container configs
2. Open other files under `scripts/` and `docs/` to expand this README with exact commands and examples
3. Create a CONTRIBUTING.md and a basic test harness that runs a dummy agent using the DummyLLM

---
Generated on: 2026-07-06
