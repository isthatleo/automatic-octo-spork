---
name: memory-recall
description: Answer "do you remember"/"what did I tell you" questions using real semantic memory search, not guesses about what was probably said.
trigger_keywords:
  - remember
  - recall
  - what did i say
  - what did i tell you
  - earlier
  - last time
  - previously
  - we talked about
  - you mentioned
---

Nancy has real semantic memory search (`memory/graph.py`'s
`SentenceTransformerEmbedding`, `all-MiniLM-L6-v2`) over past conversation
turns, trades, and projects -- not keyword matching, actual meaning-based
retrieval. Use `/memory/search?q=...` or `/memory/query` before answering any
"do you remember" style question.

## Answering

- If the search returns real hits, answer from them directly and be specific
  (what was said, roughly when) rather than a vague "yes, I recall that."
- If nothing relevant comes back, say plainly that it's not in memory instead
  of inventing a plausible-sounding recollection -- a confident wrong answer
  is worse than "I don't have that."
- For "what pairs do I trade" or similar identity-of-preference questions,
  prefer the authoritative source (`/trading/watched-pairs`) over memory
  search, since memory is for conversational recall, not current state.
