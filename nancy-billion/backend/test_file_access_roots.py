"""Prove the file tools can't read outside the allowed roots.

The hole this closes: `GET /files/read?path=/proc/1/environ` returned the
backend process's whole environment -- every API key in .env -- to anything
that could reach port 8000, because file_access.py deliberately had no sandbox
and reads were never gated by the approval flow that covers writes.

    python backend/test_file_access_roots.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# workspace_uri is the only import file_access needs from the wider backend.
try:
    import workspace_uri  # noqa: F401
except ImportError:
    mod = types.ModuleType("workspace_uri")
    mod.resolve_oc_path = lambda p: p
    sys.modules["workspace_uri"] = mod

root = Path(tempfile.mkdtemp(prefix="billion-roots-"))
(root / "inside").mkdir()
(root / "inside" / "notes.txt").write_text("visible\n", encoding="utf-8")

outside = Path(tempfile.mkdtemp(prefix="billion-outside-"))
(outside / "secrets.env").write_text("ANTHROPIC_API_KEY=sk-real\n", encoding="utf-8")

os.environ["NANCY_ALLOWED_ROOTS"] = str(root)

import file_access  # noqa: E402

file_access.reload_allowed_roots()

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  ok  {label}")
    else:
        failures.append(label)
        print(f"  FAIL {label}{': ' + detail if detail else ''}")


print("file access roots")

# --- inside the root still works normally ----------------------------------
r = file_access.read_file(str(root / "inside" / "notes.txt"))
check("a file inside an allowed root reads normally",
      r.get("success") and "visible" in r.get("content", ""), str(r)[:160])

r = file_access.list_directory(str(root / "inside"))
check("listing inside an allowed root works", r.get("success") is True, str(r)[:160])

# --- outside is refused, on every entry point -------------------------------
r = file_access.read_file(str(outside / "secrets.env"))
check("a file outside every root is refused",
      r.get("success") is False and r.get("denied") is True, str(r)[:160])
check("the refusal does not leak the file's contents",
      "sk-real" not in str(r), str(r)[:160])

r = file_access.read_file("/proc/1/environ")
check("/proc/1/environ -- the API-key leak -- is refused",
      r.get("success") is False and r.get("denied") is True, str(r)[:160])

r = file_access.list_directory(str(outside))
check("listing outside every root is refused", r.get("denied") is True, str(r)[:160])

r = file_access.write_file(str(outside / "planted.txt"), "x")
check("writing outside every root is refused", r.get("denied") is True, str(r)[:160])
check("...and really didn't write", not (outside / "planted.txt").exists())

r = file_access.search_files("KEY", str(outside))
check("searching outside every root is refused", r.get("denied") is True, str(r)[:160])

r = file_access.glob_files("*.env", str(outside))
check("globbing outside every root is refused", r.get("denied") is True, str(r)[:160])

r = file_access.delete_file(str(outside / "secrets.env"))
check("deleting outside every root is refused", r.get("denied") is True, str(r)[:160])
check("...and really didn't delete", (outside / "secrets.env").exists())

r = file_access.move_file(str(root / "inside" / "notes.txt"), str(outside / "stolen.txt"))
check("moving a file OUT of the roots is refused", r.get("denied") is True, str(r)[:160])
check("...and really didn't move", not (outside / "stolen.txt").exists())

# --- traversal and symlinks can't step outside ------------------------------
r = file_access.read_file(str(root / "inside" / ".." / ".." /
                              outside.name / "secrets.env"))
check("a '..' traversal out of the root is refused",
      r.get("success") is False, str(r)[:160])

link = root / "inside" / "escape"
try:
    link.symlink_to(outside / "secrets.env")
    r = file_access.read_file(str(link))
    check("a symlink pointing outside the root is refused",
          r.get("success") is False and r.get("denied") is True, str(r)[:160])
except (OSError, NotImplementedError):
    print("  --  symlink check skipped (not permitted on this platform)")

# --- check_python_syntax keeps its string contract --------------------------
res = file_access.check_python_syntax(str(outside / "secrets.env"))
check("check_python_syntax returns a string, not a dict, when denied",
      isinstance(res, str) and "outside the allowed roots" in res, repr(res)[:160])

# --- an explicitly empty allowlist opts out ---------------------------------
os.environ["NANCY_ALLOWED_ROOTS"] = ""
file_access.ALLOWED_ROOTS = []
r = file_access.read_file(str(outside / "secrets.env"))
check("an explicitly empty allowlist restores unrestricted access",
      r.get("success") is True, str(r)[:160])

print()
if failures:
    print(f"{len(failures)} check(s) failed")
    sys.exit(1)
print("all file access root checks passed")
