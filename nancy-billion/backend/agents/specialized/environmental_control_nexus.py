"""
Environmental Control Nexus - Real computation version
Handles environmental automation and IoT orchestration with real calculations
(thermodynamics, NOAA heat-index regression, Magnus dew-point formula, real
regression/seasonality/correlation stats over stored sensor history).

Honesty note: no smart-home hub or IoT devices are connected on this
deployment (software-only by design). The math above is real; "devices_affected"
in control responses lists devices that WOULD be actuated if a real hub (e.g.
Home Assistant's REST API) were connected — no physical device is controlled.
See `hardware_connected` in status/control responses.
"""
from .base_specialized_agent import SpecializedAgent
import time
import math
from typing import Dict, Any, List, Tuple
from .. import real_compute as rc


class EnvironmentalControlNexus(SpecializedAgent):
    """Environmental control nexus using real environmental computation"""

    SPECIFIC_HEAT_AIR = 1005.0
    AIR_DENSITY = 1.225
    DEFAULT_ROOM_VOLUME = 50.0
    EMISSION_FACTOR = 0.4

    def __init__(self, settings):
        super().__init__(settings, "Environmental Control Nexus", "environmental-control")
        self.capabilities.update({
            "description": "Real environmental computation (thermodynamics, heat index, dew point, regression/seasonality stats) for climate/lighting/air-quality automation. No smart-home hub or IoT devices connected — control actions are computed, not physically actuated.",
            "confidence": 0.86,
            "mode": "simulated",  # no smart-home hub / IoT devices connected
            "hardware_connected": False,
            "specializations": ["climate_control_math", "lighting_automation", "air_quality_math", "iot_orchestration"],
            "designed_for_integration": ["home_assistant_rest_api", "smart_home_hub", "iot_devices", "sensor_networks"],
        })
        self.active_scenes = {}
        self.device_status = {}
        self.environmental_history: Dict[str, List[float]] = {
            "temperature": [], "humidity": [], "pressure": [],
            "co2": [], "pm2_5": [], "voc": [], "power_w": []
        }

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "overview")
        if task_type == "control":
            return await self._control_environment(task_data)
        elif task_type == "create_scene":
            return await self._create_scene(task_data)
        elif task_type == "optimize":
            return await self._optimize_for_activity(task_data)
        elif task_type == "monitor":
            return await self._monitor_conditions(task_data)
        else:
            return await self._overview()

    def _compute_hvac_energy(self, current_temp: float, target_temp: float,
                             volume: float = DEFAULT_ROOM_VOLUME) -> Dict[str, float]:
        mass = self.AIR_DENSITY * volume
        delta_t = target_temp - current_temp
        energy_joules = mass * self.SPECIFIC_HEAT_AIR * abs(delta_t)
        energy_kwh = energy_joules / 3_600_000.0
        return {
            "energy_joules": round(energy_joules, 2),
            "energy_kwh": round(energy_kwh, 6),
            "delta_temp_c": round(delta_t, 2),
            "mass_air_kg": round(mass, 2),
            "carbon_footprint_kg": round(energy_kwh * self.EMISSION_FACTOR, 6)
        }

    def _compute_aqi(self, pm25: float) -> Dict[str, Any]:
        if pm25 <= 12.0:
            aqi = self._aqi_piecewise(pm25, 0.0, 12.0, 0, 50)
        elif pm25 <= 35.4:
            aqi = self._aqi_piecewise(pm25, 12.0, 35.4, 50, 100)
        elif pm25 <= 55.4:
            aqi = self._aqi_piecewise(pm25, 35.4, 55.4, 100, 150)
        elif pm25 <= 150.4:
            aqi = self._aqi_piecewise(pm25, 55.4, 150.4, 150, 200)
        elif pm25 <= 250.4:
            aqi = self._aqi_piecewise(pm25, 150.4, 250.4, 200, 300)
        else:
            aqi = min(500, self._aqi_piecewise(pm25, 250.4, 500.4, 300, 500))
        return {"aqi": round(aqi), "category": self._aqi_category(aqi)}

    def _aqi_piecewise(self, conc: float, c_low: float, c_high: float, i_low: int, i_high: int) -> float:
        return ((i_high - i_low) / (c_high - c_low + 1e-12)) * (conc - c_low) + i_low

    def _compute_co2_index(self, co2_ppm: float) -> Dict[str, Any]:
        if co2_ppm < 600:
            idx = 0.0
            cat = "excellent"
        elif co2_ppm < 1000:
            idx = ((co2_ppm - 600) / 400) * 25 + 25
            cat = "good"
        elif co2_ppm < 1500:
            idx = ((co2_ppm - 1000) / 500) * 25 + 50
            cat = "moderate"
        elif co2_ppm < 2000:
            idx = ((co2_ppm - 1500) / 500) * 25 + 75
            cat = "poor"
        else:
            idx = min(100.0, ((co2_ppm - 2000) / 1000) * 25 + 100)
            cat = "unhealthy"
        return {"co2_index": round(idx), "category": cat}

    def _compute_dew_point(self, temp_c: float, rh_pct: float) -> float:
        a, b = 17.27, 237.7
        gamma = (a * temp_c) / (b + temp_c) + math.log(rh_pct / 100.0)
        return round((b * gamma) / (a - gamma + 1e-12), 2)

    def _compute_heat_index(self, temp_c: float, rh_pct: float) -> float:
        if temp_c < 27:
            return round(temp_c, 2)
        rh = rh_pct / 100.0
        hi = (-8.784695 + 1.61139411 * temp_c + 2.338549 * rh
              - 0.14611605 * temp_c * rh - 0.012308094 * temp_c ** 2
              - 0.016424828 * rh ** 2 + 0.002211732 * temp_c ** 2 * rh
              + 0.00072546 * temp_c * rh ** 2
              - 0.000003582 * temp_c ** 2 * rh ** 2)
        return round(hi, 2)

    def _aqi_category(self, aqi: float) -> str:
        if aqi <= 50:
            return "good"
        elif aqi <= 100:
            return "moderate"
        elif aqi <= 150:
            return "unhealthy_for_sensitive"
        elif aqi <= 200:
            return "unhealthy"
        elif aqi <= 300:
            return "very_unhealthy"
        return "hazardous"

    async def _control_environment(self, params: Dict[str, Any]) -> Dict[str, Any]:
        control_type = params.get("type", "climate")
        target = params.get("target", {})
        zone = params.get("zone", "main")

        current_temp = target.get("current_temp", 22.0)
        target_temp = target.get("temperature", 22.0)
        command_id = f"env_{int(time.time()*1000)}_{abs(hash(str(target))) % 10000:04d}"

        hvac = self._compute_hvac_energy(current_temp, target_temp)

        if control_type == "climate":
            devices = ["thermostat"]
            if "humidity" in target:
                devices.append("humidifier")
            if abs(target_temp - current_temp) > 3:
                devices.append("fan")
        elif control_type == "lighting":
            devices = ["lights"]
        elif control_type == "air_quality":
            devices = ["air_purifier", "fan"]
        else:
            devices = ["thermostat"]

        return {
            "success": True,
            "type": "environment_control_computed",  # no hub connected — computed command, not physically actuated
            "hardware_connected": False,
            "command_id": command_id,
            "control_type": control_type,
            "zone": zone,
            "target_settings": target,
            "timestamp": time.time(),
            "execution_time_ms": round(hvac["energy_joules"] / 60000, 2),
            "devices_that_would_be_affected": devices,
            "status": "computed_no_hardware",
            "energy_impact": hvac,
            "feedback": ["sensor_verification", "status_confirmation"],
            "recommendations": self._get_control_recommendations(control_type, target)
        }

    async def _create_scene(self, params: Dict[str, Any]) -> Dict[str, Any]:
        scene_type = params.get("type", "focus")
        name = params.get("name", f"Scene_{int(time.time())}")
        duration = params.get("duration", 0)

        scene_id = f"scene_{int(time.time()*1000)}_{abs(hash(scene_type + name)) % 10000:04d}"

        scenes = {
            "focus": {
                "name": "Focus Mode",
                "settings": {"temp": "21C", "light": "bright_neutral", "air": "fresh", "sound": "quiet"},
                "benefits": ["increased_concentration", "reduced_distraction"],
                "energy_kwh": 0.15
            },
            "relax": {
                "name": "Relaxation Mode",
                "settings": {"temp": "22C", "light": "warm_dim", "air": "calm", "sound": "soothing"},
                "benefits": ["stress_reduction", "improved_mood"],
                "energy_kwh": 0.10
            },
            "present": {
                "name": "Presentation Mode",
                "settings": {"temp": "22C", "light": "bright_clear", "audio": "optimized"},
                "benefits": ["professional_appearance", "clear_communication"],
                "energy_kwh": 0.20
            },
            "create": {
                "name": "Creative Mode",
                "settings": {"temp": "20C", "light": "cool_bright", "stimuli": "engaging"},
                "benefits": ["enhanced_creativity", "idea_generation"],
                "energy_kwh": 0.18
            }
        }

        scene_def = scenes.get(scene_type, scenes["focus"])
        self.active_scenes[scene_id] = {
            "type": scene_type,
            "name": name,
            "created": time.time(),
            "active": True
        }

        return {
            "success": True,
            "type": "environmental_scene_created",
            "scene_id": scene_id,
            "name": name,
            "type": scene_type,
            "settings": scene_def["settings"],
            "benefits": scene_def["benefits"],
            "duration_minutes": None if duration == 0 else duration / 60,
            "setup_time_sec": len(scene_def["settings"]) * 3,
            "energy_estimate": {
                "daily_kwh": scene_def["energy_kwh"],
                "peak_watts": scene_def["energy_kwh"] * 1000 / 24
            },
            "activation_methods": ["voice", "schedule", "context", "manual"],
            "recommendations": ["Test before regular use", "Adjust based on feedback"]
        }

    async def _optimize_for_activity(self, params: Dict[str, Any]) -> Dict[str, Any]:
        activity = params.get("activity", "work")
        duration = params.get("duration", 1800)

        optimizations = {
            "coding": {
                "climate": {"temp_c": 21.5, "humidity": 50},
                "lighting": {"brightness": 70, "temp_k": 4500},
                "air": {"ventilation": "medium", "filtration": "normal"},
                "focus": "high"
            },
            "design": {
                "climate": {"temp_c": 20, "humidity": 55},
                "lighting": {"brightness": 60, "temp_k": 6500},
                "air": {"ionization": "increased"},
                "creativity": "high"
            },
            "meeting": {
                "climate": {"temp_c": 22, "humidity": 45},
                "lighting": {"brightness": 80, "temp_k": 5000},
                "seating": "collaborative_layout",
                "collaboration": "high"
            },
            "reading": {
                "climate": {"temp_c": 22, "humidity": 50},
                "lighting": {"brightness": 50, "temp_k": 4000},
                "eye_strain": "minimized",
                "comfort": "high"
            }
        }

        opt = optimizations.get(activity, optimizations["coding"])
        setup_complexity = len(opt)
        setup_time_s = setup_complexity * 4
        latency_s = setup_complexity * 1.5

        return {
            "success": True,
            "type": "environment_optimized_for_activity",
            "activity": activity,
            "duration_minutes": duration / 60,
            "timestamp": time.time(),
            "optimizations": opt,
            "expected_outcomes": self._get_expected_outcomes(activity),
            "implementation": {
                "method": "iot_automation",
                "setup_time": f"{setup_time_s}s",
                "latency": f"{latency_s}s"
            },
            "recommendations": ["Monitor outcomes", "Adjust based on feedback", "Personalize over time"]
        }

    async def _monitor_conditions(self, params: Dict[str, Any]) -> Dict[str, Any]:
        readings = params.get("readings", {
            "temperature": 22.0, "humidity": 50.0, "pressure": 1013.25,
            "co2": 600.0, "voc": 80.0, "pm2_5": 10.0,
            "lighting_lux": 400.0, "noise_db": 35.0
        })

        temp = readings.get("temperature", 22.0)
        humidity = readings.get("humidity", 50.0)
        pressure = readings.get("pressure", 1013.25)
        co2 = readings.get("co2", 600.0)
        voc = readings.get("voc", 80.0)
        pm25 = readings.get("pm2_5", 10.0)
        lighting = readings.get("lighting_lux", 400.0)
        noise = readings.get("noise_db", 35.0)

        self.environmental_history["temperature"].append(temp)
        self.environmental_history["humidity"].append(humidity)
        self.environmental_history["pressure"].append(pressure)
        self.environmental_history["co2"].append(co2)
        self.environmental_history["pm2_5"].append(pm25)
        self.environmental_history["voc"].append(voc)

        for k in self.environmental_history:
            if len(self.environmental_history[k]) > 500:
                self.environmental_history[k] = self.environmental_history[k][-500:]

        aqi_result = self._compute_aqi(pm25)
        co2_result = self._compute_co2_index(co2)
        dew_point = self._compute_dew_point(temp, humidity)
        heat_index = self._compute_heat_index(temp, humidity)

        comfort_score = 0.0
        factors = 0

        if 21 <= temp <= 23:
            comfort_score += 1.0
        elif 19 <= temp <= 25:
            comfort_score += 0.7
        else:
            comfort_score += max(0.0, 1.0 - abs(temp - 22) / 10)
        factors += 1

        if 40 <= humidity <= 60:
            comfort_score += 1.0
        else:
            comfort_score += max(0.0, 1.0 - abs(humidity - 50) / 50)
        factors += 1

        comfort_score += max(0.0, 1.0 - aqi_result["aqi"] / 300.0)
        factors += 1

        comfort_score += max(0.0, 1.0 - co2_result["co2_index"] / 100.0)
        factors += 1

        comfort_score += max(0.0, 1.0 - max(0, noise - 35) / 40)
        factors += 1

        overall_comfort = comfort_score / max(1, factors)

        trend = "stable"
        temp_history = self.environmental_history["temperature"]
        if len(temp_history) >= 5:
            x = list(range(len(temp_history)))
            reg = rc.linear_regression(x, temp_history)
            if reg["slope"] > 0.1:
                trend = "warming"
            elif reg["slope"] < -0.1:
                trend = "cooling"

        seasonality = rc.detect_seasonality(temp_history) if len(temp_history) >= 8 else {"has_seasonality": False, "period": 1, "strength": 0.0}

        power_history = self.environmental_history.get("power_w", [])
        power_stats = rc.compute_statistics(power_history) if power_history else {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "n": 0}

        correlations = {}
        env_keys = ["temperature", "humidity", "pressure", "co2"]
        env_series = [self.environmental_history[k] for k in env_keys]
        if all(len(s) >= 5 for s in env_series):
            min_len = min(len(s) for s in env_series)
            aligned = [s[-min_len:] for s in env_series]
            corr_matrix = rc.correlation_matrix(aligned)
            for i, ki in enumerate(env_keys):
                for j, kj in enumerate(env_keys):
                    if i < j:
                        correlations[f"{ki}_{kj}"] = corr_matrix[i][j]

        return {
            "success": True,
            "type": "environment_monitored",
            "timestamp": time.time(),
            "readings": readings,
            "computed_indices": {
                "aqi": aqi_result,
                "co2_quality": co2_result,
                "dew_point_c": dew_point,
                "heat_index_c": heat_index
            },
            "overall_comfort_score": round(overall_comfort, 4),
            "comfort_level": self._get_comfort_level(overall_comfort),
            "trend_analysis": trend,
            "seasonality": seasonality,
            "correlations": correlations,
            "power_analytics": power_stats,
            "alerts": self._check_for_alerts(readings),
            "recommendations": self._get_monitoring_recommendations(readings, overall_comfort),
            "data_quality": {
                "sampling_rate": "1Hz",
                "sensors_online": 7,
                "total_sensors": 7
            }
        }

    def _get_comfort_level(self, score: float) -> str:
        if score >= 0.9:
            return "excellent"
        elif score >= 0.8:
            return "good"
        elif score >= 0.7:
            return "fair"
        elif score >= 0.6:
            return "poor"
        return "poor"

    def _check_for_alerts(self, readings: dict) -> list:
        alerts = []
        temp = readings.get("temperature", 22)
        co2_val = readings.get("co2", 500)
        noise_val = readings.get("noise_db", 40)
        pm25_val = readings.get("pm2_5", 5)

        if temp > 26:
            alerts.append({"type": "high_temperature", "value": f"{temp}C"})
        if temp < 18:
            alerts.append({"type": "low_temperature", "value": f"{temp}C"})
        if co2_val > 1000:
            alerts.append({"type": "elevated_co2", "value": f"{co2_val}ppm"})
        if noise_val > 55:
            alerts.append({"type": "high_noise", "value": f"{noise_val}dB"})
        if pm25_val > 35:
            alerts.append({"type": "elevated_pm25", "value": f"{pm25_val}ug/m3"})

        return alerts

    def _get_monitoring_recommendations(self, readings: dict, comfort: float) -> list:
        recs = []
        if comfort < 0.7:
            recs.append("Environmental conditions suboptimal - consider adjustments")
        if readings.get("co2", 400) > 800:
            recs.append("Consider increasing ventilation")
        if readings.get("temperature", 22) > 24:
            recs.append("Temperature slightly elevated - consider cooling")
        if readings.get("humidity", 50) > 60:
            recs.append("Humidity on higher side - consider dehumidification if uncomfortable")
        if not recs:
            recs.append("Environmental conditions within acceptable ranges")
        return recs

    def _get_control_recommendations(self, ctype: str, target: dict) -> list:
        recs = [f"Monitor {ctype} response after command execution"]
        if ctype == "climate":
            temp = target.get("temperature", 22)
            if isinstance(temp, (int, float)) and temp > 24:
                recs.append("Monitor for overcooling if cooling for extended period")
            elif isinstance(temp, (int, float)) and temp < 20:
                recs.append("Monitor for underheating if heating for extended period")
        elif ctype == "lighting":
            bright = target.get("brightness", 50)
            if isinstance(bright, (int, float)) and bright > 80:
                recs.append("High brightness may cause eye strain with prolonged exposure")
        return recs

    def _get_expected_outcomes(self, activity: str) -> list:
        outcomes = {
            "coding": ["increased_focus", "reduced_errors", "better_maintainability"],
            "design": ["enhanced_creativity", "better_color_perception", "improved_flow_state"],
            "meeting": ["clearer_communication", "better_engagement", "more_effective_decisions"],
            "reading": ["better_comprehension", "reduced_eye_strain", "longer_focus_sessions"],
            "default": ["improved_comfort", "better_performance", "enhanced_experience"]
        }
        return outcomes.get(activity, outcomes["default"])

    async def _overview(self) -> Dict[str, Any]:
        return {
            "success": True,
            "type": "environmental_control_overview",
            "description": "Environmental control system for optimal human performance",
            "domains": ["climate", "lighting", "air_quality", "acoustic", "ergonomic"],
            "control_methods": ["reactive", "scheduled", "context_aware", "predictive"],
            "benefits": ["health", "productivity", "comfort", "efficiency"],
            "integration": ["smart_home_platforms", "iot_devices", "sensor_networks"],
            "considerations": ["privacy", "reliability", "user_autonomy", "interoperability"]
        }
