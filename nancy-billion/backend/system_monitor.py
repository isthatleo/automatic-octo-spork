import psutil
import logging
import json
import time
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


class SystemMonitor:
    """Autonomous system monitoring and health checking capabilities."""
    
    def __init__(self):
        self.last_check = None
        self.alert_thresholds = {
            'cpu_percent': 80.0,
            'memory_percent': 85.0,
            'disk_percent': 90.0,
            'temperature': 80.0  # Celsius
        }
    
    def get_cpu_info(self) -> Dict[str, Any]:
        """Get CPU utilization and core information."""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()
            
            return {
                'usage_percent': cpu_percent,
                'core_count': cpu_count,
                'frequency_mhz': cpu_freq.current if cpu_freq else 0,
                'status': 'healthy' if cpu_percent < self.alert_thresholds['cpu_percent'] else 'warning'
            }
        except Exception as e:
            logger.error(f"Error getting CPU info: {e}")
            return {'error': str(e)}
    
    def get_memory_info(self) -> Dict[str, Any]:
        """Get memory utilization information."""
        try:
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            return {
                'total_gb': round(memory.total / (1024**3), 2),
                'available_gb': round(memory.available / (1024**3), 2),
                'used_gb': round(memory.used / (1024**3), 2),
                'usage_percent': memory.percent,
                'swap_total_gb': round(swap.total / (1024**3), 2),
                'swap_used_gb': round(swap.used / (1024**3), 2),
                'swap_usage_percent': swap.percent,
                'status': 'healthy' if memory.percent < self.alert_thresholds['memory_percent'] else 'warning'
            }
        except Exception as e:
            logger.error(f"Error getting memory info: {e}")
            return {'error': str(e)}
    
    def get_disk_info(self) -> Dict[str, Any]:
        """Get disk utilization information."""
        try:
            disk = psutil.disk_usage('/')
            
            return {
                'total_gb': round(disk.total / (1024**3), 2),
                'used_gb': round(disk.used / (1024**3), 2),
                'free_gb': round(disk.free / (1024**3), 2),
                'usage_percent': round((disk.used / disk.total) * 100, 2),
                'status': 'healthy' if (disk.used / disk.total) * 100 < self.alert_thresholds['disk_percent'] else 'warning'
            }
        except Exception as e:
            logger.error(f"Error getting disk info: {e}")
            return {'error': str(e)}
    
    def get_network_info(self) -> Dict[str, Any]:
        """Get network interface information."""
        try:
            net_io = psutil.net_io_counters()
            net_if_addrs = psutil.net_if_addrs()
            net_if_stats = psutil.net_if_stats()
            
            interfaces = {}
            for interface, addrs in net_if_addrs.items():
                if interface in net_if_stats:
                    stats = net_if_stats[interface]
                    interfaces[interface] = {
                        'is_up': stats.isup,
                        'speed_mbps': stats.speed,
                        'mtu': stats.mtu,
                        'addresses': [
                            {
                                'family': str(addr.family),
                                'address': addr.address,
                                'netmask': addr.netmask,
                                'broadcast': addr.broadcast
                            }
                            for addr in addrs
                        ]
                    }
            
            return {
                'bytes_sent': net_io.bytes_sent,
                'bytes_recv': net_io.bytes_recv,
                'packets_sent': net_io.packets_sent,
                'packets_recv': net_io.packets_recv,
                'interfaces': interfaces,
                'status': 'healthy'
            }
        except Exception as e:
            logger.error(f"Error getting network info: {e}")
            return {'error': str(e)}
    
    def get_temperature_info(self) -> Dict[str, Any]:
        """Get system temperature information (if available)."""
        try:
            temps = psutil.sensors_temperatures()
            if not temps:
                return {'status': 'unavailable', 'message': 'Temperature sensors not available'}
            
            # Get the highest temperature reading
            max_temp = 0
            temp_labels = []
            
            for name, entries in temps.items():
                for entry in entries:
                    if entry.current and entry.current > max_temp:
                        max_temp = entry.current
                        temp_labels.append(f"{name}: {entry.current}°C")
            
            return {
                'max_temperature_celsius': max_temp,
                'temperature_labels': temp_labels,
                'status': 'healthy' if max_temp < self.alert_thresholds['temperature'] else 'warning'
            }
        except Exception as e:
            logger.error(f"Error getting temperature info: {e}")
            return {'error': str(e)}
    
    def get_comprehensive_health(self) -> Dict[str, Any]:
        """Get comprehensive system health report."""
        self.last_check = datetime.now().isoformat()
        
        health_report = {
            'timestamp': self.last_check,
            'cpu': self.get_cpu_info(),
            'memory': self.get_memory_info(),
            'disk': self.get_disk_info(),
            'network': self.get_network_info(),
            'temperature': self.get_temperature_info(),
            'overall_status': 'healthy'
        }
        
        # Determine overall status
        statuses = [
            health_report['cpu'].get('status', 'unknown'),
            health_report['memory'].get('status', 'unknown'),
            health_report['disk'].get('status', 'unknown'),
            health_report['temperature'].get('status', 'unknown')
        ]
        
        if 'warning' in statuses:
            health_report['overall_status'] = 'warning'
        elif 'error' in statuses:
            health_report['overall_status'] = 'error'
        
        return health_report
    
    def should_trigger_alert(self, health_report: Dict[str, Any]) -> List[str]:
        """Determine if any alerts should be triggered based on health report."""
        alerts = []
        
        if health_report['cpu'].get('status') == 'warning':
            alerts.append(f"High CPU usage: {health_report['cpu'].get('usage_percent', 0)}%")
        
        if health_report['memory'].get('status') == 'warning':
            alerts.append(f"High memory usage: {health_report['memory'].get('usage_percent', 0)}%")
        
        if health_report['disk'].get('status') == 'warning':
            alerts.append(f"High disk usage: {health_report['disk'].get('usage_percent', 0)}%")
        
        if health_report['temperature'].get('status') == 'warning':
            alerts.append(f"High temperature: {health_report['temperature'].get('max_temperature_celsius', 0)}°C")
        
        return alerts
    
    def auto_optimize_resources(self) -> Dict[str, Any]:
        """Automatically optimize system resources based on current usage."""
        health = self.get_comprehensive_health()
        optimizations = []
        
        # CPU optimization suggestions
        if health['cpu'].get('usage_percent', 0) > 70:
            optimizations.append("Consider reducing CPU-intensive processes")
        
        # Memory optimization suggestions
        if health['memory'].get('usage_percent', 0) > 75:
            optimizations.append("Consider clearing cache or reducing memory-intensive applications")
        
        # Disk optimization suggestions
        if health['disk'].get('usage_percent', 0) > 85:
            optimizations.append("Consider cleaning up temporary files or expanding storage")
        
        return {
            'timestamp': datetime.now().isoformat(),
            'optimizations_suggested': optimizations,
            'health_status': health['overall_status']
        }


# Tool functions for agent integration
def get_system_health() -> str:
    """Get current system health status."""
    monitor = SystemMonitor()
    health = monitor.get_comprehensive_health()
    return json.dumps(health, indent=2)


def get_system_alerts() -> str:
    """Get current system alerts."""
    monitor = SystemMonitor()
    health = monitor.get_comprehensive_health()
    alerts = monitor.should_trigger_alert(health)
    return json.dumps({
        'timestamp': health['timestamp'],
        'alerts': alerts,
        'alert_count': len(alerts)
    }, indent=2)


def auto_optimize_system() -> str:
    """Trigger automatic system optimization."""
    monitor = SystemMonitor()
    result = monitor.auto_optimize_resources()
    return json.dumps(result, indent=2)


def predict_maintenance_needs() -> str:
    """Predict maintenance needs based on system trends."""
    # This would typically use historical data and ML models
    # For now, return basic predictive insights
    monitor = SystemMonitor()
    health = monitor.get_comprehensive_health()
    
    predictions = []
    
    # Simple trend-based predictions
    if health['cpu'].get('usage_percent', 0) > 60:
        predictions.append("CPU usage trending high - consider process optimization")
    
    if health['memory'].get('usage_percent', 0) > 70:
        predictions.append("Memory usage elevated - monitor for potential leaks")
    
    if health['disk'].get('usage_percent', 0) > 75:
        predictions.append("Disk usage increasing - plan for cleanup or expansion")
    
    return json.dumps({
        'timestamp': datetime.now().isoformat(),
        'predictions': predictions,
        'confidence': 'medium'  # Would be higher with ML models
    }, indent=2)


def security_hardening_execute() -> str:
    """Perform security hardening checks and recommendations."""
    logger.info("Running security hardening analysis")
    try:
        import subprocess
        import os
        from datetime import datetime
        
        security_checks = []
        recommendations = []
        
        # Check for Windows Defender (if on Windows)
        if os.name == 'nt':
            try:
                # Check if Windows Defender is running
                result = subprocess.run(['sc', 'query', 'WinDefend'], capture_output=True, text=True, timeout=10)
                if 'RUNNING' in result.stdout:
                    security_checks.append("Windows Defender: ACTIVE")
                else:
                    security_checks.append("Windows Defender: INACTIVE")
                    recommendations.append("Consider enabling Windows Defender for real-time protection")
            except subprocess.TimeoutExpired:
                security_checks.append("Windows Defender: STATUS UNKNOWN (timeout)")
            except Exception:
                security_checks.append("Windows Defender: UNABLE TO CHECK")
        
        # Check firewall status
        try:
            if os.name == 'nt':
                result = subprocess.run(['netsh', 'advfirewall', 'show', 'allprofiles', 'state'], 
                                      capture_output=True, text=True, timeout=10)
                if 'State ON' in result.stdout:
                    security_checks.append("Windows Firewall: ACTIVE")
                else:
                    security_checks.append("Windows Firewall: INACTIVE")
                    recommendations.append("Consider enabling Windows Firewall")
            else:
                # For Linux/macOS, we could check ufw, iptables, etc.
                security_checks.append("Firewall: CHECK REQUIRED (platform-specific)")
        except Exception:
            security_checks.append("Firewall: UNABLE TO CHECK")
        
        # Check for recent system updates
        security_checks.append("System Updates: CHECK MANUALLY (recommended regularly)")
        recommendations.append("Ensure operating system and security software are up to date")
        
        # Check for suspicious network connections (basic)
        try:
            import psutil
            network_connections = psutil.net_connections()
            # Just report count for now - detailed analysis would be more complex
            security_checks.append(f"Network Connections: {len(network_connections)} active")
        except ImportError:
            security_checks.append("Network Connections: psutil not available for detailed analysis")
        except Exception:
            security_checks.append("Network Connections: UNABLE TO CHECK")
        
        # Generate security report
        security_report = {
            "timestamp": datetime.now().isoformat(),
            "security_score": "NEEDS_ASSESSMENT",  # Would be calculated based on checks in a full implementation
            "checks_performed": security_checks,
            "recommendations": recommendations,
            "next_steps": [
                "Review and implement high-priority recommendations",
                "Schedule regular security scans",
                "Consider implementing intrusion detection systems",
                "Ensure regular backups are maintained"
            ]
        }
        
        return json.dumps(security_report, indent=2)
    except Exception as e:
        logger.error(f"Error in security hardening: {e}")
        return json.dumps({
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }, indent=2)


if __name__ == "__main__":
    # Test the system monitor
    monitor = SystemMonitor()
    print("System Health:")
    print(json.dumps(monitor.get_comprehensive_health(), indent=2))
    print("\nAlerts:")
    print(json.dumps(monitor.should_trigger_alert(monitor.get_comprehensive_health()), indent=2))