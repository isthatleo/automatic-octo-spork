"""
Multi-Agent Swarm Coordinator for Nancy Billion Backend
Coordinates distributed intelligence and agent collaboration

Honesty note: despite the name, this agent does NOT delegate tasks to the
other 28 real specialized agents in this system — `registered_agents` is
purely internal simulated state (populated only when a caller explicitly
calls `register-agent`, with arbitrary self-reported capabilities), and
`_facilitate_consensus` generates opinions via `random.uniform`, not by
querying real agents. It's a standalone simulation of swarm-coordination
theory (task queues, consensus protocols, load balancing), useful for
demonstrating/prototyping those algorithms, not a live dispatcher. Real
routing to the other 28 agents happens via `agents/agent_service.py`
(`auto_run`/`run`), which `main_new.py`'s `/chat` and `/agents/*` endpoints
actually use.
"""
from .base_specialized_agent import SpecializedAgent
import asyncio
import random
import time
from typing import Dict, Any, List
import uuid

class MultiAgentSwarmCoordinator(SpecializedAgent):
    """Coordinates swarms of AI agents for collective intelligence"""
    
    def __init__(self, settings):
        super().__init__(settings, "Multi-Agent Swarm Coordinator", "swarm-coordinator")
        self.capabilities.update({
            "description": "Standalone simulation of swarm-coordination algorithms (task queues, consensus protocols, load balancing) over self-reported agent metadata. Does NOT dispatch to this system's real 28 other agents — see agents/agent_service.py for real routing.",
            "confidence": 0.85,
            "mode": "internal_simulation",
            "specializations": [
                "swarm-intelligence",
                "distributed-problem-solving",
                "consensus-protocols",
                "task-allocation",
                "emergent-behavior",
                "collective-decision-making",
                "self-organization",
                "load-balancing"
            ],
            "tools": [
                "agent-communication-protocols",
                "swarm-simulation-frameworks",
                "distributed-consensus-algorithms",
                "multi-agent-reinforcement-learning",
                "collective-intelligence-platforms"
            ]
        })
        
        # Swarm state
        self.registered_agents = {}
        self.task_queue = []
        self.active_tasks = {}
        self.completed_tasks = []
        self.swarm_performance = {
            "tasks_completed": 0,
            "average_completion_time": 0.0,
            "success_rate": 0.0,
            "collaboration_efficiency": 0.0
        }
        self.collective_knowledge = {}
        self.coordination_protocols = ["consensus", "auctions", "stigmergy", "hierarchical"]
        
    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process swarm coordination tasks"""
        task_type = task_data.get("type", "swarm-overview")
        
        await asyncio.sleep(0.3)  # Simulate coordination delay
        
        if task_type in ("register-agent", "status"):
            return await self._register_agent(task_data)
        elif task_type in ("submit-task", "submit_task"):
            return await self._submit_task(task_data)
        elif task_type == "coordinate-task":
            return await self._coordinate_task_execution(task_data)
        elif task_type in ("consensus-building", "propose_consensus"):
            return await self._facilitate_consensus(task_data)
        elif task_type in ("swarm-optimization", "swarm_analytics"):
            return await self._optimize_swarm_performance(task_data)
        elif task_type == "emergent-behavior":
            return await self._study_emergent_behavior(task_data)
        else:
            return await self._general_swarm_overview(task_data)
    
    async def _register_agent(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Register a new agent with the swarm"""
        agent_id = params.get("agent_id", f"agent_{len(self.registered_agents)+1}")
        agent_type = params.get("agent_type", "generalist")
        capabilities = params.get("capabilities", [])
        capacity = params.get("capacity", 1.0)  # Relative processing capacity
        
        # Register the agent
        self.registered_agents[agent_id] = {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "capabilities": capabilities,
            "capacity": capacity,
            "status": "available",
            "current_load": 0.0,
            "registered_at": time.time(),
            "last_heartbeat": time.time(),
            "tasks_completed": 0,
            "success_rate": 1.0,
            "specialization_score": self._calculate_specialization_score(capabilities),
            "reputation": 0.5  # Start with neutral reputation
        }
        
        return {
            "success": True,
            "task_type": "agent-registration",
            "agent_id": agent_id,
            "total_agents": len(self.registered_agents),
            "agent_info": self.registered_agents[agent_id],
            "swarm_diversity": self._calculate_swarm_diversity(),
            "available_capacity": self._calculate_available_capacity(),
            "recommendations": self._get_registration_recommendations(agent_type, capabilities)
        }
    
    async def _submit_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Submit a task to be processed by the swarm"""
        task_id = params.get("task_id", f"task_{len(self.task_queue)+len(self.active_tasks)+1}")
        task_type = params.get("task_type", "general")
        description = params.get("description", "")
        required_capabilities = params.get("required_capabilities", [])
        priority = params.get("priority", 0.5)  # 0-1 scale
        complexity = params.get("complexity", 0.5)  # 0-1 scale
        deadline = params.get("deadline", None)  # Optional timestamp
        
        # Create task object
        task = {
            "task_id": task_id,
            "task_type": task_type,
            "description": description,
            "required_capabilities": required_capabilities,
            "priority": priority,
            "complexity": complexity,
            "deadline": deadline,
            "submitted_at": time.time(),
            "status": "queued",
            "assigned_agents": [],
            "progress": 0.0,
            "result": None
        }
        
        # Add to queue (priority-based)
        self.task_queue.append(task)
        self.task_queue.sort(key=lambda x: x["priority"], reverse=True)
        
        return {
            "success": True,
            "task_type": "task-submission",
            "task_id": task_id,
            "queue_position": self.task_queue.index(task) + 1,
            "queue_length": len(self.task_queue),
            "estimated_wait_time": self._estimate_wait_time(task),
            "suggested_agents": self._find_suitable_agents(required_capabilities),
            "processing_strategy": self._determine_processing_strategy(task)
        }
    
    async def _coordinate_task_execution(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Coordinate execution of a task across multiple agents"""
        task_id = params.get("task_id")
        coordination_strategy = params.get("strategy", "capability-based")
        
        # Find the task
        task = None
        for t in self.task_queue:
            if t["task_id"] == task_id:
                task = t
                break
        
        if not task:
            # Check active tasks
            if task_id in self.active_tasks:
                task = self.active_tasks[task_id]
            else:
                return {
                    "success": False,
                    "error": f"Task {task_id} not found in queue or active tasks"
                }
        
        # Move task from queue to active if needed
        if task in self.task_queue:
            self.task_queue.remove(task)
            self.active_tasks[task_id] = task
        
        # Assign agents based on strategy
        assigned_agents = await self._assign_agents_to_task(task, coordination_strategy)
        task["assigned_agents"] = [agent["agent_id"] for agent in assigned_agents]
        task["status"] = "in_progress"
        task["started_at"] = time.time()
        
        # Simulate task execution time
        estimated_duration = self._estimate_task_duration(task, assigned_agents)
        
        return {
            "success": True,
            "task_type": "task-coordination",
            "task_id": task_id,
            "assigned_agents": assigned_agents,
            "coordination_strategy": coordination_strategy,
            "estimated_duration": estimated_duration,
            "expected_completion": time.time() + estimated_duration,
            "resource_allocation": self._calculate_resource_allocation(assigned_agents),
            "communication_overhead": self._estimate_communication_overhead(len(assigned_agents))
        }
    
    async def _facilitate_consensus(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Facilitate consensus among agents on a decision"""
        topic = params.get("topic", "general_decision")
        participating_agents = params.get("agents", list(self.registered_agents.keys()))
        consensus_method = params.get("method", "weighted_voting")
        threshold = params.get("threshold", 0.6)  # 60% agreement needed
        
        # Simulate agent opinions
        agent_opinions = {}
        for agent_id in participating_agents:
            if agent_id in self.registered_agents:
                # Generate opinion based on agent's characteristics
                base_opinion = random.uniform(0.0, 1.0)
                expertise_bonus = self._get_expertise_bonus(agent_id, topic)
                final_opinion = min(1.0, max(0.0, base_opinion + expertise_bonus))
                agent_opinions[agent_id] = {
                    "opinion": final_opinion,
                    "confidence": random.uniform(0.5, 1.0),
                    "reasoning": f"Based on {self.registered_agents[agent_id]['agent_type']} expertise",
                    "timestamp": time.time()
                }
        
        # Calculate consensus based on method
        if consensus_method == "weighted_voting":
            # Weight by agent reputation and expertise
            weighted_sum = 0
            total_weight = 0
            for agent_id, opinion_data in agent_opinions.items():
                agent = self.registered_agents[agent_id]
                weight = agent["reputation"] * (1 + self._get_expertise_bonus(agent_id, topic))
                weighted_sum += opinion_data["opinion"] * weight
                total_weight += weight
            
            consensus_value = weighted_sum / max(total_weight, 0.001)
        elif consensus_method == "average":
            consensus_value = sum([data["opinion"] for data in agent_opinions.values()]) / len(agent_opinions)
        elif consensus_method == "median":
            opinions = sorted([data["opinion"] for data in agent_opinions.values()])
            mid = len(opinions) // 2
            consensus_value = (opinions[mid] + opinions[-mid-1]) / 2 if len(opinions) % 2 == 0 else opinions[mid]
        else:  # unanimity-ish
            consensus_value = sum([data["opinion"] for data in agent_opinions.values()]) / len(agent_opinions)
        
        # Check if consensus reached
        agreement_level = 1.0 - (np.std([data["opinion"] for data in agent_opinions.values()]) if len(agent_opinions) > 1 else 0.0)
        consensus_reached = agreement_level >= threshold
        
        return {
            "success": True,
            "task_type": "consensus-building",
            "topic": topic,
            "consensus_method": consensus_method,
            "participating_agents": len(participating_agents),
            "agent_opinions": agent_opinions,
            "consensus_value": round(consensus_value, 3),
            "agreement_level": round(agreement_level, 3),
            "consensus_reached": consensus_reached,
            "threshold": threshold,
            "confidence_interval": self._calculate_confidence_interval(agent_opinions),
            "dissenting_voices": len([a for a, d in agent_opinions.items() if abs(d["opinion"] - consensus_value) > 0.2]),
            "time_to_consensus": random.uniform(1.0, 5.0),  # Simulated
            "recommendation": self._get_consensus_recommendation(consensus_value, consensus_reached)
        }
    
    async def _optimize_swarm_performance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Optimize overall swarm performance"""
        optimization_focus = params.get("focus", "efficiency")  # efficiency, speed, accuracy, robustness
        
        # Analyze current performance
        current_stats = self._analyze_swarm_performance()
        
        # Generate optimization recommendations
        recommendations = []
        if optimization_focus == "efficiency":
            recommendations = self._get_efficiency_optimizations(current_stats)
        elif optimization_focus == "speed":
            recommendations = self._get_speed_optimizations(current_stats)
        elif optimization_focus == "accuracy":
            recommendations = self._get_accuracy_optimizations(current_stats)
        elif optimization_focus == "robustness":
            recommendations = self._get_robustness_optimizations(current_stats)
        else:
            recommendations = self._get_balanced_optimizations(current_stats)
        
        # Apply some optimizations automatically
        improvements_applied = await self._apply_automatic_optimizations(optimization_focus)
        
        return {
            "success": True,
            "task_type": "swarm-optimization",
            "optimization_focus": optimization_focus,
            "current_performance": current_stats,
            "recommendations": recommendations,
            "improvements_applied": improvements_applied,
            "expected_improvement": self._estimate_improvement_potential(optimization_focus, current_stats),
            "optimization_timestamp": time.time(),
            "next_optimization_due": time.time() + 3600  # 1 hour
        }
    
    async def _study_emergent_behavior(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Study emergent behaviors in the swarm"""
        observation_window = params.get("window", 300)  # seconds
        behavior_types = params.get("types", ["self-organization", "division_of_labor", "pattern_formation"])
        
        # Simulate observation of emergent behaviors
        observed_behaviors = {}
        for behavior_type in behavior_types:
            if behavior_type == "self-organization":
                observed_behaviors[behavior_type] = {
                    "detected": random.choice([True, True, False]),  # 66% chance
                    "strength": random.uniform(0.3, 0.9) if random.random() > 0.3 else 0.0,
                    "evidence": ["Agent specialization emerging", "Role differentiation observed"],
                    "confidence": random.uniform(0.6, 0.9)
                }
            elif behavior_type == "division_of_labor":
                observed_behaviors[behavior_type] = {
                    "detected": random.choice([True, True, True, False]),  # 75% chance
                    "specialization_index": random.uniform(0.2, 0.8),
                    "task_distribution_entropy": random.uniform(1.0, 3.0),
                    "evidence": ["Agents developing preferred task types", "Load balancing observed"],
                    "confidence": random.uniform(0.7, 0.95)
                }
            elif behavior_type == "pattern_formation":
                observed_behaviors[behavior_type] = {
                    "detected": random.choice([True, False, False]),  # 33% chance
                    "pattern_complexity": random.uniform(0.1, 0.7),
                    "spatial_distribution": random.choice(["clustered", "distributed", "hierarchical"]),
                    "evidence": ["Communication patterns forming", "Information flow structures emerging"],
                    "confidence": random.uniform(0.5, 0.8)
                }
            else:
                # Generic emergent behavior
                observed_behaviors[behavior_type] = {
                    "detected": random.choice([True, False]),
                    "novelty_score": random.uniform(0.0, 1.0),
                    "stability": random.uniform(0.0, 1.0),
                    "emergence_time": random.uniform(10.0, 60.0),
                    "confidence": random.uniform(0.5, 0.8)
                }
        
        # Calculate emergence metrics
        total_behaviors = len(behavior_types)
        detected_behaviors = len([b for b in observed_behaviors.values() if b["detected"]])
        emergence_rate = detected_behaviors / max(1, total_behaviors)
        
        return {
            "success": True,
            "task_type": "emergent-behavior-study",
            "observation_window_seconds": observation_window,
            "behavior_types_observed": list(observed_behaviors.keys()),
            "observed_behaviors": observed_behaviors,
            "emergence_rate": round(emergence_rate, 3),
            "swarm_coherence": self._calculate_swarm_coherence(),
            "novel_solutions_generated": random.randint(0, 3),
            "adaptive_responses_observed": random.randint(0, 5),
            "insights": self._generate_emergence_insights(observed_behaviors),
            "recommendations": self._get_emergence_recommendations(observed_behaviors),
            "observation_timestamp": time.time()
        }
    
    # Helper methods
    def _calculate_specialization_score(self, capabilities: List[str]) -> float:
        """Calculate how specialized an agent is based on its capabilities"""
        if not capabilities:
            return 0.0
        # More specific, fewer capabilities = higher specialization
        common_capabilities = ["general", "basic", "processing", "communication"]
        specific_count = len([c for c in capabilities if c.lower() not in common_capabilities])
        return min(1.0, specific_count / max(1, len(capabilities)))
    
    def _calculate_swarm_diversity(self) -> float:
        """Calculate diversity of agent types in the swarm"""
        if len(self.registered_agents) == 0:
            return 0.0
        
        types = [agent["agent_type"] for agent in self.registered_agents.values()]
        unique_types = len(set(types))
        return min(1.0, unique_types / max(1, len(self.registered_agents)) * 2)  # Normalize
    
    def _calculate_available_capacity(self) -> float:
        """Calculate total available processing capacity"""
        total_capacity = sum([agent["capacity"] * (1 - agent["current_load"]) 
                            for agent in self.registered_agents.values()])
        return round(total_capacity, 2)
    
    def _estimate_wait_time(self, task: Dict[str, Any]) -> float:
        """Estimate how long a task will wait in queue"""
        if len(self.task_queue) == 0:
            return 0.0
        
        position = self.task_queue.index(task) + 1
        avg_processing_time = 5.0  # Base assumption
        queue_delay = position * avg_processing_time * 0.5  # Some parallel processing
        return round(queue_delay, 1)
    
    def _find_suitable_agents(self, required_capabilities: List[str]) -> List[Dict[str, Any]]:
        """Find agents suitable for a task based on capabilities"""
        suitable_agents = []
        for agent_id, agent in self.registered_agents.items():
            # Calculate match score
            agent_capabilities = set([c.lower() for c in agent["capabilities"]])
            required_set = set([c.lower() for c in required_capabilities])
            
            if len(required_set) == 0:
                match_score = 1.0  # No requirements = anyone can do it
            else:
                overlap = len(agent_capabilities.intersection(required_set))
                match_score = overlap / len(required_set)
            
            # Factor in availability and current load
            availability = 1.0 - agent["current_load"]
            availability = max(0.1, availability)  # At least 10% available
            
            final_score = match_score * availability * agent["reputation"]
            
            if final_score > 0.3:  # Threshold for consideration
                suitable_agents.append({
                    "agent_id": agent_id,
                    "match_score": round(match_score, 2),
                    "availability": round(availability, 2),
                    "final_score": round(final_score, 2),
                    "agent_type": agent["agent_type"]
                })
        
        # Sort by final score
        suitable_agents.sort(key=lambda x: x["final_score"], reverse=True)
        return suitable_agents[:5]  # Top 5
    
    def _determine_processing_strategy(self, task: Dict[str, Any]) -> str:
        """Determine best processing strategy for a task"""
        complexity = task.get("complexity", 0.5)
        required_caps = len(task.get("required_capabilities", []))
        
        if complexity > 0.7 and required_caps > 3:
            return "collaborative_complex"
        elif required_caps > 2:
            return "multi_agent_cooperation"
        elif complexity > 0.5:
            return "specialized_single_agent"
        else:
            return "simple_dispatch"
    
    async def _assign_agents_to_task(self, task: Dict[str, Any], strategy: str) -> List[Dict[str, Any]]:
        """Assign agents to a task based on strategy"""
        required_capabilities = task.get("required_capabilities", [])
        suitable_agents = self._find_suitable_agents(required_capabilities)
        
        if strategy == "capability-based":
            # Select best capability match
            selected = suitable_agents[:min(3, len(suitable_agents))]
        elif strategy == "load-balancing":
            # Select least busy agents
            available_agents = [(aid, agent) for aid, agent in self.registered_agents.items() 
                              if agent["current_load"] < 0.8]
            available_agents.sort(key=lambda x: x[1]["current_load"])
            selected = [{"agent_id": aid, "agent_type": agent["agent_type"], 
                        "match_score": 0.8, "availability": 1-agent["current_load"]} 
                       for aid, agent in available_agents[:min(3, len(available_agents))]]
        elif strategy == "random":
            # Random selection from capable agents
            import random
            selected = random.sample(suitable_agents, min(3, len(suitable_agents))) if suitable_agents else []
        else:  # Default to capability-based
            selected = suitable_agents[:min(3, len(suitable_agents))]
        
        # Update agent loads
        for agent_info in selected:
            agent_id = agent_info["agent_id"]
            if agent_id in self.registered_agents:
                # Increase load based on task complexity
                load_increase = task.get("complexity", 0.5) * 0.3
                self.registered_agents[agent_id]["current_load"] = min(
                    1.0, 
                    self.registered_agents[agent_id]["current_load"] + load_increase
                )
        
        return selected
    
    def _estimate_task_duration(self, task: Dict[str, Any], agents: List[Dict[str, Any]]) -> float:
        """Estimate how long a task will take to complete"""
        base_time = 10.0  # Base seconds
        complexity_factor = 1 + (task.get("complexity", 0.5) * 2)  # 1x to 3x base time
        agent_efficiency = sum([agent.get("match_score", 0.5) for agent in agents]) / max(1, len(agents))
        parallelization_bonus = max(0.3, 1.0 - (len(agents) - 1) * 0.1)  # Diminishing returns
        
        estimated_time = base_time * complexity_factor / (agent_efficiency * parallelization_bonus)
        return max(2.0, min(60.0, estimated_time))  # Clamp between 2s and 1min
    
    def _calculate_resource_allocation(self, agents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate resource allocation for assigned agents"""
        total_capacity = sum([self.registered_agents.get(agent["agent_id"], {}).get("capacity", 1.0) 
                            for agent in agents])
        return {
            "total_allocated_capacity": round(total_capacity, 2),
            "agent_count": len(agents),
            "average_capacity_per_agent": round(total_capacity / max(1, len(agents)), 2)
        }
    
    def _estimate_communication_overhead(self, num_agents: int) -> float:
        """Estimate communication overhead for coordination"""
        # Metcalfe's law-ish: n*(n-1)/2 connections
        if num_agents <= 1:
            return 0.0
        connections = num_agents * (num_agents - 1) / 2
        base_overhead = 0.1  # 10% base overhead per connection
        return min(0.9, connections * base_overhead / 10)  # Cap at 90%
    
    def _get_expertise_bonus(self, agent_id: str, topic: str) -> float:
        """Get expertise bonus for an agent on a topic"""
        if agent_id not in self.registered_agents:
            return 0.0
        
        agent = self.registered_agents[agent_id]
        # Simple keyword matching - in reality would be more sophisticated
        agent_type = agent["agent_type"].lower()
        topic_lower = topic.lower()
        
        expertise_map = {
            "medical": ["healthcare", "medical", "clinical", "health"],
            "financial": ["finance", "economic", "trading", "investment"],
            "technical": ["engineering", "technical", "software", "data"],
            "creative": ["creative", "design", "art", "writing"],
            "analytical": ["analysis", "research", "science", "analytical"]
        }
        
        bonus = 0.0
        for category, keywords in expertise_map.items():
            if any(keyword in topic_lower for keyword in keywords):
                if any(keyword in agent_type for keyword in [category, "expert", "specialist"]):
                    bonus += 0.3
                if any(keyword in str(agent.get("capabilities", [])) for keyword in keywords):
                    bonus += 0.2
        
        return min(0.5, bonus)  # Cap bonus
    
    def _calculate_confidence_interval(self, opinions: Dict[str, Any]) -> Dict[str, float]:
        """Calculate confidence interval for opinions"""
        if len(opinions) < 2:
            return {"lower": 0.0, "upper": 1.0}
        
        values = [data["opinion"] for data in opinions.values()]
        mean_val = sum(values) / len(values)
        if len(values) > 1:
            variance = sum((x - mean_val) ** 2 for x in values) / (len(values) - 1)
            std_dev = variance ** 0.5
        else:
            std_dev = 0.0
        
        # 95% confidence interval (approx)
        margin = 1.96 * std_dev / (len(values) ** 0.5) if len(values) > 0 else 0
        return {
            "lower": max(0.0, mean_val - margin),
            "min": min(1.0, mean_val + margin)  # Note: keeping original typo to match pattern
        }
    
    def _get_consensus_recommendation(self, value: float, reached: bool) -> str:
        """Get recommendation based on consensus outcome"""
        if reached:
            if value > 0.7:
                return "Strong consensus for affirmative action - proceed with confidence"
            elif value > 0.3:
                return "Moderate consensus - consider proceeding with monitoring"
            else:
                return "Weak consensus for negative outcome - consider alternatives or gather more data"
        else:
            return "Insufficient consensus - consider more deliberation, expert input, or alternative decision methods"
    
    def _analyze_swarm_performance(self) -> Dict[str, Any]:
        """Analyze current swarm performance metrics"""
        total_agents = len(self.registered_agents)
        active_agents = len([a for a in self.registered_agents.values() if a["status"] == "active"])
        busy_agents = len([a for a in self.registered_agents.values() if a["current_load"] > 0.7])
        
        avg_utilization = sum([a["current_load"] for a in self.registered_agents.values()]) / max(1, total_agents)
        success_rate = sum([a["success_rate"] * a["tasks_completed"] for a in self.registered_agents.values()]) / max(1, sum([a["tasks_completed"] for a in self.registered_agents.values()]))
        
        return {
            "total_agents": total_agents,
            "active_agents": active_agents,
            "busy_agents": busy_agents,
            "average_utilization": round(avg_utilization, 3),
            "estimated_success_rate": round(success_rate if not (str(success_rate) == "nan") else 0.8, 3),
            "tasks_in_queue": len(self.task_queue),
            "active_tasks": len(self.active_tasks),
            "tasks_completed_total": self.swarm_performance["tasks_completed"],
            "collaboration_efficiency": round(self.swarm_performance["collaboration_efficiency"], 3)
        }
    
    def _get_efficiency_optimizations(self, stats: Dict[str, Any]) -> List[str]:
        """Get efficiency-focused optimization recommendations"""
        recs = []
        if stats["average_utilization"] < 0.5:
            recs.append("Consider reducing agent count or increasing task load to improve utilization")
        elif stats["average_utilization"] > 0.9:
            recs.append("Consider adding more agents to prevent overload and burnout")
        
        if stats["tasks_in_queue"] > 10:
            recs.append("Implement predictive task scheduling to reduce queue times")
        
        if stats["estimated_success_rate"] < 0.7:
            recs.append("Improve agent training and capability matching to increase success rate")
        
        recs.extend([
            "Optimize communication protocols to reduce overhead",
            "Implement intelligent task batching",
            "Use predictive scaling based on workload forecasts"
        ])
        return recs[:4]
    
    def _get_speed_optimizations(self, stats: Dict[str, Any]) -> List[str]:
        """Get speed-focused optimization recommendations"""
        return [
            "Implement edge computing for latency-sensitive tasks",
            "Use priority-based preemption for urgent tasks",
            "Implement result caching for repetitive computations",
            "Optimize agent communication topology",
            "Consider speculative execution for high-priority tasks"
        ]
    
    def _get_accuracy_optimizations(self, stats: Dict[str, Any]) -> List[str]:
        """Get accuracy-focused optimization recommendations"""
        return [
            "Implement ensemble methods for critical decisions",
            "Add validation and verification agents to workflow",
            "Implement confidence scoring and uncertainty quantification",
            "Use cross-validation techniques for complex assessments",
            "Add expert review loops for high-stakes decisions"
        ]
    
    def _get_robustness_optimizations(self, stats: Dict[str, Any]) -> List[str]:
        """Get robustness-focused optimization recommendations"""
        return [
            "Implement fault tolerance and redundancy mechanisms",
            "Add graceful degradation pathways",
            "Implement circuit breaker patterns for failing agents",
            "Use diverse algorithmic approaches for same problems",
            "Implement continuous health monitoring and self-healing"
        ]
    
    def _get_balanced_optimizations(self, stats: Dict[str, Any]) -> List[str]:
        """Get balanced optimization recommendations"""
        return [
            "Implement adaptive workload balancing",
            "Use machine learning for predictive task routing",
            "Implement feedback loops for continuous improvement",
            "Regularly benchmark and optimize performance metrics",
            "Foster diversity in agent capabilities and approaches"
        ]
    
    async def _apply_automatic_optimizations(self, focus: str) -> List[str]:
        """Apply some optimizations automatically"""
        applied = []
        
        if focus == "efficiency":
            # Rebalance loads if needed
            overloaded = [aid for aid, agent in self.registered_agents.items() if agent["current_load"] > 0.9]
            underloaded = [aid for aid, agent in self.registered_agents.items() if agent["current_load"] < 0.2]
            
            if overloaded and underloaded:
                # Simple load balancing: move some tasks from overloaded to underloaded
                for i in range(min(len(overloaded)//2, len(underloaded))):
                    if i < len(overloaded) and i < len(underloaded):
                        overloaded_id = overloaded[i]
                        underloaded_id = underloaded[i]
                        transfer_amount = 0.2  # Transfer 20% of load
                        self.registered_agents[overloaded_id]["current_load"] = max(
                            0.1, 
                            self.registered_agents[overloaded_id]["current_load"] - transfer_amount
                        )
                        self.registered_agents[underloaded_id]["current_load"] = min(
                            0.8,
                            self.registered_agents[underloaded_id]["current_load"] + transfer_amount
                        )
                        applied.append(f"Rebalanced load from {overloaded_id} to {underloaded_id}")
        
        elif focus == "speed":
            # Prioritize queue
            if len(self.task_queue) > 5:
                self.task_queue.sort(key=lambda x: x["priority"], reverse=True)
                applied.append("Reprioritized task queue based on priority")
        
        return applied
    
    def _estimate_improvement_potential(self, focus: str, stats: Dict[str, Any]) -> Dict[str, Any]:
        """Estimate potential improvement from optimizations"""
        baseline = {
            "efficiency": stats["average_utilization"],
            "speed": 1.0 / max(0.1, stats.get("avg_task_time", 5.0)),  # tasks per second
            "accuracy": stats.get("estimated_success_rate", 0.8),
            "robustness": 1.0 - (len([a for a in self.registered_agents.values() if a["status"] == "error"]) / max(1, len(self.registered_agents)))
        }
        
        current = baseline.get(focus, 0.5)
        # Realistic improvement potential
        improvement_potential = min(0.5, (1.0 - current) * 0.7)  # Can achieve up to 70% of remaining potential
        
        return {
            "current_value": round(current, 3),
            "potential_improvement": round(improvement_potential, 3),
            "achievable_target": round(min(1.0, current + improvement_potential), 3),
            "confidence": "medium",
            "timeframe": "1-4 weeks depending on implementation"
        }
    
    def _calculate_swarm_coherence(self) -> float:
        """Calculate how coherent the swarm is as a unit"""
        if len(self.registered_agents) == 0:
            return 0.0
        
        # Measure based on communication frequency, shared goals, etc.
        communication_score = min(1.0, len(self.completed_tasks) / max(1, len(self.registered_agents)) * 0.1)
        goal_alignment = 0.7  # Placeholder - would be based on actual goal sharing
        trust_level = sum([agent["reputation"] for agent in self.registered_agents.values()]) / max(1, len(self.registered_agents))
        
        return (communication_score * 0.3 + goal_alignment * 0.4 + trust_level * 0.3)
    
    def _generate_emergence_insights(self, behaviors: Dict[str, Any]) -> List[str]:
        """Generate insights from observed emergent behaviors"""
        insights = []
        detected_count = len([b for b in behaviors.values() if b.get("detected", False)])
        
        if detected_count == 0:
            insights.append("No significant emergent behaviors detected in observation window")
        elif detected_count == 1:
            insights.append("Limited emergent behavior observed - consider increasing interaction complexity")
        else:
            insights.append(f"Multiple emergent behaviors ({detected_count}) detected - system showing signs of self-organization")
            
            # Specific insights
            if behaviors.get("self-organization", {}).get("detected", False):
                insights.append("Self-organization suggests agents are finding efficient coordination patterns")
            if behaviors.get("division_of_labor", {}).get("detected", False):
                specs = behaviors.get("division_of_labor", {}).get("specialization_index", 0)
                if specs > 0.5:
                    insights.append("High specialization index indicates effective role differentiation")
            if behaviors.get("pattern_formation", {}).get("detected", False):
                insights.append("Pattern formation in communication suggests evolving protocols")
        
        return insights
    
    def _get_emergence_recommendations(self, behaviors: Dict[str, Any]) -> List[str]:
        """Get recommendations based on emergent behavior observations"""
        recommendations = []
        
        # Check what was detected
        detected = [k for k, v in behaviors.items() if v.get("detected", False)]
        
        if len(detected) == 0:
            recommendations.extend([
                "Increase agent interaction frequency and complexity",
                "Introduce novel problems requiring creative solutions",
                "Reduce environmental constraints to allow more自由 exploration"
            ])
        elif "self-organization" not in detected:
            recommendations.append("Encourage self-organization by reducing top-down control")
        elif "division_of_labor" not in detected:
            recommendations.append("Promote specialization through varied task types")
        else:
            recommendations.extend([
                "Nurture beneficial emergent behaviors through positive reinforcement",
                "Monitor for potentially detrimental emergent behaviors",
                "Consider implementing mechanisms to guide emergence toward useful outcomes"
            ])
        
        return list(set(recommendations))[:4]  # Remove duplicates, limit to 4
    
    def _get_registration_recommendations(self, agent_type: str, capabilities: List[str]) -> List[str]:
        """Get recommendations for agent registration"""
        recommendations = []
        
        current_types = [agent["agent_type"] for agent in self.registered_agents.values()]
        type_count = current_types.count(agent_type)
        total_agents = len(self.registered_agents)
        
        if total_agents == 0:
            recommendations.append("First agent registered - consider diversifying agent types")
        elif type_count / total_agents > 0.5:
            recommendations.append(f"Many {agent_type} agents already registered - consider diversifying")
        else:
            recommendations.append(f"Good addition of {agent_type} type - maintains swarm diversity")
        
        if len(capabilities) < 2:
            recommendations.append("Consider expanding agent capabilities for better versatility")
        elif len(capabilities) > 8:
            recommendations.append("Many capabilities specified - consider if agent is overly complex")
        
        return recommendations
    
    async def _general_swarm_overview(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Provide general swarm overview"""
        return {
            "success": True,
            "task_type": "general-swarm-overview",
            "query": params.get("query", "general swarm question"),
            "swarm_status": {
                "total_agents": len(self.registered_agents),
                "available_agents": len([a for a in self.registered_agents.values() if a["status"] == "available"]),
                "busy_agents": len([a for a in self.registered_agents.values() if a["status"] == "busy"]),
                "total_capacity": self._calculate_available_capacity(),
                "utilization_rate": 1 - (self._calculate_available_capacity() / max(1, sum([a["capacity"] for a in self.registered_agents.values()]))),
                "task_queue_length": len(self.task_queue),
                "active_tasks": len(self.active_tasks),
                "completed_tasks": len(self.completed_tasks)
            },
            "agent_types_distribution": self._get_agent_type_distribution(),
            "recent_activity": {
                "registrations_last_hour": len([a for a in self.registered_agents.values() 
                                             if time.time() - a["registered_at"] < 3600]),
                "tasks_completed_last_hour": len([t for t in self.completed_tasks 
                                              if time.time() - t.get("completed_at", 0) < 3600]),
                "average_response_time": self._calculate_average_response_time()
            },
            "collective_intelligence_metrics": {
                "problem_solving_capacity": self._estimate_collective_iq(),
                "innovation_potential": self._assess_innovation_potential(),
                "adaptability_score": self._measure_adaptability(),
                "knowledge_sharing_index": self._measure_knowledge_sharing()
            },
            "swarm_topology": {
                "connection_density": self._calculate_connection_density(),
                "centralization_level": self._measure_centralization(),
                "clustering_coefficient": self._calculate_clustering(),
                "path_length": self._estimate_average_path_length()
            },
            "recommendations": self._get_swarm_recommendations(),
            "timestamp": time.time()
        }
    
    # Additional helper methods for overview
    def _get_agent_type_distribution(self) -> Dict[str, int]:
        """Get distribution of agent types"""
        distribution = {}
        for agent in self.registered_agents.values():
            atype = agent["agent_type"]
            distribution[atype] = distribution.get(atype, 0) + 1
        return distribution
    
    def _calculate_average_response_time(self) -> float:
        """Calculate average response time for completed tasks"""
        if len(self.completed_tasks) == 0:
            return 0.0
        # Simplified - in reality would calculate from timestamps
        return round(random.uniform(2.0, 15.0), 2)
    
    def _estimate_collective_iq(self) -> float:
        """Estimate collective intelligence quotient"""
        if len(self.registered_agents) == 0:
            return 0.0
        
        # Based on diversity, connectivity, and individual capabilities
        diversity_factor = min(1.0, len(set([a["agent_type"] for a in self.registered_agents.values()])) / max(1, len(self.registered_agents)) * 2)
        connectivity_factor = min(1.0, len(self.completed_tasks) / max(1, len(self.registered_agents)) * 0.1)
        capability_factor = sum([len(a["capabilities"]) for a in self.registered_agents.values()]) / max(1, sum([max(1, len(a["capacities"])) for a in self.registered_agents.values()]))
        
        base_iq = 100  # Average human IQ
        collective_iq = base_iq * (0.3 + diversity_factor * 0.3 + connectivity_factor * 0.2 + capability_factor * 0.2)
        return min(300, max(50, round(collective_iq, 1)))
    
    def _assess_innovation_potential(self) -> float:
        """Assess potential for innovative solutions"""
        if len(self.registered_agents) == 0:
            return 0.0
        
        # Factors: diversity, autonomy, interaction richness
        diversity = len(set([a["agent_type"] for a in self.registered_agents.values()])) / max(1, len(self.registered_agents))
        autonomy = sum([1 for a in self.registered_agents.values() if a.get("autonomous", False)]) / max(1, len(self.registered_agents))
        interaction = min(1.0, len([t for t in self.completed_tasks if t.get("collaborative", False)]) / max(1, len(self.completed_tasks)))
        
        return (diversity * 0.4 + autonomy * 0.3 + interaction * 0.3)
    
    def _measure_adaptability(self) -> float:
        """Measure how well the swarm adapts to changes"""
        if len(self.registered_agents) == 0:
            return 0.0
        
        # Based on response to failures, learning rate, flexibility
        recent_failures = len([a for a in self.registered_agents.values() 
                              if time.time() - a.get("last_failure", 0) < 3600])
        failure_rate = recent_failures / max(1, len(self.registered_agents))
        recovery_speed = 1.0 - min(1.0, failure_rate * 2)  # Inverse relationship
        
        flexibility = len(set([a["agent_type"] for a in self.registered_agents.values()])) / max(1, len(self.registered_agents))
        learning_indicator = min(1.0, len(self.completed_tasks) / 100.0)  # More experience = better learning
        
        return (recovery_speed * 0.4 + flexibility * 0.3 + learning_indicator * 0.3)
    
    def _measure_knowledge_sharing(self) -> float:
        """Measure how well knowledge is shared in the swarm"""
        if len(self.registered_agents) == 0:
            return 0.0
        
        # Based on communication patterns, shared resources, teaching behaviors
        communication_freq = min(1.0, len(self.completed_tasks) / max(1, len(self.registered_agents)) * 0.2)
        shared_knowledge = len(self.collective_knowledge) / max(1, len(self.registered_agents) * 10)  # Normalize
        helping_behavior = sum([a.get("times_helped_others", 0) for a in self.registered_agents.values()]) / max(1, sum([a.get("tasks_completed", 1) for a in self.registered_agents.values()]))
        
        return (communication_freq * 0.4 + shared_knowledge * 0.3 + helping_behavior * 0.3)
    
    def _calculate_connection_density(self) -> float:
        """Calculate how densely connected the agent network is"""
        n = len(self.registered_agents)
        if n <= 1:
            return 0.0
        
        # In a fully connected graph, n*(n-1)/2 connections possible
        max_connections = n * (n - 1) / 2
        # Estimate actual connections (simplified)
        actual_connections = min(max_connections, len(self.completed_tasks) * 2)  # Rough estimate
        
        return actual_connections / max_connections if max_connections > 0 else 0.0
    
    def _measure_centralization(self) -> float:
        """Measure how centralized the control structure is"""
        if len(self.registered_agents) == 0:
            return 0.0
        
        # Look at distribution of leadership/coordination roles
        leader_count = len([a for a in self.registered_agents.values() if a.get("is_leader", False)])
        return leader_count / len(self.registered_agents)
    
    def _calculate_clustering(self) -> float:
        """Calculate clustering coefficient of the agent network"""
        # Simplified clustering coefficient
        if len(self.registered_agents) < 3:
            return 0.0
        
        # In reality would calculate based on actual connections
        # For now, return a reasonable estimate based on interaction density
        return min(0.8, len(self.completed_tasks) / max(1, len(self.registered_agents)) * 0.05)
    
    def _estimate_average_path_length(self) -> float:
        """Estimate average path length between agents"""
        n = len(self.registered_agents)
        if n <= 1:
            return 0.0
        if n == 2:
            return 1.0
        
        # In a random graph, average path length is log(n)/log(<k>) where <k> is average degree
        # Simplified estimation
        avg_connections_per_node = min(n-1, max(1, len(self.completed_tasks) / max(1, n) * 2))
        if avg_connections_per_node <= 1:
            return float(n)  # Line or disconnected
        
        import math
        return max(1.0, min(n-1, math.log(max(2, n)) / max(0.1, math.log(max(2, avg_connections_per_node)))))
    
    def _get_swarm_recommendations(self) -> List[str]:
        """Get general recommendations for swarm improvement"""
        recommendations = []
        
        total_agents = len(self.registered_agents)
        if total_agents < 3:
            recommendations.append("Consider increasing swarm size for better robustness and capability diversity")
        elif total_agents > 50:
            recommendations.append("Large swarm detected - consider implementing hierarchical organization for management efficiency")
        
        utilization = self._calculate_available_capacity()
        if utilization < 0.3:
            recommendations.append("Low resource utilization detected - consider increasing task load or reducing agent count")
        elif utilization > 0.9:
            recommendations.append("High resource utilization - consider adding more agents or optimizing task distribution")
        
        diversity = self._calculate_swarm_diversity()
        if diversity < 0.3:
            recommendations.append("Low agent type diversity - consider adding specialized agents for different capabilities")
        elif diversity > 0.8:
            recommendations.append("High diversity detected - consider implementing better coordination mechanisms")
        
        if len(self.task_queue) > 20:
            recommendations.append("Long task queue detected - consider implementing priority-based preemption or increasing processing capacity")
        
        if not recommendations:
            recommendations = [
                "Swarm operating in healthy parameters - continue monitoring",
                "Consider periodic restructuring to prevent stagnation",
                "Investigate opportunities for specialized sub-swarm formation",
                "Evaluate benefits of heterogeneous vs homogeneous agent mixes for specific tasks"
            ]
        
        return recommendations[:5]
