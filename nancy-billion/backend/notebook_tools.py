"""Real Jupyter notebook (.ipynb) reading and cell-level editing -- the same
job Claude Code's own NotebookEdit tool does. A .ipynb file is just JSON
(nbformat spec: {"cells": [...], "metadata": {...}, "nbformat": 4, ...}), so
this needs no extra dependency (nbformat/nbclient) -- read/write it directly,
matching the exact shape Jupyter itself writes.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from workspace_uri import resolve_oc_path


def _source_to_text(source: Any) -> str:
    if isinstance(source, list):
        return "".join(source)
    return str(source or "")


def _text_to_source(text: str) -> List[str]:
    # nbformat convention: each line keeps its trailing "\n" except the last.
    lines = text.split("\n")
    return [line + "\n" for line in lines[:-1]] + ([lines[-1]] if lines[-1] else [])


def _summarize_outputs(outputs: Any) -> str:
    if not isinstance(outputs, list) or not outputs:
        return ""
    parts = []
    for out in outputs:
        if not isinstance(out, dict):
            continue
        if out.get("output_type") == "stream":
            parts.append(_source_to_text(out.get("text")))
        elif out.get("output_type") in ("execute_result", "display_data"):
            data = out.get("data", {})
            if "text/plain" in data:
                parts.append(_source_to_text(data["text/plain"]))
            elif data:
                parts.append(f"[{', '.join(data.keys())} output]")
        elif out.get("output_type") == "error":
            parts.append(f"{out.get('ename', 'Error')}: {out.get('evalue', '')}")
    return "\n".join(p for p in parts if p)[:2000]


def read_notebook(path: str) -> Dict[str, Any]:
    p = Path(resolve_oc_path(path)).expanduser()
    if not p.exists():
        return {"success": False, "error": f"No such file: {path}"}
    try:
        nb = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"success": False, "error": f"Not a valid notebook: {e}"}
    cells = nb.get("cells", [])
    return {
        "success": True,
        "path": str(p),
        "cell_count": len(cells),
        "cells": [
            {
                "index": i,
                "cell_type": c.get("cell_type", "code"),
                "source": _source_to_text(c.get("source")),
                "outputs_summary": _summarize_outputs(c.get("outputs")) or None,
            }
            for i, c in enumerate(cells)
        ],
    }


def edit_notebook_cell(
    path: str, cell_index: int, new_source: str = "",
    cell_type: Optional[str] = None, edit_mode: str = "replace",
) -> Dict[str, Any]:
    """edit_mode: "replace" (rewrite cell_index's source, clearing its stale
    outputs since they no longer match the new code), "insert" (add a new
    cell immediately before cell_index -- pass cell_index == cell_count to
    append at the end), or "delete" (remove cell_index)."""
    p = Path(resolve_oc_path(path)).expanduser()
    if not p.exists():
        return {"success": False, "error": f"No such file: {path}"}
    try:
        nb = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"success": False, "error": f"Not a valid notebook: {e}"}
    cells = nb.setdefault("cells", [])

    if edit_mode == "replace":
        if not (0 <= cell_index < len(cells)):
            return {"success": False, "error": f"cell_index {cell_index} out of range (0..{len(cells) - 1})."}
        cells[cell_index]["source"] = _text_to_source(new_source)
        if cell_type:
            cells[cell_index]["cell_type"] = cell_type
        if cells[cell_index].get("cell_type") == "code":
            cells[cell_index]["outputs"] = []
            cells[cell_index]["execution_count"] = None
    elif edit_mode == "insert":
        if not (0 <= cell_index <= len(cells)):
            return {"success": False, "error": f"cell_index {cell_index} out of range (0..{len(cells)})."}
        new_cell: Dict[str, Any] = {
            "cell_type": cell_type or "code",
            "metadata": {},
            "source": _text_to_source(new_source),
        }
        if new_cell["cell_type"] == "code":
            new_cell["outputs"] = []
            new_cell["execution_count"] = None
        cells.insert(cell_index, new_cell)
    elif edit_mode == "delete":
        if not (0 <= cell_index < len(cells)):
            return {"success": False, "error": f"cell_index {cell_index} out of range (0..{len(cells) - 1})."}
        cells.pop(cell_index)
    else:
        return {"success": False, "error": "edit_mode must be 'replace', 'insert', or 'delete'."}

    try:
        p.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        return {"success": False, "error": str(e)}
    return {"success": True, "path": str(p), "cell_count": len(cells)}
