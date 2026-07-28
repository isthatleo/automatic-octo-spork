"""Real browser automation via Playwright -- navigate, click, fill forms,
extract text, and screenshot ACTUAL RENDERED pages (real JavaScript
execution), distinct from web_tool.fetch_url (raw HTML -> text, no JS, no
interaction) and computer_use_tool (raw OS-level screen/mouse, not
DOM-aware). Runs headless, so this works fine inside the backend's own
Docker container -- no real display needed, unlike GUI app launching
(app_launcher.py), which does.

One persistent page for the whole backend process, lazily launched on
first use -- a conversational assistant doing "go to the page, then click
X" across a few tool calls needs the SAME page across those calls, not a
fresh one each time.
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from net_policy import is_blocked_host

logger = logging.getLogger(__name__)

MAX_TEXT_CHARS = 6000
NAV_TIMEOUT_MS = 20_000
ACTION_TIMEOUT_MS = 10_000

BROWSER_TOOLS = [
    {
        "name": "browser_navigate",
        "description": (
            "Open a real web page in a real headless browser -- runs actual JavaScript, unlike "
            "fetch_url, so this works for pages that need JS to render (SPAs, dashboards, anything "
            "dynamic). Use this before browser_click/browser_fill/browser_screenshot/browser_get_text. "
            "Returns the page title and a short text summary. Only http/https; internal/private "
            "network addresses are refused."
        ),
        "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    },
    {
        "name": "browser_get_text",
        "description": "Get the real visible text of the current page (or one element via a CSS selector). Call browser_navigate first.",
        "input_schema": {
            "type": "object",
            "properties": {"selector": {"type": "string", "description": "Optional CSS selector; omit for the whole page."}},
            "required": [],
        },
    },
    {
        "name": "browser_screenshot",
        "description": "Take a real screenshot of the current page exactly as rendered, so you can actually see it rather than just read extracted text. Call browser_navigate first.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "browser_click",
        "description": (
            "Click a real element on the current page, by CSS selector or by its visible text. "
            "Requires the user's approval first, same as screen/mouse control -- this is a real "
            "action on a real page (could submit something, follow a link, etc.)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"selector": {"type": "string", "description": "CSS selector, or plain visible text to click."}},
            "required": ["selector"],
        },
    },
    {
        "name": "browser_fill",
        "description": "Type real text into a real form field on the current page, by CSS selector. Requires the user's approval first.",
        "input_schema": {
            "type": "object",
            "properties": {"selector": {"type": "string"}, "text": {"type": "string"}},
            "required": ["selector", "text"],
        },
    },
]

_playwright = None
_browser = None
_page = None


async def _ensure_page():
    global _playwright, _browser, _page
    if _page is not None:
        return _page
    from playwright.async_api import async_playwright
    _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.launch(headless=True)
    _page = await _browser.new_page()
    return _page


def _check_url(url: str) -> Optional[str]:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return "Only http/https URLs are allowed."
    if not parsed.hostname:
        return "Invalid URL."
    if is_blocked_host(parsed.hostname):
        return "That host resolves to an internal/private address and is refused."
    return None


async def browser_navigate(url: str) -> Dict[str, Any]:
    error = _check_url(url)
    if error:
        return {"success": False, "error": error}
    try:
        page = await _ensure_page()
        await page.goto(url, timeout=NAV_TIMEOUT_MS, wait_until="domcontentloaded")
        title = await page.title()
        body_text = await page.inner_text("body")
        return {"success": True, "url": page.url, "title": title, "text": body_text[:MAX_TEXT_CHARS]}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def browser_get_text(selector: Optional[str] = None) -> Dict[str, Any]:
    try:
        page = await _ensure_page()
        text = await page.inner_text(selector or "body")
        return {"success": True, "text": text[:MAX_TEXT_CHARS]}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def browser_screenshot() -> Dict[str, Any]:
    try:
        page = await _ensure_page()
        png_bytes = await page.screenshot(type="png")
        return {"success": True, "_image_base64": base64.b64encode(png_bytes).decode("ascii")}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def browser_click(selector: str) -> Dict[str, Any]:
    try:
        page = await _ensure_page()
        try:
            await page.click(selector, timeout=ACTION_TIMEOUT_MS)
        except Exception:
            # Not a real CSS selector -- try matching by visible text instead,
            # since a model will often pass "the Login button" rather than a
            # real selector it has no way to know.
            await page.get_by_text(selector).first.click(timeout=ACTION_TIMEOUT_MS)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def browser_fill(selector: str, text: str) -> Dict[str, Any]:
    try:
        page = await _ensure_page()
        await page.fill(selector, text, timeout=ACTION_TIMEOUT_MS)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def shutdown_browser() -> None:
    global _playwright, _browser, _page
    if _browser:
        await _browser.close()
    if _playwright:
        await _playwright.stop()
    _playwright = _browser = _page = None
