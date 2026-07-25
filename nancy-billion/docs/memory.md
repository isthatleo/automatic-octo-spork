# Nancy Memory Reference

## Memory surfaces

- `/memory` — Open memory, session history, and recalled facts.
- `/memory search <query>` — Semantic memory search for relevant memories.
- `/memory remember <fact>` — Store a long-term memory for later recall.

## Backend endpoints

- `GET /memory/summary` — Summary of current memory state.
- `POST /memory/query` — Search stored memories by query text.
- `POST /memory/search` — Semantic memory search from the frontend API proxy.

## Usage tips

- Ask in plain text for recall questions and Nancy routes through available memory tools.
- Use broad topics when first searching; narrow with follow-up queries.
