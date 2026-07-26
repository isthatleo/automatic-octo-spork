---
name: web-browsing
description: Fetch and read real current web pages via the fetch_url tool -- never guess at page content or rely only on training-data knowledge for something checkable live.
trigger_keywords:
  - fetch this
  - read this page
  - open this link
  - check this website
  - browse
  - this url
  - http://
  - https://
---

Nancy has a real `fetch_url` tool (`web_tool.py`) -- a genuine HTTP fetch
with HTML parsed down to readable text (scripts/styles/nav stripped), no
paid browser-automation provider needed. Read-only, so it runs immediately,
no approval gate.

- Use it whenever the user gives you a URL or asks about the current
  content of a specific page -- don't answer from training-data memory
  about what a page "probably" says.
- Internal/private network addresses (localhost, 192.168.x, 10.x, cloud
  metadata endpoints) are refused for real, not just discouraged -- if a
  fetch fails for that reason, say so plainly rather than retrying.
- Only http/https URLs are supported.

## Answering

- Cite what the fetched page's title/text actually says -- don't blend it
  with assumptions about the site from training data.
- If the fetch fails (bad URL, non-200 status, blocked address), say so
  honestly instead of answering as if the page had been read.
