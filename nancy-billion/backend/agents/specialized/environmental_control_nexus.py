"""
Environmental Control Nexus - Compact Version
Handles environmental automation and IoT orchestration
"""
from .base_specialized_agent import SpecializedAgent
import asyncio
import random
import time
from typing import Dict, Any

class EnvironmentalControlNexus(SpecializedAgent):
    """Compact environmental control nexus"""
    
    def __init__(self, settings):
        super().__init__(settings, "Environmental Control Nexus", "environmental-control")
        self.capabilities.update({
            "description": "Environmental control system for IoT orchestration and ambient intelligence",
            "confidence": 0.86,
            "specializations": ["climate_control", "lighting_automation", "air_quality", "iot_orchestration"],
            "tools": ["smart_home_hub", "iot_devices", "sensor_networks"]
        })
        self.active_scenes = {}
        self.device_status = {}
    
    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        await asyncio.sleep(0.2)
        task_type = task_data.get("type", "overview")
        
        if task_type == "control":
            return await self._control_environment(task_data)
        elif task_type == "create_scene":
            return await self._create_scene(task_data)
        elif task_type == "optimize":
            return await self._optimize_for_activity(task_data)
        elif task_type == "monitor":
            return await self._monitor_conditions()
        else:
            return await self._overview()
    
    async def _control_environment(self, params: Dict[str, Any]) -> Dict[str, Any]:
        control_type = params.get("type", "climate")
        target = params.get("target", {})
        zone = params.get("zone", "main")
        
        command_id = f"env_{int(time.time())}_{random.randint(1000, 9999)}"
        
        # Simulate control execution
        success = random.random() > 0.03  # 97% success rate
        
        return {
            "success": True,
            "type": "environment_controlled",
            "command_id": command_id,
            "control_type": control_type,
            "zone": zone,
            "target_settings": target,
            "timestamp": time.time(),
            "execution_time_ms": random.randint(200, 800),
            "devices_affected": random.sample(["thermostat", "lights", "air_purifier", "fan", "humidifier"], 
                                            min(3, random.randint(1, 3))),
            "status": "success" if success else "failed",
            "energy_impact": {
                "power_change_w": random.randint(-30, 50),
                "daily_kwh_estimate": round(random.uniform(-0.3, 1.5), 2)
            },
            "feedback": ["sensor_verification", "status_confirmation"],
            "recommendations": self._get_control_recommendations(control_type, target)
        }
    
    async def _create_scene(self, params: Dict[str, Any]) -> Dict[str, Any]:
        scene_type = params.get("type", "focus")
        name = params.get("name", f"Scene_{int(time.time())}")
        duration = params.get("duration", 0)  # 0 = permanent
        
        scene_id = f"scene_{int(time.time())}_{random.randint(1000, 9999)}"
        
        scenes = {
            "focus": {
                "name": "Focus Mode",
                "settings": {"temp": "21°C", "light": "bright_neutral", "air": "fresh", "sound": "quiet"},
                "benefits": ["increased_concentration", "reduced_distraction"]
            },
            "relax": {
                "name": "Relaxation Mode", 
                "settings": {"temp": "22°C", "light": "warm_dim", "air": "calm", "sound": "soothing"},
                "benefits": ["stress_reduction", "improved_mood"]
            },
            "present": {
                "name": "Presentation Mode",
                "settings": {"temp": "22°C", "light": "bright_clear", "audio": "optimized"},
                "benefits": ["professional_appearance", "clear_communication"]
            },
            "create": {
                "name": "Creative Mode",
                "settings": {"temp": "20°C", "light": "cool_bright", "stimuli": "engaging"},
                "benefits": ["enhanced_creativity", "idea_generation"]
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
            "duration_minutes": None if duration == 0 else duration/60,
            "setup_time_sec": random.randint(5, 20),
            "energy_estimate": {
                "daily_kwh": round(random.uniform(0.5, 2.5), 2),
                "peak_watts": random.randint(50, 150)
            },
            "activation_methods": ["voice", "schedule", "context", "manual"],
            "recommendations": ["Test before regular use", "Adjust based on feedback"]
        }
    
    async def _optimize_for_activity(self, params: Dict[str, Any]) -> Dict[str, Any]:
        activity = params.get("activity", "work")
        duration = params.get("duration", 1800)  # 30 minutes
        
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
        
        return {
            "success": True,
            "type": "environment_optimized_for_activity",
            "activity": activity,
            "duration_minutes": duration/60,
            "timestamp": time.time(),
            "optimizations": opt,
            "expected_outcomes": self._get_expected_outcomes(activity),
            "implementation": {
                "method": "iot_automation",
                "setup_time": f"{random.randint(10, 30)}s",
                "latency": f"{random.randint(2, 8)}s"
            },
            "recommendations": ["Monitor outcomes", "Adjust based on feedback", "Personalize over time"]
        }
    
    async def _monitor_conditions(self) -> Dict[str, Any]:
        # Simulate environmental readings
        readings = {
            "temperature": {"value": round(random.uniform(19, 25), 1), "unit": "°C"},
            "humidity": {"value": random.randint(35, 65), "unit": "%"},
            "co2": {"value": random.randint(400, 1000), "unit": "ppm"},
            "voc": {"value": random.randint(0, 200), "unit": "ppb"},
            "pm2_5": {"value": random.randint(0, 20), "unit": "μg/m³"},
            "lighting": {"lux": random.randint(200, 600), "unit": "lux"},
            "noise": {"value": random.randint(30, 50), "unit": "dB"}
        }
        
        # Calculate comfort score
        comfort_factors = []
        for key, data in readings.items():
            if isinstance(data, dict) and "value" in data:
                # Simple normalization for demo
                if key == "temperature":
                    score = 1.0 - abs(data["value"] - 22) / 10  # Optimal around 22°C
                elif key == "humidity":
                    score = 1.0 - abs(data["value"] - 50) / 50  # Optimal around 50%
                elif key == "co2":
                    score = max(0, 1.0 - (data["value"] - 400) / 1000)  # Better when lower
                elif key == "voc":
                    score = max(0, 1.0 - data["value"] / 500)  # Better when lower
                elif key == "pm2_5":
                    score = max(0, 1.0 - data["value"] / 50)  # Better when lower
                elif key == "lighting":
                    score = min(1.0, data["value"] / 500)  # Better when brighter (up to 500 lux)
                elif key == "noise":
                    score = max(0, 1.0 - (data["value"] - 30) / 40)  # Better when quieter
                else:
                    score = 0.5
                comfort_factors.append(max(0, min(1, score)))
        
        overall_comfort = sum(comfort_factors) / len(comfort_factors) if comfort_factors else 0.5
        
        return {
            "success": True,
            "type": "environment_monitored",
            "timestamp": time.time(),
            "readings": readings,
            "overall_comfort_score": round(overall_comfort, 2),
            "comfort_level": self._get_comfort_level(overall_comfort),
            "trend_analysis": "stable" if random.random() > 0.3 else "changing",
            "alerts": self._check_for_alerts(readings),
            "recommendations": self._get_monitoring_recommendations(readings, overall_comfort),
            "data_quality": {
                "sampling_rate": "1Hz",
                "sensors_online": random.randint(6, 7),
                "total_sensors": 7
            }
        }
    
    def _get_comfort_level(self, score: float) -> str:
        if score >= 0.9: return "excellent"
        elif score >= 0.8: return "good"
        elif score >= 0.7: return "fair"
        elif score >= 0.6: return "poor"
        else: return "poor"
    
    def _check_for_alerts(self, readings: dict) -> list:
        alerts = []
        temp = readings.get("temperature", {}).get("value", 22)
        co2 = readings.get("co2", {}).get("value", 500)
        noise = readings.get("noise", {}).get("value", 40)
        
        if temp > 26: alerts.append({"type": "high_temperature", "value": f"{temp}°C"})
        if temp < 18: alerts.append({"type": "low_temperature", "value": f"{temp}°C"})
        if co2 > 1000: alerts.append({"type": "elevated_co2", "value": f"{co2}ppm"})
        if noise > 55: alerts.append({"type": "high_noise", "value": f"{noise}dB"})
        
        return alerts
    
    def _get_monitoring_recommendations(self, readings: dict, comfort: float) -> list:
        recs = []
        if comfort < 0.7:
            recs.append("Environmental conditions suboptimal - consider adjustments")
        if readings.get("co2", {}).get("value", 400) > 800:
            recs.append("Consider increasing ventilation")
        if readings.get("temperature", {}).get("value", 22) > 24:
            recs.append("Temperature slightly elevated - consider cooling")
        if readings.get("humidity", {}).get("value", 50) > 60:
            recs.append("Humidity on higher side - consider dehumidification if uncomfortable")
        if not recs:
            recs.append("Environmental conditions within acceptable ranges")
        return recs
    
    def _get_control_recommendations(self, ctype: str, target: dict) -> list:
        recs = [f"Monitor {ctype} response after command execution"]
        if ctype == "climate":
            if "temperature" in target:
                temp = target["temperature"]
                if isinstance(temp, dict) and temp.get("value", 22) > 24:
                    recs.append("Monitor for overcooling if cooling for extended period")
                elif isinstance(temp, dict) and temp.get("value", 22) < 20:
                    recs.append("Monitor for underheating if heating for extended period")
        elif ctype == "lighting":
            if "brightness" in target:
                bright = target["brightness"]
                if isinstance(bright, dict) and bright.get("value", 50) > 80:
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

