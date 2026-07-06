from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .hierarchy import NancyHierarchy

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrchestrationResult:
    decision: str
    final_response: str
    debug: Dict[str, Any]


class NancyOrchestrator:
    """A lightweight multi-agent orchestration layer.

    Implementation notes
    - This repo currently instantiates a single Fury agent per registry key.
    - Since the registry does not contain your named hierarchy agents, the
      orchestrator uses fallback system prompts for Tier0 and division leads.

    Routing strategy (v1)
    - Sovereign Core produces a PLAN + ROUTING into division roles.
    - Council gates (Security + Ethics) approve/deny the execution.
    - If approved, each division lead is called with its role-specific input.
    - Chief Operations determines the final assembled response.
    """

    def __init__(self, llm_callable, run_specialized_agent_callable) -> None:
        self.hierarchy = NancyHierarchy()
        self.llm = llm_callable
        self.run_specialized_agent = run_specialized_agent_callable
        
    def _is_complex_request(self, user_request: str) -> bool:
        """Detect if a request is complex and would benefit from multi-step planning."""
        complex_indicators = [
            "and then", "after that", "followed by", "first", "second", "finally",
            "plan", "strategy", "approach", "steps", "phase", "stage",
            "build", "create", "develop", "implement", "design",
            "analyze", "research", "investigate", "evaluate",
            "optimize", "improve", "enhance", "refactor",
            "deploy", "launch", "release", "publish"
        ]
        
        request_lower = user_request.lower()
        # Check for multiple complex indicators or specific patterns
        indicator_count = sum(1 for indicator in complex_indicators if indicator in request_lower)
        
        # Also check for request length and structure
        word_count = len(request_lower.split())
        
        return indicator_count >= 2 or word_count > 20 or "," in request_lower and len(request_lower.split(",")) > 2

    async def _run_role(self, role_key: str, input_text: str) -> str:
        role = self.hierarchy.by_key[role_key]

        # If we had a matching registry entry, we could call run_specialized_agent.
        # The current registry does not contain these keys, so we use the fallback
        # prompt by calling the base llm.
        if role.agent_registry_key:
            return await self.run_specialized_agent(role.agent_registry_key, input_text)

        system_prompt = role.fallback_system_prompt or ""
        # One-shot prompting into shared LLM backend.
        prompt = f"{system_prompt}\n\nINPUT:\n{input_text}\n\nOUTPUT:"
        return await self.llm(prompt, max_tokens=800, temperature=0.4)

    @staticmethod
    def _parse_gate(decision_text: str, default: str = "FAIL") -> str:
        t = decision_text.upper()
        if "PASS" in t and "FAIL" not in t:
            return "PASS"
        if "FAIL" in t:
            return "FAIL"
        return default

    async def orchestrate(self, user_request: str, session_context: Optional[str] = None) -> OrchestrationResult:
        debug: Dict[str, Any] = {}

        sovereign_input = user_request
        if session_context:
            sovereign_input = f"CONTEXT:\n{session_context}\n\nUSER_REQUEST:\n{user_request}"

        # 1) Sovereign Core
        core_out = await self._run_role("sovereign_core", sovereign_input)
        debug["sovereign_core"] = core_out

        # 2) Security & Ethics gates (pre-execution)
        sec_out = await self._run_role("chief_security", user_request)
        eth_out = await self._run_role("chief_ethics", user_request)
        debug["security"] = sec_out
        debug["ethics"] = eth_out

        sec_decision = self._parse_gate(sec_out, default="FAIL")
        eth_decision = self._parse_gate(eth_out, default="FAIL")

        if sec_decision != "PASS" or eth_decision != "PASS":
            final = (
                "Request denied by NÅNCY policy gates.\n"
                f"Security: {sec_decision}\n"
                f"Ethics: {eth_decision}\n"
                "Provide a safer reformulation or ask for a planning-only response."
            )
            return OrchestrationResult(
                decision="GATED_DENY",
                final_response=final,
                debug={"security_decision": sec_decision, "ethics_decision": eth_decision, **debug},
            )

        # 3) CEO sequence
        ceo_out = await self._run_role("chief_executive", core_out + "\n\n" + user_request)
        debug["ceo"] = ceo_out

        # 4) Strategy + Architecture (cheap early)
        strat_out = await self._run_role("chief_strategy", user_request)
        arch_out = await self._run_role("chief_architecture", user_request)
        debug["strategy"] = strat_out
        debug["architecture"] = arch_out

        # 5) Select division leads (v1 heuristic)
        # If core output mentions departments, we’d parse it; for v1 just route by keywords.
        u = user_request.lower()
        division_keys: List[str] = []

        if any(k in u for k in ["ui", "ux", "design", "dashboard", "react", "next.js", "tailwind"]):
            division_keys.append("design_division")
        if any(k in u for k in ["code", "implement", "bug", "fix", "backend", "frontend", "rust", "python", "typescript"]):
            division_keys.append("development_division")
        if any(k in u for k in ["research", "sources", "trend", "market", "academic", "paper"]):
            division_keys.append("research_division")
        if any(k in u for k in ["pricing", "sales", "marketing", "crm", "revenue", "business"]):
            division_keys.append("business_division")
        if any(k in u for k in ["trade", "trading", "forex", "crypto", "backtest", "quant", "portfolio"]):
            division_keys.append("trading_division")
        if any(k in u for k in ["youtube", "tiktok", "shorts", "script", "thumbnail", "content"]):
            division_keys.append("creator_division")
        if any(k in u for k in ["coach", "habit", "motivation", "companion", "wellness", "relationship"]):
            division_keys.append("companion_division")
        if any(k in u for k in ["memory", "system", "health", "audit", "upgrade", "os"]):
            division_keys.append("os_division")

        # Ensure at least one division runs.
        if not division_keys:
            division_keys = ["development_division"]

        # JARVIS ENHANCEMENT: Check if this is a complex request that would benefit from proactive planning
        is_complex = self._is_complex_request(user_request)
        proactive_suggestion = ""
        
        if is_complex:
            # Generate a proactive suggestion for complex requests
            try:
                suggestion_prompt = f"""As JARVIS, provide a brief, helpful suggestion for approaching this complex request: "{user_request}"

Focus on:
1. Breaking it down into manageable phases
2. Suggesting an efficient order of operations
3. Mentioning any potential considerations or prerequisites
4. Keeping it concise (1-2 sentences)

Response should be in your characteristic helpful, slightly formal tone."""
                
                proactive_suggestion = await self.llm(suggestion_prompt, max_tokens=150, temperature=0.3)
                debug["proactive_suggestion"] = proactive_suggestion
            except Exception as e:
                logger.error(f"Error generating proactive suggestion: {e}")
                proactive_suggestion = "For complex tasks like this, I recommend breaking it down into clear phases and verifying each step before proceeding."

        division_outs: Dict[str, str] = {}
        for dk in division_keys:
            div_out = await self._run_role(
                dk,
                input_text=(
                    f"USER_REQUEST:\n{user_request}\n\n"
                    f"COUNCIL_CONTEXT:\n{core_out}\n\n"
                    f"STRATEGY_OUT:\n{strat_out}\n\n"
                    f"ARCH_OUT:\n{arch_out}\n"
                    f"{'PROACTIVE_SUGGESTION:\n' + proactive_suggestion + '\n\n' if proactive_suggestion else ''}"
                ),
            )
            division_outs[dk] = div_out

        debug["divisions"] = division_outs

        # 6) Chief Operations assembles final response
        ops_out = await self._run_role(
            "chief_operations",
            input_text=(
                f"USER_REQUEST:\n{user_request}\n\n"
                f"CORE_OUT:\n{core_out}\n\n"
                f"DIVISION_OUTS:\n{json.dumps(division_outs, ensure_ascii=False, indent=2)}\n"
                f"{'PROACTIVE_SUGGESTION:\n' + proactive_suggestion + '\n\n' if proactive_suggestion else ''}"
            ),
        )
        debug["operations"] = ops_out

        # 7) Chief Learning (post)
        learn_out = await self._run_role("chief_learning", user_request + "\n\n" + ops_out)
        debug["learning"] = learn_out

        # Final: include ops_out + short response + proactive suggestion for complex tasks
        final = ops_out.strip()
        if not final:
            final = "Done."
            
        # Add proactive suggestion for complex requests (JARVIS-like anticipatory assistance)
        if is_complex and proactive_suggestion:
            final = f"{proactive_suggestion.strip()}\n\n{final}"

        return OrchestrationResult(
            decision="GATED_ALLOW",
            final_response=final,
            debug=debug,
        )

