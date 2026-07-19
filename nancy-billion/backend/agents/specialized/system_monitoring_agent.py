"""
System Monitoring Agent for Nancy Billion Backend
Real system monitoring using psutil - no simulated data.
"""
from .base_specialized_agent import SpecializedAgent
from ..real_compute import now_utc
from typing import Dict, Any
import psutil
import time
import os
from datetime import datetime, timezone


class SystemMonitoringAgent(SpecializedAgent):
    """Specialized agent for system monitoring - real psutil data"""

    def __init__(self, settings):
        super().__init__(settings, "System Monitoring Agent", "system-monitoring")
        self.capabilities.update({
            "description": "System monitoring agent using real psutil metrics",
            "confidence": 0.98,
            "specializations": ["performance-tracking", "health-diagnostics", "resource-optimization"]
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "overview")
        if task_type == "health-check":
            return await self._perform_health_check(task_data)
        elif task_type == "performance-analysis":
            return await self._analyze_performance(task_data)
        elif task_type == "resource-usage":
            return await self._analyze_resource_usage(task_data)
        else:
            return await self._general_monitoring_overview(task_data)

    async def _perform_health_check(self, params: Dict[str, Any]) -> Dict[str, Any]:
        cpu_percent = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        disk_percent = (disk.used / disk.total) * 100 if disk.total > 0 else 0

        def get_status(value, good, warn):
            return "healthy" if value <= good else "warning" if value <= warn else "critical"

        cpu_status = get_status(cpu_percent, 50, 80)
        memory_status = get_status(memory.percent, 60, 85)
        disk_status = get_status(disk_percent, 70, 90)
        statuses = [cpu_status, memory_status, disk_status]
        overall_status = "critical" if "critical" in statuses else "warning" if "warning" in statuses else "healthy"

        cpu_count = psutil.cpu_count()
        boot_time_dt = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc) if hasattr(psutil, 'boot_time') else now_utc()
        uptime_seconds = time.time() - psutil.boot_time()
        uptime_days = uptime_seconds / 86400

        return {
            "success": True, "task_type": "health-check", "timestamp": time.time(),
            "uptime_days": round(uptime_days, 2),
            "components": {
                "cpu": {"usage_percent": round(cpu_percent, 1), "status": cpu_status, "cores": cpu_count, "logical_cores": psutil.cpu_count(logical=True)},
                "memory": {"usage_percent": round(memory.percent, 1), "status": memory_status, "total_gb": round(memory.total / (1024**3), 2), "available_gb": round(memory.available / (1024**3), 2)},
                "disk": {"usage_percent": round(disk_percent, 1), "status": disk_status, "total_gb": round(disk.total / (1024**3), 2), "free_gb": round(disk.free / (1024**3), 2)}
            },
            "overall_status": overall_status,
            "health_score": round(max(0, 100 - cpu_percent + 100 - memory.percent + 100 - disk_percent) / 3, 1),
            "recommendations": self._generate_health_recommendations(cpu_status, memory_status, disk_status)
        }

    async def _analyze_performance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        duration = min(params.get("duration", 10), 30)
        interval = params.get("interval", 1)

        cpu_samples = []
        memory_samples = []
        end_time = time.time() + duration
        cpu_percent = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory()

        while time.time() < end_time:
            cpu_samples.append(psutil.cpu_percent(interval=interval))
            memory_samples.append(psutil.virtual_memory().percent)

        if cpu_samples:
            avg_cpu = sum(cpu_samples) / len(cpu_samples)
            max_cpu = max(cpu_samples)
            avg_memory = sum(memory_samples) / len(memory_samples)
            max_memory = max(memory_samples)
            cpu_trend = cpu_samples[-1] - cpu_samples[0]
        else:
            avg_cpu = max_cpu = avg_memory = max_memory = cpu_trend = 0

        return {
            "success": True, "task_type": "performance-analysis",
            "monitoring_period": {"duration_seconds": duration, "sample_count": len(cpu_samples)},
            "performance_metrics": {
                "cpu": {"average_usage_percent": round(avg_cpu, 1), "maximum_usage_percent": round(max_cpu, 1), "trend": "increasing" if cpu_trend > 5 else "decreasing" if cpu_trend < -5 else "stable"},
                "memory": {"average_usage_percent": round(avg_memory, 1), "maximum_usage_percent": round(max_memory, 1)}
            },
            "recommendations": self._generate_performance_recommendations(avg_cpu, avg_memory)
        }

    async def _analyze_resource_usage(self, params: Dict[str, Any]) -> Dict[str, Any]:
        processes = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                pinfo = proc.info
                if pinfo["cpu_percent"] is not None and pinfo["memory_percent"] is not None:
                    processes.append(pinfo)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        processes.sort(key=lambda p: p["cpu_percent"], reverse=True)
        top_cpu = processes[:5]
        processes.sort(key=lambda p: p["memory_percent"], reverse=True)
        top_memory = processes[:5]

        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        partitions_data = []
        for p in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(p.mountpoint)
                partitions_data.append({
                    "device": p.device, "mountpoint": p.mountpoint,
                    "fstype": p.fstype,
                    "total_gb": round(usage.total / (1024**3), 2),
                    "used_gb": round(usage.used / (1024**3), 2),
                    "free_gb": round(usage.free / (1024**3), 2),
                    "usage_percent": round((usage.used / usage.total) * 100, 1)
                })
            except (PermissionError, OSError):
                pass

        net = psutil.net_io_counters()
        load_avg = getattr(psutil, "getloadavg", lambda: (0, 0, 0))()

        return {
            "success": True, "task_type": "resource-usage-analysis", "timestamp": time.time(),
            "process_analysis": {"total_processes": len(processes), "top_cpu_processes": top_cpu, "top_memory_processes": top_memory},
            "cpu": {"physical_cores": psutil.cpu_count(logical=False), "logical_cores": psutil.cpu_count(logical=True), "load_average": {"1min": round(load_avg[0], 2), "5min": round(load_avg[1], 2), "15min": round(load_avg[2], 2)}, "current_usage_percent": psutil.cpu_percent(interval=0.1)},
            "memory": {"virtual": {"total_gb": round(mem.total / (1024**3), 2), "available_gb": round(mem.available / (1024**3), 2), "used_gb": round(mem.used / (1024**3), 2), "percent": mem.percent}, "swap": {"total_gb": round(swap.total / (1024**3), 2), "used_gb": round(swap.used / (1024**3), 2), "percent": swap.percent}},
            "disk": {"partitions": partitions_data},
            "network": {"bytes_sent_mb": round(net.bytes_sent / (1024**2), 2), "bytes_recv_mb": round(net.bytes_recv / (1024**2), 2), "packets_sent": net.packets_sent, "packets_recv": net.packets_recv},
            "efficiency": {"cpu_efficiency_percent": round(max(0, 100 - psutil.cpu_percent(interval=0)), 1), "memory_efficiency_percent": round(max(0, 100 - mem.percent), 1)},
            "recommendations": ["Monitor resource trends over time", "Identify resource intensive processes", "Consider resource optimization opportunities"]
        }

    def _generate_health_recommendations(self, cpu_status, memory_status, disk_status):
        recs = []
        if cpu_status in ("warning", "critical"):
            recs.append("investigate_high_cpu_usage")
        if memory_status in ("warning", "critical"):
            recs.append("investigate_high_memory_usage")
        if disk_status in ("warning", "critical"):
            recs.append("investigate_low_disk_space_or_cleanup")
        if not recs:
            recs.append("maintain_current_health_practices")
        return recs

    def _generate_performance_recommendations(self, avg_cpu, avg_memory):
        recs = []
        if avg_cpu > 70:
            recs.append("consider_cpu_optimization_or_scaling")
        if avg_memory > 70:
            recs.append("consider_memory_optimization")
        if not recs:
            recs.append("performance_within_acceptable_ranges")
        return recs

    async def _general_monitoring_overview(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = params.get("query", "general system monitoring question")
        answer = await self._llm_answer(query)
        return {
            "success": True, "task_type": "general-monitoring-overview",
            "query": query,
            **({"response": answer} if answer else {}),
            "monitoring_capabilities": [
                {"capability": "real_time_monitoring", "metrics": ["cpu", "memory", "disk", "network", "processes"], "frequency": "configurable"},
                {"capability": "health_checks", "types": ["basic", "detailed", "comprehensive"]}
            ],
            "key_metrics": [
                {"metric": "cpu_utilization", "unit": "percent", "healthy_range": "0-70%"},
                {"metric": "memory_utilization", "unit": "percent", "healthy_range": "0-70%"},
                {"metric": "disk_utilization", "unit": "percent", "healthy_range": "0-70%"},
                {"metric": "load_average", "unit": "per_core", "healthy_range": "< 1.0 per core"}
            ],
            "recommendations": ["Implement regular health checks", "Monitor key performance indicators", "Establish baselines for anomaly detection"]
        }
