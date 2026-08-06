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

Book VI Ch.7's six orbit rings (system health, memory, knowledge, agent, reasoning, network
synchronization) were already wired to a real signal before this index existed --
`backend/subsystem_activity.py`'s `SUBSYSTEMS` tuple is exactly that list, poked by real
memory/agent/LLM activity across the backend (see `Book VI Ch.7` citations via
`grep -rn "Book VI" backend/`) rather than fixed timers. Chapters beyond the ring-activity signal
(particle system, thinking-state choreography, dashboard/sidebar layout, color/motion/sound design)
have not been audited against the frontend yet.

## How this is actually used

Citing a Book/Chapter in a code comment (e.g. `trust.py`'s `# Book I Ch.10, Book IV's Agent Oath`)
means a specific principle from these documents was made structural, not aspirational, at that point
in the code -- grep for `Book ` across `backend/` to find every place this has happened so far. Real
audits against these books (see `CHANGELOG.md`, 2026-08-06 entry, and Book II Phase IV's Knowledge
Engine) start from "what does the live code actually do," not from the document text alone.
