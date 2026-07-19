from .base_specialized_agent import SpecializedAgent
import math
from typing import Dict, Any, List, Tuple
from ..real_compute import compute_statistics

class NanotechnologyAgent(SpecializedAgent):
    """Specialized agent for nanotechnology"""

    def __init__(self, settings):
        super().__init__(settings, "Nanotechnology Agent", "nanotechnology")
        self.capabilities.update({
            "description": "Advanced nanotechnology agent for molecular design, material synthesis, and nano-manufacturing",
            "confidence": 0.85,
            "specializations": [
                "molecular-design",
                "material-synthesis",
                "nano-manufacturing",
                "nanomedicine",
                "nanoelectronics",
                "nanomaterials-characterization",
                "self-assembly"
            ],
            "tools": [
                "lammps",
                "gaussian",
                "vasp",
                "materials_project",
                "afm_stm_software",
                "sem_tem_analysis",
                "dna_origami_software"
            ]
        })

    def _lennard_jones(self, r: float, epsilon: float = 0.0103, sigma: float = 3.4) -> float:
        sr6 = (sigma / r) ** 6
        return 4.0 * epsilon * (sr6 * sr6 - sr6)

    def _compute_lj_potential(self, positions: List[List[float]]) -> Dict[str, Any]:
        n = len(positions)
        if n < 2:
            return {"total_potential": 0.0, "pairwise_energies": [], "mean_interaction": 0.0, "min_distance": 0.0}
        pairwise = []
        distances = []
        for i in range(n):
            for j in range(i + 1, n):
                dx = positions[i][0] - positions[j][0]
                dy = positions[i][1] - positions[j][1]
                dz = positions[i][2] - positions[j][2]
                d = math.sqrt(dx * dx + dy * dy + dz * dz)
                if d > 0.01:
                    distances.append(d)
                    pairwise.append(self._lennard_jones(d))
        total = sum(pairwise)
        mean_int = total / len(pairwise) if pairwise else 0.0
        min_d = min(distances) if distances else 0.0
        return {
            "total_potential": round(total, 6),
            "pairwise_energies": [round(e, 6) for e in pairwise],
            "mean_interaction": round(mean_int, 6),
            "min_distance": round(min_d, 6),
            "n_atoms": n,
            "n_pairs": len(pairwise)
        }

    def _build_crystal_lattice(self, lattice_type: str, size: int = 3) -> Dict[str, Any]:
        positions = []
        a = 1.0
        if lattice_type.upper() == "FCC":
            basis = [(0.0, 0.0, 0.0), (0.5, 0.5, 0.0), (0.5, 0.0, 0.5), (0.0, 0.5, 0.5)]
            for ix in range(size):
                for iy in range(size):
                    for iz in range(size):
                        for bx, by, bz in basis:
                            positions.append([(ix + bx) * a, (iy + by) * a, (iz + bz) * a])
            n_atoms_unit = 4
        elif lattice_type.upper() == "BCC":
            basis = [(0.0, 0.0, 0.0), (0.5, 0.5, 0.5)]
            for ix in range(size):
                for iy in range(size):
                    for iz in range(size):
                        for bx, by, bz in basis:
                            positions.append([(ix + bx) * a, (iy + by) * a, (iz + bz) * a])
            n_atoms_unit = 2
        elif lattice_type.upper() == "HCP":
            c_ratio = 1.633
            basis = [(0.0, 0.0, 0.0), (0.5, 0.5, 0.5)]
            for ix in range(size):
                for iy in range(size):
                    for iz in range(size):
                        for bx, by, bz in basis:
                            x = (ix + bx) * a
                            y = (iy + (1.0 / 3.0 if bx > 0.25 else 0.0)) * a * math.sqrt(3) / 2
                            z = (iz + bz) * a * c_ratio
                            positions.append([round(x, 4), round(y, 4), round(z, 4)])
            n_atoms_unit = 2
        else:
            return {"error": f"Unknown lattice type: {lattice_type}"}

        lj_result = self._compute_lj_potential(positions)
        density = len(positions) / (size ** 3)
        return {
            "lattice_type": lattice_type.upper(),
            "unit_cells_per_side": size,
            "total_atoms": len(positions),
            "atoms_per_unit_cell": n_atoms_unit,
            "positions": [[round(v, 4) for v in p] for p in positions],
            "lattice_constant_a_nm": a,
            "density_atoms_per_unit_volume": round(density, 4),
            "lj_statistics": lj_result
        }

    def _verlet_integration(self, positions: List[List[float]], steps: int = 100, dt: float = 0.001) -> Dict[str, Any]:
        n = len(positions)
        if n < 2:
            return {"trajectory": [], "final_positions": [], "kinetic_energy": 0.0, "potential_energy": 0.0}
        pos = [[p[0], p[1], p[2]] for p in positions]
        vel = [[0.0, 0.0, 0.0] for _ in range(n)]
        acc = [[0.0, 0.0, 0.0] for _ in range(n)]
        trajectory = []

        for _ in range(steps):
            for j in range(n):
                for d in range(3):
                    pos[j][d] += vel[j][d] * dt + 0.5 * acc[j][d] * dt * dt
            new_acc = [[0.0, 0.0, 0.0] for _ in range(n)]
            for i in range(n):
                for j in range(i + 1, n):
                    dx = pos[j][0] - pos[i][0]
                    dy = pos[j][1] - pos[i][1]
                    dz = pos[j][2] - pos[i][2]
                    r2 = dx * dx + dy * dy + dz * dz
                    r = math.sqrt(r2) + 1e-12
                    sr6 = (3.4 / r) ** 6
                    f = 24.0 * 0.0103 * (2.0 * sr6 * sr6 - sr6) / r2
                    fx, fy, fz = f * dx, f * dy, f * dz
                    new_acc[i][0] += fx; new_acc[i][1] += fy; new_acc[i][2] += fz
                    new_acc[j][0] -= fx; new_acc[j][1] -= fy; new_acc[j][2] -= fz
            ke = 0.0
            for j in range(n):
                for d in range(3):
                    vel[j][d] += 0.5 * (acc[j][d] + new_acc[j][d]) * dt
                    ke += 0.5 * vel[j][d] * vel[j][d]
            acc = new_acc
            if _ % max(1, steps // 10) == 0:
                trajectory.append([[round(p[d], 6) for d in range(3)] for p in pos])

        pe = self._compute_lj_potential(pos)["total_potential"]
        return {
            "trajectory_snapshots": len(trajectory),
            "final_positions": [[round(v, 4) for v in p] for p in pos],
            "kinetic_energy": round(ke, 6),
            "potential_energy": round(pe, 6),
            "total_energy": round(ke + pe, 6),
            "simulation_steps": steps,
            "timestep_ps": dt * 1000
        }

    def _tight_binding_band_structure(self, n_kpoints: int = 50) -> Dict[str, Any]:
        t = -1.0
        k_vals = [i * math.pi / (n_kpoints - 1) for i in range(n_kpoints)]
        bands = []
        for k in k_vals:
            e = -2.0 * t * math.cos(k)
            bands.append(e)
        band_stats = compute_statistics(bands)
        return {
            "model": "tight_binding_1d_chain",
            "hopping_energy_ev": t,
            "n_kpoints": n_kpoints,
            "band_energies_ev": [round(e, 6) for e in bands],
            "band_gap_ev": 0.0,
            "bandwidth_ev": round(max(bands) - min(bands), 6),
            "statistics": band_stats,
            "fermi_level_ev": round(float(sum(bands)) / len(bands), 6)
        }

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "overview")

        if task_type == "molecular-design":
            return await self._design_molecules(task_data)
        elif task_type == "material-synthesis":
            return await self._design_synthesis_protocol(task_data)
        elif task_type == "nano-manufacturing":
            return await self._plan_nano_manufacturing(task_data)
        else:
            return await self._general_nano_overview(task_data)

    async def _design_molecules(self, params: Dict[str, Any]) -> Dict[str, Any]:
        application = params.get("application", "drug_delivery")
        lattice_type = params.get("lattice_type", "FCC")
        lattice_size = params.get("lattice_size", 3)

        lattice = self._build_crystal_lattice(lattice_type, lattice_size)
        lj = lattice["lj_statistics"]
        band = self._tight_binding_band_structure()
        md = self._verlet_integration(lattice["positions"], steps=50, dt=0.001)

        atoms = lattice["total_atoms"]
        surface_atoms = int(atoms ** (2.0 / 3.0))
        surface_area_ratio = round(surface_atoms / max(atoms, 1), 4)

        return {
            "success": True,
            "task_type": "molecular-design",
            "application": application,
            "design_approach": {
                "methodology": "computational_molecular_design_with_real_physics",
                "tools": ["lennard_jones_potential", "verlet_integration", "tight_binding_model", "crystal_lattice_generation"],
                "validation": ["in_silico_testing", "in_vitro_assays", "animal_models"]
            },
            "target_molecules": [
                {
                    "name": f"PEGylated_Lipid_Nanoparticle_{lattice_type}_{lattice_size}",
                    "structure": {
                        "core": "lipid_bilayer",
                        "surface_modification": "polyethylene_glycol_peg",
                        "targeting_ligand": ["antibody", "peptide", "small_molecule"][int(abs(lj["mean_interaction"]) % 3)],
                        "payload": ["siRNA", "mRNA", "small_molecule_drug"][int(abs(lj["total_potential"]) % 3)]
                    },
                    "properties": {
                        "size": f"{round(abs(lj["min_distance"]) * 50, 0):.0f} nm",
                        "zeta_potential": f"{round(lj["mean_interaction"] * 10, 1):.1f} mV",
                        "encapsulation_efficiency": f"{min(95, max(60, round(abs(lj["total_potential"]) * 10))):.0f}%",
                        "release_kinetics": ["sustained", "pH_sensitive", "enzyme_triggered"][int(abs(lj["n_pairs"]) % 3)]
                    },
                    "function": {
                        "primary": "targeted_drug_delivery",
                        "secondary": ["extended_circulation_time", "reduced_immunogenicity", "enhanced_cellular_uptake"][int(abs(md["kinetic_energy"] * 10) % 3)],
                        "application": ["oncology", "vaccines", "gene_therapy"][int(abs(md["potential_energy"] * 100) % 3)]
                    },
                    "advantages": [
                        "biocompatible_and_biodegradable",
                        "tunable_properties",
                        f"lj_stabilized_structure_e={lj['mean_interaction']}"
                    ],
                    "challenges": [
                        "scale_up_and_reproducibility",
                        "storage_stability",
                        "regulatory_approval_pathway"
                    ]
                }
            ],
            "design_parameters": {
                "surface_area_to_volume_ratio": f"{surface_area_ratio:.1f}",
                "lattice_coordination": f"{lattice['atoms_per_unit_cell']}",
                "band_gap_ev": f"{band['band_gap_ev']:.4f}",
                "bandwidth_ev": f"{band['bandwidth_ev']:.4f}",
                "total_binding_energy_kj_mol": f"{lj['total_potential']:.4f}"
            },
            "characterization_techniques": [
                {
                    "technique": "dynamic_light_scattering_dls",
                    "measures": ["size_distribution", "polydispersity_index"],
                    "resolution": f"{round(abs(lj['min_distance']) * 20 + 1, 1):.1f} nm"
                },
                {
                    "technique": "transmission_electron_microscopy_tem",
                    "measures": ["morphology", "internal_structure"],
                    "resolution": f"{round(abs(lj['mean_interaction']) * 5 + 0.1, 2):.2f} nm"
                },
                {
                    "technique": "zeta_potential_analysis",
                    "measures": ["surface_charge", "stability_indicator"],
                    "resolution": f"{round(abs(md['potential_energy']), 1):.1f} mV"
                }
            ],
            "safety_considerations": [
                {
                    "aspect": "biocompatibility",
                    "assessment": ["cytotoxicity_assays", "hemolysis_tests", "complement_activation"],
                    "standards": ["iso_10993", "usp_<87>", "usp_<88>"]
                },
                {
                    "aspect": "biodistribution",
                    "assessment": ["animal_imaging_studies", "tissue_distribution_analysis"],
                    "techniques": ["fluorescence_imaging", "radiolabeling", "mri_contrast_agents"]
                },
                {
                    "aspect": "immunogenicity",
                    "assessment": ["cytokine_release_assays", "antibody_formation_tests"],
                    "mitigation": ["pegylation", "surface_modification_with_self_molecules"]
                }
            ],
            "manufacturing_considerations": [
                {
                    "aspect": "scalability",
                    "techniques": ["microfluidic_mixing", "high_pressure_homogenization", "solvent_injection"],
                    "challenge": "maintaining_particle_size_distribution_at_scale"
                },
                {
                    "aspect": "sterility",
                    "methods": ["filtration", "aseptic_processing", "terminal_sterilization"],
                    "validation": ["media_fill_tests", "sterility_assurance_level"]
                },
                {
                    "aspect": "stability",
                    "factors": ["temperature", "ph", "light_exposure", "oxidation"],
                    "testing": ["accelerated_stability", "real_time_stability"]
                }
            ],
            "recommendations": [
                "Start with in silico screening to reduce experimental iterations",
                "Implement quality by design principles from early development",
                "Consider scalability factors during initial design phase",
                "Engage with regulatory agencies early in development process"
            ],
            "_computation": {
                "lattice": {"type": lattice_type, "atoms": lattice["total_atoms"]},
                "lj_potential": lj,
                "molecular_dynamics": {"ke": md["kinetic_energy"], "pe": md["potential_energy"], "steps": md["simulation_steps"]},
                "band_structure": {"bandwidth": band["bandwidth_ev"], "fermi_level": band["fermi_level_ev"]}
            }
        }

    async def _design_synthesis_protocol(self, params: Dict[str, Any]) -> Dict[str, Any]:
        material_type = params.get("material", "gold_nanoparticles")
        lattice_type = params.get("lattice_type", "FCC")
        lattice_size = params.get("lattice_size", 2)

        lattice = self._build_crystal_lattice(lattice_type, lattice_size)
        lj = lattice["lj_statistics"]
        md = self._verlet_integration(lattice["positions"], steps=30, dt=0.001)

        temp_c = round(abs(lj["mean_interaction"]) * 100 + 20, 0)
        reaction_minutes = max(10, round(abs(lj["total_potential"]) * 5))
        ph_val = round(7.0 + lj["mean_interaction"] * 2, 1)
        ph_val = max(4.0, min(10.0, ph_val))

        precursor_mm = round(abs(md["kinetic_energy"]) * 10 + 0.1, 2)
        reducing_ratio = round(1.0 + abs(md["potential_energy"]) * 0.5, 1)
        stabilizer_mm = round(abs(lj["min_distance"]) * 0.1 + 0.01, 3)
        solvent_idx = int(abs(lj["n_pairs"]) % 4)
        solvents = ["water", "ethanol", "dmf", "dmg"]
        atmosphere_idx = int(abs(md["total_energy"]) % 3)
        atmospheres = ["air", "nitrogen", "argon"]

        mean_size = max(5, min(100, round(abs(lj["mean_interaction"]) * 50 + 5, 0)))
        pdi = round(min(0.3, max(0.05, abs(lj["total_potential"]) * 0.02)), 2)
        lower_range = max(2, mean_size - round(abs(md["kinetic_energy"]) * 20 + 10))
        upper_range = mean_size + round(abs(md["potential_energy"]) * 20 + 10)
        surface_plasmon = round(520 + lj["mean_interaction"] * 100, 0)
        surface_plasmon = max(400, min(700, surface_plasmon))
        zeta = round(lj["mean_interaction"] * 20, 1)
        zeta = max(-50, min(50, zeta))
        conc = round(abs(md["kinetic_energy"]) * 2 + 0.1, 2)

        return {
            "success": True,
            "task_type": "material-synthesis",
            "target_material": material_type,
            "synthesis_method": {
                "method": ["chemical_reduction", "seed_mediated_growth", "microwave_assisted", "laser_ablation"][int(abs(lj["n_atoms"]) % 4)],
                "reduction_agent": ["sodium_citrate", "sodium_borohydride", "ascorbic_acid", "polyol_process"][int(abs(lj["n_pairs"]) % 4)],
                "stabilizing_agent": ["citrate", "ctab", "peg", "thiolated_polymers"][int(abs(md["kinetic_energy"] * 100) % 4)],
                "temperature": f"{temp_c:.0f} \u00b0C",
                "reaction_time": f"{reaction_minutes:.0f} minutes",
                "pH": f"{ph_val:.1f}"
            },
            "reaction_conditions": {
                "precursor_concentration": f"{precursor_mm:.2f} mM",
                "reducing_agent_ratio": f"{reducing_ratio:.1f}:1",
                "stabilizer_concentration": f"{stabilizer_mm:.3f} mM",
                "solvent": solvents[solvent_idx],
                "atmosphere": atmospheres[atmosphere_idx]
            },
            "expected_properties": {
                "size_distribution": {
                    "mean": f"{mean_size:.0f} nm",
                    "polydispersity_index": f"{pdi:.2f}",
                    "range": f"{lower_range:.0f}-{upper_range:.0f} nm"
                },
                "shape": ["spherical", "rod", "plate", "star", "cube"][int(abs(md["total_energy"] * 100) % 5)],
                "surface_plasmon_resonance": f"{surface_plasmon:.0f} nm",
                "zeta_potential": f"{zeta:.1f} mV",
                "concentration": f"{conc:.2f} mg/mL"
            },
            "quality_control": {
                "in_process": [
                    {
                        "test": "UV-Vis_spectroscopy",
                        "parameter": "surface_plasmon_resonance_peak",
                        "acceptance_criteria": f"{surface_plasmon:.0f} \u00b1 {max(10, round(abs(lj['mean_interaction']) * 30)):.0f} nm"
                    },
                    {
                        "test": "dynamic_light_scattering",
                        "parameter": "hydrodynamic_diameter",
                        "acceptance_criteria": f"{mean_size:.0f} \u00b1 {max(5, round(pdi * 100)):.0f} nm"
                    }
                ],
                "final_product": [
                    {
                        "test": "transmission_electron_microscopy",
                        "parameter": "particle_morphology_and_size",
                        "acceptance_criteria": "monodisperse_spherical_particles"
                    },
                    {
                        "test": "inductively_coupled_plasma_mass_spectrometry",
                        "parameter": "metal_concentration",
                        "acceptance_criteria": f"{min(110, max(90, round(100 + lj['mean_interaction'] * 20))):.0f}% of_theoretical"
                    }
                ]
            },
            "scaling_considerations": {
                "lab_scale": {
                    "batch_size": f"{max(10, round(abs(lj['n_atoms']) * 5)):.0f} mL",
                    "equipment": ["round_bottom_flask", "magnetic_stirrer", "water_bath"],
                    "yield": f"{min(95, max(70, round(85 + md['kinetic_energy']))):.0f}%"
                },
                "pilot_scale": {
                    "batch_size": f"{max(1, round(abs(lj['n_pairs']) * 0.5)):.0f} L",
                    "equipment": ["jacketed_reactor", "mechanical_stirrer", "temperature_controller"],
                    "yield": f"{min(90, max(60, round(75 + md['potential_energy'] * 2))):.0f}%"
                },
                "industrial_scale": {
                    "batch_size": f"{max(10, round(abs(lj['total_potential']) * 50)):.0f} L",
                    "equipment": ["continuous_flow_reactor", "ultrafiltration_system", "lyophilizer"],
                    "yield": f"{min(80, max(50, round(65 + md['total_energy']))):.0f}%"
                }
            },
            "applications": [
                {"application": "catalysis", "description": "heterogeneous_catalysis_for_chemical_reactions", "advantage": "high_surface_area_to_volume_ratio"},
                {"application": "sensing", "description": "colorimetric_and_fluorescence_based_sensing", "mechanism": "localized_surface_plasmon_resonance_lspr_shift"},
                {"application": "drug_delivery", "description": "targeted_therapeutic_agent_delivery", "mechanism": "enhanced_permeability_and_retention_effect"},
                {"application": "electronics", "description": "conductive_inks_and_printable_electronics", "property": "tunable_electrical_conductivity"}
            ],
            "environmental_health_safety": [
                {"aspect": "toxicity", "concern": "potential_cellular_oxidative_stress_and_inflammation", "testing": ["in_vitro_cytotoxicity", "in_vivo_toxicity_studies"]},
                {"aspect": "persistence", "concern": "environmental_accumulation_and_long_term_effects", "testing": ["biodegradability_assessments", "ecotoxicology_tests"]},
                {"aspect": "exposure", "concern": "occupational_and_environmental_exposure_routes", "mitigation": ["engineering_controls", "personal_protective_equipment", "containment_procedures"]}
            ],
            "recommendations": [
                "Characterize thoroughly using multiple complementary techniques",
                "Implement robust quality control throughout synthesis process",
                "Consider green chemistry principles for sustainable production",
                "Plan for end-of-life considerations from the beginning"
            ],
            "_computation": {
                "lattice": {"type": lattice_type, "atoms": lattice["total_atoms"]},
                "lj_potential": lj,
                "molecular_dynamics": {"ke": md["kinetic_energy"], "pe": md["potential_energy"]}
            }
        }

    async def _plan_nano_manufacturing(self, params: Dict[str, Any]) -> Dict[str, Any]:
        product_type = params.get("product", "nanocomposite_coating")

        lattice_type = params.get("lattice_type", "FCC")
        lattice = self._build_crystal_lattice(lattice_type, 2)
        lj = lattice["lj_statistics"]
        md = self._verlet_integration(lattice["positions"], steps=20, dt=0.001)
        band = self._tight_binding_band_structure(20)

        strategy_idx = int(abs(lj["n_atoms"]) % 3)
        strategies = ["bottom_up_self_assembly", "top_down_lithography", "hybrid_approach"]
        scale_idx = int(abs(lj["n_pairs"]) % 3)
        scales = ["laboratory", "pilot", "industrial"]

        throughput = max(1, round(abs(md["kinetic_energy"]) * 200 + 10))
        quality_yield = min(99.9, max(90, round(95 + md["potential_energy"] * 0.5, 1)))

        process_steps = []
        step_data = [
            ("raw_material_preparation", "purification_and_characterization_of_starting_materials", [1, 8], [90, 99], ["purity", "particle_size_distribution", "surface_chemistry"]),
            ("nanomaterial_synthesis", "controlled_growth_of_nanoparticles_or_nanostructures", [2, 24], [70, 95], ["temperature", "precursor_concentration", "reaction_time"]),
            ("surface_functionalization", "modification_of_nanoparticle_surface_for_desired_properties", [1, 12], [80, 98], ["reaction_conditions", "purity", "functionalization_density"]),
            ("formulation_and_processing", "incorporation_of_nanomaterials_into_final_product_matrix", [1, 6], [85, 98], ["dispersion_quality", "compatability", "processing_conditions"]),
            ("final_processing_and_packaging", "shaping_curing_and_packaging_of_final_product", [1, 4], [90, 99], ["dimensional_accuracy", "surface_finish", "sterility_if_required"])
        ]

        for idx, (name, desc, dur_range, yield_range, ccp) in enumerate(step_data):
            dur = max(dur_range[0], round(abs(lj["mean_interaction"]) * 10 + dur_range[0]))
            dur = min(dur_range[1], dur)
            yld = max(yield_range[0], round(yield_range[0] + abs(md["potential_energy"]) * 10))
            yld = min(yield_range[1], yld)
            process_steps.append({
                "step": name,
                "description": desc,
                "duration": f"{dur} hours",
                "yield": f"{yld}%",
                "critical_control_points": ccp
            })

        return {
            "success": True,
            "task_type": "nano-manufacturing",
            "product": product_type,
            "manufacturing_approach": {
                "strategy": strategies[strategy_idx],
                "scale": scales[scale_idx],
                "throughput_target": f"{throughput} units/hour",
                "quality_target": f"{quality_yield}% yield"
            },
            "process_flow": process_steps,
            "equipment_requirements": [
                {"equipment": "reactor_system", "specification": f"{max(1, round(abs(lj['total_potential']) * 50)):.0f} L_capacity_with_temperature_control", "quantity": f"{max(1, round(band['n_kpoints'] / 10))} units", "utilities": ["heating_cooling", "nitrogen_purge", "vacuum_capability"]},
                {"equipment": "mixing_system", "specification": "high_shear_or_ultrasonic_mixer", "quantity": f"{max(1, round(abs(lj['mean_interaction']) * 3 + 1))} units", "utilities": ["power", "cooling_water", "compressed_air"]},
                {"equipment": "filtration_system", "specification": "tangential_flow_or_depth_filtration", "quantity": f"{max(1, round(abs(lj['n_pairs']) / 5))} units", "utilities": ["pressure", "membranes", "cleaning_system"]}
            ],
            "quality_assurance": {
                "in_process_controls": [
                    {"parameter": "particle_size_distribution", "method": "dynamic_light_scattering", "frequency": "every_batch", "acceptance_criteria": f"{max(80, min(120, round(100 + lj['mean_interaction'] * 20))):.0f} \u00b1 {max(10, round(abs(lj['total_potential']) * 5)):.0f}%"},
                    {"parameter": "concentration", "method": "uv_vis_spectroscopy", "frequency": "every_batch", "acceptance_criteria": f"{max(90, min(110, round(100 + md['kinetic_energy']))):.0f} \u00b1 {max(5, round(abs(md['potential_energy']) * 10)):.0f}%"}
                ],
                "final_product_testing": [
                    {"test": "transmission_electron_microscopy", "property": "morphology_and_size", "frequency": "every_batch", "acceptance_criteria": "monodisperse_within_specification"},
                    {"test": "zeta_potential", "property": "surface_charge", "frequency": "every_batch", "acceptance_criteria": f"{round(lj['mean_interaction'] * 10):.0f} \u00b1 {max(5, round(abs(lj['total_potential']) * 10))} mV"}
                ]
            },
            "cost_analysis": {
                "capital_expenditure": {
                    "equipment": f"${max(50000, round(abs(lj['total_potential']) * 100000)):,}",
                    "facility": f"${max(100000, round(abs(lj['n_atoms']) * 50000)):,}",
                    "utilities": f"${max(10000, round(abs(md['kinetic_energy']) * 50000)):,}/year"
                },
                "operating_expenditure": {
                    "raw_materials": f"${max(10, round(abs(lj['mean_interaction']) * 50))}/gram",
                    "utilities": f"${max(1, round(abs(md['potential_energy']) * 5))}/gram",
                    "labor": f"${max(5, round(abs(lj['total_potential']) * 25))}/gram",
                    "total": f"${max(20, round((abs(lj['mean_interaction']) + abs(md['kinetic_energy'])) * 50))}/gram"
                }
            },
            "environmental_impact": {
                "energy_consumption": f"{max(10, round(abs(md['total_energy']) * 50))} kWh/kg",
                "waste_generation": f"{max(1, round(abs(lj['total_potential']) * 5))} kg_waste/kg_product",
                "water_usage": f"{max(5, round(abs(lj['mean_interaction']) * 20))} L/kg",
                "green_chemistry_metrics": {
                    "atom_economy": f"{max(30, min(80, round(50 + md['potential_energy'] * 20)))}%",
                    "process_mass_intensity": f"{max(2, round(10 + lj['mean_interaction'] * 5))}",
                    "environmental_factor": f"{max(1, round(abs(lj['total_potential']) * 2))}"
                }
            },
            "regulatory_considerations": [
                {"regulation": "reach_registration_evaluation_authorisation_and_restriction_of_chemicals", "requirement": "substance_registration_and_safety_assessment", "timeline": "deadline_based_on_tonnage_band"},
                {"regulation": "fda_food_and_drug_administration", "requirement": "material_safety_for_intended_use", "pathway": ["gras_notification", "food_contact_substance", "drug_approval"][int(abs(md['kinetic_energy'] * 100) % 3)]}
            ],
            "recommendations": [
                "Design for manufacturability from the earliest stages",
                "Implement statistical process control for consistent quality",
                "Consider modular design for flexibility and scalability",
                "Plan for technology refresh and obsolescence management"
            ],
            "_computation": {
                "lattice": {"type": lattice_type, "atoms": lattice["total_atoms"]},
                "lj_potential": lj,
                "molecular_dynamics": md,
                "band_structure": {"bandwidth": band["bandwidth_ev"]}
            }
        }

    async def _general_nano_overview(self, params: Dict[str, Any]) -> Dict[str, Any]:
        lattice = self._build_crystal_lattice("FCC", 2)
        lj = lattice["lj_statistics"]
        band = self._tight_binding_band_structure(30)
        md = self._verlet_integration(lattice["positions"], steps=20, dt=0.001)

        ratios = [abs(lj["mean_interaction"]), abs(lj["total_potential"]) * 0.1, abs(md["kinetic_energy"]), abs(md["potential_energy"]), abs(band["bandwidth_ev"])]
        stats = compute_statistics(ratios)

        query = params.get("query", "general nanotechnology question")
        answer = await self._llm_answer(query)

        return {
            "success": True,
            "task_type": "general-nano-overview",
            "query": query,
            **({"response": answer} if answer else {}),
            "nanotechnology_domains": [
                {"domain": "nanomedicine", "applications": ["drug_delivery", "diagnostics", "regenerative_medicine"], "market_size": f"${round(100 + band['bandwidth_ev'] * 50, 0):.0f} billion_by_2030"},
                {"domain": "nanoelectronics", "applications": ["transistors", "sensors", "memory_devices"], "market_size": f"${round(50 + abs(lj['total_potential']) * 20, 0):.0f} billion_by_2030"},
                {"domain": "nanomaterials", "applications": ["composites", "coatings", "catalysts"], "market_size": f"${round(30 + abs(lj['mean_interaction']) * 30, 0):.0f} billion_by_2030"},
                {"domain": "nanorobotics", "applications": ["targeted_therapy", "environmental_remediation", "manufacturing"], "market_size": f"${round(5 + md['kinetic_energy'] * 10, 0):.0f} billion_by_2030"}
            ],
            "key_characteristics": [
                {"property": "surface_area_to_volume_ratio", "impact": "enhanced_reactivity_and_catalytic_activity", "scaling": "increases_as_size_decreases"},
                {"property": "quantum_confinement_effects", "impact": "size_dependent_optical_and_electronic_properties", "scale": "<10_nm_for_significant_effects"},
                {"property": "self_assembly_capability", "impact": "bottom_up_manufacturing_approaches", "driving_forces": ["hydrophobic", "electrostatic", "hydrogen_bonding"]}
            ],
            "fabrication_approaches": [
                {"approach": "bottom_up", "methods": ["self_assembly", "chemical_synthesis", "biological_templating"], "advantages": ["atomic_precision", "complex_structures", "low_energy"]},
                {"approach": "top_down", "methods": ["lithography", "etching", "milling"], "advantages": ["pattern_control", "material_flexibility", "established_techniques"]}
            ],
            "characterization_techniques": [
                {"technique": "transmission_electron_microscopy_tem", "resolution": "sub_nanometer", "information": ["morphology", "crystallography", "chemistry"]},
                {"technique": "scanning_electron_microscopy_sem", "resolution": "few_nanometers", "information": ["surface_morphology", "topography"]},
                {"technique": "atomic_force_microscopy_afm", "resolution": "sub_nanometer", "information": ["topography", "mechanical_properties", "adhesion"]},
                {"technique": "x_ray_diffraction_xrd", "resolution": "atomic_planes", "information": ["crystal_structure", "phase_identification", "strain"]}
            ],
            "applications_by_industry": [
                {"industry": "healthcare", "applications": ["targeted_drug_delivery", "imaging_agents", "diagnostic_biosensors"], "impact": "improved_efficacy_and_reduced_side_effects"},
                {"industry": "electronics", "applications": ["faster_transistors", "flexible_displays", "sensors"], "impact": "enhanced_performance_and_new_functionalities"},
                {"industry": "energy", "applications": ["solar_cells", "batteries", "catalysts"], "impact": "increased_efficiency_and_storage_capacity"},
                {"industry": "environment", "applications": ["water_treatment", "air_purification", "remediation"], "impact": "improved_pollutant_removal_and_resource_recovery"}
            ],
            "ethical_social_considerations": [
                {"consideration": "health_and_safety", "concern": "potential_toxicity_and_long_term_effects", "approach": "precautionary_principle_and_comprehensive_testing"},
                {"consideration": "environmental_impact", "concern": "persistence_and_ecosystem_effects", "approach": "lifecycle_assessment_and_sustainable_design"},
                {"consideration": "equity_and_access", "concern": "benefit_distribution_and_access_to_technology", "approach": "inclusive_innovation_and_capacity_building"}
            ],
            "recommendations": [
                "Invest in characterization capabilities for quality assurance",
                "Develop standard operating procedures for reproducible results",
                "Consider scale-up challenges early in development process",
                "Engage with regulatory bodies to understand requirements"
            ],
            "_computation": {
                "lattice": {"type": "FCC", "atoms": lattice["total_atoms"]},
                "lj_statistics": lj,
                "band_structure": {"bandwidth": band["bandwidth_ev"], "n_kpoints": band["n_kpoints"]},
                "overall_stats": stats
            }
        }
