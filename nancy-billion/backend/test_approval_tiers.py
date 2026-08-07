"""Check the graduated-trust tier added this session: delete_file,
place_phone_call, and git_push must always require a live approval --
never bypassed by arm_switch being armed, and (separately, in
_request_approval itself) never bypassed by _current_turn_chat_approved
either. Every other gated tool (write_file, git_commit, ...) keeps the
old bypass-while-armed behavior.

Same "lift the real source, don't hand-copy it" approach as
test_tool_backend_order.py: this pulls the actual gating expressions out
of main_new.py and evaluates them directly, so an edit to the logic (not
just the tool sets) is an edit this test sees -- a hand-copied restatement
of the boolean logic would keep passing even if the real code regressed.

    python backend/test_approval_tiers.py
"""
from __future__ import annotations

from pathlib import Path

SRC = (Path(__file__).parent / "main_new.py").read_text(encoding="utf-8")


def _extract_line(marker: str) -> str:
    i = SRC.index(marker)
    j = SRC.index("\n", i)
    return SRC[i:j]


def _extract_parenthesized(start_marker: str) -> str:
    """start_marker must end in the expression's opening '(' -- returns
    everything up to (not including) its matching close paren, honoring
    nesting (e.g. arm_switch.is_armed())."""
    i = SRC.index(start_marker) + len(start_marker)
    depth = 0
    j = i
    while True:
        if SRC[j] == "(":
            depth += 1
        elif SRC[j] == ")":
            if depth == 0:
                break
            depth -= 1
        j += 1
    return SRC[i:j]


# --- the two tier constants, verbatim --------------------------------------
ns: dict = {}
exec(compile(_extract_line("_FILE_WRITE_TOOLS = "), "main_new.py:tiers", "exec"), ns)
exec(compile(_extract_line("_ALWAYS_CONFIRM_TOOLS = "), "main_new.py:tiers", "exec"), ns)
FILE_WRITE_TOOLS = ns["_FILE_WRITE_TOOLS"]
ALWAYS_CONFIRM_TOOLS = ns["_ALWAYS_CONFIRM_TOOLS"]

# --- the two gating expressions, verbatim ----------------------------------
file_write_gate_expr = _extract_parenthesized("if name in _FILE_WRITE_TOOLS and (")
git_gate_expr = _extract_parenthesized("if is_mutating and (")

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  ok  {label}")
    else:
        failures.append(f"{label}{': ' + detail if detail else ''}")


class _FakeArmSwitch:
    def __init__(self, armed: bool) -> None:
        self._armed = armed

    def is_armed(self) -> bool:
        return self._armed


def file_write_would_ask(name: str, armed: bool, voice_mismatch: bool) -> bool:
    scope = {
        "_always_confirm_file_op": name in ALWAYS_CONFIRM_TOOLS,
        "arm_switch": _FakeArmSwitch(armed),
        "_voice_mismatch": lambda: voice_mismatch,
    }
    return eval(file_write_gate_expr, scope)  # noqa: S307 -- trusted local source, not user input


def git_would_ask(name: str, armed: bool, voice_mismatch: bool) -> bool:
    scope = {
        "always_confirm": name in ALWAYS_CONFIRM_TOOLS,
        "arm_switch": _FakeArmSwitch(armed),
        "_voice_mismatch": lambda: voice_mismatch,
    }
    return eval(git_gate_expr, scope)  # noqa: S307


print("graduated trust tiers")

check(
    "delete_file, place_phone_call and git_push are the always-confirm tier",
    ALWAYS_CONFIRM_TOOLS == {"delete_file", "place_phone_call", "git_push"},
    str(ALWAYS_CONFIRM_TOOLS),
)
check("delete_file is a real file-write tool", "delete_file" in FILE_WRITE_TOOLS)

# The bypass-while-armed shortcut still applies to ordinary gated tools.
check("write_file is bypassed while armed", not file_write_would_ask("write_file", armed=True, voice_mismatch=False))
check("move_file is bypassed while armed", not file_write_would_ask("move_file", armed=True, voice_mismatch=False))
check("edit_file is bypassed while armed", not file_write_would_ask("edit_file", armed=True, voice_mismatch=False))
check("git_commit is bypassed while armed", not git_would_ask("git_commit", armed=True, voice_mismatch=False))

# The always-confirm tier ignores arm_switch entirely.
check("delete_file is NOT bypassed while armed", file_write_would_ask("delete_file", armed=True, voice_mismatch=False))
check("delete_file still asks when unarmed too", file_write_would_ask("delete_file", armed=False, voice_mismatch=False))
check("git_push is NOT bypassed while armed", git_would_ask("git_push", armed=True, voice_mismatch=False))
check("git_pull (not in the always-confirm tier) IS bypassed while armed", not git_would_ask("git_pull", armed=True, voice_mismatch=False))

# A voice mismatch already forces approval regardless -- always-confirm
# tools should obviously still ask too, not regress to "safe" somehow.
check("delete_file still asks on a voice mismatch, unarmed", file_write_would_ask("delete_file", armed=False, voice_mismatch=True))
check("write_file asks on a voice mismatch even while armed", file_write_would_ask("write_file", armed=True, voice_mismatch=True))

if failures:
    print(f"\n{len(failures)} FAILURE(S):")
    for f in failures:
        print(f"  - {f}")
    raise SystemExit(1)
print("\nall graduated trust tier checks passed")
