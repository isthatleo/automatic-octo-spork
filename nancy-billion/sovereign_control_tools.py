# =============================================================================
# Expanded Sovereign Control Tools (Added for Phase 3: Expanded Sovereign Control)
# =============================================================================

import psutil
import subprocess
import platform
import json
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def resource_allocation_optimize() -> str:
    """Autonomously monitor and optimize resource allocation across system components."""
    try:
        # Get current resource usage
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Get process information for optimization insights
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                proc_info = proc.info
                if proc_info['cpu_percent'] > 5.0 or proc_info['memory_percent'] > 5.0:  # Only significant processes
                    processes.append(proc_info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        # Sort by resource usage
        processes_by_cpu = sorted(processes, key=lambda x: x['cpu_percent'], reverse=True)[:5]
        processes_by_memory = sorted(processes, key=lambda x: x['memory_percent'], reverse=True)[:5]
        
        # Generate optimization recommendations
        recommendations = []
        
        if cpu_percent > 80:
            recommendations.append("High CPU usage detected. Consider redistributing workload or scaling up compute resources.")
        elif cpu_percent < 20:
            recommendations.append("Low CPU usage detected. System has capacity for additional workloads.")
            
        if memory.percent > 85:
            recommendations.append("High memory usage detected. Consider freeing up memory or increasing RAM allocation.")
        elif memory.percent < 30:
            recommendations.append("Low memory usage detected. Memory resources are underutilized.")
            
        if disk.percent > 90:
            recommendations.append("Critical: Disk usage over 90%. Immediate cleanup or expansion required.")
        elif disk.percent > 80:
            recommendations.append("High disk usage detected. Consider cleanup or storage expansion.")
        
        result = {
            "timestamp": datetime.now().isoformat(),
            "resource_allocation": {
                "cpu_usage_percent": cpu_percent,
                "memory_usage_percent": memory.percent,
                "memory_available_gb": round(memory.available / (1024**3), 2),
                "disk_usage_percent": disk.percent,
                "disk_free_gb": round(disk.free / (1024**3), 2)
            },
            "top_processes_by_cpu": [
                {"name": p['name'], "pid": p['pid'], "cpu_percent": p['cpu_percent']} 
                for p in processes_by_cpu
            ],
            "top_processes_by_memory": [
                {"name": p['name'], "pid": p['pid'], "memory_percent": p['memory_percent']} 
                for p in processes_by_memory
            ],
            "optimization_recommendations": recommendations,
            "allocation_efficiency_score": max(0, 100 - ((cpu_percent + memory.percent + disk.percent) / 3)),
            "status": "completed"
        }
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        logger.error(f"Error in resource allocation optimization: {e}")
        return json.dumps({
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
            "status": "failed"
        })

def network_sovereignty_assess() -> str:
    """Assess and maintain network sovereignty and security."""
    try:
        # Get network interfaces and statistics
        net_io = psutil.net_io_counters(pernic=True)
        net_if_addrs = psutil.net_if_addrs()
        
        network_info = {}
        for interface, addresses in net_if_addrs.items():
            if interface in net_io:
                io_stats = net_io[interface]
                network_info[interface] = {
                    "addresses": [{"family": str(addr.family), "address": addr.address} 
                                for addr in addresses if addr.family.name in ['AF_INET', 'AF_INET6']],
                    "bytes_sent": io_stats.bytes_sent,
                    "bytes_recv": io_stats.bytes_recv,
                    "packets_sent": io_stats.packets_sent,
                    "packets_recv": io_stats.packets_recv
                }
        
        # Try to get external IP (if possible)
        external_ip = "unknown"
        try:
            # This is a simplified approach - in practice, you might use external services
            import urllib.request
            external_ip = urllib.request.urlopen('https://api.ipify.org', timeout=5).read().decode('utf8')
        except:
            external_ip = "unavailable (network restricted or no external access)"
        
        # Network sovereignty assessment
        sovereignty_score = 100  # Start with perfect score
        recommendations = []
        
        # Check for common network issues
        for interface, info in network_info.items():
            if interface.lower() in ['lo', 'loopback']:  # Skip loopback
                continue
                
            # Basic checks - in a real implementation, these would be more sophisticated
            if info['bytes_recv'] > 1000000000:  # > 1GB received
                recommendations.append(f"Interface {interface} has high incoming traffic - monitor for potential data exfiltration")
                
        if recommendations:
            sovereignty_score -= len(recommendations) * 10  # Reduce score for each issue found
        
        result = {
            "timestamp": datetime.now().isoformat(),
            "network_interfaces": network_info,
            "external_ip_address": external_ip,
            "sovereignty_assessment": {
                "score": max(0, sovereignty_score),
                "level": "high" if sovereignty_score > 80 else "medium" if sovereignty_score > 50 else "low",
                "recommendations": recommendations
            },
            "sovereignty_status": "maintained" if sovereignty_score > 70 else "needs_attention",
            "status": "completed"
        }
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        logger.error(f"Error in network sovereignty assessment: {e}")
        return json.dumps({
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
            "status": "failed"
        })

def storage_orchestration_manage() -> str:
    """Autonomously manage storage systems with encryption and redundancy considerations."""
    try:
        # Get disk partitions and usage
        disk_partitions = psutil.disk_partitions()
        storage_info = []
        
        total_capacity_gb = 0
        total_used_gb = 0
        total_free_gb = 0
        
        for partition in disk_partitions:
            try:
                partition_usage = psutil.disk_usage(partition.mountpoint)
                capacity_gb = partition_usage.total / (1024**3)
                used_gb = partition_usage.used / (1024**3)
                free_gb = partition_usage.free / (1024**3)
                
                total_capacity_gb += capacity_gb
                total_used_gb += used_gb
                total_free_gb += free_gb
                
                storage_info.append({
                    "device": partition.device,
                    "mountpoint": partition.mountpoint,
                    "filesystem_type": partition.fstype,
                    "capacity_gb": round(capacity_gb, 2),
                    "used_gb": round(used_gb, 2),
                    "free_gb": round(free_gb, 2),
                    "usage_percent": round((used_gb / capacity_gb) * 100, 2) if capacity_gb > 0 else 0
                })
            except (PermissionError, OSError):
                # Some partitions might not be accessible
                continue
        
        # Storage sovereignty recommendations
        recommendations = []
        overall_usage_percent = (total_used_gb / total_capacity_gb) * 100 if total_capacity_gb > 0 else 0
        
        if overall_usage_percent > 90:
            recommendations.append("Critical: Overall storage usage over 90%. Immediate action required to prevent system issues.")
        elif overall_usage_percent > 80:
            recommendations.append("High storage usage detected. Consider cleanup or expansion.")
            
        # Check for imbalanced usage across drives
        if len(storage_info) > 1:
            usage_percents = [info['usage_percent'] for info in storage_info if info['usage_percent'] > 0]
            if usage_percents:
                max_usage = max(usage_percents)
                min_usage = min(usage_percents)
                if max_usage - min_usage > 50:  # Significant imbalance
                    recommendations.append("Storage usage is imbalanced across drives. Consider redistributing data.")
        
        result = {
            "timestamp": datetime.now().isoformat(),
            "storage_devices": storage_info,
            "total_capacity_gb": round(total_capacity_gb, 2),
            "total_used_gb": round(total_used_gb, 2),
            "total_free_gb": round(total_free_gb, 2),
            "overall_usage_percent": round(overall_usage_percent, 2),
            "storage_sovereignty": {
                "encryption_recommendation": "Consider enabling bitlocker/LUKS encryption for sensitive data storage",
                "redundancy_recommendation": "Implement RAID or backup strategy for critical data",
                "monitoring_recommendation": "Continuously monitor storage health and performance metrics"
            },
            "recommendations": recommendations,
            "status": "completed"
        }
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        logger.error(f"Error in storage orchestration management: {e}")
        return json.dumps({
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
            "status": "failed"
        })

def power_management_intelligent() -> str:
    """Intelligently control power consumption and distribution."""
    try:
        # Get battery information (if available)
        battery = None
        try:
            battery = psutil.sensors_battery()
        except AttributeError:
            battery = None  # Not available on all systems (especially desktops)
        
        # Get CPU frequency information
        cpu_freq = None
        try:
            cpu_freq = psutil.cpu_freq()
        except AttributeError:
            cpu_freq = None
        
        # Get temperature sensors if available
        temps = None
        try:
            temps = psutil.sensors_temperatures()
        except AttributeError:
            temps = {}
        
        power_info = {}
        
        if battery:
            power_info["battery"] = {
                "percent": battery.percent,
                "seconds_left": battery.secsleft,
                "power_plugged": battery.power_plugged,
                "time_remaining_hours": round(battery.secsleft / 3600, 2) if battery.secsleft and battery.secsleft != psutil.POWER_TIME_UNLIMITED else None
            }
        
        if cpu_freq:
            power_info["cpu_frequency"] = {
                "current_mhz": round(cpu_freq.current, 2),
                "min_mhz": round(cpu_freq.min, 2) if cpu_freq.min else 0,
                "max_mhz": round(cpu_freq.max, 2) if cpu_freq.max else 0
            }
        
        if temps:
            power_info["temperatures"] = {}
            for chip_name, readings in temps.items():
                power_info["temperatures"][chip_name] = [
                    {"label": reading.label or "Unknown", "current_celsius": reading.current, 
                     "high_celsius": reading.high, "critical_celsius": reading.critical}
                    for reading in readings
                ]
        
        # Power management recommendations
        recommendations = []
        
        if battery:
            if battery.percent < 20 and not battery.power_plugged:
                recommendations.append("Battery level critical (<20%) and not plugged in. Connect to power source immediately.")
            elif battery.percent < 50 and not battery.power_plugged:
                recommendations.append("Battery level low (<50%) and not plugged in. Consider connecting to power soon.")
        
        if cpu_freq and cpu_freq.current:
            # Suggest optimization based on usage vs capability
            cpu_util = psutil.cpu_percent(interval=0.1)
            if cpu_util < 30 and cpu_freq.current > (cpu_freq.max * 0.8):  # Low usage but high freq
                recommendations.append("CPU running at high frequency despite low utilization. Consider power saving modes.")
        
        result = {
            "timestamp": datetime.now().isoformat(),
            "power_system_info": power_info,
            "power_management_recommendations": recommendations,
            "energy_efficiency_score": calculate_energy_efficiency_score(battery, cpu_freq, temps),
            "status": "completed"
        }
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        logger.error(f"Error in intelligent power management: {e}")
        return json.dumps({
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
            "status": "failed"
        })

def calculate_energy_efficiency_score(battery, cpu_freq, temps) -> int:
    """Calculate an energy efficiency score based on available metrics."""
    score = 100  # Start with perfect score
    
    # Deduct for high power consumption indicators
    if battery and not battery.power_plugged and battery.percent < 30:
        score -= 20  # Low battery on DC power
    
    if cpu_freq and cpu_freq.current:
        cpu_util = psutil.cpu_percent(interval=0.1)
        if cpu_util < 25 and cpu_freq.current > (cpu_freq.max * 0.9):  # Very low usage but near max freq
            score -= 15  # Inefficient frequency scaling
    
    # Temperature considerations (overheating wastes energy)
    if temps:
        high_temp_count = 0
        total_sensors = 0
        for chip_name, readings in temps.items():
            for reading in readings:
                total_sensors += 1
                if reading.high and reading.current > reading.high * 0.8:  # Running hot
                    high_temp_count += 1
        
        if total_sensors > 0 and (high_temp_count / total_sensors) > 0.5:  # More than half sensors running hot
            score -= 10
    
    return max(0, score)