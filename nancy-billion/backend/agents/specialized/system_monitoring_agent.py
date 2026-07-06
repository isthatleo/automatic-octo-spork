"""
System Monitoring Agent for Nancy Billion Backend - Short Version
Handles performance tracking, health diagnostics, and resource optimization
"""
from .base_specialized_agent import SpecializedAgent
import asyncio
import random
import psutil
from typing import Dict, Any
import time

class SystemMonitoringAgent(SpecializedAgent):
    """Specialized agent for system monitoring"""
    
    def __init__(self, settings):
        super().__init__(settings, "System Monitoring Agent", "system-monitoring")
        self.capabilities.update({
            "description": "Advanced system monitoring agent for performance tracking and health diagnostics",
            "confidence": 0.90,
            "specializations": [
                "performance-tracking",
                "health-diagnostics", 
                "resource-optimization"
            ],
            "tools": [
                "psutil",
                "built-in-system-tools"
            ]
        })
    
    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process system monitoring tasks"""
        await asyncio.sleep(1)
        
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
        """Perform system health check"""
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        def get_status(value, thresholds):
            if value <= thresholds['good']: return 'healthy'
            elif value <= thresholds['warning']: return 'warning'
            else: return 'critical'
        
        cpu_status = get_status(cpu_percent, {'good': 50, 'warning': 80})
        memory_status = get_status(memory.percent, {'good': 60, 'warning': 85})
        disk_status = get_status((disk.used / disk.total) * 100, {'good': 70, 'warning': 90})
        
        statuses = [cpu_status, memory_status, disk_status]
        overall_status = 'critical' if 'critical' in statuses else 'warning' if 'warning' in statuses else 'healthy'
        
        return {
            "success": True,
            "task_type": "health-check",
            "timestamp": time.time(),
            "components": {
                "cpu": {
                    "usage_percent": f"{cpu_percent:.1f}%",
                    "status": cpu_status,
                    "cores": psutil.cpu_count()
                },
                "memory": {
                    "usage_percent": f"{memory.percent:.1f}%",
                    "status": memory_status,
                    "total_gb": f"{memory.total / (1024**3):.2f}",
                    "available_gb": f"{memory.available / (1024**3):.2f}"
                },
                "disk": {
                    "usage_percent": f"{(disk.used / disk.total) * 100:.1f}%",
                    "status": disk_status,
                    "total_gb": f"{disk.total / (1024**3):.2f}",
                    "free_gb": f"{disk.free / (1024**3):.2f}"
                }
            },
            "overall_status": overall_status,
            "health_score": round((max(0, 100-cpu_percent) + max(0, 100-memory.percent) + max(0, 100-(disk.used/disk.total)*100)) / 3, 1),
            "recommendations": self._generate_health_recommendations(cpu_status, memory_status, disk_status)
        }
    
    async def _analyze_performance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze system performance"""
        duration = min(params.get("duration", 30), 30)  # Max 30 seconds
        
        # Collect samples
        samples = []
        end_time = time.time() + duration
        
        while time.time() < end_time:
            samples.append({
                cpu: psutil.cpu_percent(interval=None),
                memory: psutil.virtual_memory().percent,
                timestamp: time.time()
            })
            await asyncio.sleep(1)
        
        if samples:
            avg_cpu = sum(s[cpu] for s in samples) / len(samples)
            avg_memory = sum(s[memory] for s in samples) / len(samples)
            max_cpu = max(s[cpu] for s in samples)
            max_memory = max(s[memory] for s in samples)
        else:
            avg_cpu = avg_memory = max_cpu = max_memory = 0
        
        return {
            "success": True,
            "task_type": "performance-analysis",
            "monitoring_period": {
                "duration_seconds": len(samples),
                "sample_count": len(samples)
            },
            "performance_metrics": {
                "cpu": {
                    "average_usage_percent": f"{avg_cpu:.1f}%",
                    "maximum_usage_percent": f"{max_cpu:.1f}%",
                    "trend": "increasing" if len(samples) > 1 and samples[-1][cpu] > samples[0][cpu] else "stable"
                },
                "memory": {
                    "average_usage_percent": f"{avg_memory:.1f}%",
                    "maximum_usage_percent": f"{max_memory:.1f}%",
                    "trend": "increasing" if len(samples) > 1 and samples[-1][memory] > samples[0][memory] else "stable"
                }
            },
            "recommendations": self._generate_performance_recommendations(avg_cpu, avg_memory)
        }
    
    async def _analyze_resource_usage(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze resource usage"""
        return {
            "success": True,
            "task_type": "resource-usage-analysis",
            "timestamp": time.time(),
            "process_analysis": {
                "total_processes": len(psutil.pids()),
                "top_cpu_processes": self._get_top_processes(cpu, 3),
                "top_memory_processes": self._get_top_processes(memory, 3)
            },
            "memory_breakdown": {
                "virtual_memory": dict(psutil.virtual_memory()._asdict()),
                "swap_memory": dict(psutil.swap_memory()._asdict()) if hasattr(psutil, swap_memory) else {}
            },
            "disk_analysis": {
                "partitions": [p._asdict() for p in psutil.disk_partitions()],
                "usage": [{
                    device: p.device,
                    mountpoint: p.mountpoint,
                    usage_percent: f"{(psutil.disk_usage(p.mountpoint).used / psutil.disk_usage(p.mountpoint).total) * 100:.1f}"
                } for p in psutil.disk_partitions() if os.access(p.mountpoint, os.R_OK)]
            },
            "resource_efficiency": {
                "cpu_efficiency": f"{max(0, 100 - psutil.cpu_percent()):.1f}%",
                "memory_efficiency": f"{max(0, 100 - psutil.virtual_memory().percent):.1f}%"
            },
            "recommendations": [
                "monitor_resource_trends_over_time",
                "identify_resource_intensive_processes",
                "consider_resource_optimization_opportunities"
            ]
        }
    
    def _get_top_processes(self, sort_by, count):
        """Get top processes by CPU or memory usage"""
        try:
            processes = []
            for proc in psutil.process_iter([pid, name, cpu_percent, memory_percent]):
                try:
                    pinfo = proc.info
                    if pinfo[cpu_percent] is not None and pinfo[memory_percent] is not None:
                        if sort_by == cpu:
                            processes.append((pinfo[pid], pinfo[name], pinfo[cpu_percent], pinfo[memory_percent]))
                        else:
                            processes.append((pinfo[pid], pinfo[name], pinfo[memory_percent], pinfo[cpu_percent]))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            processes.sort(key=lambda x: x[2 if sort_by == cpu else 1], reverse=True)
            return [{pid: p[0], name: p[1], cpu_percent: p[2], memory_percent: p[3]} for p in processes[:count]]
        except Exception:
            return []
    
    def _generate_health_recommendations(self, cpu_status, memory_status, disk_status):
        """Generate health-based recommendations"""
        recommendations = []
        if cpu_status in [warning, critical]:
            recommendations.append("investigate_high_cpu_usage")
        if memory_status in [warning, critical]:
            recommendations.append("investigate_high_memory_usage")
        if disk_status in [warning, critical]:
            recommendations.append("investigate_low_disk_space")
        if not recommendations:
            recommendations.append("maintain_current_health_practices")
        return recommendations
    
    def _generate_performance_recommendations(self, avg_cpu, avg_memory):
        """Generate performance-based recommendations"""
        recommendations = []
        if avg_cpu > 70:
            recommendations.append("consider_cpu_optimization")
        if avg_memory > 70:
            recommendations.append("consider_memory_optimization")
        if not recommendations:
            recommendations.append("performance_within_acceptable_ranges")
        return recommendations
    
    async def _general_monitoring_overview(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Provide general monitoring overview"""
        return {
            "success": True,
            "task_type": "general-monitoring-overview",
            "query": params.get("query", "general system monitoring question"),
            "monitoring_capabilities": [
                {
                    "capability": "real_time_monitoring",
                    "metrics": ["cpu", "memory", "disk"],
                    "frequency": "continuous"
                },
                {
                    "capability": "health_checks",
                    "types": ["basic", "detailed", "comprehensive"],
                    "frequency": "configurable"
                }
            ],
            "key_metrics": [
                {
                    "metric": "cpu_utilization",
                    "unit": "percent",
                    "healthy_range": "0-70%"
                },
                {
                    "metric": "memory_utilization", 
                    "unit": "percent",
                    "healthy_range": "0-70%"
                },
                {
                    "metric": "disk_utilization",
                    "unit": "percent",
                    "healthy_range": "0-70%"
                }
            ],
            "recommendations": [
                "implement_regular_health_checks",
                "monitor_key_performance_indicators",
                "establish_baselines_for_anomaly_detection"
            ]
        }

