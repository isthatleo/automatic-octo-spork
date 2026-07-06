import psutil
import subprocess
import time
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
import threading
import signal
import os

class AutoRecovery:
    def __init__(self, log_dir="logs/recovery"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_dir / "recovery.log"),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger("AutoRecovery")
        
        # Recovery rules
        self.recovery_rules = {
            'high_cpu': {
                'threshold': 90,
                'duration': 30,  # seconds
                'action': self.handle_high_cpu,
                'cooldown': 300  # 5 minutes
            },
            'high_memory': {
                'threshold': 95,
                'duration': 30,
                'action': self.handle_high_memory,
                'cooldown': 300
            },
            'low_disk': {
                'threshold': 95,
                'duration': 60,
                'action': self.handle_low_disk,
                'cooldown': 600
            },
            'process_crash': {
                'action': self.handle_process_crash,
                'cooldown': 60
            }
        }
        
        # State tracking
        self.last_action_time = {}
        self.monitoring = False
        self.monitor_thread = None
        self.critical_processes = []  # List of process names to monitor
        
    def log_recovery_event(self, event_type, details):
        """Log a recovery event"""
        event = {
            'timestamp': datetime.now().isoformat(),
            'type': event_type,
            'details': details
        }
        
        # Log to file
        date_str = datetime.now().strftime("%Y-%m-%d")
        log_file = self.log_dir / f"events_{date_str}.jsonl"
        
        with open(log_file, 'a') as f:
            f.write(json.dumps(event) + '\n')
        
        self.logger.info(f"Recovery event: {event_type} - {details}")
    
    def can_take_action(self, rule_name):
        """Check if enough time has passed since last action for this rule"""
        if rule_name not in self.last_action_time:
            return True
        
        cooldown = self.recovery_rules[rule_name].get('cooldown', 300)
        last_time = self.last_action_time[rule_name]
        return (datetime.now() - last_time).total_seconds() > cooldown
    
    def record_action_time(self, rule_name):
        """Record the time of last action for a rule"""
        self.last_action_time[rule_name] = datetime.now()
    
    def handle_high_cpu(self, details):
        """Handle high CPU usage"""
        self.logger.warning(f"Handling high CPU: {details}")
        
        # Try to identify and reduce load from non-critical processes
        try:
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
                try:
                    pinfo = proc.info
                    if pinfo['cpu_percent'] and pinfo['cpu_percent'] > 10:
                        processes.append(pinfo)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            # Sort by CPU usage
            processes.sort(key=lambda x: x['cpu_percent'], reverse=True)
            
            # Log top consumers
            top_consumers = processes[:5]
            self.logger.info(f"Top CPU consumers: {top_consumers}")
            
            # In a real system, we might:
            # 1. Notify user about high CPU usage
            # 2. Suggest closing non-essential applications
            # 3. Throttle background processes
            # 4. Only kill processes as last resort
            
            self.log_recovery_event('high_cpu_handled', {
                'action_taken': 'logged_and_notified',
                'top_consumers': top_consumers
            })
            
        except Exception as e:
            self.logger.error(f"Error handling high CPU: {e}")
    
    def handle_high_memory(self, details):
        """Handle high memory usage"""
        self.logger.warning(f"Handling high memory: {details}")
        
        try:
            # Identify memory-heavy processes
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'memory_percent']):
                try:
                    pinfo = proc.info
                    if pinfo['memory_percent'] and pinfo['memory_percent'] > 5:
                        processes.append(pinfo)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            processes.sort(key=lambda x: x['memory_percent'] or 0, reverse=True)
            top_consumers = processes[:5]
            
            self.logger.info(f"Top memory consumers: {top_consumers}")
            
            self.log_recovery_event('high_memory_handled', {
                'action_taken': 'logged_and_notified',
                'top_consumers': top_consumers
            })
            
        except Exception as e:
            self.logger.error(f"Error handling high memory: {e}")
    
    def handle_low_disk(self, details):
        """Handle low disk space"""
        self.logger.warning(f"Handling low disk space: {details}")
        
        try:
            # Find large files or suggest cleanup
            self.log_recovery_event('low_disk_handled', {
                'action_taken': 'logged_and_notified',
                'suggestion': 'Consider running disk cleanup or moving files to external storage'
            })
            
        except Exception as e:
            self.logger.error(f"Error handling low disk: {e}")
    
    def handle_process_crash(self, details):
        """Handle unexpected process termination"""
        self.logger.warning(f"Handling process crash: {details}")
        
        # Try to restart critical processes if applicable
        process_name = details.get('process_name')
        if process_name in self.critical_processes:
            self.logger.info(f"Attempting to restart critical process: {process_name}")
            # Implementation would depend on the specific process
        
        self.log_recovery_event('process_crash_handled', {
            'action_taken': 'logged_and_monitored',
            'process_name': process_name
        })
    
    def monitor_system_health(self, check_interval=10):
        """Continuously monitor system health and trigger recoveries"""
        self.logger.info("Starting system health monitoring for auto-recovery")
        self.monitoring = True
        
        # Track state for duration-based thresholds
        cpu_high_start = None
        memory_high_start = None
        disk_low_start = None
        
        while self.monitoring:
            try:
                # Get current metrics
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                disk_usage = psutil.disk_usage('/')
                disk_percent = (disk_usage.used / disk_usage.total) * 100
                
                current_time = datetime.now()
                
                # Check CPU
                if cpu_percent > self.recovery_rules['high_cpu']['threshold']:
                    if cpu_high_start is None:
                        cpu_high_start = current_time
                    elif (current_time - cpu_high_start).total_seconds() > self.recovery_rules['high_cpu']['duration']:
                        if self.can_take_action('high_cpu'):
                            self.handle_high_cpu({
                                'cpu_percent': cpu_percent,
                                'duration': (current_time - cpu_high_start).total_seconds()
                            })
                            self.record_action_time('high_cpu')
                            cpu_high_start = None  # Reset after action
                else:
                    cpu_high_start = None
                
                # Check Memory
                if memory.percent > self.recovery_rules['high_memory']['threshold']:
                    if memory_high_start is None:
                        memory_high_start = current_time
                    elif (current_time - memory_high_start).total_seconds() > self.recovery_rules['high_memory']['duration']:
                        if self.can_take_action('high_memory'):
                            self.handle_high_memory({
                                'memory_percent': memory.percent,
                                'duration': (current_time - memory_high_start).total_seconds()
                            })
                            self.record_action_time('high_memory')
                            memory_high_start = None
                else:
                    memory_high_start = None
                
                # Check Disk
                if disk_percent > self.recovery_rules['low_disk']['threshold']:
                    if disk_low_start is None:
                        disk_low_start = current_time
                    elif (current_time - disk_low_start).total_seconds() > self.recovery_rules['low_disk']['duration']:
                        if self.can_take_action('low_disk'):
                            self.handle_low_disk({
                                'disk_percent': disk_percent,
                                'duration': (current_time - disk_low_start).total_seconds()
                            })
                            self.record_action_time('low_disk')
                            disk_low_start = None
                else:
                    disk_low_start = None
                
                # Check for process crashes (simplified)
                # In a full implementation, we'd track specific PIDs
                
                time.sleep(check_interval)
                
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                time.sleep(check_interval)
    
    def start_monitoring(self, check_interval=10):
        """Start the auto-recovery monitoring in a background thread"""
        if self.monitoring:
            self.logger.warning("Monitoring already started")
            return
        
        self.monitor_thread = threading.Thread(
            target=self.monitor_system_health,
            args=(check_interval,),
            daemon=True
        )
        self.monitor_thread.start()
        self.logger.info("Auto-recovery monitoring started")
    
    def stop_monitoring(self):
        """Stop the monitoring"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        self.logger.info("Auto-recovery monitoring stopped")

# Example usage and testing functions
def test_recovery_system():
    """Test the recovery system"""
    recovery = AutoRecovery()
    
    # Run a quick system check
    print("Testing recovery system initialization...")
    print(f"Log directory: {recovery.log_dir}")
    print("Recovery rules configured:", list(recovery.recovery_rules.keys()))
    
    # Don't actually start monitoring in test to avoid blocking
    print("Recovery system ready for monitoring")

if __name__ == "__main__":
    test_recovery_system()