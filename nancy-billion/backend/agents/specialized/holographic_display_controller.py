from .base_specialized_agent import SpecializedAgent
import math
import time
from typing import Dict, Any, List, Tuple

class HolographicDisplayController(SpecializedAgent):
    """Compact holographic display controller"""

    def __init__(self, settings):
        super().__init__(settings, "Holographic Display Controller", "holographic-display")
        self.capabilities.update({
            "description": "3D holographic display controller for spatial visualization and interaction",
            "confidence": 0.84,
            "specializations": ["3d_rendering", "spatial_interaction", "holographic_projection"],
            "tools": ["light_field_display", "volumetric_display", "ar_headsets"]
        })
        self.display_active = False
        self.active_holograms = {}

    def _perspective_projection(self, fov_deg: float = 60.0, aspect: float = 16.0 / 9.0, near: float = 0.1, far: float = 100.0) -> List[List[float]]:
        f = 1.0 / math.tan(math.radians(fov_deg) / 2.0)
        return [
            [f / aspect, 0.0, 0.0, 0.0],
            [0.0, f, 0.0, 0.0],
            [0.0, 0.0, (far + near) / (near - far), 2.0 * far * near / (near - far)],
            [0.0, 0.0, -1.0, 0.0]
        ]

    def _orthographic_projection(self, left: float = -1.0, right: float = 1.0, bottom: float = -1.0, top: float = 1.0, near: float = -1.0, far: float = 1.0) -> List[List[float]]:
        return [
            [2.0 / (right - left), 0.0, 0.0, -(right + left) / (right - left)],
            [0.0, 2.0 / (top - bottom), 0.0, -(top + bottom) / (top - bottom)],
            [0.0, 0.0, -2.0 / (far - near), -(far + near) / (far - near)],
            [0.0, 0.0, 0.0, 1.0]
        ]

    def _rotation_matrix(self, angle_deg: float, axis: str) -> List[List[float]]:
        a = math.radians(angle_deg)
        c = math.cos(a)
        s = math.sin(a)
        if axis == "x":
            return [[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]]
        elif axis == "y":
            return [[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]]
        else:
            return [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]

    def _transform_point(self, point: List[float], matrix: List[List[float]]) -> List[float]:
        n = len(matrix[0])
        result = [0.0] * n
        for i in range(len(matrix)):
            s = 0.0
            for j in range(min(len(point), len(matrix[i]))):
                s += matrix[i][j] * point[j]
            result[i] = s
        return result

    def _beam_steering_angle(self, wavelength_nm: float, grating_period_nm: float) -> Dict[str, float]:
        wavelength_m = wavelength_nm * 1e-9
        period_m = grating_period_nm * 1e-9
        if period_m <= 0:
            return {"diffraction_angle_deg": 0.0, "max_order": 0, "angular_resolution_deg": 0.0}
        max_order = int(period_m / wavelength_m) if wavelength_m > 0 else 0
        theta = math.asin(min(1.0, wavelength_m / period_m)) if period_m > wavelength_m else math.asin(1.0)
        angular_res = math.degrees(math.atan(wavelength_m / (period_m * 1000)))
        return {
            "diffraction_angle_deg": round(math.degrees(theta), 4),
            "max_diffraction_order": max_order,
            "angular_resolution_deg": round(angular_res, 6)
        }

    def _fraunhofer_diffraction(self, slit_width_m: float, wavelength_m: float, screen_dist_m: float, n_points: int = 50) -> Dict[str, Any]:
        k = 2.0 * math.pi / wavelength_m
        positions = [i * slit_width_m * 2 / n_points - slit_width_m for i in range(n_points)]
        angles = []
        intensities = []
        for x in positions:
            theta = math.atan2(x, screen_dist_m)
            angles.append(math.degrees(theta))
            beta = 0.5 * k * slit_width_m * math.sin(theta)
            intensity = (math.sin(beta) / (beta + 1e-12)) ** 2 if abs(beta) > 1e-12 else 1.0
            intensities.append(round(intensity, 6))
        max_int = max(intensities)
        normalized = [round(i / max_int, 6) if max_int > 0 else i for i in intensities]
        return {
            "angles_deg": [round(a, 4) for a in angles],
            "intensity": normalized,
            "peak_intensity": round(max_int, 6),
            "central_lobe_width_deg": round(abs(angles[-1] - angles[0]) / 2, 4)
        }

    def _voxel_transform(self, voxel_coords: List[List[float]], projection: str = "perspective") -> Dict[str, Any]:
        if not voxel_coords:
            return {"transformed": [], "view_volume": "empty"}
        if projection == "orthographic":
            m = self._orthographic_projection()
        else:
            m = self._perspective_projection()
        transformed = [self._transform_point(v + [1.0], m) for v in voxel_coords]
        if projection != "orthographic":
            transformed = [[v[0] / (v[3] + 1e-12), v[1] / (v[3] + 1e-12), v[2] / (v[3] + 1e-12)] for v in transformed]
        visible = sum(1 for v in transformed if abs(v[0]) <= 1.0 and abs(v[1]) <= 1.0)
        return {
            "transformed": [[round(c, 6) for c in v] for v in transformed],
            "visible_voxels": visible,
            "total_voxels": len(voxel_coords),
            "visibility_ratio": round(visible / max(1, len(voxel_coords)), 4)
        }

    def _compute_latency(self, voxel_count: int, refresh_rate_hz: float = 60.0) -> Dict[str, float]:
        frame_time_s = 1.0 / refresh_rate_hz
        compute_time_s = voxel_count * 1e-9
        render_time_s = voxel_count * 2e-9
        total_s = compute_time_s + render_time_s + frame_time_s
        pipeline_latency_ms = total_s * 1000
        return {
            "compute_latency_ms": round(compute_time_s * 1000, 6),
            "render_latency_ms": round(render_time_s * 1000, 6),
            "frame_interval_ms": round(frame_time_s * 1000, 2),
            "total_pipeline_latency_ms": round(pipeline_latency_ms, 2),
            "effective_fps": round(1.0 / max(total_s, 1e-12), 1)
        }

    def _beats_per_minute_for_wavelength(self, wavelength_nm: float) -> float:
        freq_hz = 3e8 / (wavelength_nm * 1e-9)
        return round(freq_hz * 60 * 1e-12, 2)

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "overview")

        if task_type == "project_hologram":
            return await self._project_hologram(task_data)
        elif task_type == "create_interface":
            return await self._create_spatial_interface(task_data)
        elif task_type == "manipulate_object":
            return await self._manipulate_3d_object(task_data)
        else:
            return await self._overview()

    async def _project_hologram(self, params: Dict[str, Any]) -> Dict[str, Any]:
        hologram_type = params.get("type", "data_viz")
        duration = params.get("duration", 300)
        wavelength_nm = params.get("wavelength_nm", 532.0)
        grating_period_nm = params.get("grating_period_nm", 1000.0)
        n_voxels = params.get("n_voxels", 1000)

        steering = self._beam_steering_angle(wavelength_nm, grating_period_nm)
        diffraction = self._fraunhofer_diffraction(slit_width_m=1e-6, wavelength_m=wavelength_nm * 1e-9, screen_dist_m=2.0, n_points=30)
        latency = self._compute_latency(n_voxels)
        persp = self._perspective_projection()

        hologram_id = f"holo_{int(time.time())}_{hash(hologram_type) % 10000:04d}"

        self.active_holograms[hologram_id] = {
            "id": hologram_id,
            "type": hologram_type,
            "start_time": time.time(),
            "duration": duration,
            "wavelength_nm": wavelength_nm,
            "diffraction_angle": steering["diffraction_angle_deg"],
            "active": True
        }
        self.display_active = True

        resolution_px = round(1920 * (1 + steering["angular_resolution_deg"] * 10))
        resolution = f"{resolution_px}p_equivalent"
        viewing_angle = round(steering["diffraction_angle_deg"] * 4, 1)
        update_rate = latency["effective_fps"]

        return {
            "success": True,
            "type": "hologram_projected",
            "hologram_id": hologram_id,
            "hologram_type": hologram_type,
            "duration_seconds": duration,
            "technical_specs": {
                "resolution": resolution,
                "viewing_angle": f"{viewing_angle}\u00b0",
                "update_rate": f"{update_rate}fps",
                "latency_ms": f"{latency['total_pipeline_latency_ms']:.0f}ms"
            },
            "interaction_methods": ["hand_gestures", "gaze_control", "voice_commands"],
            "auto_expires_in": duration,
            "power_consumption_watts": round(20 + abs(steering["diffraction_angle_deg"]) * 0.5, 1),
            "recommendations": ["Ensure clear viewing zone", "Maintain adequate lighting"],
            "_computation": {
                "beam_steering": steering,
                "fraunhofer_diffraction": {"angles_sampled": diffraction["angles_deg"][:5], "peak": diffraction["peak_intensity"]},
                "latency": latency,
                "projection_matrix_4x4": [[round(v, 4) for v in row] for row in persp]
            }
        }

    async def _create_spatial_interface(self, params: Dict[str, Any]) -> Dict[str, Any]:
        interface_type = params.get("type", "dashboard")
        wavelength_nm = params.get("wavelength_nm", 450.0)
        field_of_view_deg = params.get("field_of_view_deg", 90.0)
        n_voxels = params.get("n_voxels", 500)

        ortho = self._orthographic_projection()
        persp = self._perspective_projection(field_of_view_deg)
        steering = self._beam_steering_angle(wavelength_nm, 800.0)
        latency = self._compute_latency(n_voxels)

        interface_id = f"si_{int(time.time())}_{abs(hash(interface_type)) % 10000:04d}"

        user_pos = {"x": 0, "y": 0, "z": -1.5}
        origin_4d = self._transform_point([0.0, 0.0, -1.5, 1.0], persp)
        if abs(origin_4d[3]) > 1e-12:
            origin_3d = [origin_4d[0] / origin_4d[3], origin_4d[1] / origin_4d[3], origin_4d[2] / origin_4d[3]]
        else:
            origin_3d = [0.0, 0.0, -1.5]

        resolution_per_eye = f"{round(1440 * (1 + steering['angular_resolution_deg'] * 5))}p_per_eye"

        return {
            "success": True,
            "type": "spatial_interface_created",
            "interface_id": interface_id,
            "interface_type": interface_type,
            "components": self._get_interface_components(interface_type),
            "user_position": user_pos,
            "interaction_zone": {
                "shape": "hemisphere",
                "radius_meters": "2.0m",
                "height_range": "0.5-2.0m"
            },
            "technical_details": {
                "tracking": "6dof_inside_out",
                "latency_ms": f"{latency['total_pipeline_latency_ms']:.0f}ms",
                "resolution": resolution_per_eye,
                "refresh_rate": f"{latency['effective_fps']:.0f}Hz"
            },
            "interaction_modalities": ["hand_gestures", "gaze_selection", "voice_commands"],
            "setup_time_seconds": round(2 + latency["total_pipeline_latency_ms"] * 0.1, 1),
            "power_watts": round(30 + abs(steering["diffraction_angle_deg"]) * 0.8, 1),
            "recommendations": ["Calibrate user position", "Define interaction boundaries"],
            "_computation": {
                "projection_origin_ndc": [round(v, 4) for v in origin_3d],
                "beam_steering": steering,
                "latency": latency,
                "orthographic_matrix_4x4": [[round(v, 4) for v in row] for row in ortho]
            }
        }

    async def _manipulate_3d_object(self, params: Dict[str, Any]) -> Dict[str, Any]:
        obj_id = params.get("object_id", "target_object")
        action = params.get("action", "rotate")
        angle = params.get("angle_deg", 45.0)
        axis = params.get("axis", "y")
        distance = params.get("distance", 20.0)
        scale_factor = params.get("scale_factor", 1.0)

        rotation = self._rotation_matrix(angle, axis)
        if action == "rotate":
            detail = {"axis": axis, "degrees": round(angle, 1)}
        elif action == "translate":
            detail = {"axis": axis, "distance": round(distance, 1)}
        elif action == "scale":
            detail = {"factor": round(scale_factor, 2)}
        else:
            detail = {"action": action}

        latency = self._compute_latency(100)
        tracking_accuracy = round(0.5 + latency["render_latency_ms"] * 0.02, 1)

        return {
            "success": True,
            "type": "object_manipulated",
            "object_id": obj_id,
            "action": action,
            "details": detail,
            "timestamp": time.time(),
            "latency_ms": round(latency["total_pipeline_latency_ms"], 1),
            "tracking_accuracy": f"{tracking_accuracy:.1f}mm",
            "undo_available": True,
            "_computation": {
                "rotation_matrix_x3": [[round(v, 4) for v in row] for row in rotation],
                "latency": latency
            }
        }

    def _get_interface_components(self, interface_type: str) -> dict:
        components = {
            "dashboard": ["floating_charts", "3d_kpis", "interactive_models", "data_streams"],
            "workstation": ["virtual_monitors", "3d_tool_palette", "document_stack"],
            "control_panel": ["dials_switches", "lever_controls", "status_indicators"],
            "collaboration": ["shared_whiteboard", "3d_sketch_canvas", "avatar_representations"]
        }
        return components.get(interface_type, components["dashboard"])

    async def _overview(self) -> Dict[str, Any]:
        persp = self._perspective_projection()
        ortho = self._orthographic_projection()
        steering = self._beam_steering_angle(532.0, 1000.0)
        latency = self._compute_latency(1000)

        return {
            "success": True,
            "type": "holographic_display_overview",
            "description": "3D holographic display for spatial computing",
            "technologies": ["light_field", "volumetric_led", "ar_headsets"],
            "capabilities": ["true_3d_rendering", "spatial_interaction", "multi_user_collaboration"],
            "applications": ["data_visualization", "product_design", "education", "telepresence"],
            "requirements": ["modern_gpu", "tracking_system", "clear_viewing_space"],
            "_computation": {
                "projection_capabilities": {
                    "perspective_fov_60": {"matrix_4x4": [[round(v, 4) for v in row] for row in persp]},
                    "orthographic": {"matrix_4x4": [[round(v, 4) for v in row] for row in ortho]}
                },
                "beam_steering_532nm": steering,
                "latency_1k_voxels": latency
            }
        }
