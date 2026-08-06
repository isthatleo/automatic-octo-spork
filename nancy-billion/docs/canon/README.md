# NÅNCY Canonical Specification

The constitution and long-term design reference for NÅNCY/Billion. When uncertain, these documents
take precedence -- but see the implementation note in Book III: aspirational architecture and the
actual live codebase are not always the same thing, and where they conflict, real working code wins
over a literal rewrite.

| Book | Title | Scope |
|---|---|---|
| [I](BOOK_I_CANONICAL_VISION.md) | The Canonical Vision | Mission, five foundations, sovereignty, north star -- no code implications on its own |
| [II](BOOK_II_MASTER_ROADMAP.md) | Master Development Roadmap | 20-phase roadmap, Phase 0 (Foundation) through Phase XX (Sovereign Intelligence Network) |
| [III](BOOK_III_ENGINEERING_ARCHITECTURE.md) | Engineering Architecture Bible | Target architecture (Rust/Axum, Postgres/Qdrant, monorepo) -- treated as aspirational guidance, not an active migration; see the note at the top of the file |
| [IV](BOOK_IV_AGENT_BIBLE.md) | The Agent Bible | Agent hierarchy, DNA, lifecycle, divisions, the Agent Oath |
| [V](BOOK_V_MEMORY_KNOWLEDGE_COGNITIVE.md) | Memory, Knowledge & Cognitive Architecture | Memory categories, knowledge graph node/relationship types, the cognitive stack |
| [VI](BOOK_VI_UI_UX_EXPERIENCE.md) | UI/UX, Visual Language & Experience Bible | The Orb (Intelligence Core), its six orbit rings and ten thinking states, dashboard/sidebar/chat layout, motion/color/typography language |

**Book VI status (audited + partially wired 2026-08-06, see `CHANGELOG.md`):**
- Ch.7 (six orbit rings) -- REAL. All six (health/memory/knowledge/agent/reasoning/network) render in
  `components/nancy/nancy-orb.tsx`, each bound to `backend/subsystem_activity.py`'s live signal via
  `onSubsystemActivity`, invisible at rest.
- Ch.10 (ten thinking states) -- REAL for the 7 previously-dead cognitive states. `orbStateForTool()`
  (`nancy-orb.tsx`) maps real in-flight tool names to reasoning/researching/recalling/planning/
  learning/executing; `sleeping` is driven by a genuine pointer/keyboard inactivity timer in
  `app/page.tsx`. `reflecting` remains defined but has no real trigger wired yet.
- Ch.18 (color philosophy) -- **superseded by a deliberate decision, not an oversight.** The live app
  runs "Graphite & Ember" (`app/globals.css`), which explicitly rejects Book VI's blue/cyan/violet
  palette. Ring/state *colors* inside the Orb itself still use Book VI's hues (Amber=memory,
  Emerald=health, Ice cyan=knowledge, Electric blue=network/idle) since those are semantic bindings
  internal to the Orb, not the app-wide theme -- the two currently coexist without conflict.
- Ch.8 (particle system), Ch.11/12 (dashboard/sidebar layout), Ch.6 (glass/WebGL energy core), Ch.20
  (beyond sound, which is REAL -- see `lib/nancy/sfx.ts`) -- not yet audited/wired against the rest of
  the frontend.

## How this is actually used

Citing a Book/Chapter in a code comment (e.g. `trust.py`'s `# Book I Ch.10, Book IV's Agent Oath`)
means a specific principle from these documents was made structural, not aspirational, at that point
in the code -- grep for `Book ` across `backend/` to find every place this has happened so far. Real
audits against these books (see `CHANGELOG.md`, 2026-08-06 entry, and Book II Phase IV's Knowledge
Engine) start from "what does the live code actually do," not from the document text alone.
