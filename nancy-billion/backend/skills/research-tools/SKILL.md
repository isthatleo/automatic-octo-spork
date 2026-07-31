---
name: research-tools
description: Real arXiv academic paper search and Polymarket prediction-market lookups -- both free, no API key, no approval needed.
trigger_keywords:
  - arxiv
  - academic paper
  - research paper
  - prediction market
  - polymarket
  - betting odds
---

Nancy has two real, keyless research tools (`research_tools.py`):

- `search_arxiv`: real arXiv.org search (title, authors, abstract, link).
  Use for physics/math/CS/related academic questions instead of guessing at
  paper titles from training data -- arXiv's own index is always current.
- `get_prediction_markets`: real, currently-active Polymarket markets
  matching a topic, with real odds (implied probability from each
  outcome's current price), volume, and end date.

Both are genuinely free and keyless (no vendor account needed at all), but
arXiv's own public API is occasionally slow (can take 10-30s for a real
response) -- that's arXiv's server, not a bug, so don't retry rapidly if one
call is slow; arXiv's rate limiter will start rejecting requests outright if
you do.

Report only what these tools actually returned -- a real market's current
odds are a live snapshot, not a prediction from you, and should be
presented as such ("Polymarket currently prices this at X%", not "there's
an X% chance").
