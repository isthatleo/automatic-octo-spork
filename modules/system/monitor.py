import psutil
import json
import time
from datetime import datetime
from pathlib import Path

class SystemMonitor:
    def __init__(self, log_dir="logs/system"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.alerts = []
        
    def get_cpu_usage(self):
        """Get current CPU usage percentage"""
        return psutil.cpu_percent(interval=1)
    
    def get_memory_info(self):
        """Get memory usage information"""
        memory = psutil.virtual_memory()
        return {
            'total': memory.total,
            'available': memory.available,
            'percent': memory.percent,
            'used': memory.used,
            'free': memory.free
        }
    
    def get_disk_usage(self):
        """Get disk usage for all mounted partitions"""
        disks = []
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disks.append({
                    'device': partition.device,
                    'mountpoint': partition.mountpoint,
                    'fstype': partition.fstype,
                    'total': usage.total,
                    'used': usage.used,
                    'free': usage.free,
                    'percent': (usage.used / usage.total) * 100
                })
            except PermissionError:
                # Some partitions may be inaccessible
                continue
        return disks
    
    def get_network_info(self):
        """Get network interface statistics"""
        net_io = psutil.net_io_counters(pernic=True)
        network_info = {}
        for interface, stats in net_io.items():
            network_info[interface] = {
                'bytes_sent': stats.bytes_sent,
                'bytes_recv': stats.bytes_recv,
                'packets_sent': stats.packets_sent,
                'packets_recv': stats.packets_recv,
                'errin': stats.errin,
                'errout': stats.errout,
                'dropin': stats.dropin,
                'dropout': stats.dropout
            }
        return network_info
    
    def get_system_snapshot(self):
        """Get a complete snapshot of system status"""
        return {
            'timestamp': datetime.now().isoformat(),
            'cpu': {
                'usage_percent': self.get_cpu_usage(),
                'count': psutil.cpu_count(),
                'frequency': psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None
            },
            'memory': self.get_memory_info(),
            'disk': self.get_disk_usage(),
            'network': self.get_network_info(),
            'boot_time': psutil.boot_time(),
            'users': len(psutil.users()),
            'processes': len(psutil.pids())
        }
    
    def log_snapshot(self, snapshot=None):
        """Log system snapshot to file"""
        if snapshot is None:
            snapshot = self.get_system_snapshot()
            
        date_str = datetime.now().strftime("%Y-%m-%d")
        log_file = self.log_dir / f"system_{date_str}.jsonl"
        
        with open(log_file, 'a') as f:
            f.write(json.dumps(snapshot) + '\n')
    
    def check_alerts(self, snapshot=None, thresholds=None):
        """Check if any metrics exceed thresholds and return alerts"""
        if snapshot is None:
            snapshot = self.get_system_snapshot()
            
        if thresholds is None:
            thresholds = {
                'cpu_percent': 80,
                'memory_percent': 85,
                'disk_percent': 90
            }
            
        alerts = []
        
        # Check CPU
        if snapshot['cpu']['usage_percent'] > thresholds['cpu_percent']:
            alerts.append({
                'type': 'cpu_high',
                'message': f"CPU usage high: {snapshot['cpu']['usage_percent']:.1f}%",
                'value': snapshot['cpu']['usage_percent'],
                'threshold': thresholds['cpu_percent'],
                'timestamp': snapshot['timestamp']
            })
        
        # Check Memory
        if snapshot['memory']['percent'] > thresholds['memory_percent']:
            alerts.append({
                'type': 'memory_high',
                'message': f"Memory usage high: {snapshot['memory']['percent']:.1f}%",
                'value': snapshot['memory']['percent'],
                'threshold': thresholds['memory_percent'],
                'timestamp': snapshot['timestamp']
            })
        
        # Check Disk
        for disk in snapshot['disk']:
            if disk['percent'] > thresholds['disk_percent']:
                alerts.append({
                    'type': 'disk_high',
                    'message': f"Disk usage high on {disk['mountpoint']}: {disk['percent']:.1f}%",
                    'value': disk['percent'],
                    'threshold': thresholds['disk_percent'],
                    'device': disk['device'],
                    'mountpoint': disk['mountpoint'],
                    'timestamp': snapshot['timestamp']
                })
                
        self.alerts.extend(alerts)
        return alerts
    
    def start_monitoring(self, interval=30, duration=None):
        """Start continuous monitoring"""
        start_time = time.time()
        print(f"Starting system monitoring (interval: {interval}s)")
        
        try:
            while True:
                snapshot = self.get_system_snapshot()
                self.log_snapshot(snapshot)
                alerts = self.check_alerts(snapshot)
                
                if alerts:
                    print(f"[{snapshot['timestamp']}] ALERTS: {len(alerts)} threshold(s) exceeded")
                    for alert in alerts:
                        print(f"  - {alert['message']}")
                else:
                    print(f"[{snapshot['timestamp']}] System normal")
                
                if duration and (time.time() - start_time) > duration:
                    break
                    
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\nMonitoring stopped by user")
        except Exception as e:
            print(f"\nMonitoring error: {e}")

if __name__ == "__main__":
    monitor = SystemMonitor()
    monitor.start_monitoring(interval=10)