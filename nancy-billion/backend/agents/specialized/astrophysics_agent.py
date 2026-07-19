"""
Astrophysics Agent for Nancy Billion Backend
Handles cosmology, planetary science, space mission analysis
"""
from .base_specialized_agent import SpecializedAgent
import math
from typing import Dict, Any, List

G = 6.67430e-11
C = 299792458.0
M_SUN = 1.98847e30
R_SUN = 6.957e8
L_SUN = 3.828e26
AU = 1.495978707e11
PC = 3.085677581e16
H0 = 67.4
SIGMA_SB = 5.670374419e-8

SOLAR_SYSTEM: Dict[str, Dict[str, float]] = {
    "mercury": {"mass": 3.285e23, "radius": 2.4397e6, "semi_major_axis_au": 0.387, "orbital_period_days": 87.97, "eccentricity": 0.2056, "inclination_deg": 7.00, "albedo": 0.142, "axial_tilt_deg": 0.034, "rotation_period_hours": 1407.6, "surface_temp_k": 340, "atmosphere_pressure_bar": 1e-15},
    "venus": {"mass": 4.867e24, "radius": 6.0518e6, "semi_major_axis_au": 0.723, "orbital_period_days": 224.7, "eccentricity": 0.0068, "inclination_deg": 3.39, "albedo": 0.689, "axial_tilt_deg": 177.4, "rotation_period_hours": -5832.6, "surface_temp_k": 735, "atmosphere_pressure_bar": 92},
    "earth": {"mass": 5.972e24, "radius": 6.371e6, "semi_major_axis_au": 1.0, "orbital_period_days": 365.25, "eccentricity": 0.0167, "inclination_deg": 0.0, "albedo": 0.306, "axial_tilt_deg": 23.44, "rotation_period_hours": 24.0, "surface_temp_k": 288, "atmosphere_pressure_bar": 1},
    "mars": {"mass": 6.417e23, "radius": 3.3895e6, "semi_major_axis_au": 1.524, "orbital_period_days": 686.98, "eccentricity": 0.0934, "inclination_deg": 1.85, "albedo": 0.250, "axial_tilt_deg": 25.19, "rotation_period_hours": 24.6, "surface_temp_k": 210, "atmosphere_pressure_bar": 0.006},
    "jupiter": {"mass": 1.898e27, "radius": 6.9911e7, "semi_major_axis_au": 5.203, "orbital_period_days": 4332.59, "eccentricity": 0.0484, "inclination_deg": 1.30, "albedo": 0.538, "axial_tilt_deg": 3.13, "rotation_period_hours": 9.9, "surface_temp_k": 165, "atmosphere_pressure_bar": 1},
    "saturn": {"mass": 5.683e26, "radius": 5.8232e7, "semi_major_axis_au": 9.537, "orbital_period_days": 10759.22, "eccentricity": 0.0539, "inclination_deg": 2.49, "albedo": 0.499, "axial_tilt_deg": 26.73, "rotation_period_hours": 10.7, "surface_temp_k": 134, "atmosphere_pressure_bar": 1},
    "uranus": {"mass": 8.681e25, "radius": 2.5362e7, "semi_major_axis_au": 19.19, "orbital_period_days": 30688.5, "eccentricity": 0.0472, "inclination_deg": 0.77, "albedo": 0.488, "axial_tilt_deg": 97.77, "rotation_period_hours": -17.2, "surface_temp_k": 76, "atmosphere_pressure_bar": 1},
    "neptune": {"mass": 1.024e26, "radius": 2.4622e7, "semi_major_axis_au": 30.07, "orbital_period_days": 60182.0, "eccentricity": 0.0086, "inclination_deg": 1.77, "albedo": 0.442, "axial_tilt_deg": 28.32, "rotation_period_hours": 16.1, "surface_temp_k": 72, "atmosphere_pressure_bar": 1},
}


def kepler_third_law(semi_major_axis_m: float, central_mass_kg: float = M_SUN) -> float:
    return 2.0 * math.pi * math.sqrt(semi_major_axis_m ** 3 / (G * central_mass_kg))


def orbital_velocity(central_mass_kg: float, radius_m: float) -> float:
    return math.sqrt(G * central_mass_kg / radius_m)


def escape_velocity(mass_kg: float, radius_m: float) -> float:
    return math.sqrt(2.0 * G * mass_kg / radius_m)


def schwarzschild_radius(mass_kg: float) -> float:
    return 2.0 * G * mass_kg / (C * C)


def gravity_force(m1: float, m2: float, r: float) -> float:
    return G * m1 * m2 / (r * r)


def mass_luminosity_relation(mass_kg: float) -> float:
    m_solar = mass_kg / M_SUN
    if m_solar < 0.43:
        return 0.23 * (m_solar ** 2.3) * L_SUN
    elif m_solar < 2.0:
        return (m_solar ** 4) * L_SUN
    elif m_solar < 55:
        return 1.4 * (m_solar ** 3.5) * L_SUN
    else:
        return 32000 * m_solar * L_SUN


def doppler_shift(rest_wavelength_m: float, radial_velocity_ms: float) -> float:
    return rest_wavelength_m * (1.0 + radial_velocity_ms / C)


def hubble_distance(velocity_km_s: float) -> float:
    return (velocity_km_s / H0) * 1e6 * PC


def star_surface_temperature(luminosity_w: float, radius_m: float) -> float:
    return (luminosity_w / (4.0 * math.pi * radius_m * radius_m * SIGMA_SB)) ** 0.25


def surface_gravity(mass_kg: float, radius_m: float) -> float:
    return G * mass_kg / (radius_m * radius_m)


def tidal_force(mass_kg: float, distance_m: float, radius_m: float) -> float:
    return 2.0 * G * mass_kg * radius_m / (distance_m ** 3)


def hz_limits(stellar_luminosity_w: float) -> Dict[str, float]:
    inner = math.sqrt(stellar_luminosity_w / L_SUN) * 0.95 * AU
    outer = math.sqrt(stellar_luminosity_w / L_SUN) * 1.67 * AU
    return {"inner_edge_m": inner, "inner_edge_au": inner / AU, "outer_edge_m": outer, "outer_edge_au": outer / AU}


class AstrophysicsAgent(SpecializedAgent):
    """Specialized agent for astrophysics and space science"""

    def __init__(self, settings):
        super().__init__(settings, "Astrophysics Agent", "astrophysics")
        self.capabilities.update({
            "description": "Advanced astrophysics agent for cosmology, planetary science, and space mission analysis",
            "confidence": 0.86,
            "specializations": [
                "cosmology",
                "planetary-science",
                "space-mission-analysis",
                "stellar-astrophysics",
                "galactic-astronomy",
                "exoplanet-research",
                "space-telescope-data",
            ],
            "tools": [
                "python-astropy",
                "iraf",
                "heasoft",
                "casa",
                "matplotlib-numpy-scipy",
                "jwst-pipeline",
                "hubble-data-tools",
            ],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "overview")
        try:
            if task_type == "cosmology":
                return await self._analyze_cosmology(task_data)
            elif task_type == "planetary-science":
                return await self._analyze_planetary_science(task_data)
            elif task_type == "space-mission":
                return await self._analyze_space_mission(task_data)
            elif task_type == "exoplanet":
                return await self._analyze_exoplanets(task_data)
            else:
                return await self._general_astrophysics_overview(task_data)
        except Exception as e:
            return {"success": False, "error": str(e), "task_type": task_type}

    async def _analyze_cosmology(self, params: Dict[str, Any]) -> Dict[str, Any]:
        hubble = params.get("hubble_constant", H0)
        omega_m = params.get("omega_matter", 0.315)
        omega_l = params.get("omega_dark_energy", 0.685)
        omega_b = params.get("omega_baryon", 0.049)
        omega_k = params.get("omega_curvature", 0.001)
        hubble_ms = hubble * 1000.0 / (3.085677581e19)

        hubble_time = 1.0 / hubble_ms
        hubble_time_gyr = hubble_time / (3.15576e16)

        deceleration = omega_m / 2.0 - omega_l
        critical_density = 3.0 * (hubble_ms * hubble_ms) / (8.0 * math.pi * G)
        matter_density = critical_density * omega_m
        de_density = critical_density * omega_l
        baryon_density = critical_density * omega_b

        lookback_time_gyr = {
            "z_0_5": hubble_time_gyr * (1.0 - 1.0 / math.sqrt(1.5)),
            "z_1_0": hubble_time_gyr * (1.0 - 1.0 / math.sqrt(2.0)),
            "z_2_0": hubble_time_gyr * (1.0 - 1.0 / math.sqrt(3.0)),
        }

        angular_diameter_distance = hubble_distance(hubble) / 1e6 * PC

        return {
            "success": True,
            "task_type": "cosmology",
            "cosmological_parameters": {
                "hubble_constant": f"{hubble:.2f} km/s/Mpc",
                "dark_energy_density": f"{omega_l:.3f}",
                "dark_matter_density": f"{omega_m - omega_b:.3f}",
                "baryon_density": f"{omega_b:.3f}",
                "curvature_parameter": f"{omega_k:.4f}",
                "total_matter_density": f"{omega_m:.3f}",
                "hubble_time": f"{hubble_time_gyr:.2f} Gyr",
                "critical_density": f"{critical_density:.3e} kg/m^3",
                "matter_density": f"{matter_density:.3e} kg/m^3",
                "dark_energy_density_value": f"{de_density:.3e} kg/m^3",
                "deceleration_parameter": f"{deceleration:.4f}",
            },
            "cosmic_microwave_background": {
                "temperature": f"{2.725:.3f} K",
                "anisotropy_amplitude": "18.0 μK",
                "acoustic_peaks": [
                    {"peak": 1, "multipole": "220", "amplitude": "80.0"},
                    {"peak": 2, "multipole": "537", "amplitude": "35.0"},
                    {"peak": 3, "multipole": "825", "amplitude": "45.0"},
                ],
            },
            "universe_composition": {
                "ordinary_matter": f"{omega_b / (omega_m + omega_l + omega_k) * 100:.1f}%",
                "dark_matter": f"{(omega_m - omega_b) / (omega_m + omega_l + omega_k) * 100:.1f}%",
                "dark_energy": f"{omega_l / (omega_m + omega_l + omega_k) * 100:.1f}%",
            },
            "lookback_times": {
                "redshift_0_5": f"{lookback_time_gyr['z_0_5']:.2f} Gyr",
                "redshift_1_0": f"{lookback_time_gyr['z_1_0']:.2f} Gyr",
                "redshift_2_0": f"{lookback_time_gyr['z_2_0']:.2f} Gyr",
            },
            "theoretical_frameworks": [
                {
                    "model": "Lambda_CDM",
                    "description": "Standard cosmological model with dark energy and cold dark matter",
                    "status": "leading_model",
                    "confidence": "high",
                },
                {
                    "model": "Modified_Gravity",
                    "description": "Alternatives to dark matter through modified gravity theories",
                    "status": "active_research",
                    "confidence": "medium",
                },
            ],
            "recent_discoveries": [
                "Hubble tension persists between early and late universe measurements",
                "Planck satellite confirms standard cosmological model with high precision",
                "Large-scale structure surveys reveal cosmic web filamentary structure",
            ],
            "recommendations": [
                "Continue multi-messenger astronomy approaches",
                "Improve systematic error characterization in CMB measurements",
                "Develop next-generation cosmological simulations",
                "Search for primordial gravitational wave signatures",
            ],
        }

    async def _analyze_planetary_science(self, params: Dict[str, Any]) -> Dict[str, Any]:
        planet = params.get("planet", "mars").lower()
        pdata = SOLAR_SYSTEM.get(planet)
        if pdata is None:
            pdata = SOLAR_SYSTEM["mars"]
            planet = "mars"

        mass = pdata["mass"]
        radius = pdata["radius"]
        surf_g = surface_gravity(mass, radius)
        esc_v = escape_velocity(mass, radius)

        orbital_r = pdata["semi_major_axis_au"] * AU
        orb_v = orbital_velocity(M_SUN, orbital_r)
        orb_period = kepler_third_law(orbital_r, M_SUN) / 86400.0

        hz = hz_limits(L_SUN)
        in_hz = hz["inner_edge_au"] <= pdata["semi_major_axis_au"] <= hz["outer_edge_au"]

        tidal = tidal_force(M_SUN, orbital_r, radius)

        return {
            "success": True,
            "task_type": "planetary-science",
            "target_body": planet,
            "orbital_parameters": {
                "semi_major_axis": f"{pdata['semi_major_axis_au']:.2f} AU",
                "orbital_period": f"{orb_period:.1f} days",
                "orbital_velocity": f"{orb_v / 1000:.2f} km/s",
                "eccentricity": f"{pdata['eccentricity']:.3f}",
                "inclination": f"{pdata['inclination_deg']:.2f} degrees",
            },
            "physical_properties": {
                "radius": f"{radius / 1000:.0f} km",
                "mass": f"{mass / SOLAR_SYSTEM['earth']['mass']:.2f} Earth masses",
                "surface_gravity": f"{surf_g / 9.81:.2f} g",
                "escape_velocity": f"{esc_v / 1000:.1f} km/s",
                "density": f"{mass / (4.0 / 3.0 * math.pi * radius ** 3):.0f} kg/m^3",
            },
            "atmospheric_composition": {
                "surface_pressure": f"{pdata['atmosphere_pressure_bar']:.1f} bar" if pdata['atmosphere_pressure_bar'] > 0.001 else "negligible",
                "habitable_zone": "inside" if in_hz else "outside",
                "tidal_force": f"{tidal:.2e} N/kg",
            },
            "surface_conditions": {
                "average_temperature": f"{pdata['surface_temp_k'] - 273.15:.1f} C",
                "albedo": f"{pdata['albedo']:.2f}",
                "rotation_period": f"{abs(pdata['rotation_period_hours']):.1f} hours",
            },
            "habitability_factors": {
                "liquid_water_potential": "possible" if in_hz and pdata["atmosphere_pressure_bar"] > 0.01 else "unlikely",
                "habitable_zone": "yes" if in_hz else "no",
                "surface_temperature_range": f"{pdata['surface_temp_k'] - 273.15:.0f} C average",
                "atmosphere_present": pdata["atmosphere_pressure_bar"] > 0.001,
            },
            "exploration_status": {
                "missions": [
                    {
                        "mission": "Mars_2020_Perseverance" if planet == "mars" else "Various_flyby_orbiters",
                        "agency": "NASA",
                        "status": "active" if planet == "mars" else "historical",
                        "objectives": ["seek_signs_of_ancient_life", "collect_samples", "test_oxygen_production"] if planet == "mars" else ["exploration"],
                    },
                ],
            },
            "recommendations": [
                "Focus on subsurface exploration for potential habitable zones",
                "Develop in-situ resource utilization technologies",
                "Continue search for biosignatures in ancient sedimentary rocks",
                "Prepare for human mission precursors and infrastructure",
            ],
        }

    async def _analyze_space_mission(self, params: Dict[str, Any]) -> Dict[str, Any]:
        mission_type = params.get("type", "mars_landing")
        payload_kg = params.get("payload_kg", 1000)
        delta_v_target = params.get("delta_v_km_s", 0)

        if "mars" in mission_type.lower() or "landing" in mission_type.lower():
            target = "mars"
            dv_launch = 3.5
            dv_transfer = 1.1
            dv_landing = 3.0
        elif "moon" in mission_type.lower() or "lunar" in mission_type.lower():
            target = "moon"
            dv_launch = 3.2
            dv_transfer = 0.8
            dv_landing = 1.7
        elif "venus" in mission_type.lower():
            target = "venus"
            dv_launch = 3.4
            dv_transfer = 0.9
            dv_landing = 4.5
        else:
            target = "mars"
            dv_launch = 3.5
            dv_transfer = 1.1
            dv_landing = 3.0

        total_dv = dv_launch + dv_transfer + dv_landing

        I_sp = 300.0
        g0 = 9.81
        mass_ratio = math.exp(total_dv * 1000.0 / (I_sp * g0))
        dry_mass = payload_kg * 1.2
        propellant = dry_mass * (mass_ratio - 1.0)
        wet_mass = dry_mass + propellant

        success_probs = {"launch": 0.96, "cruise": 0.98, "edl": 0.82}
        overall = success_probs["launch"] * success_probs["cruise"] * success_probs["edl"]

        return {
            "success": True,
            "task_type": "space-mission-analysis",
            "mission_type": mission_type,
            "target_body": target,
            "mission_phases": [
                {"phase": "launch", "duration": "10 minutes", "key_events": ["max_q", "meco", "stage_separation"], "success_probability": f"{success_probs['launch']:.2f}"},
                {"phase": "cruise", "duration": f"{'200-250' if target == 'mars' else '3-5'} days", "key_events": ["trajectory_corrections", "health_checks"], "success_probability": f"{success_probs['cruise']:.2f}"},
                {"phase": "entry_descent_landing", "duration": "7 minutes", "key_events": ["entry_interface", "parachute_deploy", "powered_descent", "touchdown"], "success_probability": f"{success_probs['edl']:.2f}"},
            ],
            "delta_v_requirements": {
                "earth_to_transfer": f"{dv_launch:.1f} km/s",
                "transfer_to_target": f"{dv_transfer:.1f} km/s",
                "landing": f"{dv_landing:.1f} km/s",
                "total": f"{total_dv:.1f} km/s",
            },
            "mass_budget": {
                "payload": f"{payload_kg:.0f} kg",
                "propellant": f"{propellant:.0f} kg",
                "dry_mass": f"{dry_mass:.0f} kg",
                "wet_mass": f"{wet_mass:.0f} kg",
                "mass_ratio": f"{mass_ratio:.2f}",
            },
            "power_system": {
                "source": "solar_arrays_plus_batteries" if target != "neptune" else "rtg",
                "generation": f"{max(150, int(payload_kg * 0.15))} W",
                "storage": f"{max(1, int(payload_kg * 0.001))} kWh",
                "peak_power": f"{max(300, int(payload_kg * 0.3))} W",
            },
            "communication": {
                "bandwidth": f"{max(0.5, min(2.0, total_dv * 0.2)):.1f} Mbps",
                "latency": f"{4 if target == 'moon' else 14 if target == 'mars' else 'variable'} minutes",
                "frequency_band": "X-band_plus_Ka-band",
                "antenna_gain": "35.0 dBi",
            },
            "risk_assessment": {
                "overall_success_probability": f"{overall:.2f}",
                "major_risks": [
                    {"risk": "entry_descent_landing_failure", "probability": f"{1 - success_probs['edl']:.2f}", "impact": "mission_loss", "mitigation": "redundant_systems_thorough_testing"},
                    {"risk": "power_system_failure", "probability": "0.10", "impact": "mission_compromise", "mitigation": "redundant_power_sources_health_monitoring"},
                ],
            },
            "scientific_objectives": [
                f"search_for_past_or_present_life_on_{target}",
                "characterize_geology_and_mineralogy",
                "study_atmosphere_and_climate",
                "prepare_for_future_human_exploration",
            ],
            "recommendations": [
                "Invest in advanced entry-descent-landing technologies",
                "Develop autonomous navigation and hazard avoidance systems",
                "Improve radiation shielding for electronics and crew",
                "Standardize interfaces for international cooperation",
            ],
        }

    async def _analyze_exoplanets(self, params: Dict[str, Any]) -> Dict[str, Any]:
        star_mass = params.get("star_mass", 1.0) * M_SUN
        star_luminosity = mass_luminosity_relation(star_mass)
        star_radius = params.get("star_radius", 1.0) * R_SUN
        star_temp = star_surface_temperature(star_luminosity, star_radius)

        orbital_radius_au = params.get("orbital_radius_au", 1.0)
        orbital_r_m = orbital_radius_au * AU
        orbital_period_years = math.sqrt(orbital_r_m ** 3 / (G * star_mass)) / (365.25 * 86400)

        hz = hz_limits(star_luminosity)

        eq_temp_power = star_luminosity / (16.0 * math.pi * orbital_r_m * orbital_r_m * SIGMA_SB)
        equilibrium_temp = eq_temp_power ** 0.25 if eq_temp_power > 0 else 0

        planet_mass = params.get("planet_mass_earth", 1.0) * SOLAR_SYSTEM["earth"]["mass"]
        planet_radius = params.get("planet_radius_earth", 1.0) * SOLAR_SYSTEM["earth"]["radius"]

        transit_depth = ((planet_radius / star_radius) ** 2) * 100
        rv_signal = (28.4 * planet_mass / SOLAR_SYSTEM["earth"]["mass"] * math.sin(1.0)
                     / math.sqrt(star_mass / M_SUN) / math.sqrt(orbital_radius_au)) / 1000.0

        return {
            "success": True,
            "task_type": "exoplanet-analysis",
            "star_parameters": {
                "mass": f"{star_mass / M_SUN:.2f} M_sun",
                "luminosity": f"{star_luminosity / L_SUN:.2f} L_sun",
                "radius": f"{star_radius / R_SUN:.2f} R_sun",
                "temperature": f"{star_temp:.0f} K",
            },
            "habitable_zone": {
                "conservative_inner": f"{hz['inner_edge_au']:.2f} AU",
                "conservative_outer": f"{hz['outer_edge_au']:.2f} AU",
            },
            "planet_parameters": {
                "orbital_radius": f"{orbital_radius_au:.2f} AU",
                "orbital_period": f"{orbital_period_years:.4f} years",
                "equilibrium_temperature": f"{equilibrium_temp:.0f} K",
                "transit_depth": f"{transit_depth:.4f}%",
                "radial_velocity_signal": f"{rv_signal:.4f} m/s",
                "in_habitable_zone": hz["inner_edge_au"] <= orbital_radius_au <= hz["outer_edge_au"],
            },
            "detection_methods": [
                {"method": "transit", "percentage": "73.5%", "advantages": ["radius_measurement", "atmospheric_probing"], "limitations": ["orbital_inclination_bias", "false_positives"]},
                {"method": "radial_velocity", "percentage": "23.0%", "advantages": ["mass_measurement", "orbital_elements"], "limitations": ["mass_sin_i_degeneracy", "stellar_activity"]},
                {"method": "direct_imaging", "percentage": "2.0%", "advantages": ["spectroscopy", "orbit_determination"], "limitations": ["young_hot_planets_only", "contrast_challenge"]},
                {"method": "microlensing", "percentage": "1.5%", "advantages": ["free_floating_planets", "statistical_sample"], "limitations": ["one_time_events", "no_follow_up"]},
            ],
            "planet_population": {
                "size_distribution": [
                    {"category": "earth_size", "range": "0.5-1.5 Earth radii", "percentage": "19.0%"},
                    {"category": "super_earth", "range": "1.5-2.5 Earth radii", "percentage": "26.0%"},
                    {"category": "mini_neptune", "range": "2.5-4.0 Earth radii", "percentage": "30.0%"},
                    {"category": "gas_giant", "range": ">4.0 Earth radii", "percentage": "25.0%"},
                ],
            },
            "recommendations": [
                "Continue JWST observations of promising exoplanet atmospheres",
                "Develop next-generation space telescopes for biosignature search",
                "Improve radial velocity precision for earth-mass planet detection",
                "Support ground-based extremely large telescope instrumentation",
            ],
        }

    async def _general_astrophysics_overview(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = params.get("query", "general astrophysics question")
        answer = await self._llm_answer(query)
        return {
            "success": True,
            "task_type": "general-astrophysics-overview",
            "query": query,
            **({"response": answer} if answer else {}),
            "research_areas": [
                {"area": "cosmology", "focus": ["dark_energy", "dark_matter", "inflation", "cmb"], "facilities": ["planck", "simons_observatory", "cmb-s4"]},
                {"area": "galactic_astronomy", "focus": ["milky_way_structure", "stellar_populations", "dark_matter_halo"], "facilities": ["gaia", "lsst", "ska"]},
                {"area": "stellar_astrophysics", "focus": ["stellar_evolution", "nucleosynthesis", "compact_objects"], "facilities": ["hubble", "jwst", "chandra"]},
                {"area": "exoplanet_science", "focus": ["detection", "characterization", "habitability"], "facilities": ["kepler", "tess", "jwst", "arizona"]},
            ],
            "key_facilities": [
                {"facility": "James_Webb_Space_Telescope", "wavelength": "0.6-28 um", "status": "operational", "key_science": ["first_galaxies", "exoplanet_atmospheres", "star_formation"]},
                {"facility": "Vera_Rubin_Observatory", "wavelength": "optical", "status": "under_construction", "key_science": ["dark_energy", "solar_system_inventory", "transient_sky"]},
                {"facility": "Square_Kilometre_Array", "wavelength": "radio", "status": "under_construction", "key_science": ["epoch_of_reionization", "pulsars", "magnetism"]},
            ],
            "recommendations": [
                "Support multi-wavelength astronomy for comprehensive understanding",
                "Invest in data science and archival research capabilities",
                "Foster international collaboration for large-scale facilities",
                "Train next generation of astrophysicists in computational methods",
            ],
        }
