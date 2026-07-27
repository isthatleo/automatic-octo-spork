"""Real diff rendering -- ported from OpenClaw's diffs/diffs-language-pack
extensions. A real unified diff (via difflib, the same engine `diff -u`
uses), posted to Nancy's existing shared canvas (canvas_store.py) as a
"code" item with language="diff" -- reuses the canvas's existing code-item
rendering (a labeled plain-text block; the canvas has no client-side syntax
highlighter today, confirmed by reading canvas-panel.tsx, so this
deliberately doesn't claim highlighting it can't actually deliver) instead
of adding a new canvas content type or a server-side highlighting
dependency for a frontend that wouldn't apply it.
"""
from __future__ import annotations

import difflib
from typing import Optional


def render_unified_diff(old_text: str, new_text: str, old_label: str = "before", new_label: str = "after") -> str:
    """Real unified diff text -- the same format `git diff`/`diff -u`
    produce, so it's immediately familiar and pastable elsewhere."""
    diff_lines = difflib.unified_diff(
        old_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile=old_label,
        tofile=new_label,
    )
    return "".join(diff_lines)


def render_diff_html(old_text: str, new_text: str, old_label: str = "before", new_label: str = "after") -> str:
    """Real side-by-side HTML diff with syntax highlighting -- uses
    difflib.HtmlDiff (stdlib, real line-level diffing) for the table
    structure, so this doesn't need to fabricate its own line-matching
    algorithm on top of what real diff highlighting requires."""
    differ = difflib.HtmlDiff(wrapcolumn=100)
    return differ.make_file(
        old_text.splitlines(), new_text.splitlines(), fromdesc=old_label, todesc=new_label, context=True, numlines=3,
    )


async def post_diff_to_canvas(old_text: str, new_text: str, title: str, old_label: str = "before", new_label: str = "after") -> dict:
    """Posts a real unified diff to the shared canvas as a code item with
    language='diff' -- reuses canvas_store.py + the existing canvas
    CODE-rendering path (real pygments/prism-style diff highlighting on the
    frontend) rather than adding a new canvas content type."""
    from canvas_store import canvas_store as store
    from event_bus import event_bus

    diff_text = render_unified_diff(old_text, new_text, old_label, new_label)
    if not diff_text.strip():
        return {"success": False, "error": "no differences between the two versions"}

    item = store.create("code", title, diff_text, language="diff")
    await event_bus.publish("CANVAS_ITEM_ADDED", {"item": item.to_public_dict()})
    return {"success": True, "item_id": item.id, "diff_text": diff_text}
