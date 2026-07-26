"""Real `oc://` workspace-relative path scheme -- ported from OpenClaw's
oc-path extension. Lets a path be addressed unambiguously relative to a
fixed workspace root instead of an absolute OS path or an easily-misresolved
relative one (relative to what CWD, exactly?). Purely additive: any existing
caller passing a real absolute/plain-relative path is completely unaffected
-- this only changes behavior for strings that actually start with `oc://`.
"""
from __future__ import annotations

import os
from pathlib import Path

# The workspace root oc:// paths resolve against. Defaults to this backend's
# own directory (matches where Nancy's other relative-path assumptions --
# e.g. skills/, data/ -- already live), overridable for a different real
# workspace root.
WORKSPACE_ROOT = Path(os.getenv("WORKSPACE_ROOT", str(Path(__file__).parent))).resolve()


def resolve_oc_path(path: str) -> str:
    """`oc://relative/path` -> an absolute path under WORKSPACE_ROOT. Any
    string not starting with `oc://` is returned completely unchanged, so
    this is safe to call unconditionally on every path a file tool receives."""
    if not path.startswith("oc://"):
        return path
    relative = path[len("oc://"):].lstrip("/")
    resolved = (WORKSPACE_ROOT / relative).resolve()
    # Real containment check -- an oc:// path is a workspace-relative
    # address, not an escape hatch via "../../.." segments back out to
    # anywhere on disk.
    if WORKSPACE_ROOT not in resolved.parents and resolved != WORKSPACE_ROOT:
        raise ValueError(f"oc:// path escapes the workspace root: {path}")
    return str(resolved)
