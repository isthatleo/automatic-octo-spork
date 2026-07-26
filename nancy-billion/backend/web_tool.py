"""Real web-page fetching for Claude's tool-use loop -- gives the model
access to actual current web content instead of only what's in its
training data, without needing a paid provider (Browserbase/Firecrawl-style
services from the Hermes/OpenClaw research). Read-only, so no Telegram
approval gate (same tier as read_file/list_directory) -- but real network
access from an LLM-controlled tool call is still a genuine SSRF surface, so
requests to localhost/private/link-local addresses are refused outright
regardless of approval, since that's not something a human glancing at an
approval prompt would reliably catch anyway.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_S = 15.0
MAX_TEXT_CHARS = 4000
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


def _is_blocked_host(hostname: str) -> bool:
    """Refuses localhost/private/link-local/loopback targets -- an LLM tool
    call fetching http://169.254.169.254/ (cloud metadata) or an internal
    LAN service is a real SSRF pattern, not a hypothetical one, even on a
    single-user personal machine that itself runs other local services."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return True  # can't resolve -- refuse rather than let a DNS trick through
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return True
    return False


async def fetch_url(url: str) -> dict:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return {"success": False, "error": "Only http/https URLs are supported"}
    if not parsed.hostname:
        return {"success": False, "error": "URL has no host"}
    if _is_blocked_host(parsed.hostname):
        return {"success": False, "error": f"Refusing to fetch internal/private address: {parsed.hostname}"}

    try:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_S, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": _USER_AGENT})
    except Exception as e:
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
