"""
Quantum Computing Agent for Nancy Billion Backend
Handles quantum algorithms, error correction, quantum applications
"""
from .base_specialized_agent import SpecializedAgent
import numpy as np
import math
from typing import Dict, Any, List

_I = complex(0, 1)
SQRT2 = math.sqrt(2)

I_2 = np.eye(2, dtype=complex)
X = np.array([[0, 1], [1, 0]], dtype=complex)
Y = np.array([[0, -_I], [_I, 0]], dtype=complex)
Z = np.array([[1, 0], [0, -1]], dtype=complex)
H = np.array([[1, 1], [1, -1]], dtype=complex) / SQRT2
S = np.array([[1, 0], [0, _I]], dtype=complex)
T = np.array([[1, 0], [0, np.exp(_I * math.pi / 4)]], dtype=complex)

CNOT = np.array([
    [1, 0, 0, 0],
    [0, 1, 0, 0],
    [0, 0, 0, 1],
    [0, 0, 1, 0],
], dtype=complex)

SWAP = np.array([
    [1, 0, 0, 0],
    [0, 0, 1, 0],
    [0, 1, 0, 0],
    [0, 0, 0, 1],
], dtype=complex)

CZ = np.array([
    [1, 0, 0, 0],
    [0, 1, 0, 0],
    [0, 0, 1, 0],
    [0, 0, 0, -1],
], dtype=complex)

TOFFOLI = np.zeros((8, 8), dtype=complex)
for i in range(8):
    TOFFOLI[i, i] = 1
TOFFOLI[6, 6] = 0
TOFFOLI[7, 7] = 0
TOFFOLI[6, 7] = 1
TOFFOLI[7, 6] = 1


def _tensor(*matrices: np.ndarray) -> np.ndarray:
    result = np.array([[1]], dtype=complex)
    for m in matrices:
        result = np.kron(result, m)
    return result


def _state_vector(n_qubits: int) -> np.ndarray:
    size = 1 << n_qubits
    psi = np.zeros(size, dtype=complex)
    psi[0] = 1.0
    return psi


def apply_gate(state: np.ndarray, gate: np.ndarray, qubits: List[int], n_qubits: int) -> np.ndarray:
    n_gate = int(round(math.log2(gate.shape[0])))
    all_qubits = list(range(n_qubits))
    if n_gate == 1:
        op = 1
        for i in reversed(all_qubits):
            op = np.kron(gate if i == qubits[0] else I_2, op)
    elif n_gate == 2:
        ordered = qubits if qubits[0] < qubits[1] else [qubits[1], qubits[0]]
        swapped = qubits[0] > qubits[1]
        op = 1
        for i in reversed(all_qubits):
            if i == ordered[0]:
                op = np.kron(SWAP if swapped else gate, op)
            elif i == ordered[1] and swapped:
                op = np.kron(I_2, op)
            elif i == ordered[1]:
                pass
            else:
                op = np.kron(I_2, op)
    else:
        op = np.eye(1 << n_qubits, dtype=complex)
        for i in range(1 << n_qubits):
            target = i
            control_mask = 0
            for j, q in enumerate(qubits[:n_gate - 1]):
                control_mask |= (1 << q)
            if (i & control_mask) == control_mask:
                target ^= (1 << qubits[-1])
            if target != i:
                op[i, i] = 0
                op[i, target] = 1
    return op @ state


def bloch_sphere(state: np.ndarray) -> Dict[str, float]:
    if len(state) < 2:
        return {"x": 0.0, "y": 0.0, "z": 0.0}
    rho = np.outer(state[:2], state[:2].conj())
    x = float(2 * np.real(rho[0, 1]))
    y = float(2 * np.imag(rho[0, 1]))
    z = float(rho[0, 0] - rho[1, 1])
    return {"x": round(x, 6), "y": round(y, 6), "z": round(z, 6)}


def density_matrix(state: np.ndarray) -> np.ndarray:
    return np.outer(state, state.conj())


def partial_trace(rho: np.ndarray, trace_out_qubit: int, n_qubits: int) -> np.ndarray:
    dim = 1 << n_qubits
    kept_dim = dim >> 1
    result = np.zeros((kept_dim, kept_dim), dtype=complex)
    for i in range(kept_dim):
        i0 = i
        i1 = i | (1 << trace_out_qubit)
        if trace_out_qubit > 0 and (i >> trace_out_qubit) & 1:
            base_high = i >> trace_out_qubit
            i0 = ((base_high << (trace_out_qubit + 1))
                  | (i & ((1 << trace_out_qubit) - 1)))
            i1 = i0 | (1 << trace_out_qubit)
        for j in range(kept_dim):
            j0 = j
            j1 = j | (1 << trace_out_qubit)
            if trace_out_qubit > 0 and (j >> trace_out_qubit) & 1:
                base_high = j >> trace_out_qubit
                j0 = ((base_high << (trace_out_qubit + 1))
                      | (j & ((1 << trace_out_qubit) - 1)))
                j1 = j0 | (1 << trace_out_qubit)
            result[i, j] = rho[i0, j0] + rho[i1, j1]
    return result


def von_neumann_entropy(rho: np.ndarray) -> float:
    evals = np.linalg.eigvalsh(rho)
    evals = evals[evals > 1e-12]
    if len(evals) == 0:
        return 0.0
    return float(-np.sum(evals * np.log2(evals)))


def qft_matrix(n_qubits: int) -> np.ndarray:
    N = 1 << n_qubits
    omega = np.exp(2 * math.pi * _I / N)
    Q = np.zeros((N, N), dtype=complex)
    for i in range(N):
        for j in range(N):
            Q[i, j] = omega ** (i * j) / math.sqrt(N)
    return Q


def grover_iteration(n_qubits: int, target: int) -> np.ndarray:
    N = 1 << n_qubits
    oracle = np.eye(N, dtype=complex)
    oracle[target, target] = -1
    diffuser = 2.0 * np.full((N, N), 1.0 / N, dtype=complex) - np.eye(N, dtype=complex)
    return diffuser @ oracle


def pauli_rotation(axis: str, theta: float) -> np.ndarray:
    pauli = {"x": X, "y": Y, "z": Z}.get(axis.lower(), X)
    return np.array(np.cos(theta / 2) * I_2 - _I * np.sin(theta / 2) * pauli, dtype=complex)


class QuantumComputingAgent(SpecializedAgent):
    """Specialized agent for quantum computing"""

    def __init__(self, settings):
        super().__init__(settings, "Quantum Computing Agent", "quantum-computing")
        self.capabilities.update({
            "description": "Advanced quantum computing agent for quantum algorithms, error correction, and applications",
            "confidence": 0.84,
            "specializations": [
                "quantum-algorithms",
                "error-correction",
                "quantum-applications",
                "quantum-hardware",
                "quantum-software",
                "quantum-algorithms",
                "quantum-machine-learning",
            ],
            "tools": [
                "qiskit",
                "cirq",
                "pennylane",
                "braket",
                "qulacs",
                "projectq",
                "stim",
            ],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "overview")
        try:
            if task_type == "algorithm-design":
                return await self._design_quantum_algorithm(task_data)
            elif task_type == "error-correction":
                return await self._analyze_error_correction(task_data)
            elif task_type == "application":
                return await self._suggest_quantum_application(task_data)
            elif task_type == "hardware-evaluation":
                return await self._evaluate_quantum_hardware(task_data)
            else:
                return await self._general_quantum_overview(task_data)
        except Exception as e:
            return {"success": False, "error": str(e), "task_type": task_type}

    async def _design_quantum_algorithm(self, params: Dict[str, Any]) -> Dict[str, Any]:
        problem_type = params.get("problem", "optimization")
        n_qubits = params.get("n_qubits", 4)
        n_qubits = max(2, min(8, int(n_qubits)))

        psi = _state_vector(n_qubits)
        measurements = {}

        if problem_type == "search":
            target = params.get("target", 1) % (1 << n_qubits)
            psi = _state_vector(n_qubits)
            psi_h = H
            for q in range(n_qubits):
                psi = apply_gate(psi, psi_h, [q], n_qubits)
            iterations = int(math.pi / 4 * math.sqrt(1 << n_qubits))
            for _ in range(min(iterations, 8)):
                gate = grover_iteration(n_qubits, target)
                psi = gate @ psi
            probs = np.abs(psi) ** 2
            target_prob = float(probs[target])
            measurements = {
                "algorithm": "Grover_Search",
                "target_state": target,
                "success_probability": round(target_prob, 6),
                "iterations": iterations,
            }

        elif problem_type == "qft":
            Q = qft_matrix(n_qubits)
            psi = Q @ psi
            probs = np.abs(psi) ** 2
            measurements = {
                "algorithm": "Quantum_Fourier_Transform",
                "output_probs": [round(float(p), 6) for p in probs],
                "entropy": round(float(-np.sum(probs[probs > 0] * np.log2(probs[probs > 0]))), 6),
            }

        elif problem_type == "entanglement":
            psi = _state_vector(n_qubits)
            psi = apply_gate(psi, H, [0], n_qubits)
            psi = apply_gate(psi, CNOT, [0, 1], n_qubits)
            rho = density_matrix(psi)
            rho_a = partial_trace(rho, 1, n_qubits)
            ent = von_neumann_entropy(rho_a)
            bloch = bloch_sphere(psi)
            measurements = {
                "algorithm": "Bell_State_Preparation",
                "entanglement_entropy": round(ent, 6),
                "bloch_sphere_first_qubit": bloch,
                "state_vector": [f"{round(v.real, 4)}+{round(v.imag, 4)}i" if abs(v.imag) > 1e-10 else str(round(v.real, 4)) for v in psi],
            }

        else:
            psi = apply_gate(psi, H, [0], n_qubits)
            for q in range(1, n_qubits):
                psi = apply_gate(psi, CNOT, [q - 1, q], n_qubits)
            probs = np.abs(psi) ** 2
            rho = density_matrix(psi)
            entropies = []
            for q in range(n_qubits):
                rho_q = partial_trace(rho, q, n_qubits)
                entropies.append(round(von_neumann_entropy(rho_q), 6))
            measurements = {
                "algorithm": "GHZ_State_Preparation",
                "n_qubits": n_qubits,
                "entanglement_entropies": entropies,
                "mean_entropy": round(float(np.mean(entropies)), 6),
            }

        gate_totals = {"H": n_qubits, "CNOT": n_qubits - 1, "X": 0, "other": 0}

        return {
            "success": True,
            "task_type": "quantum-algorithm-design",
            "problem_type": problem_type,
            "n_qubits": n_qubits,
            "recommended_algorithm": {
                "name": measurements.get("algorithm", "Variational_Quantum_Eigensolver"),
                "description": f"real_{problem_type}_algorithm_simulation_on_{n_qubits}_qubits",
                "quantum_advantage": "quadratic" if problem_type == "search" else "exponential" if problem_type in ("qft", "simulation") else "potential",
                "circuit_depth": f"{n_qubits * 2} layers",
                "qubit_requirement": f"{n_qubits} logical_qubits",
            },
            "algorithm_details": {
                "measurements": measurements,
                "gates_used": gate_totals,
            },
            "resource_requirements": {
                "logical_qubits": str(n_qubits),
                "physical_qubits": f"{n_qubits * 9} (surface_code_encoding)",
                "gate_count": str(sum(gate_totals.values())),
                "circuit_depth": str(n_qubits * 2),
                "coherence_time": f"{n_qubits * 50} us",
            },
            "implementation_considerations": [
                "error_mitigation_techniques_essential_for_nisq",
                "hardware_connectivity_affects_performance",
                "barren_plateaus_may_occur_for_deep_circuits",
            ],
            "alternative_approaches": [
                {"algorithm": "Variational_Quantum_Eigensolver_VQE", "use_case": "ground_state_energy_calculation", "advantage": "natural_for_chemistry_materials_problems"},
                {"algorithm": "Quantum_Approximate_Optimization_Algorithm_QAOA", "use_case": "combinatorial_optimization", "advantage": "flexible_for_different_problem_types"},
                {"algorithm": "Grover_Search_Algorithm", "use_case": "unstructured_search", "advantage": "quadratic_speedup_over_classical"},
            ],
            "recommendations": [
                "Start with small problem instances to validate approach",
                "Implement error mitigation techniques from the beginning",
                "Benchmark against classical algorithms for fair comparison",
                "Consider hybrid quantum-classical approaches for near-term advantage",
            ],
        }

    async def _analyze_error_correction(self, params: Dict[str, Any]) -> Dict[str, Any]:
        code_type = params.get("code", "surface_code")
        d = params.get("distance", 3)
        d = max(3, min(7, int(d)))
        p_phys = params.get("physical_error_rate", 0.001)

        code_params = {
            "surface_code": {"name": "Surface Code", "n_physical": 2 * d * d - 1, "logical_per_physical": f"1/{2 * d * d - 1}", "threshold": 0.009},
            "color_code": {"name": "Color Code", "n_physical": 4 * d * d - 1, "logical_per_physical": f"1/{4 * d * d - 1}", "threshold": 0.007},
            "steane_code": {"name": "Steane Code [[7,1,3]]", "n_physical": 7, "logical_per_physical": "1/7", "threshold": 0.005},
            "shor_code": {"name": "Shor Code [[9,1,3]]", "n_physical": 9, "logical_per_physical": "1/9", "threshold": 0.004},
        }
        cp = code_params.get(code_type, code_params["surface_code"])

        p_th = cp["threshold"]
        if p_phys < p_th:
            p_log = p_phys * ((p_phys / p_th) ** ((d - 1) / 2))
            log_rate = round(p_log, 8)
            improvement = round(p_phys / max(p_log, 1e-20), 1)
        else:
            p_log = p_phys
            log_rate = round(p_log, 6)
            improvement = 1.0

        n_phys = cp["n_physical"]
        gate_overhead = d * 5
        meas_overhead = d * 3
        space_time = d * d * n_phys

        resource_estimates = {
            "factorization_2048_bit": {
                "logical_qubits": "2048",
                "physical_qubits": f"{2048 * n_phys}",
                "gate_count": "~1e10",
                "runtime": "8 hours",
            },
            "simulation_chemical_system": {
                "logical_qubits": "100",
                "physical_qubits": f"{100 * n_phys}",
                "gate_count": "~1e8",
                "runtime": "30 minutes",
            },
        }

        return {
            "success": True,
            "task_type": "quantum-error-correction",
            "error_correction_code": code_type,
            "code_properties": {
                "name": cp["name"],
                "distance": str(d),
                "logical_qubits_per_physical": cp["logical_per_physical"],
                "threshold_error_rate": f"{cp['threshold']:.3f}",
                "decoding_algorithm": "minimum_weight_perfect_matching" if code_type == "surface_code" else "neural_network_decoder",
            },
            "resource_overhead": {
                "physical_to_logical_ratio": f"{n_phys}:1",
                "gate_overhead": f"{gate_overhead}x",
                "measurement_overhead": f"{meas_overhead}x",
                "space_time_overhead": f"{space_time}x",
            },
            "logical_error_rate": {
                "physical_error_rate": f"{p_phys:.3f}",
                "logical_error_rate": f"{log_rate}",
                "improvement_factor": f"{improvement}x",
            },
            "implementation_approach": {
                "layout": "square_lattice",
                "stabilizer_measurements": "parity_checks",
                "gate_implementation": "lattice_surgery",
                "decoding_frequency": "real_time_or_batch_processing",
            },
            "resource_estimates_for_logical_qubit": resource_estimates,
            "challenges": [
                "high_overhead_makes_early_fault_tolerance_challenging",
                "decoding_complexity_scales_with_code_distance",
                "leakage_errors_require_specialized_handling",
                "crosstalk_between_logical_qubits_needs_mitigation",
            ],
            "recommendations": [
                "Start with small distance codes for logical qubit demonstrations",
                "Invest in high-fidelity gates and measurements",
                "Develop efficient decoders for real-time operation",
                "Consider subsystem codes for reduced overhead",
            ],
        }

    async def _suggest_quantum_application(self, params: Dict[str, Any]) -> Dict[str, Any]:
        industry = params.get("industry", "pharmaceuticals")
        n_qubits = params.get("n_qubits", 50)

        applications_map = {
            "pharmaceuticals": [
                {"application": "molecular_simulation", "description": "simulate_complex_molecular_interactions_for_drug_design", "quantum_advantage": "exponential_for_correlated_electron_systems", "maturity": "near_term", "estimated_qubits": "100-1000", "timeline": "3-8 years"},
                {"application": "protein_folding", "description": "predict_protein_structures_from_amino_acid_sequences", "quantum_advantage": "polynomial_speedup_for_specific_problems", "maturity": "mid_term", "estimated_qubits": "500-5000", "timeline": "5-12 years"},
            ],
            "finance": [
                {"application": "portfolio_optimization", "description": "optimize_investment_portfolios_under_risk_constraints", "quantum_advantage": "quadratic_via_amplitude_estimation", "maturity": "near_term", "estimated_qubits": "50-500", "timeline": "2-6 years"},
                {"application": "option_pricing", "description": "price_financial_derivatives_with_improved_accuracy", "quantum_advantage": "quadratic_via_monte_carlo_methods", "maturity": "near_term", "estimated_qubits": "100-1000", "timeline": "3-7 years"},
            ],
            "logistics": [
                {"application": "route_optimization", "description": "optimize_delivery_routes_and_supply_chain_logistics", "quantum_advantage": "quadratic_via_grover_or_qaoa", "maturity": "near_term", "estimated_qubits": "100-1000", "timeline": "3-8 years"},
                {"application": "inventory_management", "description": "optimize_inventory_levels_across_multi_echelon_networks", "quantum_advantage": "exponential_for_dynamic_programming_problems", "maturity": "mid_term", "estimated_qubits": "200-2000", "timeline": "5-12 years"},
            ],
            "materials_science": [
                {"application": "materials_property_prediction", "description": "predict_electronic_and_magnetic_properties_of_novel_materials", "quantum_advantage": "exponential_for_strongly_correlated_systems", "maturity": "near_term", "estimated_qubits": "50-500", "timeline": "3-8 years"},
                {"application": "catalyst_design", "description": "design_efficient_catalysts_for_chemical_reactions", "quantum_advantage": "exponential_for_reaction_mechanism_modeling", "maturity": "mid_term", "estimated_qubits": "100-1000", "timeline": "5-12 years"},
            ],
        }

        selected = applications_map.get(industry.lower(), applications_map["pharmaceuticals"])

        qpu_coherence = 300e-6
        gate_time = 50e-9
        max_circuit_depth = qpu_coherence / gate_time
        feasible_now = n_qubits <= 1000 and max_circuit_depth >= 100

        n_phys_with_ec = n_qubits * 9

        return {
            "success": True,
            "task_type": "quantum-application-suggestion",
            "target_industry": industry,
            "recommended_applications": selected,
            "hardware_feasibility": {
                "n_qubits_available": min(n_qubits, 1000),
                "n_physical_with_error_correction": n_phys_with_ec,
                "coherence_us": round(qpu_coherence * 1e6, 1),
                "gate_time_ns": round(gate_time * 1e9, 1),
                "max_circuit_depth": int(max_circuit_depth),
                "feasible_on_current_hardware": feasible_now,
            },
            "implementation_roadmap": {
                "phase_1": {"timeline": "0-2 years", "focus": "algorithm_development_and_simulation", "resources": ["quantum_software_engineers", "domain_experts"], "milestones": ["proof_of_concept_algorithms", "benchmark_against_classical"]},
                "phase_2": {"timeline": "2-5 years", "focus": "hardware_access_and_hybrid_approaches", "resources": ["quantum_hardware_partnerships", "error_mitigation_experts"], "milestones": ["demonstrate_quantum_advantage", "pilot_production_scale_tests"]},
                "phase_3": {"timeline": "5+ years", "focus": "fault_tolerant_quantum_advantage", "resources": ["error_correction_specialists", "fault_tolerant_architects"], "milestones": ["logical_qubit_demonstrations", "scalable_fault_tolerant_processors"]},
            },
            "risk_factors": [
                {"risk": "hardware_development_delays", "probability": "0.40", "impact": "timeline_extension", "mitigation": "maintain_algorithm_development_independently"},
                {"risk": "algorithm_breakthrough_by_competitors", "probability": "0.30", "impact": "competitive_disadvantage", "mitigation": "maintain_ip_through_patents_and_trade_secrets"},
            ],
            "recommendations": [
                "Start building quantum expertise now through training and partnerships",
                "Begin with problem formulation and algorithm development",
                "Establish partnerships with quantum hardware providers",
                "Create internal quantum readiness assessment programs",
            ],
        }

    async def _evaluate_quantum_hardware(self, params: Dict[str, Any]) -> Dict[str, Any]:
        technology = params.get("technology", "superconducting")

        hardware_specs = {
            "superconducting": {
                "qubit_type": "transmon",
                "operating_temperature": "10-15 mK",
                "gate_times": {"single_qubit": "30 ns", "two_qubit": "150 ns"},
                "coherence_times": {"t1": "100 us", "t2": "80 us"},
                "gate_fidelities": {"single_qubit": 0.999, "two_qubit": 0.985},
                "connectivity": "nearest_neighbor",
                "scalability_challenge": "cryogenic_infrastructure_and_crosstalk",
                "quantum_volume": 128,
            },
            "trapped_ion": {
                "qubit_type": "hyperfine_or_optical",
                "operating_temperature": "4 K",
                "gate_times": {"single_qubit": "5 us", "two_qubit": "50 us"},
                "coherence_times": {"t1": "5000 s", "t2": "500 s"},
                "gate_fidelities": {"single_qubit": 0.9995, "two_qubit": 0.980},
                "connectivity": "all_to_all_via_phonons",
                "scalability_challenge": "laser_complexity_and_ion_heating",
                "quantum_volume": 64,
            },
            "photonic": {
                "qubit_type": "polarization_or_time_bin",
                "operating_temperature": "room_temperature",
                "gate_times": {"single_qubit": "10 ps", "two_qubit": "500 ps"},
                "coherence_times": {"t1": "limited_by_photon_loss", "t2": "limited_by_dephasing"},
                "gate_fidelities": {"single_qubit": 0.980, "two_qubit": 0.900},
                "connectivity": "graph_state_based",
                "scalability_challenge": "deterministic_photon_sources_and_detectors",
                "quantum_volume": 16,
            },
        }

        specs = hardware_specs.get(technology.lower(), hardware_specs["superconducting"])

        qv = specs["quantum_volume"]
        depth = int(math.log2(qv)) if qv > 1 else 1
        algo_success = specs["gate_fidelities"]["single_qubit"] ** depth * specs["gate_fidelities"]["two_qubit"] ** (depth // 2)

        return {
            "success": True,
            "task_type": "quantum-hardware-evaluation",
            "technology": technology,
            "hardware_specifications": {
                "qubit_type": specs["qubit_type"],
                "operating_temperature": specs["operating_temperature"],
                "gate_times": specs["gate_times"],
                "coherence_times": specs["coherence_times"],
                "gate_fidelities": {k: f"{v:.4f}" for k, v in specs["gate_fidelities"].items()},
                "connectivity": specs["connectivity"],
                "scalability_challenge": specs["scalability_challenge"],
            },
            "performance_metrics": {
                "quantum_volume": str(qv),
                "algorithm_success_rate": f"{algo_success:.4f}",
                "available_qubits": "100",
                "connectivity_quality": f"{0.85 if specs['connectivity'] == 'all_to_all' else 0.75:.2f}",
                "reset_fidelity": "0.98",
            },
            "software_ecosystem": {
                "sdk_availability": "qiskit" if technology == "superconducting" else "cirq" if technology == "trapped_ion" else "braket",
                "simulator_support": "state_vector_and_density_matrix",
                "cloud_access": "ibm_quantum" if technology == "superconducting" else "azure_quantum" if technology == "trapped_ion" else "aws_braket",
                "open_source_contributions": "250 repositories",
            },
            "limitations": [
                {"limitation": "decoherence", "impact": "limits_circuit_depth_and_complexity", "mitigation": "error_correction_and_dynamical_decoupling"},
                {"limitation": "gate_errors", "impact": "limits_algorithm_accuracy_and_scalability", "mitigation": "error_mitigation_and_fault_tolerance"},
                {"limitation": "connectivity_constraints", "impact": "increases_overhead_for_non_local_interactions", "mitigation": "sophisticated_mapping_and_routing_algorithms"},
            ],
            "recommendations": [
                "Benchmark against specific algorithms of interest",
                "Consider hybrid quantum-classical approaches for near-term advantage",
                "Invest in error mitigation techniques",
                "Monitor roadmap for fidelity and qubit count improvements",
            ],
        }

    async def _general_quantum_overview(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "success": True,
            "task_type": "general-quantum-overview",
            "query": params.get("query", "general quantum computing question"),
            "quantum_advantage_areas": [
                {"area": "factorization", "algorithm": "shors_algorithm", "speedup": "exponential", "problem_size": "thousands_of_bits", "applications": ["cryptography_breaking"]},
                {"area": "unstructured_search", "algorithm": "grovers_algorithm", "speedup": "quadratic", "problem_size": "millions_to_billions_of_items", "applications": ["database_search", "optimization"]},
                {"area": "quantum_simulation", "algorithm": "various_hamiltonian_simulation", "speedup": "exponential", "problem_size": "complex_quantum_systems", "applications": ["chemistry", "materials_science", "physics"]},
                {"area": "optimization", "algorithm": "qaoa_vqe_etc", "speedup": "polynomial_to_exponential_depending_on_problem", "problem_size": "combinatorial_optimization_problems", "applications": ["logistics", "finance", "machine_learning"]},
            ],
            "current_hardware_era": {
                "name": "NISQ (Noisy Intermediate-Scale Quantum)",
                "characteristics": ["50-1000_physical_qubits", "limited_coherence", "gate_errors_present"],
                "approach": "variational_algorithms_and_error_mitigation",
                "timeline": "present_to_~2030",
            },
            "future_horizons": [
                {"era": "Early_Fault_Tolerant", "qubit_range": "thousands_to_tens_of_thousands_logical_qubits", "timeline": "2030-2040", "capabilities": ["error_corrected_logical_operations"]},
                {"era": "Fully_Fault_Tolerant", "qubit_range": "millions_of_logical_qubits", "timeline": "2040+", "capabilities": ["scalable_quantum_advantage", "cryptographically_relevant_factoring"]},
            ],
            "key_challenges": [
                "qubit_coherence_and_gate_fidelity",
                "scalability_and_connectivity",
                "error_correction_overhead",
                "software_and_algorithm_development",
                "cryogenic_infrastructure_and_control_electronics",
            ],
            "recommendations": [
                "Invest in quantum workforce development",
                "Start with quantum-ready problem formulation",
                "Build partnerships with quantum hardware and software providers",
                "Monitor technological roadmaps and adjust strategies accordingly",
            ],
        }
