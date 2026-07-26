"""Real web-page fetching for Claude's tool-use loop -- gives the model
access to actual current web content instead of only what's in its
training data, without needing a paid provider (Browserbase/Firecrawl-style
services from the Hermes/OpenClaw research). Read-only, so no Telegram
approval gate (same tier as read_file/list_directory) -- but real network
access from an LLM-controlled tool call is still a genuine SSRF surface, so
requests are checked against net_policy.py's shared IP-classification
policy regardless of approval, since that's not something a human glancing
at an approval prompt would reliably catch anyway.
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from net_policy import is_blocked_host, redact_url_for_logging

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_S = 15.0
MAX_TEXT_CHARS = 4000
MAX_REDIRECTS = 5
_USER_AGENT = "Mozilla/5.0 (compatible; NancyBillion/1.0; +local-assistant)"

WEB_TOOLS = [
    {
        "name": "fetch_url",
        "description": (
            "Fetch a real web page and return its readable text content (title + body text, "
            "scripts/styles/nav stripped). Use this for current information not in your training "
            "data -- news, docs, a specific page the user mentioned. Only http/https URLs; "
            "internal/private network addresses are refused."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
]


async def fetch_url(url: str) -> dict:
    """Manual redirect handling (not httpx's follow_redirects=True) is
    deliberate: a server can 302 an initially-safe public URL to an
    internal address, and blindly following that would bypass the host
    check entirely since it only ever validated the original URL -- a real,
    known SSRF technique, not a hypothetical one. Every hop is re-checked."""
    current_url = url
    try:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_S, follow_redirects=False) as client:
            for _ in range(MAX_REDIRECTS + 1):
                parsed = urlparse(current_url)
                if parsed.scheme not in ("http", "https"):
                    return {"success": False, "error": "Only http/https URLs are supported"}
                if not parsed.hostname:
                    return {"success": False, "error": "URL has no host"}
                if is_blocked_host(parsed.hostname):
                    return {"success": False, "error": f"Refusing to fetch internal/private address: {parsed.hostname}"}

                resp = await client.get(current_url, headers={"User-Agent": _USER_AGENT})
                if resp.is_redirect:
                    next_url = resp.headers.get("location")
                    if not next_url:
                        return {"success": False, "error": "Redirect response had no Location header"}
                    current_url = str(httpx.URL(current_url).join(next_url))
                    continue
                break
            else:
                return {"success": False, "error": f"Too many redirects (> {MAX_REDIRECTS})"}
    except Exception as e:
        logger.warning("fetch_url failed for %s: %s", redact_url_for_logging(url), e)
        return {"success": False, "error": f"Fetch failed: {e}"}

    if resp.status_code >= 400:
        return {"success": False, "error": f"HTTP {resp.status_code}"}

    content_type = resp.headers.get("content-type", "")
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        # Real non-HTML content (JSON, plain text, etc.) -- just return it
        # truncated rather than failing outright.
        return {"success": True, "url": str(resp.url), "title": None, "text": resp.text[:MAX_TEXT_CHARS]}

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    title = soup.title.string.strip() if soup.title and soup.title.string else None
    text = " ".join(soup.get_text(separator=" ").split())
    return {"success": True, "url": str(resp.url), "title": title, "text": text[:MAX_TEXT_CHARS]}
