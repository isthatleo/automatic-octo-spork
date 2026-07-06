import subprocess
import platform
import psutil
import json
from datetime import datetime
from pathlib import Path
import sys

class SystemDiagnostics:
    def __init__(self):
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'system_info': {},
            'hardware': {},
            'software': {},
            'performance': {},
            'recommendations': []
        }
    
    def get_system_info(self):
        """Collect basic system information"""
        self.results['system_info'] = {
            'platform': platform.platform(),
            'system': platform.system(),
            'release': platform.release(),
            'version': platform.version(),
            'machine': platform.machine(),
            'processor': platform.processor(),
            'python_version': sys.version,
            'hostname': platform.node()
        }
    
    def get_hardware_info(self):
        """Collect hardware information"""
        # CPU info
        self.results['hardware']['cpu'] = {
            'physical_cores': psutil.cpu_count(logical=False),
            'total_cores': psutil.cpu_count(logical=True),
            'max_frequency': psutil.cpu_freq().max if psutil.cpu_freq() else None,
            'current_frequency': psutil.cpu_freq().current if psutil.cpu_freq() else None
        }
        
        # Memory info
        memory = psutil.virtual_memory()
        self.results['hardware']['memory'] = {
            'total_gb': round(memory.total / (1024**3), 2),
            'available_gb': round(memory.available / (1024**3), 2),
            'used_gb': round(memory.used / (1024**3), 2),
            'percent_used': memory.percent
        }
        
        # Disk info
        disk_partitions = psutil.disk_partitions()
        self.results['hardware']['disks'] = []
        for partition in disk_partitions:
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                self.results['hardware']['disks'].append({
                    'device': partition.device,
                    'mountpoint': partition.mountpoint,
                    'filesystem': partition.fstype,
                    'total_gb': round(usage.total / (1024**3), 2),
                    'used_gb': round(usage.used / (1024**3), 2),
                    'free_gb': round(usage.free / (1024**3), 2),
                    'percent_used': round((usage.used / usage.total) * 100, 2)
                })
            except PermissionError:
                continue
        
        # Battery info (if available)
        if hasattr(psutil, "sensors_battery"):
            battery = psutil.sensors_battery()
            if battery:
                self.results['hardware']['battery'] = {
                    'percent': battery.percent,
                    'power_plugged': battery.power_plugged,
                    'seconds_left': battery.secsleft if battery.secsleft != psutil.POWER_TIME_UNLIMITED else None
                }
    
    def get_software_info(self):
        """Collect software and process information"""
        # Running processes
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        # Sort by CPU usage
        processes.sort(key=lambda x: x['cpu_percent'] or 0, reverse=True)
        
        self.results['software'] = {
            'boot_time': datetime.fromtimestamp(psutil.boot_time()).isoformat(),
            'users_logged_in': len(psutil.users()),
            'total_processes': len(list(psutil.process_iter())),
            'top_cpu_processes': processes[:5],
            'top_memory_processes': sorted(processes, key=lambda x: x['memory_percent'] or 0, reverse=True)[:5]
        }
    
    def run_performance_tests(self):
        """Run basic performance tests"""
        # CPU test - simple calculation
        start = time.time()
        result = sum(i * i for i in range(100000))
        cpu_time = time.time() - start
        
        # Memory test - allocation and access
        start = time.time()
        test_data = [0] * 1000000
        for i in range(len(test_data)):
            test_data[i] = i
        mem_time = time.time() - start
        
        self.results['performance'] = {
            'cpu_test_time': cpu_time,
            'memory_test_time': mem_time,
            'current_cpu_percent': psutil.cpu_percent(interval=1),
            'current_memory_percent': psutil.virtual_memory().percent
        }
    
    def generate_recommendations(self):
        """Generate optimization recommendations based on results"""
        recommendations = []
        
        # CPU recommendations
        if self.results['performance']['current_cpu_percent'] > 80:
            recommendations.append({
                'category': 'CPU',
                'issue': 'High CPU usage detected',
                'recommendation': 'Consider closing unnecessary applications or upgrading CPU',
                'priority': 'high'
            })
        
        # Memory recommendations
        if self.results['hardware']['memory']['percent_used'] > 85:
            recommendations.append({
                'category': 'Memory',
                'issue': 'High memory usage detected',
                'recommendation': 'Consider adding more RAM or closing memory-intensive applications',
                'priority': 'high'
            })
        
        # Disk recommendations
        for disk in self.results['hardware']['disks']:
            if disk['percent_used'] > 90:
                recommendations.append({
                    'category': 'Storage',
                    'issue': f"Low disk space on {disk['mountpoint']} ({disk['percent_used']}% used)",
                    'recommendation': f'Clean up files on {disk["mountpoint"]} or add more storage',
                    'priority': 'high'
                })
        
        # Temperature check (if available)
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for name, entries in temps.items():
                    for entry in entries:
                        if entry.current > 80:  # Assuming Celsius
                            recommendations.append({
                                'category': 'Temperature',
                                'issue': f'High temperature detected: {entry.current}°C on {entry.label or name}',
                                'recommendation': 'Check cooling system and ventilation',
                                'priority': 'medium'
                            })
        except AttributeError:
            pass  # sensors_temperatures not available on all systems
        
        self.results['recommendations'] = recommendations
    
    def run_full_diagnostics(self):
        """Run all diagnostic checks"""
        print("Running system diagnostics...")
        self.get_system_info()
        self.get_hardware_info()
        self.get_software_info()
        self.run_performance_tests()
        self.generate_recommendations()
        return self.results
    
    def save_results(self, filepath=None):
        """Save diagnostic results to file"""
        if filepath is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"diagnostics_report_{timestamp}.json"
        
        with open(filepath, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"Diagnostic report saved to {filepath}")
        return filepath
    
    def print_summary(self):
        """Print a human-readable summary"""
        print("\n" + "="*50)
        print("SYSTEM DIAGNOSTIC SUMMARY")
        print("="*50)
        
        print(f"\nSystem: {self.results['system_info']['system']} {self.results['system_info']['release']}")
        print(f"Platform: {self.results['system_info']['platform']}")
        print(f"Hostname: {self.results['system_info']['hostname']}")
        
        print(f"\nHardware:")
        print(f"  CPU: {self.results['hardware']['cpu']['total_cores']} cores")
        print(f"  Memory: {self.results['hardware']['memory']['total_gb']} GB "
              f"({self.results['hardware']['memory']['percent_used']}% used)")
        print(f"  Disks: {len(self.results['hardware']['disks'])} partition(s)")
        
        print(f"\nSoftware:")
        print(f"  Boot Time: {self.results['software']['boot_time']}")
        print(f"  Users Logged In: {self.results['software']['users_logged_in']}")
        print(f"  Total Processes: {self.results['software']['total_processes']}")
        
        print(f"\nPerformance:")
        print(f"  Current CPU Usage: {self.results['performance']['current_cpu_percent']}%")
        print(f"  Current Memory Usage: {self.results['performance']['current_memory_percent']}%")
        
        if self.results['recommendations']:
            print(f"\nRecommendations ({len(self.results['recommendations'])}):")
            for rec in self.results['recommendations']:
                priority_symbol = {'high': '!!', 'medium': '!', 'low': ''}.get(rec['priority'], '')
                print(f"  {priority_symbol} [{rec['category']}] {rec['issue']}")
                print(f"    → {rec['recommendation']}")
        else:
            print("\nNo recommendations - system appears healthy!")
        
        print("\n" + "="*50)

if __name__ == "__main__":
    import time
    diagnostics = SystemDiagnostics()
    results = diagnostics.run_full_diagnostics()
    diagnostics.print_summary()
    diagnostics.save_results()