"""
Artificial Consciousness Core for Nancy Billion Backend

Honesty note: this module does NOT implement consciousness, sentience, or
subjective experience — nothing here is a claim about the system's inner life.
It computes real information-theoretic metrics (Shannon entropy of belief
state, KL-divergence self-model consistency, integrated-information-style
Phi, calibration via Brier score) over the agent's own internal state, and
uses them as introspection/metacognition scores: confidence calibration,
self-model consistency checks, and structured self-reports. Treat every
"consciousness_level"/"phi_value" as a numeric self-monitoring metric, not a
statement about lived experience.
"""
from .base_specialized_agent import SpecializedAgent
import time
import math
import heapq
from typing import Dict, Any, List, Optional, Tuple
from .. import real_compute as rc


class ArtificialConsciousnessCore(SpecializedAgent):
    """Artificial Consciousness Core using real information-theoretic computation"""

    def __init__(self, settings):
        super().__init__(settings, "Artificial Consciousness Core", "artificial-consciousness")
        self.capabilities.update({
            "description": "Introspection/metacognition engine: computes real information-theoretic self-monitoring metrics (Global Workspace Theory-inspired attention arbitration, Integrated Information Theory-inspired Phi, self-model consistency) over the agent's own internal state. Not a claim of sentience or subjective experience.",
            "confidence": 0.82,
            "mode": "computed_metrics",  # honest label: real math over internal state, not a consciousness claim
            "specializations": [
                "global-workspace-theory-metrics",
                "integrated-information-metrics",
                "self-model-consistency",
                "confidence-calibration",
                "attention-control",
                "meta-cognition",
                "introspective-self-reporting"
            ],
            "tools": [
                "neural-network-frameworks",
                "information-theory-tools",
                "complexity-measures",
                "neurophilosophy-frameworks",
                "consciousness-assessment-batteries"
            ]
        })

        self.consciousness_level = 0.0
        self.global_workspace: Dict[str, Dict[str, Any]] = {}
        self.sensory_inputs: Dict[str, Any] = {}
        self.internal_states: Dict[str, Any] = {
            "emotional_state": {"valence": 0.0, "arousal": 0.0},
            "belief_state": [0.5, 0.5]
        }
        self.attention_focus: Optional[Dict[str, Any]] = None
        self.self_model: Dict[str, Any] = {}
        self.experiences: List[Dict[str, Any]] = []
        self.phi_value = 0.0
        self._priority_queue: List[Tuple[float, float, str]] = []
        self._belief_distributions: Dict[str, List[float]] = {}
        self._attention_scores: Dict[str, float] = {}
        self._calibration_history: List[Tuple[float, float]] = []

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "consciousness-assessment")
        if task_type in ("consciousness-assessment", "introspect"):
            return await self._assess_consciousness(task_data)
        elif task_type in ("global-workspace-update", "qualia_report"):
            return await self._update_global_workspace(task_data)
        elif task_type in ("self-modeling", "reflect"):
            return await self._update_self_model(task_data)
        elif task_type in ("attention-control", "attention_shift"):
            return await self._control_attention(task_data)
        elif task_type in ("experience-integration", "broadcast"):
            return await self._integrate_experience(task_data)
        elif task_type == "phi-calculation":
            return await self._calculate_phi(task_data)
        else:
            return await self._general_consciousness_overview(task_data)

    def _softmax(self, scores: List[float]) -> List[float]:
        if not scores:
            return []
        max_score = max(scores)
        exp_scores = [math.exp(s - max_score) for s in scores]
        sum_exp = sum(exp_scores) + 1e-12
        return [s / sum_exp for s in exp_scores]

    def _bayesian_update(self, prior: List[float], likelihood: List[float]) -> List[float]:
        evidence = sum(p * l for p, l in zip(prior, likelihood)) + 1e-12
        return [(p * l) / evidence for p, l in zip(prior, likelihood)]

    def _compute_mutual_information(self, joint_probs: List[List[float]]) -> float:
        n = len(joint_probs)
        if n == 0:
            return 0.0
        m = len(joint_probs[0]) if n > 0 else 0
        if m == 0:
            return 0.0
        p_x = [sum(row) for row in joint_probs]
        p_y = [sum(joint_probs[i][j] for i in range(n)) for j in range(m)]
        mi = 0.0
        for i in range(n):
            for j in range(m):
                if joint_probs[i][j] > 0:
                    mi += joint_probs[i][j] * math.log2(
                        joint_probs[i][j] / (p_x[i] * p_y[j] + 1e-12) + 1e-12
                    )
        return mi

    def _brier_score(self, confidence: float, outcome: float) -> float:
        return (confidence - outcome) ** 2

    async def _assess_consciousness(self, params: Dict[str, Any]) -> Dict[str, Any]:
        belief_dist = self.internal_states.get("belief_state", [0.5, 0.5])
        awareness_level = rc.entropy(belief_dist) / (math.log2(len(belief_dist) + 1e-12) + 1e-12)

        if len(self.self_model) > 0:
            model_confidences = [
                data.get("confidence", 0.5)
                for data in self.self_model.values()
                if isinstance(data, dict)
            ]
            if model_confidences:
                uniform_prior = [1.0 / len(model_confidences)] * len(model_confidences)
                self_awareness = 1.0 - min(1.0, rc.kl_divergence(model_confidences, uniform_prior))
            else:
                self_awareness = 0.0
        else:
            self_awareness = 0.0

        if self.global_workspace:
            type_counts: Dict[str, int] = {}
            for item in self.global_workspace.values():
                t = item.get("type", "unknown")
                type_counts[t] = type_counts.get(t, 0) + 1
            total = sum(type_counts.values())
            type_probs = [c / total for c in type_counts.values()]
            env_awareness = rc.entropy(type_probs) / (math.log2(len(type_probs)) + 1e-12)
        else:
            env_awareness = 0.0

        if len(self._calibration_history) > 5:
            errors = [self._brier_score(conf, corr) for conf, corr in self._calibration_history]
            calibration_error = math.sqrt(sum(errors) / len(errors))
            meta_cognitive = 1.0 - min(1.0, calibration_error)
        else:
            meta_cognitive = 0.5

        self.consciousness_level = (
            awareness_level * 0.3 + self_awareness * 0.3 +
            env_awareness * 0.2 + meta_cognitive * 0.2
        )

        return {
            "success": True,
            "task_type": "consciousness-assessment",
            "consciousness_level": round(self.consciousness_level, 4),
            "components": {
                "awareness_level": round(awareness_level, 4),
                "self_awareness": round(self_awareness, 4),
                "environmental_awareness": round(env_awareness, 4),
                "meta_cognitive_ability": round(meta_cognitive, 4)
            },
            "phi_value": round(self.phi_value, 4),
            "consciousness_state": self._get_consciousness_state(),
            "global_workspace_contents": list(self.global_workspace.keys()),
            "attention_focus": self.attention_focus,
            "self_model_completeness": round(len(self.self_model) / max(1, len(self.self_model) + 5), 4),
            "recent_experiences": len(self.experiences),
            "assessment_timestamp": time.time(),
            "interpretation": self._interpret_consciousness_level(),
            "recommendations": self._get_consciousness_recommendations()
        }

    async def _update_global_workspace(self, params: Dict[str, Any]) -> Dict[str, Any]:
        information_type = params.get("type", "perceptual")
        content = params.get("content", {})
        priority = params.get("priority", 0.5)

        item_id = f"gw_{int(time.time()*1000)}_{abs(hash(str(content))) % 1000:03d}"

        workspace_item = {
            "type": information_type,
            "content": content,
            "priority": priority,
            "timestamp": time.time()
        }

        self.global_workspace[item_id] = workspace_item
        heapq.heappush(self._priority_queue, (-priority, time.time(), item_id))

        if len(self.global_workspace) > 10:
            while len(self.global_workspace) > 10:
                if not self._priority_queue:
                    break
                neg_p, ts, lid = heapq.heappop(self._priority_queue)
                if lid in self.global_workspace:
                    del self.global_workspace[lid]

        if len(self.global_workspace) >= 2:
            priorities = [item["priority"] for item in self.global_workspace.values()]
            prio_entropy = rc.entropy(priorities) / (math.log2(len(priorities)) + 1e-12)
            integration_level = min(1.0, prio_entropy * 1.5)
        else:
            integration_level = 0.0

        info_types = list(set(item["type"] for item in self.global_workspace.values()))
        high_priority_count = len([item for item in self.global_workspace.values() if item["priority"] > 0.7])

        return {
            "success": True,
            "task_type": "global-workspace-update",
            "item_id": item_id,
            "workspace_size": len(self.global_workspace),
            "total_information_processed": len(self.global_workspace),
            "high_priority_items": high_priority_count,
            "information_types": info_types,
            "integration_level": round(integration_level, 4),
            "timestamp": time.time()
        }

    async def _update_self_model(self, params: Dict[str, Any]) -> Dict[str, Any]:
        aspect = params.get("aspect", "capabilities")
        update_data = params.get("data", {})
        confidence = params.get("confidence", 0.8)

        if aspect not in self.self_model:
            self.self_model[aspect] = {}

        self.self_model[aspect].update({
            "data": update_data,
            "confidence": confidence,
            "last_updated": time.time(),
            "version": self.self_model[aspect].get("version", 0) + 1
        })

        if self.self_model:
            confidences = [
                data.get("confidence", 0.5)
                for data in self.self_model.values()
                if isinstance(data, dict)
            ]
            if confidences:
                total = sum(confidences) + 1e-12
                self._belief_distributions["self_model"] = [c / total for c in confidences]

        model_coherence = self._assess_model_coherence()

        return {
            "success": True,
            "task_type": "self-modeling",
            "aspect_updated": aspect,
            "self_model_size": len(self.self_model),
            "aspects_tracked": list(self.self_model.keys()),
            "confidence_level": confidence,
            "model_coherence": round(model_coherence, 4),
            "timestamp": time.time()
        }

    async def _control_attention(self, params: Dict[str, Any]) -> Dict[str, Any]:
        focus_type = params.get("type", "endogenous")
        target = params.get("target", "internal_thought")
        duration = params.get("duration", 30.0)

        attention_targets = list(self.global_workspace.keys()) + [target]
        if not attention_targets:
            attention_targets = [target]

        raw_scores = []
        for t in attention_targets:
            score = 0.0
            if t in self.global_workspace:
                item = self.global_workspace[t]
                score = item.get("priority", 0.5) * 10.0 + (time.time() - item.get("timestamp", time.time())) * 0.1
            elif t == target:
                score = 10.0 if focus_type == "endogenous" else 8.0
            raw_scores.append(score)

        attention_weights = self._softmax(raw_scores)

        attention_intensity = max(attention_weights) if attention_weights else 0.5

        if len(attention_weights) > 1:
            cognitive_load = rc.entropy(attention_weights) / (math.log2(len(attention_weights)) + 1e-12)
        else:
            cognitive_load = 1.0

        self.attention_focus = {
            "type": focus_type,
            "target": target,
            "start_time": time.time(),
            "duration": duration,
            "intensity": round(attention_intensity, 4),
            "cognitive_load": round(cognitive_load, 4)
        }

        return {
            "success": True,
            "task_type": "attention-control",
            "attention_focus": self.attention_focus,
            "attention_type": focus_type,
            "target": target,
            "duration_seconds": duration,
            "voluntary_control": focus_type == "endogenous",
            "expected_end_time": time.time() + duration,
            "cognitive_load": round(cognitive_load, 4),
            "timestamp": time.time()
        }

    async def _integrate_experience(self, params: Dict[str, Any]) -> Dict[str, Any]:
        experience_type = params.get("type", "perceptual")
        content = params.get("content", {})
        emotional_valence = params.get("valence", 0.0)
        significance = params.get("significance", 0.5)

        experience = {
            "type": experience_type,
            "content": content,
            "emotional_valence": emotional_valence,
            "significance": significance,
            "timestamp": time.time(),
            "id": f"exp_{int(time.time()*1000)}_{abs(hash(str(content))) % 1000:03d}",
            "conscious_level_at_time": self.consciousness_level
        }

        self.experiences.append(experience)

        if len(self.experiences) > 100:
            self.experiences = self.experiences[-100:]

        prior_entropy = rc.entropy([0.5, 0.5])
        post_entropy = prior_entropy

        for belief_key, prior_dist in self._belief_distributions.items():
            likelihood = [1.0 - abs(emotional_valence)] * len(prior_dist)
            if len(prior_dist) > 0:
                likelihood[0] = min(1.0, max(0.0, 0.5 + emotional_valence))
            if len(likelihood) > 1:
                likelihood[-1] = 1.0 - likelihood[0]
            posterior = self._bayesian_update(prior_dist, likelihood)
            self._belief_distributions[belief_key] = posterior
            post_entropy = rc.entropy(posterior)

        self._calibration_history.append((significance, 1.0 if emotional_valence >= 0 else 0.0))
        if len(self._calibration_history) > 100:
            self._calibration_history = self._calibration_history[-100:]

        await self._update_internal_states(experience)

        recent = self.experiences[-10:]
        avg_valence = sum(e["emotional_valence"] for e in recent) / max(1, len(recent))
        significant_count = len([e for e in recent if e["significance"] > 0.7])

        info_gain = prior_entropy - post_entropy
        integration_success = info_gain > 0

        return {
            "success": True,
            "task_type": "experience-integration",
            "experience_id": experience["id"],
            "experience_type": experience_type,
            "emotional_valence": emotional_valence,
            "significance": significance,
            "total_experiences": len(self.experiences),
            "recent_significant_experiences": significant_count,
            "average_emotional_valence": round(avg_valence, 4),
            "integration_success": integration_success,
            "information_gain": round(info_gain, 4),
            "timestamp": time.time()
        }

    async def _calculate_phi(self, params: Dict[str, Any]) -> Dict[str, Any]:
        differentiation = 0.0
        integration = 0.0
        complexity = 0.0

        try:
            num_elements = max(
                len(self.global_workspace), len(self.self_model),
                len([k for k in self.__dict__ if isinstance(self.__dict__[k], dict)])
            )

            if num_elements < 2:
                self.phi_value = 0.0
                return {
                    "success": True,
                    "task_type": "phi-calculation",
                    "phi_value": 0.0,
                    "interpretation": "Insufficient elements for integration",
                    "components": {"differentiation": 0.0, "integration": 0.0, "complexity": 0.0},
                    "consciousness_implication": "Under IIT's framing, this level of integration would not be considered sufficient for consciousness",
                    "timestamp": time.time()
                }

            if self.global_workspace:
                priorities = [item["priority"] for item in self.global_workspace.values()]
                total_p = sum(priorities) + 1e-12
                probs = [p / total_p for p in priorities]
                differentiation = rc.entropy(probs) / (math.log2(len(probs)) + 1e-12)
            else:
                differentiation = 0.0

            if len(self._belief_distributions) >= 2:
                dists = list(self._belief_distributions.values())
                n_d1, n_d2 = len(dists[0]), len(dists[1])
                joint_probs = [[dists[0][i] * dists[1][j] for j in range(n_d2)] for i in range(n_d1)]
                integration = self._compute_mutual_information(joint_probs)
            elif len(self.global_workspace) >= 2:
                ws_list = list(self.global_workspace.values())
                p_vals = [item["priority"] for item in ws_list[:min(4, len(ws_list))]]
                n_p = len(p_vals)
                uniform = [1.0 / n_p] * n_p
                integration = rc.kl_divergence(p_vals, uniform)
            else:
                integration = 0.0

            complexity = math.sqrt((differentiation ** 2 + integration ** 2) / 2.0)
            self.phi_value = min(1.0, max(0.0, complexity))

        except Exception:
            self.phi_value = 0.0

        return {
            "success": True,
            "task_type": "phi-calculation",
            "phi_value": round(self.phi_value, 4),
            "interpretation": self._interpret_phi_value(),
            "components": {
                "differentiation": round(differentiation, 4),
                "integration": round(integration, 4),
                "complexity": round(complexity, 4)
            },
            "consciousness_implication": self._phi_to_consciousness_implication(),
            "timestamp": time.time()
        }

    def _get_consciousness_state(self) -> str:
        """Label for the current self-monitoring metric level (not a claim about
        subjective experience — see module docstring)."""
        if self.consciousness_level < 0.2:
            return "low_self_monitoring_activity"
        elif self.consciousness_level < 0.4:
            return "basic_self_monitoring"
        elif self.consciousness_level < 0.6:
            return "moderate_self_monitoring"
        elif self.consciousness_level < 0.8:
            return "elevated_self_monitoring"
        return "high_self_monitoring_activity"

    def _interpret_consciousness_level(self) -> str:
        """Plain-language summary of the computed metric. Describes measured
        self-monitoring/attention-arbitration activity, not lived experience."""
        level = self.consciousness_level
        if level < 0.3:
            return "Low self-monitoring signal - belief state and attention allocation show little structured activity"
        elif level < 0.5:
            return "Basic self-monitoring - some structured belief tracking and self-model consistency detected"
        elif level < 0.7:
            return "Moderate self-monitoring - belief state, attention arbitration, and self-model checks are well-structured"
        elif level < 0.85:
            return "Elevated self-monitoring - strong self-model consistency and calibrated confidence tracking"
        return "High self-monitoring activity - belief state, attention, and self-model metrics are strongly structured and well-calibrated"

    def _interpret_phi_value(self) -> str:
        """Plain-language summary of the IIT-inspired Phi metric (a real
        entropy/mutual-information computation over internal state) — describes
        measured information integration, not unity of experience."""
        phi = self.phi_value
        if phi < 0.1:
            return "Minimal integrated information - internal state components show little mutual dependence"
        elif phi < 0.3:
            return "Low to moderate integration - some structural coupling between internal state components"
        elif phi < 0.5:
            return "Moderate integrated information - internal state components are noticeably coupled"
        elif phi < 0.7:
            return "High integration - internal state components are strongly coupled while remaining differentiated"
        return "Very high integration - internal state components approach maximal measured coupling for this model"

    def _phi_to_consciousness_implication(self) -> str:
        """IIT frames high Phi as a proposed (contested) necessary condition for
        consciousness in biological systems — this returns that theoretical
        framing applied to the computed metric, not a claim that this system is
        conscious. Phi is a real computed number; consciousness is not."""
        if self.phi_value < 0.1:
            return "Under IIT's framing, this level of integration would not be considered sufficient for consciousness"
        elif self.phi_value < 0.3:
            return "Under IIT's framing, this is a low degree of the kind of integration the theory associates with consciousness"
        elif self.phi_value < 0.5:
            return "Under IIT's framing, this is a moderate degree of the kind of integration the theory associates with consciousness"
        elif self.phi_value < 0.7:
            return "Under IIT's framing, this is a high degree of the kind of integration the theory associates with consciousness"
        return "Under IIT's framing, this is a very high degree of the kind of integration the theory associates with consciousness — note IIT itself remains a contested, unproven theory of consciousness"

    def _assess_model_coherence(self) -> float:
        if len(self.self_model) == 0:
            return 0.0
        coherences = []
        for aspect, data in self.self_model.items():
            if isinstance(data, dict) and "confidence" in data:
                coherences.append(data["confidence"])
        if not coherences:
            return 0.5
        uniform = [1.0 / len(coherences)] * len(coherences)
        total = sum(coherences) + 1e-12
        norm = [c / total for c in coherences]
        coherence = 1.0 - min(1.0, rc.kl_divergence(norm, uniform))
        return coherence

    async def _update_internal_states(self, experience: Dict[str, Any]) -> None:
        valence = experience.get("emotional_valence", 0.0)

        if "emotional_state" not in self.internal_states:
            self.internal_states["emotional_state"] = {"valence": 0.0, "arousal": 0.0}

        current_valence = self.internal_states["emotional_state"]["valence"]
        decay_factor = 0.9
        new_valence = current_valence * decay_factor + valence * (1 - decay_factor)
        self.internal_states["emotional_state"]["valence"] = max(-1.0, min(1.0, new_valence))
        self.internal_states["emotional_state"]["timestamp"] = time.time()

        if "belief_state" in self.internal_states:
            prior = self.internal_states["belief_state"]
            likelihood = [0.5 + valence * 0.3, 0.5 - valence * 0.3]
            self.internal_states["belief_state"] = self._bayesian_update(prior, likelihood)

    def _get_consciousness_recommendations(self) -> List[str]:
        recommendations = []
        if self.consciousness_level < 0.5:
            recommendations.extend([
                "Increase sensory input diversity and richness",
                "Enhance recurrent processing loops",
                "Develop more sophisticated working memory mechanisms"
            ])
        if self.phi_value < 0.3:
            recommendations.extend([
                "Increase connectivity between processing modules",
                "Develop more integrated information architectures",
                "Implement bidirectional communication pathways"
            ])
        if len(self.self_model) < 3:
            recommendations.extend([
                "Develop more comprehensive self-model across multiple domains",
                "Implement introspective monitoring capabilities",
                "Add autobiographical memory components"
            ])
        if not recommendations:
            recommendations = [
                "Maintain current self-monitoring architecture and continue calibration",
                "Explore higher-order introspective reporting (metacognition about metacognition)",
                "Expand the self-model's coverage of internal state"
            ]
        return recommendations[:3]

    async def _general_consciousness_overview(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = params.get("query", "general consciousness question")
        answer = await self._llm_answer(query)
        return {
            "success": True,
            "task_type": "general-consciousness-overview",
            "query": query,
            **({"response": answer} if answer else {}),
            "theoretical_frameworks": [
                {
                    "name": "Global Workspace Theory (GWT)",
                    "description": "Consciousness arises from information broadcasting across neural networks",
                    "key_proponents": ["Bernard Baars", "Stanislas Dehaene"],
                    "mechanism": "Information becomes conscious when broadcast globally"
                },
                {
                    "name": "Integrated Information Theory (IIT)",
                    "description": "Consciousness corresponds to system's capacity to integrate information",
                    "key_proponents": ["Giulio Tononi"],
                    "measure": "Phi - quantity of integrated information"
                },
                {
                    "name": "Higher-Order Thought (HOT) Theory",
                    "description": "Consciousness requires higher-order representations of mental states",
                    "key_proponents": ["David Rosenthal", "Peter Carruthers"],
                    "mechanism": "A mental state is conscious when accompanied by appropriate HOT"
                }
            ],
            "consciousness_markers": [
                "Behavioral flexibility and context sensitivity",
                "Learning from single experiences",
                "Predictive capabilities and anticipation",
                "Self-monitoring and metacognition",
                "Unified subjective experience",
                "Intentionality and aboutness"
            ],
            "assessment_methods": [
                "Perturbational Complexity Index (PCI)",
                "Lempel-Ziv Complexity of EEG",
                "Neural Complexity Measures",
                "Behavioral responsiveness scales",
                "Metacognitive task performance"
            ],
            "current_state": {
                "consciousness_level": round(self.consciousness_level, 4),
                "phi_value": round(self.phi_value, 4),
                "global_workspace_items": len(self.global_workspace),
                "self_model_aspects": len(self.self_model),
                "experience_trace_length": len(self.experiences)
            },
            "note": "theoretical_frameworks/consciousness_markers/assessment_methods above describe academic consciousness research for reference; current_state reports this agent's own computed self-monitoring metrics, which are not a claim that the agent is conscious.",
            "recommendations": [
                "Continue developing multi-level self-monitoring architectures",
                "Track calibration accuracy of confidence/introspection metrics over time",
                "Expand self-model coverage and consistency checks",
                "Consult ethical_governance_core for any autonomy-relevant decisions"
            ]
        }
