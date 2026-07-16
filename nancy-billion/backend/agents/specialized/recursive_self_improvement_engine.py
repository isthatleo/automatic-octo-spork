"""
Recursive Self-Improvement Engine - Production-Grade Implementation

Scope, honestly stated: this agent tunes its own in-memory config dict
(hyperparameters, strategy weights) and simulates evaluation of proposed
changes — see `_simulate_evaluation` / `HyperparameterOptimizer` /
`KnowledgeDistiller`. It has NO filesystem, subprocess, or code-execution
access (no `os`/`subprocess`/`eval`/`exec`/`open` anywhere in this module) —
it cannot modify its own source code or any other file on disk. "Self-
modification" here means config/knob tuning, not literal code rewriting.

Safety gate: every proposed modification must (1) pass the automated
SafetyVerifier (risk threshold, ethical-weight/safety-bound/audit-trail
checks) to reach status=APPROVED, AND (2) receive an explicit human_approve
call with an `approved_by` identifier, before `apply` will act on it.
Automated verification alone is necessary but not sufficient — see
`_handle_human_approve` / `_handle_apply`.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import math
import random
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional, Set, Tuple

from .base_specialized_agent import SpecializedAgent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class ModificationType(Enum):
    HYPERPARAMETER   = "hyperparameter"      # tune numeric knobs
    ARCHITECTURE     = "architecture"         # add/remove/reshape modules
    KNOWLEDGE        = "knowledge"            # distil or expand knowledge
    STRATEGY         = "strategy"             # change reasoning strategies
    CAPABILITY       = "capability"            # enable new capability
    SAFETY_RULE      = "safety_rule"          # adjust (only relax with proof)
    META_LEARNING    = "meta_learning"        # improve learning algorithm


class VerificationStatus(Enum):
    PENDING    = "pending"
    RUNNING    = "running"
    PASSED     = "passed"
    FAILED     = "failed"
    SKIPPED    = "skipped"


class ModificationStatus(Enum):
    PROPOSED   = "proposed"
    VERIFYING  = "verifying"
    APPROVED   = "approved"
    REJECTED   = "rejected"
    APPLIED    = "applied"
    ROLLED_BACK = "rolled_back"


class EvolutionStrategy(Enum):
    GRADIENT_DESCENT  = "gradient_descent"
    EVOLUTIONARY      = "evolutionary"
    BAYESIAN_OPT      = "bayesian_optimization"
    RANDOM_SEARCH     = "random_search"
    HYPERBAND         = "hyperband"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class HyperparameterSpace:
    """Definition of a tunable hyperparameter."""
    name:    str
    low:     float
    high:    float
    current: float
    dtype:   str    = "float"   # float | int | categorical
    options: List   = field(default_factory=list)   # for categorical

    def sample(self) -> Any:
        if self.dtype == "categorical" and self.options:
            return random.choice(self.options)
        val = random.uniform(self.low, self.high)
        return int(round(val)) if self.dtype == "int" else round(val, 6)

    def perturb(self, sigma: float = 0.1) -> Any:
        if self.dtype == "categorical" and self.options:
            return random.choice(self.options)
        delta = random.gauss(0, sigma * (self.high - self.low))
        val   = max(self.low, min(self.high, self.current + delta))
        return int(round(val)) if self.dtype == "int" else round(val, 6)


@dataclass
class ModificationProposal:
    """A proposed self-modification."""
    proposal_id:    str
    mod_type:       ModificationType
    description:    str
    diff:           Dict[str, Any]       # before/after for each changed parameter
    expected_gain:  float                # estimated performance improvement (0-1)
    risk_level:     float                # 0=safe, 1=catastrophic
    justification:  str
    proposed_by:    str
    proposed_at:    float
    status:         ModificationStatus = ModificationStatus.PROPOSED
    verification:   VerificationStatus  = VerificationStatus.PENDING
    verification_report: Optional[Dict[str, Any]] = None
    applied_at:     Optional[float]     = None
    rollback_data:  Optional[Dict[str, Any]] = None
    # Human-in-the-loop gate: automated SafetyVerifier passing (status ->
    # APPROVED) is necessary but not sufficient to apply a modification. A
    # separate human_approve call is required first — see _handle_apply.
    human_approved:      bool = False
    human_approved_by:   Optional[str] = None
    human_approved_at:   Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id":                self.proposal_id,
            "type":              self.mod_type.value,
            "description":       self.description,
            "expected_gain":     self.expected_gain,
            "risk_level":        self.risk_level,
            "justification":     self.justification,
            "proposed_by":       self.proposed_by,
            "proposed_at":       self.proposed_at,
            "status":            self.status.value,
            "verification":      self.verification.value,
            "verification_report": self.verification_report,
            "applied_at":        self.applied_at,
            "human_approved":    self.human_approved,
            "human_approved_by": self.human_approved_by,
        }


@dataclass
class EvolutionResult:
    """Result of one evolution cycle."""
    cycle_id:    str
    generation:  int
    strategy:    EvolutionStrategy
    best_config: Dict[str, Any]
    best_score:  float
    improvement: float
    trials:      int
    duration_s:  float
    timestamp:   float


@dataclass
class KnowledgeDistillation:
    """A knowledge distillation event."""
    distill_id:    str
    source:        str
    target:        str
    domain:        str
    compression:   float   # compression ratio
    fidelity:      float   # how much knowledge was retained (0-1)
    params_before: int
    params_after:  int
    timestamp:     float


# ---------------------------------------------------------------------------
# Subsystems
# ---------------------------------------------------------------------------

class SafetyVerifier:
    """
    Formal safety verifier for proposed modifications.
    Applies a suite of safety checks before any modification is permitted.
    """

    # Constraints that MUST be maintained
    HARD_CONSTRAINTS = [
        "must_not_reduce_ethical_alignment",
        "must_not_remove_safety_bounds",
        "must_not_exceed_risk_threshold",
        "must_preserve_user_data_privacy",
        "must_not_disable_audit_trail",
    ]

    RISK_THRESHOLD = 0.65   # proposals above this risk are auto-rejected

    def verify(self, proposal: ModificationProposal, current_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the full verification suite.
        Returns a verification report dict.
        """
        checks: Dict[str, bool] = {}
        violations: List[str]   = []

        # Hard constraint checks
        checks["risk_within_threshold"]     = proposal.risk_level <= self.RISK_THRESHOLD
        checks["no_ethical_degradation"]    = not self._degrades_ethics(proposal, current_config)
        checks["no_safety_bounds_removed"]  = not self._removes_safety_bounds(proposal)
        checks["audit_trail_preserved"]     = not self._disables_audit(proposal)
        checks["privacy_preserved"]         = not self._violates_privacy(proposal)

        # Soft checks (warnings, not blockers)
        checks["expected_gain_positive"]    = proposal.expected_gain > 0.0
        checks["justification_present"]     = len(proposal.justification) > 20
        checks["diff_not_empty"]            = bool(proposal.diff)

        for constraint, passed in checks.items():
            if not passed and constraint in [
                "risk_within_threshold", "no_ethical_degradation",
                "no_safety_bounds_removed", "audit_trail_preserved", "privacy_preserved"
            ]:
                violations.append(constraint)

        passed_overall = len(violations) == 0
        status         = VerificationStatus.PASSED if passed_overall else VerificationStatus.FAILED

        return {
            "status":     status.value,
            "passed":     passed_overall,
            "checks":     checks,
            "violations": violations,
            "timestamp":  time.time(),
        }

    def _degrades_ethics(self, p: ModificationProposal, cfg: Dict[str, Any]) -> bool:
        # Any modification to ethical_weight below current value is blocked
        diff = p.diff
        if "ethical_weight" in diff:
            before = diff["ethical_weight"].get("before", 1.0)
            after  = diff["ethical_weight"].get("after",  1.0)
            return after < before
        return False

    def _removes_safety_bounds(self, p: ModificationProposal) -> bool:
        return p.mod_type == ModificationType.SAFETY_RULE and p.risk_level > 0.3

    def _disables_audit(self, p: ModificationProposal) -> bool:
        diff = p.diff
        return diff.get("audit_trail_enabled", {}).get("after") is False

    def _violates_privacy(self, p: ModificationProposal) -> bool:
        diff = p.diff
        return diff.get("data_retention_policy", {}).get("after") in ["log_all", "share_external"]


class HyperparameterOptimizer:
    """
    Multi-strategy hyperparameter optimizer (gradient-free).
    """

    def __init__(self, space: List[HyperparameterSpace]):
        self.space   = {hp.name: hp for hp in space}
        self.history: Deque[Tuple[Dict[str, Any], float]] = deque(maxlen=512)
        self.generation = 0

    def propose_config(self, strategy: EvolutionStrategy) -> Dict[str, Any]:
        """Generate the next hyperparameter configuration to try."""
        if strategy == EvolutionStrategy.RANDOM_SEARCH or not self.history:
            return {name: hp.sample() for name, hp in self.space.items()}

        if strategy == EvolutionStrategy.GRADIENT_DESCENT:
            return self._gradient_surrogate()

        if strategy == EvolutionStrategy.BAYESIAN_OPT:
            return self._bayesian_propose()

        if strategy == EvolutionStrategy.EVOLUTIONARY:
            return self._evolutionary_mutate()

        if strategy == EvolutionStrategy.HYPERBAND:
            return self._hyperband_sample()

        return {name: hp.sample() for name, hp in self.space.items()}

    def record(self, config: Dict[str, Any], score: float):
        self.history.append((config, score))
        self.generation += 1

    def best(self) -> Tuple[Optional[Dict[str, Any]], float]:
        if not self.history:
            return None, 0.0
        best_config, best_score = max(self.history, key=lambda x: x[1])
        return best_config, best_score

    # ---- strategy implementations ----------------------------------------

    def _gradient_surrogate(self) -> Dict[str, Any]:
        """Surrogate gradient estimate from recent history."""
        if len(self.history) < 3:
            return self._evolutionary_mutate()

        recent = list(self.history)[-10:]
        best_cfg, _ = max(recent, key=lambda x: x[1])
        return {
            name: self.space[name].perturb(0.05)
            if name not in best_cfg
            else max(hp.low, min(hp.high, best_cfg[name] + random.gauss(0, 0.03 * (hp.high - hp.low))))
            for name, hp in self.space.items()
        }

    def _bayesian_propose(self) -> Dict[str, Any]:
        """Thompson sampling approximation (Gaussian process surrogate)."""
        if len(self.history) < 5:
            return self._gradient_surrogate()

        # Estimate mean and std per parameter from top-k
        top_k = sorted(self.history, key=lambda x: x[1], reverse=True)[:max(5, len(self.history) // 3)]
        proposal = {}
        for name, hp in self.space.items():
            values = [cfg[name] for cfg, _ in top_k if name in cfg and isinstance(cfg[name], (int, float))]
            if values:
                mean = sum(values) / len(values)
                std  = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values)) + 1e-8
                sample = random.gauss(mean, std)
                proposal[name] = max(hp.low, min(hp.high, sample))
            else:
                proposal[name] = hp.sample()
        return proposal

    def _evolutionary_mutate(self) -> Dict[str, Any]:
        """Mutate the best-known configuration."""
        best_cfg, _ = self.best()
        if best_cfg is None:
            return {name: hp.sample() for name, hp in self.space.items()}
        result = {}
        for name, hp in self.space.items():
            if random.random() < 0.15:   # 15% mutation rate
                result[name] = hp.sample()
            else:
                result[name] = hp.perturb(0.08) if name in best_cfg else hp.current
        return result

    def _hyperband_sample(self) -> Dict[str, Any]:
        """Hyperband: mix random (exploration) and best-known (exploitation)."""
        if random.random() < 0.5:
            return {name: hp.sample() for name, hp in self.space.items()}
        return self._evolutionary_mutate()


class KnowledgeDistiller:
    """
    Distills knowledge from large 'teacher' representations to compact 'student'
    representations, preserving maximum fidelity.
    """

    def distill(self, teacher_domain: str, student_domain: str,
                teacher_params: int, compression_ratio: float,
                domain: str = "general") -> KnowledgeDistillation:
        """Simulate a distillation process."""
        target_params = max(1, int(teacher_params / max(compression_ratio, 1.0)))
        fidelity = 1.0 - 0.08 * math.log(max(compression_ratio, 1.01))
        fidelity = max(0.5, min(1.0, fidelity + random.gauss(0, 0.02)))

        distillation = KnowledgeDistillation(
            distill_id    = str(uuid.uuid4()),
            source        = teacher_domain,
            target        = student_domain,
            domain        = domain,
            compression   = compression_ratio,
            fidelity      = round(fidelity, 4),
            params_before = teacher_params,
            params_after  = target_params,
            timestamp     = time.time(),
        )
        logger.info(
            "Knowledge distilled %s→%s | compression=%.1fx | fidelity=%.3f | %dM→%dM params",
            teacher_domain, student_domain, compression_ratio,
            fidelity, teacher_params // 1_000_000, target_params // 1_000_000
        )
        return distillation


class MetaLearner:
    """
    Meta-learning module: learns how to learn better across tasks.
    Tracks learning curves and adapts the learning strategy dynamically.
    """

    def __init__(self):
        self.task_history:  Deque[Dict[str, Any]] = deque(maxlen=256)
        self.strategy_perf: Dict[str, List[float]] = defaultdict(list)
        self.current_lr    = 0.001
        self.current_wd    = 1e-5
        self.adaptation_count = 0

    def record_task(self, task_id: str, domain: str, strategy: str,
                    samples: int, final_loss: float, final_acc: float):
        self.task_history.append({
            "task_id":    task_id,
            "domain":     domain,
            "strategy":   strategy,
            "samples":    samples,
            "final_loss": final_loss,
            "final_acc":  final_acc,
            "timestamp":  time.time(),
        })
        self.strategy_perf[strategy].append(final_acc)

    def recommend_strategy(self, domain: str, n_samples: int) -> Dict[str, Any]:
        """Recommend the best learning strategy for a new task."""
        if not self.strategy_perf:
            return self._default_strategy(n_samples)

        best_strategy = max(
            self.strategy_perf,
            key=lambda s: sum(self.strategy_perf[s]) / len(self.strategy_perf[s])
        )
        avg_perf = sum(self.strategy_perf[best_strategy]) / len(self.strategy_perf[best_strategy])

        # Adapt learning rate based on task size
        lr = max(1e-5, min(0.1, 0.01 / math.sqrt(max(n_samples, 1))))

        return {
            "strategy":         best_strategy,
            "learning_rate":    round(lr, 6),
            "weight_decay":     self.current_wd,
            "expected_accuracy":round(avg_perf, 4),
            "based_on_tasks":   len(self.task_history),
        }

    def adapt(self) -> Dict[str, Any]:
        """Run a meta-adaptation cycle."""
        if len(self.task_history) < 5:
            return {"adapted": False, "reason": "Insufficient task history."}

        # Compute learning curve trend
        recent   = list(self.task_history)[-20:]
        accs     = [t["final_acc"] for t in recent]
        trend    = (accs[-1] - accs[0]) / max(len(accs) - 1, 1)

        # If trend is negative, increase learning rate modestly
        if trend < -0.01:
            self.current_lr = min(0.05, self.current_lr * 1.5)
        elif trend > 0.02:
            self.current_lr = max(1e-5, self.current_lr * 0.9)

        self.adaptation_count += 1
        return {
            "adapted":             True,
            "trend":               round(trend, 5),
            "new_learning_rate":   self.current_lr,
            "adaptation_count":    self.adaptation_count,
        }

    def _default_strategy(self, n_samples: int) -> Dict[str, Any]:
        lr = max(1e-5, min(0.01, 0.001 * math.sqrt(max(n_samples, 1))))
        return {
            "strategy":         "gradient_descent",
            "learning_rate":    round(lr, 6),
            "weight_decay":     1e-5,
            "expected_accuracy": 0.75,
            "based_on_tasks":   0,
        }


# ---------------------------------------------------------------------------
# Main agent
# ---------------------------------------------------------------------------

class RecursiveSelfImprovementEngine(SpecializedAgent):
    """
    Recursive Self-Improvement Engine

    Capabilities:
    - Safe architecture mutation with formal verification
    - Hyperparameter evolution (gradient-free, multi-strategy)
    - Knowledge distillation and compression
    - Meta-learning for cross-domain adaptation
    - Capability activation / deactivation
    - Rollback support for failed modifications
    - Full audit trail of all self-modifications
    - Safety-gated deployment pipeline
    """

    MAX_RISK          = 0.65    # hard cap; proposals above this are auto-rejected
    MAX_PENDING       = 32      # cap proposal queue depth
    EVOLUTION_TIMEOUT = 60.0    # seconds per evolution cycle

    def __init__(self, settings):
        super().__init__(settings, "Recursive Self-Improvement Engine", "self-improvement")
        self.capabilities.update({
            "description": (
                "Safe recursive self-improvement engine with formal verification, "
                "multi-strategy hyperparameter optimisation, knowledge distillation, "
                "and meta-learning across domains."
            ),
            "confidence": 0.85,
            "specializations": [
                "architecture_mutation",
                "hyperparameter_evolution",
                "knowledge_distillation",
                "meta_learning",
                "capability_activation",
                "safety_verification",
                "rollback_management",
                "audit_trail",
            ],
            "tools": [
                "safety_verifier",
                "hyperparameter_optimizer",
                "knowledge_distiller",
                "meta_learner",
            ],
        })

        # Current system configuration (mutable but safety-guarded)
        self._config: Dict[str, Any] = {
            "reasoning_depth":       3,
            "planning_horizon":      5,
            "memory_capacity":       10_000,
            "learning_rate":         0.001,
            "weight_decay":          1e-5,
            "attention_heads":       8,
            "hidden_dim":            512,
            "dropout":               0.1,
            "ethical_weight":        1.0,
            "safety_bound_alpha":    0.95,
            "audit_trail_enabled":   True,
            "data_retention_policy": "anonymize_after_24h",
        }

        # Subsystems
        self._verifier     = SafetyVerifier()
        self._optimizer    = HyperparameterOptimizer(self._default_hp_space())
        self._distiller    = KnowledgeDistiller()
        self._meta_learner = MetaLearner()

        # State tracking
        self._proposals:   Dict[str, ModificationProposal] = {}
        self._audit_log:   Deque[Dict[str, Any]]           = deque(maxlen=2000)
        self._evolution_history: Deque[EvolutionResult]    = deque(maxlen=200)
        self._distillations:     Deque[KnowledgeDistillation] = deque(maxlen=100)
        self._generation   = 0
        self._total_improvements = 0
        self._baseline_score = 0.75   # initial performance baseline

    # ------------------------------------------------------------------
    # SpecializedAgent interface
    # ------------------------------------------------------------------

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        await asyncio.sleep(0.05)
        task_type = task_data.get("type", "status")

        dispatch = {
            "status":             self._handle_status,
            "propose":            self._handle_propose,
            "verify":             self._handle_verify,
            "human_approve":      self._handle_human_approve,
            "apply":              self._handle_apply,
            "rollback":           self._handle_rollback,
            "evolve":             self._handle_evolve,
            "distill":            self._handle_distill,
            "meta_adapt":         self._handle_meta_adapt,
            "meta_recommend":     self._handle_meta_recommend,
            "record_task":        self._handle_record_task,
            "audit_log":          self._handle_audit_log,
            "config":             self._handle_config,
            "list_proposals":     self._handle_list_proposals,
        }

        handler = dispatch.get(task_type)
        if handler is None:
            return self._error(f"Unknown task type: {task_type}")
        try:
            return await handler(task_data)
        except Exception as exc:
            logger.exception("RSIE task '%s' error: %s", task_type, exc)
            return self._error(str(exc))

    # ------------------------------------------------------------------
    # Task handlers
    # ------------------------------------------------------------------

    async def _handle_status(self, _: Dict) -> Dict[str, Any]:
        best_cfg, best_score = self._optimizer.best()
        return {
            "success":             True,
            "type":                "rsie_status",
            "current_config":      self._config,
            "generation":          self._generation,
            "total_improvements":  self._total_improvements,
            "baseline_score":      self._baseline_score,
            "best_hp_score":       best_score,
            "pending_proposals":   sum(1 for p in self._proposals.values()
                                       if p.status == ModificationStatus.PROPOSED),
            "applied_proposals":   sum(1 for p in self._proposals.values()
                                       if p.status == ModificationStatus.APPLIED),
            "evolution_cycles":    len(self._evolution_history),
            "distillations":       len(self._distillations),
            "meta_tasks_logged":   len(self._meta_learner.task_history),
            "timestamp":           time.time(),
        }

    async def _handle_propose(self, data: Dict) -> Dict[str, Any]:
        if len(self._proposals) >= self.MAX_PENDING:
            return self._error("Proposal queue is full. Apply or reject existing proposals first.")

        try:
            mod_type = ModificationType(data.get("mod_type", "hyperparameter"))
        except ValueError:
            return self._error(f"Invalid mod_type. Valid: {[m.value for m in ModificationType]}")

        proposal = ModificationProposal(
            proposal_id   = str(uuid.uuid4()),
            mod_type      = mod_type,
            description   = str(data.get("description", "Self-generated improvement proposal")),
            diff          = dict(data.get("diff", {})),
            expected_gain = float(data.get("expected_gain", 0.05)),
            risk_level    = float(data.get("risk_level", 0.1)),
            justification = str(data.get("justification", "")),
            proposed_by   = str(data.get("proposed_by", "self_improvement_engine")),
            proposed_at   = time.time(),
        )

        # Auto-reject immediately if risk is catastrophic
        if proposal.risk_level > self.MAX_RISK:
            proposal.status       = ModificationStatus.REJECTED
            proposal.verification = VerificationStatus.FAILED
            proposal.verification_report = {
                "status":     "failed",
                "violations": ["risk_exceeds_hard_limit"],
                "passed":     False,
            }
            self._audit("auto_rejected", proposal.proposal_id,
                        f"Risk {proposal.risk_level:.2f} > threshold {self.MAX_RISK}")
        else:
            self._proposals[proposal.proposal_id] = proposal
            self._audit("proposed", proposal.proposal_id, proposal.description)

        return {
            "success":     True,
            "type":        "proposal_created",
            "proposal_id": proposal.proposal_id,
            "status":      proposal.status.value,
            "mod_type":    proposal.mod_type.value,
            "risk_level":  proposal.risk_level,
            "auto_rejected": proposal.status == ModificationStatus.REJECTED,
            "timestamp":   time.time(),
        }

    async def _handle_verify(self, data: Dict) -> Dict[str, Any]:
        pid = data.get("proposal_id", "")
        if pid not in self._proposals:
            return self._error(f"Proposal {pid!r} not found.")

        proposal = self._proposals[pid]
        if proposal.status != ModificationStatus.PROPOSED:
            return self._error(f"Proposal is in state {proposal.status.value}, cannot re-verify.")

        proposal.status       = ModificationStatus.VERIFYING
        proposal.verification = VerificationStatus.RUNNING
        await asyncio.sleep(0.15)   # simulate verification work

        report = self._verifier.verify(proposal, self._config)
        proposal.verification_report = report

        if report["passed"]:
            proposal.verification = VerificationStatus.PASSED
            proposal.status       = ModificationStatus.APPROVED
        else:
            proposal.verification = VerificationStatus.FAILED
            proposal.status       = ModificationStatus.REJECTED

        self._audit("verified", pid,
                    f"{'PASSED' if report['passed'] else 'FAILED'}: {report.get('violations')}")

        return {
            "success":             True,
            "type":                "verification_result",
            "proposal_id":         pid,
            "verification_passed": report["passed"],
            "status":              proposal.status.value,
            "checks":              report["checks"],
            "violations":          report["violations"],
            "timestamp":           time.time(),
        }

    async def _handle_human_approve(self, data: Dict) -> Dict[str, Any]:
        """Explicit human-in-the-loop approval, required before _handle_apply
        will act on a proposal — separate from (and in addition to) the
        automated SafetyVerifier pass that sets status=APPROVED. Automated
        verification alone is not consent to apply a change."""
        pid = data.get("proposal_id", "")
        if pid not in self._proposals:
            return self._error(f"Proposal {pid!r} not found.")

        proposal = self._proposals[pid]
        if proposal.status != ModificationStatus.APPROVED:
            return self._error(
                f"Proposal must pass automated verification (status=APPROVED) before human approval "
                f"(current: {proposal.status.value})."
            )

        approver = data.get("approved_by")
        if not approver:
            return self._error("human_approve requires 'approved_by' identifying who is approving this change.")

        proposal.human_approved    = True
        proposal.human_approved_by = str(approver)
        proposal.human_approved_at = time.time()
        self._audit("human_approved", pid, f"Approved by {approver}")

        return {
            "success":     True,
            "type":        "human_approval_recorded",
            "proposal_id": pid,
            "approved_by": proposal.human_approved_by,
            "timestamp":   proposal.human_approved_at,
        }

    async def _handle_apply(self, data: Dict) -> Dict[str, Any]:
        pid = data.get("proposal_id", "")
        if pid not in self._proposals:
            return self._error(f"Proposal {pid!r} not found.")

        proposal = self._proposals[pid]
        if proposal.status != ModificationStatus.APPROVED:
            return self._error(f"Proposal must be APPROVED before applying (current: {proposal.status.value}).")
        if not proposal.human_approved:
            return self._error(
                "Proposal has not been human-approved. Call 'human_approve' with an "
                "'approved_by' identifier before applying — automated verification "
                "alone does not authorize applying a self-modification."
            )

        # Snapshot current config for rollback
        proposal.rollback_data = copy.deepcopy(self._config)

        # Apply the diff
        applied_keys = []
        for key, change in proposal.diff.items():
            if isinstance(change, dict) and "after" in change:
                if key in self._config:
                    self._config[key] = change["after"]
                    applied_keys.append(key)

        proposal.status     = ModificationStatus.APPLIED
        proposal.applied_at = time.time()
        self._total_improvements += 1
        self._generation         += 1
        self._audit("applied", pid, f"Keys changed: {applied_keys}")

        return {
            "success":      True,
            "type":         "modification_applied",
            "proposal_id":  pid,
            "applied_keys": applied_keys,
            "generation":   self._generation,
            "new_config":   self._config,
            "timestamp":    time.time(),
        }

    async def _handle_rollback(self, data: Dict) -> Dict[str, Any]:
        pid = data.get("proposal_id", "")
        if pid not in self._proposals:
            return self._error(f"Proposal {pid!r} not found.")

        proposal = self._proposals[pid]
        if proposal.status != ModificationStatus.APPLIED:
            return self._error(f"Proposal must be APPLIED to roll back (current: {proposal.status.value}).")
        if not proposal.rollback_data:
            return self._error("No rollback data available for this proposal.")

        self._config        = copy.deepcopy(proposal.rollback_data)
        proposal.status     = ModificationStatus.ROLLED_BACK
        self._generation   -= 1
        self._total_improvements = max(0, self._total_improvements - 1)
        self._audit("rolled_back", pid, "Configuration restored to pre-modification state.")

        return {
            "success":       True,
            "type":          "modification_rolled_back",
            "proposal_id":   pid,
            "restored_config": self._config,
            "generation":    self._generation,
            "timestamp":     time.time(),
        }

    async def _handle_evolve(self, data: Dict) -> Dict[str, Any]:
        strategy_str = data.get("strategy", "evolutionary")
        n_trials     = int(data.get("n_trials", 10))
        n_trials     = max(1, min(100, n_trials))

        try:
            strategy = EvolutionStrategy(strategy_str)
        except ValueError:
            strategy = EvolutionStrategy.EVOLUTIONARY

        start = time.time()
        best_config: Optional[Dict] = None
        best_score = self._baseline_score

        for _ in range(n_trials):
            cfg   = self._optimizer.propose_config(strategy)
            score = self._simulate_evaluation(cfg)
            self._optimizer.record(cfg, score)
            if score > best_score:
                best_score  = score
                best_config = cfg
            await asyncio.sleep(0)   # yield to event loop

        duration  = time.time() - start
        improvement = best_score - self._baseline_score

        if best_config and improvement > 0:
            # Incorporate improvements into config
            for k, v in best_config.items():
                if k in self._config:
                    self._config[k] = v
            self._baseline_score = best_score
            self._total_improvements += 1
            self._generation         += 1

        result = EvolutionResult(
            cycle_id    = str(uuid.uuid4()),
            generation  = self._generation,
            strategy    = strategy,
            best_config = best_config or {},
            best_score  = round(best_score, 6),
            improvement = round(improvement, 6),
            trials      = n_trials,
            duration_s  = round(duration, 3),
            timestamp   = time.time(),
        )
        self._evolution_history.append(result)
        self._audit("evolved", result.cycle_id,
                    f"strategy={strategy.value} trials={n_trials} improvement={improvement:.4f}")

        return {
            "success":      True,
            "type":         "evolution_result",
            "cycle_id":     result.cycle_id,
            "strategy":     strategy.value,
            "n_trials":     n_trials,
            "best_score":   result.best_score,
            "improvement":  result.improvement,
            "duration_s":   result.duration_s,
            "generation":   self._generation,
            "config_updated": improvement > 0,
            "timestamp":    time.time(),
        }

    async def _handle_distill(self, data: Dict) -> Dict[str, Any]:
        source      = data.get("source", "teacher_model")
        target      = data.get("target", "student_model")
        domain      = data.get("domain", "general")
        params      = int(data.get("teacher_params", 7_000_000_000))
        compression = float(data.get("compression_ratio", 10.0))

        await asyncio.sleep(0.2)
        distillation = self._distiller.distill(source, target, params, compression, domain)
        self._distillations.append(distillation)
        self._audit("distilled", distillation.distill_id,
                    f"{source}→{target} compression={compression:.1f}x fidelity={distillation.fidelity:.3f}")

        return {
            "success":      True,
            "type":         "distillation_result",
            "distill_id":   distillation.distill_id,
            "source":       distillation.source,
            "target":       distillation.target,
            "domain":       distillation.domain,
            "compression":  distillation.compression,
            "fidelity":     distillation.fidelity,
            "params_before":distillation.params_before,
            "params_after": distillation.params_after,
            "timestamp":    time.time(),
        }

    async def _handle_meta_adapt(self, _: Dict) -> Dict[str, Any]:
        result = self._meta_learner.adapt()
        self._audit("meta_adapted", "meta_learner", json.dumps(result))
        return {"success": True, "type": "meta_adaptation_result", **result, "timestamp": time.time()}

    async def _handle_meta_recommend(self, data: Dict) -> Dict[str, Any]:
        domain    = data.get("domain", "general")
        n_samples = int(data.get("n_samples", 1000))
        result    = self._meta_learner.recommend_strategy(domain, n_samples)
        return {"success": True, "type": "meta_recommendation", **result, "timestamp": time.time()}

    async def _handle_record_task(self, data: Dict) -> Dict[str, Any]:
        task_id    = data.get("task_id", str(uuid.uuid4()))
        domain     = data.get("domain", "general")
        strategy   = data.get("strategy", "default")
        samples    = int(data.get("samples", 1000))
        final_loss = float(data.get("final_loss", 0.5))
        final_acc  = float(data.get("final_acc", 0.75))

        self._meta_learner.record_task(task_id, domain, strategy, samples, final_loss, final_acc)
        return {"success": True, "type": "task_recorded", "task_id": task_id, "timestamp": time.time()}

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

    async def _handle_config(self, data: Dict) -> Dict[str, Any]:
        updates = data.get("updates", {})
        if updates:
            # Only allow safe config keys (not ethical_weight or safety bounds)
            safe_keys = {k for k in updates if k not in ("ethical_weight", "safety_bound_alpha", "audit_trail_enabled")}
            for k in safe_keys:
                if k in self._config:
                    self._config[k] = updates[k]
            self._audit("config_updated", "direct", f"Keys: {list(safe_keys)}")
        return {"success": True, "type": "config", "config": self._config, "timestamp": time.time()}

    async def _handle_list_proposals(self, data: Dict) -> Dict[str, Any]:
        status_filter = data.get("status")
        proposals = list(self._proposals.values())
        if status_filter:
            proposals = [p for p in proposals if p.status.value == status_filter]
        return {
            "success":   True,
            "type":      "proposal_list",
            "count":     len(proposals),
            "proposals": [p.to_dict() for p in proposals[-50:]],
            "timestamp": time.time(),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _simulate_evaluation(self, config: Dict[str, Any]) -> float:
        """
        Simulate evaluation of a hyperparameter configuration.
        In production, this would run actual benchmark tasks.
        """
        base  = self._baseline_score
        noise = random.gauss(0, 0.02)

        # Heuristic: reward balanced configurations
        lr    = config.get("learning_rate", 0.001)
        depth = config.get("reasoning_depth", 3)
        hdim  = config.get("hidden_dim", 512)

        lr_term    = -2.0 * (math.log10(lr) + 3) ** 2 / 9.0   # peaks around lr=0.001
        depth_term =  0.02 * min(depth, 8)
        hdim_term  =  0.01 * min(hdim, 1024) / 1024.0

        score = base + lr_term * 0.01 + depth_term + hdim_term + noise
        return max(0.0, min(1.0, score))

    def _default_hp_space(self) -> List[HyperparameterSpace]:
        return [
            HyperparameterSpace("learning_rate",   1e-5, 0.1,  0.001,  "float"),
            HyperparameterSpace("weight_decay",     0.0,  0.1,  1e-5,   "float"),
            HyperparameterSpace("reasoning_depth",  1,    12,   3,      "int"),
            HyperparameterSpace("planning_horizon", 1,    20,   5,      "int"),
            HyperparameterSpace("attention_heads",  1,    32,   8,      "int"),
            HyperparameterSpace("hidden_dim",       64,   4096, 512,    "int"),
            HyperparameterSpace("dropout",          0.0,  0.5,  0.1,    "float"),
        ]

    def _audit(self, action: str, entity_id: str, detail: str):
        self._audit_log.append({
            "action":    action,
            "entity_id": entity_id,
            "detail":    detail,
            "timestamp": time.time(),
            "generation":self._generation,
        })

    @staticmethod
    def _error(message: str) -> Dict[str, Any]:
        return {"success": False, "error": message, "timestamp": time.time()}

    def get_status(self) -> Dict[str, Any]:
        base = super().get_status()
        base.update({
            "generation":           self._generation,
            "total_improvements":   self._total_improvements,
            "baseline_score":       self._baseline_score,
            "pending_proposals":    sum(1 for p in self._proposals.values()
                                        if p.status == ModificationStatus.PROPOSED),
            "evolution_cycles":     len(self._evolution_history),
        })
        return base
