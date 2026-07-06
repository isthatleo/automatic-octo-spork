"""
Operations Research Agent for Nancy Billion Backend
Handles process optimization, resource allocation, and supply chain optimization
"""
from .base_specialized_agent import SpecializedAgent
from .. import real_compute as rc
from typing import Dict, Any, List, Tuple
import numpy as np
import heapq
import math


class OperationsResearchAgent(SpecializedAgent):
    """Specialized agent for operations research and optimization"""

    def __init__(self, settings):
        super().__init__(settings, "Operations Research Agent", "operations-research")
        self.capabilities.update({
            "description": "Advanced operations research agent for process optimization, resource allocation, and supply chain optimization",
            "confidence": 0.88,
            "specializations": [
                "linear-programming",
                "integer-programming",
                "network-optimization",
                "queueing-theory",
                "inventory-management",
                "supply-chain-optimization",
                "scheduling",
                "simulation-modeling"
            ],
            "tools": [
                "gurobi-cplex",
                "python-pulp",
                "matlab-optimization",
                "anylogic-areana",
                "simul8",
                "lindo-lingo"
            ]
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process operations research tasks"""
        task_type = task_data.get("type", "optimization")

        if task_type == "process-optimization":
            return await self._optimize_process(task_data)
        elif task_type == "resource-allocation":
            return await self._allocate_resources(task_data)
        elif task_type == "supply-chain":
            return await self._optimize_supply_chain(task_data)
        elif task_type == "scheduling":
            return await self._optimize_schedule(task_data)
        else:
            return await self._general_or_consultation(task_data)

    async def _optimize_process(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Optimize business processes using real linear programming"""
        process = params.get("process", "order_fulfillment")
        c = params.get("objective_coeffs", None)
        A = params.get("constraint_matrix", None)
        b = params.get("constraint_rhs", None)
        bounds = params.get("bounds", None)

        lp_result = None
        if c and A and b:
            try:
                lp_result = rc.solve_linear_program(c, A, b, bounds)
            except Exception:
                lp_result = {"success": False, "message": "LP solve failed"}

        return {
            "success": True,
            "task_type": "process-optimization",
            "process": process,
            "linear_programming_result": lp_result,
            "optimization_approach": {
                "methodology": "linear_programming",
                "tools": ["value_stream_mapping", "root_cause_analysis", "process_capability_analysis"],
                "phases": [
                    {"phase": "define", "activities": ["project_charter", "stakeholder_analysis", "goal_setting"]},
                    {"phase": "measure", "activities": ["baseline_metrics", "data_collection", "measurement_system_analysis"]},
                    {"phase": "analyze", "activities": ["process_analysis", "bottleneck_identification", "root_cause_analysis"]},
                    {"phase": "improve", "activities": ["solution_generation", "pilot_testing", "implementation"]},
                    {"phase": "control", "activities": ["process_control", "monitoring", "continuous_improvement"]},
                ]
            },
            "recommendations": [
                "Implement visual management systems",
                "Standardize work procedures",
                "Create cross-functional improvement teams",
                "Establish continuous improvement culture"
            ]
        }

    async def _allocate_resources(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Allocate resources optimally using constrained optimization"""
        resource_type = params.get("type", "budget")
        total_budget = params.get("total_budget", 1000000)
        project_costs = params.get("project_costs", None)
        project_returns = params.get("project_returns", None)
        project_names = params.get("project_names", None)

        allocation = []
        if project_costs and project_returns and isinstance(project_costs, list) and isinstance(project_returns, list):
            n = min(len(project_costs), len(project_returns))
            costs = np.array(project_costs[:n], dtype=np.float64)
            returns = np.array(project_returns[:n], dtype=np.float64)
            rois = (returns - costs) / (costs + 1e-12)

            ratios = rois / (costs + 1e-12)
            sorted_indices = np.argsort(-ratios)

            remaining = float(total_budget)
            selected = []
            for idx in sorted_indices:
                cost = float(costs[idx])
                if cost <= remaining * 1.05:
                    allocated = min(cost, remaining)
                    roi = float(rois[idx])
                    name = project_names[idx] if project_names and idx < len(project_names) else f"Project_{idx}"
                    selected.append({
                        "project": name,
                        "cost": round(cost, 2),
                        "expected_return": round(float(returns[idx]), 2),
                        "roi": round(roi, 4),
                        "allocated": round(allocated, 2),
                        "allocation_pct": round(allocated / (total_budget + 1e-12) * 100, 2),
                    })
                    remaining -= cost
                    if remaining <= 0:
                        break

            total_allocated = sum(s["allocated"] for s in selected)
            total_return = sum(s["expected_return"] for s in selected)
            allocation = {
                "selected_projects": selected,
                "total_allocated": round(total_allocated, 2),
                "total_expected_return": round(total_return, 2),
                "portfolio_roi": round((total_return - total_allocated) / (total_allocated + 1e-12), 4),
                "remaining_budget": round(remaining, 2),
            }

        return {
            "success": True,
            "task_type": "resource-allocation",
            "resource_type": resource_type,
            "total_budget": total_budget,
            "allocation": allocation,
            "method": "knapsack_by_roi_density",
            "recommendations": [
                "Regularly review and adjust allocations based on performance",
                "Implement stage-gate process for project approval",
                "Maintain reserve capacity for unexpected opportunities",
                "Track actual vs planned resource utilization"
            ]
        }

    async def _optimize_supply_chain(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Optimize supply chain network using real algorithms"""
        product = params.get("product", "consumer_goods")
        distance_matrix = params.get("distance_matrix", None)
        node_names = params.get("node_names", None)
        source_idx = params.get("source_idx", 0)
        demand = params.get("demand", 1000)
        order_cost = params.get("order_cost", 100)
        holding_cost = params.get("holding_cost", 10)

        shortest_paths = None
        if distance_matrix and isinstance(distance_matrix, list) and len(distance_matrix) > 0:
            n_nodes = len(distance_matrix)
            dist_matrix = np.array(distance_matrix, dtype=np.float64)
            distances, predecessors = _dijkstra_all_pairs(dist_matrix, source_idx)

            paths_from_source = []
            for target in range(n_nodes):
                if target == source_idx:
                    continue
                path = _reconstruct_path(predecessors, target)
                name_target = node_names[target] if node_names and target < len(node_names) else f"Node_{target}"
                paths_from_source.append({
                    "from": node_names[source_idx] if node_names else f"Node_{source_idx}",
                    "to": name_target,
                    "distance": round(float(distances[target]), 4),
                    "path": [node_names[p] if node_names else f"Node_{p}" for p in path],
                })
            shortest_paths = {
                "source": node_names[source_idx] if node_names else f"Node_{source_idx}",
                "paths": paths_from_source,
            }

        eoq = None
        if demand > 0 and order_cost > 0 and holding_cost > 0:
            optimal_q = math.sqrt(2.0 * demand * order_cost / (holding_cost + 1e-12))
            optimal_orders = demand / (optimal_q + 1e-12)
            total_cost_inv = optimal_q * holding_cost / 2.0 + order_cost * demand / (optimal_q + 1e-12)
            cycle_time = optimal_q / (demand + 1e-12) * 365
            eoq = {
                "economic_order_quantity": round(optimal_q, 2),
                "optimal_order_frequency": round(optimal_orders, 2),
                "total_inventory_cost": round(total_cost_inv, 2),
                "cycle_days": round(cycle_time, 1),
                "demand": demand,
                "order_cost": order_cost,
                "holding_cost": holding_cost,
            }

        return {
            "success": True,
            "task_type": "supply-chain-optimization",
            "product": product,
            "shortest_paths": shortest_paths,
            "inventory_optimization": eoq,
            "recommendations": [
                "Consider postponement strategies for customization",
                "Implement vendor-managed inventory for key suppliers",
                "Evaluate cross-docking opportunities for fast-moving items",
                "Regularly review network design as demand patterns change"
            ]
        }

    async def _optimize_schedule(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Optimize scheduling using real priority queue and greedy algorithms"""
        schedule_type = params.get("type", "production")
        job_times = params.get("job_times", None)
        job_deadlines = params.get("job_deadlines", None)
        job_priorities = params.get("job_priorities", None)
        machine_count = params.get("machine_count", 1)

        scheduling_result = None
        if job_times and isinstance(job_times, list) and len(job_times) > 0:
            n_jobs = len(job_times)
            times = np.array(job_times, dtype=np.float64)

            if job_deadlines and isinstance(job_deadlines, list) and len(job_deadlines) == n_jobs:
                deadlines = np.array(job_deadlines, dtype=np.float64)
                indices = np.argsort(deadlines)
                scheduled = []
                current_time = 0.0
                job_heap = []
                for idx in indices:
                    heapq.heappush(job_heap, (-times[idx], idx))
                    current_time += times[idx]
                    if current_time > deadlines[idx] + 1e-9:
                        longest = heapq.heappop(job_heap)
                        current_time -= -longest[0]

                scheduled_indices = [item[1] for item in sorted(job_heap, key=lambda x: x[1])]
                makespan = current_time
                scheduled = [
                    {
                        "job": f"Job_{j}",
                        "time": float(times[j]),
                        "deadline": float(deadlines[j]) if j < len(deadlines) else None,
                        "priority": float(job_priorities[j]) if job_priorities and j < len(job_priorities) else 1.0,
                    }
                    for j in scheduled_indices
                ]

                total_tardiness = 0.0
                ct = 0.0
                for j in scheduled_indices:
                    ct += times[j]
                    if j < len(deadlines):
                        total_tardiness += max(0.0, ct - deadlines[j])
            else:
                mc = max(1, int(machine_count))
                machines = [0.0] * mc
                machine_jobs = [[] for _ in range(mc)]
                priorities = np.array(job_priorities) if job_priorities and len(job_priorities) == n_jobs else np.ones(n_jobs)
                sorted_by_priority = np.argsort(-priorities)
                for idx in sorted_by_priority:
                    earliest = min(range(mc), key=lambda m: machines[m])
                    machines[earliest] += times[idx]
                    machine_jobs[earliest].append({
                        "job": f"Job_{idx}",
                        "time": float(times[idx]),
                        "priority": float(priorities[idx]),
                    })
                makespan = max(machines)
                scheduled = machine_jobs
                total_tardiness = 0.0

            scheduling_result = {
                "jobs_scheduled": n_jobs,
                "makespan": round(float(makespan), 4),
                "total_tardiness": round(float(total_tardiness), 4),
                "schedule": scheduled,
                "method": "earliest_deadline_first" if job_deadlines else "priority_based_load_balancing",
            }

        return {
            "success": True,
            "task_type": "scheduling",
            "schedule_type": schedule_type,
            "scheduling_result": scheduling_result,
            "recommendations": [
                "Consider batching similar jobs to reduce setup times",
                "Implement dynamic rescheduling for disruptions",
                "Use scheduling software for real-time adjustments",
                "Monitor and adjust based on actual performance"
            ]
        }

    async def _general_or_consultation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Provide general operations research consultation"""
        return {
            "success": True,
            "task_type": "general-or-consultation",
            "query": params.get("query", "general operations research question"),
            "or_methodologies": [
                {"method": "linear_programming", "applications": ["resource_allocation", "production_planning", "transportation"], "assumptions": ["linearity", "divisibility", "certainty"]},
                {"method": "integer_programming", "applications": ["facility_location", "network_design", "scheduling"], "assumptions": ["integrality", "linearity"]},
                {"method": "network_analysis", "applications": ["shortest_path", "maximum_flow", "minimum_spanning_tree"], "assumptions": ["connectivity", "non_negative_weights"]},
                {"method": "simulation", "applications": ["queueing_systems", "manufacturing_systems", "logistics"], "assumptions": ["model_accuracy", "input_data_quality"]},
            ],
            "recommendations": [
                "Clearly define problem objectives and constraints",
                "Validate model assumptions against reality",
                "Start with simplified models before adding complexity",
                "Consider multiple solution approaches for comparison"
            ]
        }


def _dijkstra_all_pairs(dist_matrix: np.ndarray, source: int) -> Tuple[np.ndarray, np.ndarray]:
    """Dijkstra's algorithm using heapq for real shortest path computation."""
    n = dist_matrix.shape[0]
    distances = np.full(n, np.inf)
    predecessors = np.full(n, -1, dtype=np.int64)
    distances[source] = 0.0
    pq = [(0.0, source)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > distances[u] + 1e-12:
            continue
        for v in range(n):
            if u != v and not np.isinf(dist_matrix[u, v]) and dist_matrix[u, v] >= 0:
                nd = d + dist_matrix[u, v]
                if nd < distances[v] - 1e-12:
                    distances[v] = nd
                    predecessors[v] = u
                    heapq.heappush(pq, (nd, v))
    return distances, predecessors


def _reconstruct_path(predecessors: np.ndarray, target: int) -> List[int]:
    """Reconstruct shortest path from predecessors array."""
    path = []
    current = target
    while current != -1:
        path.append(int(current))
        current = int(predecessors[current])
    return path[::-1]
