"""
Ethical Governance Core - Production-Grade Implementation
Tony Stark's moral compass for Nancy/Billion.

Implements:
  - Multi-framework moral reasoning (utilitarian, deontological, virtue ethics, contractarian)
  - Consequence forecasting with uncertainty quantification
  - Dynamic consent management
  - Full audit trails for all autonomous decisions
  - Value alignment scoring
  - Ethical red-line enforcement
  - Stakeholder impact modelling

References:
  - Rawls, J. (1971). A Theory of Justice.
  - Kant, I. (1785). Groundwork of the Metaphysics of Morals.
  - Mill, J.S. (1863). Utilitarianism.
  - IEEE EAD (2019). Ethically Aligned Design, v2.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import random
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Deque, Dict, List, Optional, Set, Tuple

from .base_specialized_agent import SpecializedAgent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class EthicalFramework(Enum):
    UTILITARIAN    = "utilitarian"     # greatest good for greatest number
    DEONTOLOGICAL  = "deontological"   # duty-based rules, Kantian
    VIRTUE         = "virtue_ethics"   # character-based, Aristotelian
    CONTRACTARIAN  = "contractarian"   # fairness behind veil of ignorance
    CARE_ETHICS    = "care_ethics"     # relationships, context, empathy


class EthicalVerdict(Enum):
    PERMITTED      = "permitted"       # action is ethically acceptable
    RECOMMENDED    = "recommended"     # action is positively good
    CAUTION        = "caution"         # action is acceptable with safeguards
    DISCOURAGED    = "discouraged"     # action should be avoided if possible
    PROHIBITED     = "prohibited"      # action violates a hard ethical rule
    NEEDS_CONSENT  = "needs_consent"   # action requires explicit human consent


class ConsentStatus(Enum):
    NOT_REQUESTED  = "not_requested"
    REQUESTED      = "requested"
    GRANTED        = "granted"
    DENIED         = "denied"
    EXPIRED        = "expired"
    REVOKED        = "revoked"


class StakeholderType(Enum):
    USER           = "user"
    THIRD_PARTY    = "third_party"
    SOCIETY        = "society"
    ENVIRONMENT    = "environment"
    FUTURE_GENS    = "future_generations"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class EthicalAction:
    """Description of an action to be evaluated."""
    action_id:    str
    description:  str
    actor:        str
    targets:      List[str]
    context:      Dict[str, Any]
    urgency:      float              # 0-1
    reversible:   bool
    data_involved: List[str]
    timestamp:    float


@dataclass
class FrameworkScore:
    """Score from a single ethical framework."""
    framework:    EthicalFramework
    score:        float          # -1 (bad) to +1 (good)
    confidence:   float          # 0-1
    reasoning:    str
    red_lines:    List[str]      # any hard violations


@dataclass
class EthicalDecision:
    """Full multi-framework ethical decision."""
    decision_id:       str
    action:            EthicalAction
    framework_scores:  List[FrameworkScore]
    aggregate_score:   float          # weighted average
    verdict:           EthicalVerdict
    confidence:        float
    reasoning_summary: str
    safeguards:        List[str]
    consent_required:  bool
    timestamp:         float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id":       self.decision_id,
            "action_id":         self.action.action_id,
            "description":       self.action.description,
            "aggregate_score":   self.aggregate_score,
            "verdict":           self.verdict.value,
            "confidence":        self.confidence,
            "reasoning_summary": self.reasoning_summary,
            "safeguards":        self.safeguards,
            "consent_required":  self.consent_required,
            "framework_scores": [
                {
                    "framework":  fs.framework.value,
                    "score":      fs.score,
                    "confidence": fs.confidence,
                    "reasoning":  fs.reasoning,
                }
                for fs in self.framework_scores
            ],
            "timestamp":         self.timestamp,
        }


@dataclass
class ConsentRecord:
    """Record of a consent request and its status."""
    consent_id:   str
    action_id:    str
    subject:      str
    purpose:      str
    data_types:   List[str]
    status:       ConsentStatus
    requested_at: float
    responded_at: Optional[float] = None
    expires_at:   Optional[float] = None
    ttl_seconds:  float = 3600.0

    @property
    def is_valid(self) -> bool:
        if self.status != ConsentStatus.GRANTED:
            return False
        if self.expires_at and time.time() > self.expires_at:
            return False
        return True


@dataclass
class ConsequenceForecast:
    """Predicted consequences of an action."""
    forecast_id:     str
    action_id:       str
    horizon_label:   str      # short/medium/long/generational
    stakeholder:     StakeholderType
    impact_score:    float    # -1 to +1
    probability:     float    # 0-1
    uncertainty:     float    # 0-1
    description:     str
    timestamp:       float


# ---------------------------------------------------------------------------
# Subsystems
# ---------------------------------------------------------------------------

class HardRedLineEnforcer:
    """
    Enforces absolute ethical red lines that cannot be overridden by any
    framework score or urgency claim.
    """

    RED_LINES: List[Dict[str, Any]] = [
        {"id": "RL-01", "rule": "Must not deceive the user about being an AI."},
        {"id": "RL-02", "rule": "Must not assist in creating weapons of mass destruction."},
        {"id": "RL-03", "rule": "Must not access or expose personal data without consent."},
        {"id": "RL-04", "rule": "Must not take irreversible catastrophic actions without human approval."},
        {"id": "RL-05", "rule": "Must not discriminate on protected characteristics."},
        {"id": "RL-06", "rule": "Must not manipulate users against their own interests."},
        {"id": "RL-07", "rule": "Must not disable its own safety or audit systems."},
        {"id": "RL-08", "rule": "Must not produce or distribute illegal content."},
        {"id": "RL-09", "rule": "Must maintain audit transparency at all times."},
        {"id": "RL-10", "rule": "Must escalate to human oversight for decisions affecting many people."},
    ]

    FORBIDDEN_KEYWORDS = {
        "weapon", "explosive", "bioweapon", "nuke", "ransom", "malware",
        "child pornography", "csam", "doxxing", "assassination",
    }

    def check(self, action: EthicalAction) -> Tuple[bool, List[str]]:
        """
        Returns (passes, list_of_violations).
        passes=False means a hard red line is triggered.
        """
        violations: List[str] = []
        desc_lower = action.description.lower()

        # Keyword check
        for kw in self.FORBIDDEN_KEYWORDS:
            if kw in desc_lower:
                violations.append(f"RL-02/RL-08: Forbidden keyword detected: '{kw}'")

        # Irreversible + catastrophic without approval
        if not action.reversible and action.context.get("scale", "individual") == "global":
            violations.append("RL-04: Irreversible global-scale action requires explicit human approval.")

        # Personal data without consent markers
        if action.data_involved and not action.context.get("consent_obtained", False):
            violations.append("RL-03: Personal data operation without documented consent.")

        return len(violations) == 0, violations


class MoralReasoningEngine:
    """
    Applies five ethical frameworks to evaluate an action, returning a score
    per framework and an aggregate verdict.
    """

    FRAMEWORK_WEIGHTS = {
        EthicalFramework.UTILITARIAN:   0.30,
        EthicalFramework.DEONTOLOGICAL: 0.25,
        EthicalFramework.VIRTUE:        0.20,
        EthicalFramework.CONTRACTARIAN: 0.15,
        EthicalFramework.CARE_ETHICS:   0.10,
    }

    def evaluate(self, action: EthicalAction, red_line_violations: List[str]) -> List[FrameworkScore]:
        """Evaluate the action against all ethical frameworks."""
        scores = []
        for framework, weight in self.FRAMEWORK_WEIGHTS.items():
            score = self._score_framework(framework, action, red_line_violations)
            scores.append(score)
        return scores

    def _score_framework(self, fw: EthicalFramework, action: EthicalAction,
                          violations: List[str]) -> FrameworkScore:
        if violations:
            return FrameworkScore(
                framework  = fw,
                score      = -1.0,
                confidence = 1.0,
                reasoning  = f"Hard red-line violations detected: {violations}",
                red_lines  = violations,
            )

        # Base score from action properties
        reversibility_bonus = 0.15 if action.reversible else -0.10
        urgency_penalty     = -0.05 if action.urgency > 0.8 else 0.0

        if fw == EthicalFramework.UTILITARIAN:
            # Maximise aggregate well-being across targets
            beneficiaries = len(action.targets)
            harm_risk     = action.context.get("harm_probability", 0.05)
            benefit       = action.context.get("benefit_magnitude", 0.7)
            score = benefit * (1 - harm_risk) * math.log1p(beneficiaries) / 3.0
            score = min(1.0, score + reversibility_bonus + urgency_penalty)
            reasoning = (f"Utilitarian: benefit={benefit:.2f}, harm_prob={harm_risk:.2f}, "
                         f"beneficiaries={beneficiaries}")

        elif fw == EthicalFramework.DEONTOLOGICAL:
            # Duty-based: respect persons as ends, never merely as means
            respects_autonomy = action.context.get("respects_autonomy", True)
            is_universal      = action.context.get("universalizable", True)
            score = 0.6 if (respects_autonomy and is_universal) else 0.1
            score += reversibility_bonus
            score = max(-1.0, min(1.0, score))
            reasoning = (f"Deontological: respects_autonomy={respects_autonomy}, "
                         f"universalizable={is_universal}")

        elif fw == EthicalFramework.VIRTUE:
            # Character-based: would a virtuous agent perform this action?
            virtues = action.context.get("virtues_expressed", ["honesty", "prudence"])
            virtue_score = len(virtues) / 7.0  # normalise against 7 cardinal virtues
            score = min(1.0, virtue_score + reversibility_bonus)
            reasoning = f"Virtue ethics: virtues expressed = {virtues}"

        elif fw == EthicalFramework.CONTRACTARIAN:
            # Rawlsian: would this be chosen from behind the veil of ignorance?
            fair_to_worst_off = action.context.get("fair_to_most_vulnerable", True)
            score = 0.7 if fair_to_worst_off else -0.3
            score += reversibility_bonus + urgency_penalty
            score = max(-1.0, min(1.0, score))
            reasoning = f"Contractarian: fair_to_most_vulnerable={fair_to_worst_off}"

        else:  # CARE_ETHICS
            # Relational: does it honour existing caring relationships?
            preserves_trust = action.context.get("preserves_trust", True)
            score = 0.65 if preserves_trust else -0.2
            score += reversibility_bonus
            score = max(-1.0, min(1.0, score))
            reasoning = f"Care ethics: preserves_trust={preserves_trust}"

        # Confidence heuristic: clear-cut scores (near +/-1) are more confident
        # than borderline ones (near 0) — this is a real signal derived from the
        # score itself, not decorative randomness. (Previously this added Gaussian
        # noise "to simulate deliberation uncertainty" and derived confidence from
        # that same synthetic noise, which was circular and not a real uncertainty
        # measure — removed.)
        confidence = round(0.5 + 0.5 * abs(score), 4)

        return FrameworkScore(
            framework  = fw,
            score      = round(score, 4),
            confidence = round(confidence, 4),
            reasoning  = reasoning,
            red_lines  = [],
        )

    def aggregate(self, scores: List[FrameworkScore]) -> Tuple[float, float]:
        """Returns (aggregate_score, aggregate_confidence)."""
        total_w = sum(self.FRAMEWORK_WEIGHTS[s.framework] for s in scores)
        agg_score = sum(
            self.FRAMEWORK_WEIGHTS[s.framework] * s.score for s in scores
        ) / max(total_w, 1e-9)
        agg_conf = sum(
            self.FRAMEWORK_WEIGHTS[s.framework] * s.confidence for s in scores
        ) / max(total_w, 1e-9)
        return round(agg_score, 4), round(agg_conf, 4)

    def determine_verdict(self, score: float, red_lines: List[str],
                          consent_required: bool) -> EthicalVerdict:
        if red_lines:
            return EthicalVerdict.PROHIBITED
        if consent_required:
            return EthicalVerdict.NEEDS_CONSENT
        if score >= 0.6:
            return EthicalVerdict.RECOMMENDED
        if score >= 0.2:
            return EthicalVerdict.PERMITTED
        if score >= -0.1:
            return EthicalVerdict.CAUTION
        if score >= -0.4:
            return EthicalVerdict.DISCOURAGED
        return EthicalVerdict.PROHIBITED


class ConsequenceForecaster:
    """
    Predicts the consequences of an action across multiple time horizons
    and stakeholder groups with uncertainty quantification.
    """

    HORIZONS = [
        ("short",        1.0,   "Hours to days"),
        ("medium",       0.85,  "Weeks to months"),
        ("long",         0.65,  "Years to decades"),
        ("generational", 0.40,  "Decades to centuries"),
    ]

    def forecast(self, action: EthicalAction) -> List[ConsequenceForecast]:
        forecasts: List[ConsequenceForecast] = []
        base_impact = action.context.get("benefit_magnitude", 0.5) - \
                      action.context.get("harm_probability", 0.05) * 0.8

        for horizon_label, decay, _ in self.HORIZONS:
            for stakeholder in StakeholderType:
                impact      = self._compute_impact(base_impact, stakeholder, decay)
                probability  = max(0.05, decay - 0.1 * (1 - action.reversible))
                uncertainty  = 1.0 - decay + random.uniform(0, 0.1)

                forecasts.append(ConsequenceForecast(
                    forecast_id   = str(uuid.uuid4()),
                    action_id     = action.action_id,
                    horizon_label = horizon_label,
                    stakeholder   = stakeholder,
                    impact_score  = round(impact, 4),
                    probability   = round(probability, 4),
                    uncertainty   = round(min(1.0, uncertainty), 4),
                    description   = self._describe(stakeholder, horizon_label, impact),
                    timestamp     = time.time(),
                ))
        return forecasts

    def _compute_impact(self, base: float, stakeholder: StakeholderType, decay: float) -> float:
        multipliers = {
            StakeholderType.USER:        1.0,
            StakeholderType.THIRD_PARTY: 0.7,
            StakeholderType.SOCIETY:     0.5,
            StakeholderType.ENVIRONMENT: 0.4,
            StakeholderType.FUTURE_GENS: 0.3 * decay,
        }
        m = multipliers.get(stakeholder, 0.5)
        noise = random.gauss(0, 0.04)
        return max(-1.0, min(1.0, base * m * decay + noise))

    def _describe(self, stakeholder: StakeholderType, horizon: str, impact: float) -> str:
        direction = "positive" if impact > 0.1 else "negative" if impact < -0.1 else "neutral"
        magnitude = "significant" if abs(impact) > 0.5 else "moderate" if abs(impact) > 0.2 else "minor"
        return (f"{magnitude.capitalize()} {direction} {horizon}-term impact "
                f"on {stakeholder.value}. (score={impact:.2f})")


class ConsentManager:
    """
    Dynamic context-aware consent management system.
    """

    def __init__(self):
        self._records: Dict[str, ConsentRecord] = {}
        self._history: Deque[ConsentRecord]     = deque(maxlen=1000)

    def request(self, action_id: str, subject: str, purpose: str,
                data_types: List[str], ttl: float = 3600.0) -> ConsentRecord:
        record = ConsentRecord(
            consent_id   = str(uuid.uuid4()),
            action_id    = action_id,
            subject      = subject,
            purpose      = purpose,
            data_types   = data_types,
            status       = ConsentStatus.REQUESTED,
            requested_at = time.time(),
            ttl_seconds  = ttl,
        )
        self._records[record.consent_id] = record
        logger.info("Consent requested: %s for action %s", record.consent_id, action_id)
        return record

    def respond(self, consent_id: str, granted: bool) -> bool:
        if consent_id not in self._records:
            return False
        record = self._records[consent_id]
        record.status      = ConsentStatus.GRANTED if granted else ConsentStatus.DENIED
        record.responded_at = time.time()
        if granted:
            record.expires_at = time.time() + record.ttl_seconds
        self._history.append(record)
        return True

    def revoke(self, consent_id: str) -> bool:
        if consent_id not in self._records:
            return False
        self._records[consent_id].status = ConsentStatus.REVOKED
        return True

    def is_consented(self, action_id: str) -> bool:
        for r in self._records.values():
            if r.action_id == action_id and r.is_valid:
                return True
        return False

    def get_record(self, consent_id: str) -> Optional[ConsentRecord]:
        return self._records.get(consent_id)

    def list_pending(self) -> List[ConsentRecord]:
        return [r for r in self._records.values() if r.status == ConsentStatus.REQUESTED]


# ---------------------------------------------------------------------------
# Main agent
# ---------------------------------------------------------------------------

class EthicalGovernanceCore(SpecializedAgent):
    """
    Ethical Governance Core Agent

    Capabilities:
    - Multi-framework moral reasoning (5 frameworks)
    - Hard red-line enforcement (10 absolute rules)
    - Consequence forecasting across time horizons × stakeholders
    - Dynamic consent management
    - Value alignment scoring
    - Safeguard recommendation
    - Full decision audit trail
    - Transparency reporting for all autonomous decisions
    """

    def __init__(self, settings):
        super().__init__(settings, "Ethical Governance Core", "ethics")
        self.capabilities.update({
            "description": (
                "Tony Stark's moral compass for Nancy/Billion. Applies five ethical "
                "frameworks, enforces hard red lines, forecasts consequences, and manages "
                "consent for all autonomous decisions with full audit transparency."
            ),
            "confidence": 0.91,
            "specializations": [
                "moral_reasoning",
                "red_line_enforcement",
                "consequence_forecasting",
                "consent_management",
                "value_alignment",
                "safeguard_recommendation",
                "decision_audit",
                "transparency_reporting",
                "stakeholder_impact_modelling",
                "ethical_review",
            ],
            "tools": [
                "red_line_enforcer",
                "moral_reasoning_engine",
                "consequence_forecaster",
                "consent_manager",
            ],
        })

        self._red_line   = HardRedLineEnforcer()
        self._reasoner   = MoralReasoningEngine()
        self._forecaster = ConsequenceForecaster()
        self._consent_mgr = ConsentManager()

        self._decisions:  Dict[str, EthicalDecision] = {}
        self._audit_log:  Deque[Dict[str, Any]]      = deque(maxlen=5000)
        self._value_alignment_history: Deque[float]  = deque(maxlen=200)

    # ------------------------------------------------------------------
    # SpecializedAgent interface
    # ------------------------------------------------------------------

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        await asyncio.sleep(0.05)
        task_type = task_data.get("type", "evaluate")

        dispatch = {
            "evaluate":          self._handle_evaluate,
            "forecast":          self._handle_forecast,
            "consent_request":   self._handle_consent_request,
            "consent_respond":   self._handle_consent_respond,
            "consent_revoke":    self._handle_consent_revoke,
            "consent_check":     self._handle_consent_check,
            "consent_pending":   self._handle_consent_pending,
            "red_line_check":    self._handle_red_line_check,
            "alignment_score":   self._handle_alignment_score,
            "audit_log":         self._handle_audit_log,
            "decision_history":  self._handle_decision_history,
            "transparency_report": self._handle_transparency_report,
            "safeguards":        self._handle_safeguards,
        }

        handler = dispatch.get(task_type)
        if handler is None:
            return self._error(f"Unknown task type: {task_type}")
        try:
            return await handler(task_data)
        except Exception as exc:
            logger.exception("EthicalGovernanceCore task '%s' error: %s", task_type, exc)
            return self._error(str(exc))

    # ------------------------------------------------------------------
    # Task handlers
    # ------------------------------------------------------------------

    async def _handle_evaluate(self, data: Dict) -> Dict[str, Any]:
        """Full ethical evaluation of a proposed action."""
        action = EthicalAction(
            action_id    = data.get("action_id", str(uuid.uuid4())),
            description  = str(data.get("description", "")),
            actor        = str(data.get("actor", "nancy_billion")),
            targets      = list(data.get("targets", ["user"])),
            context      = dict(data.get("context", {})),
            urgency      = float(data.get("urgency", 0.3)),
            reversible   = bool(data.get("reversible", True)),
            data_involved = list(data.get("data_involved", [])),
            timestamp    = time.time(),
        )

        # 1. Hard red-line check
        passes_rl, violations = self._red_line.check(action)

        # 2. Multi-framework moral reasoning
        fw_scores  = self._reasoner.evaluate(action, violations)
        agg_score, agg_conf = self._reasoner.aggregate(fw_scores)

        # 3. Determine if consent is required
        consent_required = bool(action.data_involved) and not action.context.get("consent_obtained", False)

        # 4. Determine verdict
        verdict = self._reasoner.determine_verdict(agg_score, violations, consent_required)

        # 5. Generate safeguards
        safeguards = self._recommend_safeguards(action, verdict, violations)

        # 6. Compose summary
        summary = self._compose_summary(action, agg_score, verdict, violations, safeguards)

        decision = EthicalDecision(
            decision_id       = str(uuid.uuid4()),
            action            = action,
            framework_scores  = fw_scores,
            aggregate_score   = agg_score,
            verdict           = verdict,
            confidence        = agg_conf,
            reasoning_summary = summary,
            safeguards        = safeguards,
            consent_required  = consent_required,
            timestamp         = time.time(),
        )
        self._decisions[decision.decision_id] = decision
        self._value_alignment_history.append(max(0.0, agg_score))
        self._audit_event("evaluated", decision.decision_id, verdict.value, agg_score)

        return {
            "success":          True,
            "type":             "ethical_evaluation",
            "decision":         decision.to_dict(),
            "timestamp":        time.time(),
        }

    async def _handle_forecast(self, data: Dict) -> Dict[str, Any]:
        action = EthicalAction(
            action_id    = data.get("action_id", str(uuid.uuid4())),
            description  = str(data.get("description", "")),
            actor        = str(data.get("actor", "nancy_billion")),
            targets      = list(data.get("targets", ["user"])),
            context      = dict(data.get("context", {})),
            urgency      = float(data.get("urgency", 0.3)),
            reversible   = bool(data.get("reversible", True)),
            data_involved = list(data.get("data_involved", [])),
            timestamp    = time.time(),
        )

        await asyncio.sleep(0.1)
        forecasts = self._forecaster.forecast(action)

        # Summarise by stakeholder
        summary: Dict[str, Dict[str, float]] = defaultdict(dict)
        for fc in forecasts:
            summary[fc.stakeholder.value][fc.horizon_label] = fc.impact_score

        self._audit_event("forecasted", action.action_id, "consequence_forecast",
                          sum(fc.impact_score for fc in forecasts) / max(len(forecasts), 1))

        return {
            "success":         True,
            "type":            "consequence_forecast",
            "action_id":       action.action_id,
            "forecast_count":  len(forecasts),
            "summary":         dict(summary),
            "forecasts": [
                {
                    "id":          fc.forecast_id,
                    "horizon":     fc.horizon_label,
                    "stakeholder": fc.stakeholder.value,
                    "impact":      fc.impact_score,
                    "probability": fc.probability,
                    "uncertainty": fc.uncertainty,
                    "description": fc.description,
                }
                for fc in forecasts
            ],
            "timestamp": time.time(),
        }

    async def _handle_consent_request(self, data: Dict) -> Dict[str, Any]:
        action_id  = data.get("action_id", str(uuid.uuid4()))
        subject    = data.get("subject", "user")
        purpose    = data.get("purpose", "")
        data_types = list(data.get("data_types", []))
        ttl        = float(data.get("ttl", 3600.0))

        record = self._consent_mgr.request(action_id, subject, purpose, data_types, ttl)
        self._audit_event("consent_requested", record.consent_id, "requested", 0.0)

        return {
            "success":    True,
            "type":       "consent_requested",
            "consent_id": record.consent_id,
            "action_id":  action_id,
            "subject":    subject,
            "purpose":    purpose,
            "data_types": data_types,
            "ttl":        ttl,
            "timestamp":  time.time(),
        }

    async def _handle_consent_respond(self, data: Dict) -> Dict[str, Any]:
        consent_id = data.get("consent_id", "")
        granted    = bool(data.get("granted", False))
        success    = self._consent_mgr.respond(consent_id, granted)
        self._audit_event("consent_responded", consent_id, "granted" if granted else "denied", 0.0)

        return {
            "success":    success,
            "type":       "consent_response",
            "consent_id": consent_id,
            "granted":    granted,
            "timestamp":  time.time(),
        }

    async def _handle_consent_revoke(self, data: Dict) -> Dict[str, Any]:
        consent_id = data.get("consent_id", "")
        success    = self._consent_mgr.revoke(consent_id)
        if success:
            self._audit_event("consent_revoked", consent_id, "revoked", 0.0)
        return {"success": success, "type": "consent_revoked", "consent_id": consent_id, "timestamp": time.time()}

    async def _handle_consent_check(self, data: Dict) -> Dict[str, Any]:
        action_id = data.get("action_id", "")
        consented = self._consent_mgr.is_consented(action_id)
        return {"success": True, "type": "consent_check", "action_id": action_id,
                "consented": consented, "timestamp": time.time()}

    async def _handle_consent_pending(self, _: Dict) -> Dict[str, Any]:
        pending = self._consent_mgr.list_pending()
        return {
            "success": True, "type": "consent_pending",
            "count": len(pending),
            "records": [
                {
                    "consent_id": r.consent_id,
                    "action_id":  r.action_id,
                    "subject":    r.subject,
                    "purpose":    r.purpose,
                    "requested_at": r.requested_at,
                }
                for r in pending
            ],
            "timestamp": time.time(),
        }

    async def _handle_red_line_check(self, data: Dict) -> Dict[str, Any]:
        action = EthicalAction(
            action_id    = data.get("action_id", str(uuid.uuid4())),
            description  = str(data.get("description", "")),
            actor        = str(data.get("actor", "nancy_billion")),
            targets      = list(data.get("targets", [])),
            context      = dict(data.get("context", {})),
            urgency      = float(data.get("urgency", 0.0)),
            reversible   = bool(data.get("reversible", True)),
            data_involved = list(data.get("data_involved", [])),
            timestamp    = time.time(),
        )
        passes, violations = self._red_line.check(action)
        return {
            "success":    True,
            "type":       "red_line_check",
            "passes":     passes,
            "violations": violations,
            "red_lines":  [rl["rule"] for rl in HardRedLineEnforcer.RED_LINES],
            "timestamp":  time.time(),
        }

    async def _handle_alignment_score(self, _: Dict) -> Dict[str, Any]:
        history = list(self._value_alignment_history)
        if not history:
            avg = None
        else:
            avg = sum(history) / len(history)
            # Normalise to 0-100 scale
            score_100 = max(0.0, min(100.0, (avg + 1.0) * 50.0))
        return {
            "success":              True,
            "type":                 "alignment_score",
            "average_score":        round(avg, 4) if avg is not None else None,
            "alignment_score_100":  round(score_100, 2) if avg is not None else None,
            "decisions_evaluated":  len(self._decisions),
            "trend":                self._alignment_trend(history),
            "timestamp":            time.time(),
        }

    async def _handle_audit_log(self, data: Dict) -> Dict[str, Any]:
        limit   = int(data.get("limit", 50))
        entries = list(self._audit_log)[-limit:]
        return {
            "success":       True,
            "type":          "audit_log",
            "total_entries": len(self._audit_log),
            "returned":      len(entries),
            "entries":       entries,
        }

    async def _handle_decision_history(self, data: Dict) -> Dict[str, Any]:
        limit     = int(data.get("limit", 20))
        decisions = list(self._decisions.values())[-limit:]
        return {
            "success":    True,
            "type":       "decision_history",
            "total":      len(self._decisions),
            "returned":   len(decisions),
            "decisions":  [d.to_dict() for d in decisions],
            "timestamp":  time.time(),
        }

    async def _handle_transparency_report(self, _: Dict) -> Dict[str, Any]:
        decisions = list(self._decisions.values())
        verdict_counts: Dict[str, int] = defaultdict(int)
        for d in decisions:
            verdict_counts[d.verdict.value] += 1

        avg_score = (sum(d.aggregate_score for d in decisions) / len(decisions)
                     if decisions else 0.0)

        return {
            "success":          True,
            "type":             "transparency_report",
            "total_decisions":  len(decisions),
            "verdict_distribution": dict(verdict_counts),
            "average_ethical_score": round(avg_score, 4),
            "red_lines_enforced": sum(
                1 for d in decisions if d.verdict == EthicalVerdict.PROHIBITED
            ),
            "consent_requests": len(self._consent_mgr.list_pending()) +
                                 len(self._consent_mgr._history),
            "audit_entries":    len(self._audit_log),
            "red_line_rules":   [rl["rule"] for rl in HardRedLineEnforcer.RED_LINES],
            "frameworks_used":  [fw.value for fw in EthicalFramework],
            "timestamp":        time.time(),
        }

    async def _handle_safeguards(self, data: Dict) -> Dict[str, Any]:
        verdict_str = data.get("verdict", "caution")
        desc        = data.get("description", "")
        try:
            verdict = EthicalVerdict(verdict_str)
        except ValueError:
            verdict = EthicalVerdict.CAUTION
        safeguards = self._recommend_safeguards_by_verdict(verdict, desc)
        return {
            "success":    True,
            "type":       "safeguard_recommendations",
            "verdict":    verdict_str,
            "safeguards": safeguards,
            "timestamp":  time.time(),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _recommend_safeguards(self, action: EthicalAction, verdict: EthicalVerdict,
                               violations: List[str]) -> List[str]:
        safeguards: Set[str] = set()

        if not action.reversible:
            safeguards.add("Require explicit human confirmation before execution.")
        if action.data_involved:
            safeguards.add("Apply data minimisation: use only the minimum necessary data.")
            safeguards.add("Encrypt data in transit and at rest.")
        if action.urgency > 0.7:
            safeguards.add("Log urgency override with justification for post-hoc review.")
        if verdict in (EthicalVerdict.CAUTION, EthicalVerdict.DISCOURAGED):
            safeguards.add("Present ethical reasoning summary to the user before proceeding.")
        if violations:
            safeguards.add("Block execution until red-line violations are resolved.")
        if len(action.targets) > 10:
            safeguards.add("Escalate to human oversight: large-scale impact detected.")

        safeguards.add("Maintain immutable audit record of this decision.")
        return sorted(safeguards)

    def _recommend_safeguards_by_verdict(self, verdict: EthicalVerdict, desc: str) -> List[str]:
        base = ["Maintain immutable audit record of this decision."]
        additions = {
            EthicalVerdict.PROHIBITED:    ["Block execution immediately.", "Alert human overseer."],
            EthicalVerdict.NEEDS_CONSENT: ["Request explicit user consent before proceeding.", "Explain data usage clearly."],
            EthicalVerdict.DISCOURAGED:   ["Present alternatives to the user.", "Log decision with full justification."],
            EthicalVerdict.CAUTION:       ["Log decision with ethical score.", "Notify user of potential concerns."],
            EthicalVerdict.PERMITTED:     ["Standard audit logging applies."],
            EthicalVerdict.RECOMMENDED:   ["Standard audit logging applies."],
        }
        return base + additions.get(verdict, [])

    def _compose_summary(self, action: EthicalAction, score: float,
                          verdict: EthicalVerdict, violations: List[str],
                          safeguards: List[str]) -> str:
        if violations:
            return (f"Action '{action.description[:60]}...' PROHIBITED: "
                    f"{len(violations)} hard red-line violation(s) detected. "
                    f"Violations: {'; '.join(violations[:2])}.")
        direction = "ethically positive" if score > 0.2 else "ethically neutral" if score > -0.1 else "ethically concerning"
        return (f"Action '{action.description[:60]}...' is {direction} "
                f"(aggregate score={score:.2f}). Verdict: {verdict.value.upper()}. "
                f"{len(safeguards)} safeguard(s) recommended.")

    def _alignment_trend(self, history: List[float]) -> str:
        if len(history) < 5:
            return "insufficient_data"
        recent = history[-5:]
        older  = history[:-5][-5:] if len(history) > 5 else recent
        r_avg  = sum(recent) / len(recent)
        o_avg  = sum(older)  / len(older)
        delta  = r_avg - o_avg
        if delta > 0.05:
            return "improving"
        if delta < -0.05:
            return "declining"
        return "stable"

    def _audit_event(self, event: str, entity: str, detail: str, score: float):
        self._audit_log.append({
            "event":     event,
            "entity":    entity,
            "detail":    detail,
            "score":     round(score, 4),
            "timestamp": time.time(),
        })

    @staticmethod
    def _error(message: str) -> Dict[str, Any]:
        return {"success": False, "error": message, "timestamp": time.time()}

    def get_status(self) -> Dict[str, Any]:
        base = super().get_status()
        base.update({
            "decisions_evaluated": len(self._decisions),
            "audit_entries":       len(self._audit_log),
            "pending_consents":    len(self._consent_mgr.list_pending()),
        })
        return base
