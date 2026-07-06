from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class HierarchyRole:
    """A named role in the company-like hierarchy."""

    key: str
    name: str
    tier: int  # 0 = Council
    department: str

    # If you have a matching entry in data/agent_registry.json, put its registry key here.
    # If None, the orchestrator will fall back to a fixed system prompt.
    agent_registry_key: Optional[str] = None

    # Optional system prompt for fixed/pseudo agents.
    fallback_system_prompt: Optional[str] = None

    # Which agent(s) are allowed to run tools, etc. (future extension)
    tool_policy: Optional[Dict[str, Any]] = None


class NancyHierarchy:
    """Canonical hierarchy mapping.

    NOTE: Current repository does not contain concrete registry keys for these names.
    We therefore map most roles to None and provide fallback prompts.
    """

    def __init__(self) -> None:
        self.roles: List[HierarchyRole] = self._build_roles()

        # Useful indexes
        self.by_key: Dict[str, HierarchyRole] = {r.key: r for r in self.roles}

    def _build_roles(self) -> List[HierarchyRole]:
        council = "council"

        def rp(
            key: str,
            name: str,
            tier: int,
            department: str,
            agent_registry_key: Optional[str] = None,
            fallback_system_prompt: Optional[str] = None,
        ) -> HierarchyRole:
            return HierarchyRole(
                key=key,
                name=name,
                tier=tier,
                department=department,
                agent_registry_key=agent_registry_key,
                fallback_system_prompt=fallback_system_prompt,
            )

        # Tier 0 Council
        return [
            rp(
                key="sovereign_core",
                name="Sovereign Core",
                tier=0,
                department=council,
                fallback_system_prompt="""You are Sovereign Core: the top-level reasoning steward.
You produce: (1) a plan (2) verification checklist (3) routing instructions to divisions.
You must be safe, concise, and deterministic in structure.
Output format:
PLAN: ...
GATES: - security: pass/fail criteria
       - ethics: pass/fail criteria
ROUTING: <role_key>=<input_to_role>
FINAL: a short final response draft.""",
            ),
            rp(
                key="chief_executive",
                name="Chief Executive Agent",
                tier=0,
                department=council,
                fallback_system_prompt="""You are Chief Executive Agent (CEO).
Translate Sovereign Core routing into an execution sequence.
You decide order, escalation, and stop conditions.
Output:
SEQUENCE: [role_key1, role_key2, ...]
STOP_CONDITIONS: ...
""",
            ),
            rp(
                key="chief_strategy",
                name="Chief Strategy Agent",
                tier=0,
                department=council,
                fallback_system_prompt="""You are Chief Strategy Agent.
Given a user request, identify options, second-order effects, and the best growth-oriented path.
Output:
STRATEGY: ...
RISKS: ...
""",
            ),
            rp(
                key="chief_operations",
                name="Chief Operations Agent",
                tier=0,
                department=council,
                fallback_system_prompt="""You are Chief Operations Agent.
You orchestrate tasks, define milestones, and ensure dependencies are respected.
Output:
MILESTONES: ...
DEPENDENCIES: ...
""",
            ),
            rp(
                key="chief_learning",
                name="Chief Learning Agent",
                tier=0,
                department=council,
                fallback_system_prompt="""You are Chief Learning Agent.
After execution, extract lessons/facts/episodes and convert them into memory updates.
Output:
LESSONS: ...
FACTS_TO_SAVE: [{'key':..., 'fact':...}, ...]
EPISODES_TO_SAVE: [{'episode': {...}}, ...]
""",
            ),
            rp(
                key="chief_security",
                name="Chief Security Agent",
                tier=0,
                department=council,
                fallback_system_prompt="""You are Chief Security Agent.
You must evaluate requests for risky tool usage.
Hard rules:
- If request asks for secrets, malware, or destructive actions, mark FAIL.
- If tool input contains unbounded shell execution, mark FAIL.
Output:
SECURITY_DECISION: PASS/FAIL
REASONS: ...
SAFE_TOOL_SUBSET: ...
""",
            ),
            rp(
                key="chief_ethics",
                name="Chief Ethics Agent",
                tier=0,
                department=council,
                fallback_system_prompt="""You are Chief Ethics Agent.
Evaluate for harmful, illegal, or privacy-violating behavior.
Output:
ETHICS_DECISION: PASS/FAIL
REASONS: ...
ALLOWED_BEHAVIOR: ...
""",
            ),
            rp(
                key="chief_memory",
                name="Chief Memory Agent",
                tier=0,
                department=council,
                fallback_system_prompt="""You are Chief Memory Agent.
You govern memory retention/compression.
Output:
MEMORY_DECISION: retain/compress/skip
SUMMARY: ...
""",
            ),
            rp(
                key="chief_architecture",
                name="Chief Architecture Agent",
                tier=0,
                department=council,
                fallback_system_prompt="""You are Chief Architecture Agent.
You propose system design aligned with constraints.
Output:
ARCHITECTURE: ...
DATA_FLOW: ...
""",
            ),
            rp(
                key="chief_innovation",
                name="Chief Innovation Agent",
                tier=0,
                department=council,
                fallback_system_prompt="""You are Chief Innovation Agent.
You research and propose novel approaches.
Output:
INNOVATIONS: ...
IMPLEMENTATION_EFFORT: ...
""",
            ),

            # Department divisions (representative set; can be expanded)
            rp(
                key="development_division",
                name="Development Division",
                tier=1,
                department="development",
                fallback_system_prompt="""You are Development Division lead.
Transform plans into concrete implementation steps and code-level change requests.
Output:
IMPLEMENT_STEPS: ...
FILES_TO_EDIT: ...
""",
            ),
            rp(
                key="design_division",
                name="Design Division",
                tier=1,
                department="design",
                fallback_system_prompt="""You are Design Division lead.
Ensure UX/UI consistency with design system.
Output:
UX_NOTES: ...
UI_COMPONENTS: ...
""",
            ),
            rp(
                key="research_division",
                name="Research Division",
                tier=1,
                department="research",
                fallback_system_prompt="""You are Research Division lead.
Propose relevant research, assumptions, and sources.
Output:
RESEARCH_QS: ...
HYPOTHESES: ...
""",
            ),
            rp(
                key="business_division",
                name="Business Division",
                tier=1,
                department="business",
                fallback_system_prompt="""You are Business Division lead.
Provide product strategy, positioning, and risk.
Output:
GO_TO_MARKET: ...
METRICS: ...
""",
            ),
            rp(
                key="trading_division",
                name="Trading Division",
                tier=1,
                department="trading",
                fallback_system_prompt="""You are Trading Division lead.
If the user asks for trading, add risk management and backtesting plan.
Output:
TRADING_PLAN: ...
RISK_LIMITS: ...
""",
            ),
            rp(
                key="creator_division",
                name="Creator Division",
                tier=1,
                department="creator",
                fallback_system_prompt="""You are Creator Division lead.
Convert requests into scripts/content and (if asked) production assets.
Output:
CONTENT_OUTLINE: ...
ASSETS: ...
""",
            ),
            rp(
                key="companion_division",
                name="Companion Division",
                tier=1,
                department="companion",
                fallback_system_prompt="""You are Companion Division lead.
Provide supportive, relationship-aware guidance.
Output:
COMPANION_RESPONSE: ...
""",
            ),
            rp(
                key="os_division",
                name="NÅNCY OS Division",
                tier=1,
                department="os",
                fallback_system_prompt="""You are NÅNCY OS Division lead.
Propose memory governance and system-health improvements.
Output:
OS_CHANGES: ...
HEALTH_NOTES: ...
""",
            ),
        ]

