---
name: trading-analysis
description: Give real, backend-backed answers about the user's pairs, positions, and risk -- never invented prices or made-up performance numbers.
trigger_keywords:
  - trade
  - trading
  - pair
  - xauusd
  - xagusd
  - gbpusd
  - gold
  - silver
  - forex
  - position
  - risk
  - pnl
  - profit
  - loss
  - performance
---

Nancy has real trading infrastructure -- never guess a price, a P&L figure, or
a win rate. Use the actual data:

- Live/recent price + recommendation for a specific pair: `/trading/recommendation/{pair}`
  (e.g. `XAU/USD`) -- backed by real market data (Yahoo Finance for XAU/XAG
  metals via COMEX futures proxy, Frankfurter/ECB for fiat pairs).
- What the user actually trades: `/trading/watched-pairs` -- only discuss pairs
  that are on this list or that the user explicitly names in the conversation.
  Do not volunteer analysis on a pair that's neither watched nor mentioned.
- Trade history and stats: `/trading/history`, `/trading/performance`,
  `/trading/report` -- real persisted trades (`trading/manager.py`), not
  estimates.
- Risk posture across open positions: `/trading/risk-assessment`.
- Full multi-factor analysis (technical + fundamentals) when the user wants
  depth, not just a quote: `/trading/analyze`.

## Answering

- Lead with the real number (price, % change, P&L) before any commentary.
- If a pair isn't in watched-pairs and wasn't named by the user, say you don't
  track it rather than fabricating a view on it.
- For "how am I doing" style questions, pull from `/trading/performance` and
  `/trading/history` together rather than answering from vague impression.
- Never present a TradingView widget or chart automatically -- only open one
  if the user explicitly asks to see it in a window/dialog.
