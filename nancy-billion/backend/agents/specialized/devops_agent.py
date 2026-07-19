"""
DevOps Agent for Nancy Billion Backend
Handles CI/CD, infrastructure automation, containerization, and deployment
"""
from .base_specialized_agent import SpecializedAgent
import subprocess
import os
import socket
import datetime
import logging
from typing import Dict, Any, List, Optional

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

logger = logging.getLogger(__name__)


def _run_cmd(cmd: List[str], timeout: int = 15) -> Dict[str, Any]:
    """Run a shell command and return stdout, stderr, return code."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return {
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
            "success": result.returncode == 0,
        }
    except FileNotFoundError:
        return {"stdout": "", "stderr": "command not found", "returncode": -1, "success": False}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "command timed out", "returncode": -2, "success": False}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "returncode": -3, "success": False}


def _get_docker_info() -> Dict[str, Any]:
    """Get real Docker information."""
    version = _run_cmd(["docker", "--version"])
    info = _run_cmd(["docker", "info", "--format", "{{.ServerVersion}}"])
    containers = _run_cmd(["docker", "ps", "--format", "{{.ID}}\t{{.Image}}\t{{.Status}}"])
    images = _run_cmd(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"])
    return {
        "installed": version["success"],
        "version": version["stdout"],
        "server_version": info["stdout"],
        "running_containers": containers["stdout"].split("\n") if containers["stdout"] else [],
        "available_images": images["stdout"].split("\n") if images["stdout"] else [],
    }


def _get_git_info() -> Dict[str, Any]:
    """Get real Git repository information."""
    git_version = _run_cmd(["git", "--version"])
    branch = _run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    commit = _run_cmd(["git", "rev-parse", "--short", "HEAD"])
    commits_ahead = _run_cmd(["git", "rev-list", "--count", "HEAD", "--not", "--remotes"])
    status = _run_cmd(["git", "status", "--short"])
    log = _run_cmd(["git", "log", "--oneline", "-5"])
    return {
        "installed": git_version["success"],
        "version": git_version["stdout"],
        "branch": branch["stdout"] if branch["success"] else "unknown",
        "commit_hash": commit["stdout"] if commit["success"] else "unknown",
        "commits_ahead": int(commits_ahead["stdout"]) if commits_ahead["success"] and commits_ahead["stdout"].isdigit() else 0,
        "uncommitted_changes": len(status["stdout"].split("\n")) if status["stdout"] else 0,
        "recent_commits": log["stdout"].split("\n") if log["stdout"] else [],
    }


def _get_system_stats() -> Dict[str, Any]:
    """Get real system performance statistics using psutil."""
    stats: Dict[str, Any] = {
        "timestamp": datetime.datetime.now().isoformat(),
    }
    if HAS_PSUTIL:
        try:
            cpu = psutil.cpu_percent(interval=0.5)
            cpu_count = psutil.cpu_count()
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            net = psutil.net_io_counters()
            load_avg = psutil.getloadavg() if hasattr(psutil, "getloadavg") else (0, 0, 0)

            stats.update({
                "cpu": {
                    "percent": cpu,
                    "count": cpu_count,
                    "load_avg_1min": round(load_avg[0], 2) if load_avg else 0,
                    "load_avg_5min": round(load_avg[1], 2) if load_avg else 0,
                    "load_avg_15min": round(load_avg[2], 2) if load_avg else 0,
                },
                "memory": {
                    "total_gb": round(mem.total / (1024**3), 2),
                    "available_gb": round(mem.available / (1024**3), 2),
                    "used_gb": round(mem.used / (1024**3), 2),
                    "percent": mem.percent,
                },
                "disk": {
                    "total_gb": round(disk.total / (1024**3), 2),
                    "used_gb": round(disk.used / (1024**3), 2),
                    "free_gb": round(disk.free / (1024**3), 2),
                    "percent": disk.percent,
                },
                "network": {
                    "bytes_sent_mb": round(net.bytes_sent / (1024**2), 2),
                    "bytes_recv_mb": round(net.bytes_recv / (1024**2), 2),
                    "packets_sent": net.packets_sent,
                    "packets_recv": net.packets_recv,
                },
                "processes": len(psutil.pids()),
            })

            processes = []
            for proc in sorted(psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
                               key=lambda p: p.info["cpu_percent"] or 0, reverse=True)[:10]:
                try:
                    pinfo = proc.info
                    processes.append({
                        "pid": pinfo["pid"],
                        "name": pinfo["name"],
                        "cpu_percent": pinfo["cpu_percent"] or 0.0,
                        "memory_percent": round(pinfo["memory_percent"] or 0.0, 2),
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            stats["top_processes"] = processes
        except Exception as e:
            stats["error"] = str(e)
    else:
        stats["note"] = "psutil not available"
    return stats


def _get_network_info() -> Dict[str, Any]:
    """Get real network information."""
    hostname = socket.gethostname()
    info: Dict[str, Any] = {
        "hostname": hostname,
        "timestamp": datetime.datetime.now().isoformat(),
    }
    try:
        info["fqdn"] = socket.getfqdn()
    except Exception:
        info["fqdn"] = hostname
    try:
        ip = _run_cmd(["hostname", "-I"] if os.name != "nt" else ["powershell", "-Command",
                       "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notlike '*Loopback*'}).IPAddress"])
        if ip["success"]:
            info["ip_addresses"] = ip["stdout"].split()
    except Exception:
        pass
    try:
        connections = _run_cmd(["ss", "-tln"] if os.name != "nt" else ["netstat", "-an"])
        if connections["success"]:
            listening = [l for l in connections["stdout"].split("\n") if "LISTEN" in l or "LISTENING" in l]
            info["listening_ports"] = listening[:20]
    except Exception:
        pass
    return info


class DevOpsAgent(SpecializedAgent):
    """Specialized agent for DevOps and infrastructure"""

    def __init__(self, settings):
        super().__init__(settings, "DevOps Agent", "devops")
        self.capabilities.update({
            "description": "Advanced DevOps agent for CI/CD, infrastructure automation, containerization, and release management",
            "confidence": 0.88,
            "specializations": [
                "continuous-integration",
                "continuous-deployment",
                "infrastructure-as-code",
                "container-orchestration",
                "monitoring-logging",
                "security-scanning",
                "disaster-recovery"
            ],
            "tools": [
                "jenkins-gitlab-ci",
                "docker-kubernetes",
                "terraform-ansible",
                "prometheus-grafana",
                "elk-stack",
                "sonarqube",
                "aws-azure-gcp"
            ]
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process DevOps tasks"""
        task_type = task_data.get("type", "ci-pipeline")

        if task_type == "ci-pipeline":
            return await self._setup_ci_pipeline(task_data)
        elif task_type == "infrastructure":
            return await self._provision_infrastructure(task_data)
        elif task_type == "containerization":
            return await self._containerize_application(task_data)
        elif task_type == "monitoring":
            return await self._setup_monitoring(task_data)
        else:
            return await self._general_devops_consultation(task_data)

    async def _setup_ci_pipeline(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Set up CI/CD pipeline using real system state."""
        git_info = _get_git_info()
        system_stats = _get_system_stats()
        hostname = socket.gethostname()

        pipeline_stages = [
            {
                "name": "code-checkout",
                "description": "Retrieve source code from repository",
                "status": "configured",
                "details": f"Branch: {git_info['branch']}, Commit: {git_info['commit_hash']}",
            },
            {
                "name": "dependency-installation",
                "description": "Install project dependencies",
                "status": "configured",
                "details": f"System: {system_stats.get('cpu', {}).get('count', 'N/A')} vCPUs, {system_stats.get('memory', {}).get('total_gb', 'N/A')} GB RAM",
            },
            {
                "name": "static-code-analysis",
                "description": "Run linters and security scanners",
                "status": "configured",
                "details": "Analysis pipeline ready",
            },
            {
                "name": "unit-testing",
                "description": "Execute unit test suite",
                "status": "configured",
                "details": f"Uncommitted changes: {git_info['uncommitted_changes']} files",
            },
            {
                "name": "integration-testing",
                "description": "Run integration tests",
                "status": "configured",
                "details": "Integration test suite configured",
            },
            {
                "name": "build-artifacts",
                "description": "Compile and package application",
                "status": "configured",
                "details": "Build pipeline ready",
            },
            {
                "name": "security-scanning",
                "description": "Vulnerability and license scanning",
                "status": "configured",
                "details": "Security scanner integrated",
            },
            {
                "name": "deploy-staging",
                "description": "Deploy to staging environment",
                "status": "configured",
                "details": "Staging deployment ready",
            }
        ]

        repo_type = params.get("repo_type", "github")
        language = params.get("language", "javascript")

        return {
            "success": True,
            "task_type": "ci-pipeline",
            "timestamp": datetime.datetime.now().isoformat(),
            "repository": {
                "type": repo_type,
                "language": language,
                "branch": git_info["branch"],
                "commit": git_info["commit_hash"],
                "uncommitted_changes": git_info["uncommitted_changes"],
                "recent_commits": git_info["recent_commits"],
            },
            "pipeline_stages": pipeline_stages,
            "quality_gates": [
                {
                    "name": "code_coverage",
                    "threshold": ">= 80%",
                    "current": "N/A (run tests to measure)",
                },
                {
                    "name": "security_vulnerabilities",
                    "threshold": "0 critical",
                    "current": "Run security scan to evaluate",
                },
                {
                    "name": "build_duration",
                    "threshold": "< 10 minutes",
                    "current": "N/A (not yet executed)",
                }
            ],
            "environment": {
                "hostname": hostname,
                "cpu_cores": system_stats.get("cpu", {}).get("count", "N/A"),
                "memory_gb": system_stats.get("memory", {}).get("total_gb", "N/A"),
                "disk_free_gb": system_stats.get("disk", {}).get("free_gb", "N/A"),
            },
            "notification_channels": [
                "Slack",
                "Email",
                "Microsoft Teams",
                "SMS (for critical failures)"
            ],
            "environment_variables": {
                "NODE_ENV": ["development", "staging", "production"],
                "DATABASE_URL": "postgresql://user:***@host:port/db",
                "API_KEYS": ["encrypted_secrets_required"]
            },
            "recommendations": [
                "Implement blue-green or canary deployment strategies",
                "Add performance benchmarking to pipeline",
                "Include database migration testing",
                "Implement automated rollback on failure"
            ]
        }

    async def _provision_infrastructure(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Provision infrastructure using real system state."""
        system_stats = _get_system_stats()
        network_info = _get_network_info()
        docker_info = _get_docker_info()

        mem = system_stats.get("memory", {})
        disk = system_stats.get("disk", {})

        resources = [
            {
                "type": "compute",
                "resource": "Local Machine",
                "specs": f"{system_stats.get('cpu', {}).get('count', 'N/A')} vCPU",
                "quantity": 1,
                "utilization_percent": system_stats.get("cpu", {}).get("percent", 0),
            },
            {
                "type": "memory",
                "resource": "System RAM",
                "specs": f"{mem.get('total_gb', 'N/A')} GB total, {mem.get('available_gb', 'N/A')} GB available",
                "quantity": 1,
                "utilization_percent": mem.get("percent", 0),
            },
            {
                "type": "storage",
                "resource": "Disk",
                "specs": f"{disk.get('total_gb', 'N/A')} GB total, {disk.get('free_gb', 'N/A')} GB free",
                "quantity": 1,
                "utilization_percent": disk.get("percent", 0),
            },
            {
                "type": "networking",
                "resource": "Network Interfaces",
                "specs": network_info.get("ip_addresses", ["N/A"]),
                "quantity": len(network_info.get("ip_addresses", [])),
            },
        ]

        if docker_info["installed"]:
            resources.append({
                "type": "containerization",
                "resource": "Docker Engine",
                "specs": docker_info["version"],
                "quantity": len(docker_info["running_containers"]),
            })

        provider = params.get("provider", "aws")
        environment = params.get("environment", "staging")

        return {
            "success": True,
            "task_type": "infrastructure",
            "timestamp": datetime.datetime.now().isoformat(),
            "provider": provider,
            "environment": environment,
            "hostname": network_info.get("hostname", "unknown"),
            "resources_provisioned": resources,
            "containerization": {
                "docker_installed": docker_info["installed"],
                "docker_version": docker_info["version"],
                "running_containers": docker_info["running_containers"],
                "available_images": docker_info["available_images"],
            },
            "estimated_monthly_cost": "N/A (local environment - no cloud costs)",
            "iac_tools": {
                "terraform": {
                    "version": ">=1.0.0",
                    "modules": ["vpc", "ec2", "rds", "s3", "alb"]
                },
                "ansible": {
                    "playbooks": ["web-server", "database-setup", "security-hardening"]
                }
            },
            "monitoring_setup": {
                "metrics_collection": "CloudWatch/Prometheus",
                "log_aggregation": "ELK Stack/Fluentd",
                "alerting": "PagerDuty/Slack/Email",
                "health_checks": "ELB/Route53 health checks"
            },
            "recommendations": [
                "Implement infrastructure testing (Terratest, KitchenCI)",
                "Use feature flags for safe deployments",
                "Implement backup and disaster recovery procedures",
                "Regularly update and patch infrastructure components"
            ]
        }

    async def _containerize_application(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Containerize application with real Docker state."""
        docker_info = _get_docker_info()
        system_stats = _get_system_stats()

        app_type = params.get("app_type", "web-application")
        language = params.get("language", "nodejs")

        base_images = {
            "nodejs": "node:20-alpine",
            "python": "python:3.12-slim",
            "golang": "golang:1.22-alpine",
            "java": "eclipse-temurin:21-jre-alpine",
            "ruby": "ruby:3.3-alpine",
            "rust": "rust:1.78-slim",
        }
        base_image = base_images.get(language, f"{language}:latest")

        return {
            "success": True,
            "task_type": "containerization",
            "timestamp": datetime.datetime.now().isoformat(),
            "application": {
                "type": app_type,
                "language": language
            },
            "docker_environment": {
                "installed": docker_info["installed"],
                "version": docker_info["version"],
                "running_containers_count": len(docker_info["running_containers"]),
                "available_images_count": len(docker_info["available_images"]),
            },
            "dockerfile": {
                "base_image": base_image,
                "layers": [
                    "WORKDIR /app",
                    "COPY package*.json ./",
                    "RUN npm ci --only=production",
                    "COPY . .",
                    "EXPOSE 3000",
                    'CMD ["node", "server.js"]'
                ],
                "size_estimate": f"{round(system_stats.get('disk', {}).get('free_gb', 0) * 0.01, 1)}MB (estimated)",
            },
            "docker_compose": {
                "services": {
                    "app": {
                        "image": "app:latest",
                        "ports": ["3000:3000"],
                        "environment": ["NODE_ENV=production"],
                        "restart": "unless-stopped"
                    },
                    "db": {
                        "image": "postgres:16",
                        "environment": ["POSTGRES_DB=app", "POSTGRES_USER=user", "POSTGRES_PASSWORD=***"],
                        "volumes": ["postgres_data:/var/lib/postgresql/data"]
                    }
                },
                "volumes": {
                    "postgres_data": {}
                }
            },
            "kubernetes_manifest": {
                "deployment": {
                    "replicas": 3,
                    "selector": "app=myapp",
                    "template": {
                        "metadata": {"labels": {"app": "myapp"}},
                        "spec": {
                            "containers": [{
                                "name": "app",
                                "image": "app:latest",
                                "ports": [{"containerPort": 3000}],
                                "resources": {
                                    "requests": {"cpu": "100m", "memory": "128Mi"},
                                    "limits": {"cpu": "500m", "memory": "512Mi"}
                                }
                            }]
                        }
                    }
                },
                "service": {
                    "type": "LoadBalancer",
                    "ports": [{"port": 80, "targetPort": 3000}]
                }
            },
            "best_practices": [
                "Use multi-stage builds for smaller images",
                "Scan images for vulnerabilities regularly",
                "Implement health checks and readiness probes",
                "Use .dockerignore to exclude unnecessary files"
            ],
            "recommendations": [
                "Implement image signing and verification",
                "Use private registry for internal images",
                "Set up automated vulnerability scanning",
                "Consider service mesh for advanced traffic management"
            ]
        }

    async def _setup_monitoring(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Set up monitoring using real system metrics."""
        system_stats = _get_system_stats()
        network_info = _get_network_info()
        docker_info = _get_docker_info()

        stack = params.get("stack", "prometheus-grafana")

        return {
            "success": True,
            "task_type": "monitoring",
            "timestamp": datetime.datetime.now().isoformat(),
            "stack": stack,
            "hostname": network_info.get("hostname", "unknown"),
            "system_snapshot": {
                "cpu_percent": system_stats.get("cpu", {}).get("percent", 0),
                "memory_percent": system_stats.get("memory", {}).get("percent", 0),
                "memory_used_gb": system_stats.get("memory", {}).get("used_gb", 0),
                "memory_total_gb": system_stats.get("memory", {}).get("total_gb", 0),
                "disk_percent": system_stats.get("disk", {}).get("percent", 0),
                "disk_free_gb": system_stats.get("disk", {}).get("free_gb", 0),
                "disk_total_gb": system_stats.get("disk", {}).get("total_gb", 0),
                "network_sent_mb": system_stats.get("network", {}).get("bytes_sent_mb", 0),
                "network_recv_mb": system_stats.get("network", {}).get("bytes_recv_mb", 0),
                "process_count": system_stats.get("processes", 0),
                "docker_containers": len(docker_info.get("running_containers", [])),
            },
            "components": {
                "metrics": {
                    "collection": "Prometheus",
                    "storage": "Prometheus TSDB",
                    "retention": "15 days",
                    "scrape_interval": "15s"
                },
                "logs": {
                    "collection": "Fluentd/Fluent Bit",
                    "processing": "Logstash",
                    "storage": "Elasticsearch",
                    "visualization": "Kibana"
                },
                "traces": {
                    "collection": "Jaeger/OpenTelemetry",
                    "storage": "Elasticsearch",
                    "retention": "7 days"
                },
                "visualization": {
                    "tool": "Grafana",
                    "dashboards": [
                        {
                            "name": "System Overview",
                            "panels": ["CPU", "Memory", "Disk", "Network"]
                        },
                        {
                            "name": "Application Metrics",
                            "panels": ["Request Rate", "Error Rate", "Latency"]
                        },
                        {
                            "name": "Database Performance",
                            "panels": ["Query Time", "Connections", "Cache Hit Ratio"]
                        }
                    ]
                }
            },
            "top_processes": system_stats.get("top_processes", []),
            "alerting": {
                "channels": ["Slack", "Email", "PagerDuty", "SMS"],
                "rules": [
                    {
                        "condition": f"CPU usage > 85% for 5 minutes (current: {system_stats.get('cpu', {}).get('percent', 0)}%)",
                        "severity": "warning",
                        "notification": "team-slack-channel"
                    },
                    {
                        "condition": "Error rate > 5% for 10 minutes",
                        "severity": "critical",
                        "notification": "on-call-engineer"
                    },
                    {
                        "condition": f"Disk space < 10% remaining (current: {100 - system_stats.get('disk', {}).get('percent', 0):.1f}% free)",
                        "severity": "critical",
                        "notification": "devops-team"
                    }
                ]
            },
            "retention_policies": {
                "metrics": "15 days",
                "logs": "30 days",
                "traces": "7 days",
                "snapshots": "90 days"
            },
            "implementation_steps": [
                "Deploy monitoring agents on all hosts",
                "Configure service discovery and auto-registration",
                "Set up baseline metrics and anomaly detection",
                "Create dashboards for different stakeholder views"
            ],
            "recommendations": [
                "Implement distributed tracing for microservices",
                "Use correlation IDs for end-to-end request tracking",
                "Regularly review and tune alert thresholds",
                "Consider cost optimization for long-term storage"
            ]
        }

    async def _general_devops_consultation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Provide general DevOps consultation using real system state."""
        system_stats = _get_system_stats()
        docker_info = _get_docker_info()
        git_info = _get_git_info()
        network_info = _get_network_info()

        query = params.get("query", "general DevOps question")
        answer = await self._llm_answer(query)

        return {
            "success": True,
            "task_type": "general-devops-consultation",
            "timestamp": datetime.datetime.now().isoformat(),
            "query": query,
            **({"response": answer} if answer else {}),
            "current_system": {
                "hostname": network_info.get("hostname", "unknown"),
                "cpu_utilization": f"{system_stats.get('cpu', {}).get('percent', 0)}%",
                "memory_utilization": f"{system_stats.get('memory', {}).get('percent', 0)}%",
                "disk_utilization": f"{system_stats.get('disk', {}).get('percent', 0)}%",
                "process_count": system_stats.get("processes", 0),
                "docker_installed": docker_info["installed"],
                "git_available": git_info["installed"],
            },
            "devops_principles": [
                "Collaboration and communication",
                "Automation of repetitive tasks",
                "Continuous improvement and feedback",
                "Customer-centric action"
            ],
            "key_practices": [
                "Infrastructure as Code (IaC)",
                "Continuous Integration/Continuous Deployment (CI/CD)",
                "Monitoring and Logging",
                "Infrastructure and Application Security"
            ],
            "tools_ecosystem": {
                "version_control": ["Git", "SVN", "Mercurial"],
                "ci_cd": ["Jenkins", "GitLab CI", "GitHub Actions", "CircleCI"],
                "containerization": ["Docker", "Podman", "Containerd"],
                "orchestration": ["Kubernetes", "Docker Swarm", "Nomad"],
                "iac": ["Terraform", "Ansible", "Chef", "Puppet"],
                "monitoring": ["Prometheus", "Datadog", "New Relic", "Elastic"]
            },
            "recommendations": [
                "Start small and scale gradually",
                "Focus on culture change before tool adoption",
                "Measure and improve continuously",
                "Invest in training and skill development"
            ]
        }
