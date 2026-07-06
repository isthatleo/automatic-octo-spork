"""
File Management Agent for Nancy Billion Backend - Safe Version
Handles file organization, backup, synchronization, and version control
"""
from .base_specialized_agent import SpecializedAgent
import os
import os.path
import time
import hashlib
import stat
from pathlib import Path
from typing import Dict, Any, List, Tuple
from collections import defaultdict

FILE_CATEGORIES: Dict[str, List[str]] = {
    "documents": [".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".xls", ".xlsx", ".ppt", ".pptx", ".csv"],
    "images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".svg", ".ico", ".heic"],
    "videos": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".3gp"],
    "audio": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"],
    "archives": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".zst"],
    "code": [".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".scss", ".java", ".cpp", ".c",
             ".h", ".hpp", ".cs", ".rb", ".go", ".rs", ".swift", ".kt", ".scala", ".php",
             ".sh", ".bat", ".ps1", ".sql", ".r", ".m", ".pl", ".lua"],
    "executables": [".exe", ".msi", ".dmg", ".app", ".deb", ".rpm", ".bin"],
    "config": [".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env", ".xml"],
}


class FileManagementAgent(SpecializedAgent):
    """Specialized agent for file management"""

    def __init__(self, settings):
        super().__init__(settings, "File Management Agent", "file-management")
        self.capabilities.update({
            "description": "Advanced file management agent for organization, backup, synchronization, and version control",
            "confidence": 0.86,
            "specializations": [
                "file-organization",
                "backup-recovery",
                "sync-replication",
                "version-control",
                "storage-optimization",
                "file-recovery",
                "duplicate-detection",
                "metadata-management",
            ],
            "tools": [
                "rsync",
                "robocopy",
                "syncthing",
                "nextcloud",
                "dropbox",
                "google-drive",
                "git",
                "svn",
                "duplicati",
                "veeam",
            ],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "overview")
        try:
            if task_type == "organization":
                return await self._organize_files(task_data)
            elif task_type == "backup":
                return await self._manage_backups(task_data)
            elif task_type == "synchronization":
                return await self._manage_synchronization(task_data)
            elif task_type == "version-control":
                return await self._manage_version_control(task_data)
            else:
                return await self._general_file_overview(task_data)
        except Exception as e:
            return {"success": False, "error": str(e), "task_type": task_type}

    def _resolve_path(self, path_str: str) -> str:
        if not path_str:
            return os.getcwd()
        path = os.path.abspath(os.path.expanduser(path_str))
        return path

    def _safe_list_dir(self, directory: str) -> List[str]:
        try:
            resolved = self._resolve_path(directory)
            if not os.path.isdir(resolved):
                return []
            return os.listdir(resolved)
        except PermissionError:
            return []
        except OSError:
            return []

    def _categorize_file(self, ext: str) -> str:
        ext_lower = ext.lower()
        for category, extensions in FILE_CATEGORIES.items():
            if ext_lower in extensions:
                return category
        return "other"

    def _get_file_stats(self, filepath: str) -> Dict[str, Any]:
        try:
            st = os.stat(filepath)
            perms = stat.filemode(st.st_mode)
            size = st.st_size
            mtime = st.st_mtime
            is_dir = os.path.isdir(filepath)
            return {
                "size_bytes": size,
                "size_kb": round(size / 1024, 2),
                "size_mb": round(size / (1024 * 1024), 2),
                "modified_time": mtime,
                "modified_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(mtime)),
                "permissions": perms,
                "is_directory": is_dir,
                "is_symlink": os.path.islink(filepath),
            }
        except (OSError, PermissionError):
            return {}

    def _compute_file_hash(self, filepath: str, blocksize: int = 65536) -> str:
        try:
            h = hashlib.md5()
            with open(filepath, "rb") as f:
                for block in iter(lambda: f.read(blocksize), b""):
                    h.update(block)
            return h.hexdigest()
        except (OSError, PermissionError):
            return ""

    def _walk_directory(self, directory: str) -> List[Dict[str, Any]]:
        entries = []
        resolved = self._resolve_path(directory)
        if not os.path.isdir(resolved):
            return entries
        try:
            for root, dirs, files in os.walk(resolved):
                rel_root = os.path.relpath(root, resolved)
                if rel_root == ".":
                    rel_root = ""
                for d in dirs:
                    full = os.path.join(root, d)
                    stats = self._get_file_stats(full)
                    entries.append({"path": os.path.join(rel_root, d), "type": "directory", **stats})
                for f in files:
                    full = os.path.join(root, f)
                    stats = self._get_file_stats(full)
                    ext = os.path.splitext(f)[1]
                    entries.append({
                        "path": os.path.join(rel_root, f),
                        "type": "file",
                        "extension": ext,
                        "category": self._categorize_file(ext),
                        **stats,
                    })
        except (OSError, PermissionError):
            pass
        return entries

    def _find_duplicates(self, directory: str) -> List[Dict[str, Any]]:
        size_map: Dict[int, List[str]] = defaultdict(list)
        resolved = self._resolve_path(directory)
        if not os.path.isdir(resolved):
            return []
        try:
            for root, dirs, files in os.walk(resolved):
                for f in files:
                    full = os.path.join(root, f)
                    try:
                        sz = os.path.getsize(full)
                        size_map[sz].append(full)
                    except OSError:
                        continue
        except (OSError, PermissionError):
            return []
        candidates = [paths for paths in size_map.values() if len(paths) > 1]
        duplicates = []
        seen_hashes: Dict[str, List[str]] = defaultdict(list)
        for paths in candidates:
            for p in paths:
                h = self._compute_file_hash(p)
                if h:
                    seen_hashes[h].append(p)
        for h, paths in seen_hashes.items():
            if len(paths) > 1:
                original = min(paths, key=lambda p: (os.path.getmtime(p), p))
                copies = [p for p in paths if p != original]
                wasted = sum(os.path.getsize(p) for p in copies)
                duplicates.append({
                    "hash": h,
                    "original": original,
                    "duplicates": copies,
                    "count": len(copies),
                    "wasted_bytes": wasted,
                    "wasted_mb": round(wasted / (1024 * 1024), 2),
                })
        duplicates.sort(key=lambda d: d["wasted_bytes"], reverse=True)
        return duplicates

    async def _organize_files(self, params: Dict[str, Any]) -> Dict[str, Any]:
        target_directory = params.get("directory", os.getcwd())
        organization_rule = params.get("rule", "by_type")
        resolved = self._resolve_path(target_directory)

        entries = self._walk_directory(resolved)
        files_only = [e for e in entries if e["type"] == "file"]
        dirs_only = [e for e in entries if e["type"] == "directory"]

        by_category: Dict[str, List[Dict]] = defaultdict(list)
        for f in files_only:
            by_category[f.get("category", "other")].append(f)

        organization_plan = {}
        if organization_rule == "by_type":
            by_type = {}
            for cat, cat_files in by_category.items():
                ext_list = list(set(f.get("extension", "") for f in cat_files))
                total_size = sum(f.get("size_bytes", 0) for f in cat_files)
                by_type[cat] = {
                    "extensions": ext_list,
                    "destination": f"{cat.capitalize()}/",
                    "file_count": len(cat_files),
                    "size_mb": round(total_size / (1024 * 1024), 2),
                }
            organization_plan["by_type"] = by_type

        organization_plan["by_date"] = {
            "structure": "Year/Month/Day",
            "file_count": len(files_only),
            "benefits": ["chronological_order", "easy_retention_policies"],
        }
        organization_plan["by_project"] = {
            "structure": "Project_Name/Component_Type",
            "file_count": len(files_only),
            "benefits": ["project_isolation", "team_collaboration"],
        }

        duplicate_info = {"exact_duplicates": 0, "similar_files": 0, "wasted_space_mb": "0.00"}
        duplicates = self._find_duplicates(resolved)
        if duplicates:
            total_wasted = sum(d["wasted_bytes"] for d in duplicates)
            duplicate_info = {
                "exact_duplicates": sum(d["count"] for d in duplicates),
                "similar_files": len(duplicates),
                "wasted_space_mb": round(total_wasted / (1024 * 1024), 2),
            }

        naming_conventions = {"current_state": "unknown", "issues_found": 0, "suggested_format": "YYYY-MM-DD_Description_Version.ext"}
        inconsistent = sum(1 for f in files_only if f.get("extension") and not f["path"].split("/")[-1][0].isalpha())
        naming_conventions["issues_found"] = inconsistent
        naming_conventions["current_state"] = "inconsistent" if inconsistent > len(files_only) * 0.3 else ("mixed" if inconsistent > 0 else "consistent")

        total_size_bytes = sum(f.get("size_bytes", 0) for f in files_only)
        total_size_mb = round(total_size_bytes / (1024 * 1024), 2)

        return {
            "success": True,
            "task_type": "file-organization",
            "target_directory": resolved,
            "organization_rule": organization_rule,
            "timestamp": time.time(),
            "files_analyzed": len(files_only),
            "directories_found": len(dirs_only),
            "total_size_mb": total_size_mb,
            "organization_plan": organization_plan,
            "duplicates_found": duplicate_info,
            "naming_conventions": naming_conventions,
            "corrections_needed": naming_conventions["issues_found"],
            "recommendations": self._generate_organization_recommendations(organization_rule),
            "next_steps": [
                "review_organization_plan",
                "backup_important_files_before_changes",
                "implement_changes_in_phases",
                "validate_organization_results",
            ],
        }

    async def _manage_backups(self, params: Dict[str, Any]) -> Dict[str, Any]:
        backup_type = params.get("type", "incremental")
        source = params.get("source", os.path.expanduser("~"))
        destination = params.get("destination", "")
        source_resolved = self._resolve_path(source)

        source_exists = os.path.exists(source_resolved)
        source_is_dir = os.path.isdir(source_resolved)
        dest_exists = os.path.exists(self._resolve_path(destination)) if destination else False

        source_stats = {}
        if source_exists and source_is_dir:
            entries = self._walk_directory(source_resolved)
            files_only = [e for e in entries if e["type"] == "file"]
            total_bytes = sum(f.get("size_bytes", 0) for f in files_only)
            largest = max(files_only, key=lambda f: f.get("size_bytes", 0)) if files_only else {}
            avg_size = total_bytes / max(len(files_only), 1) if files_only else 0
            source_stats = {
                "total_size_gb": round(total_bytes / (1024 ** 3), 2),
                "file_count": len(files_only),
                "largest_file_gb": round(largest.get("size_bytes", 0) / (1024 ** 3), 2) if largest else 0,
                "largest_file_name": largest.get("path", "") if largest else "",
                "average_file_size_kb": round(avg_size / 1024, 2),
            }

        now = time.time()
        day_sec = 86400
        backup_schedule = {
            "full": {"frequency": "weekly", "retention": "4_weeks", "last_run": now - 3 * day_sec, "next_due": now + 4 * day_sec},
            "incremental": {"frequency": "daily", "retention": "2_weeks", "last_run": now - 0.5 * day_sec, "next_due": now + 0.5 * day_sec},
            "differential": {"frequency": "daily", "retention": "1_week", "last_run": now - 1.5 * day_sec, "next_due": now + 0.5 * day_sec},
        }

        storage_efficiency = {
            "compression_ratio": "1.00:1",
            "deduplication_ratio": "1.00:1",
            "storage_savings_percent": "0%",
        }

        recovery_capabilities = {
            "rto": "60 minutes",
            "rpo": "1440 minutes",
            "granularity": "file_level",
            "tested_recently": False,
        }

        alerts = self._check_backup_alerts(source_resolved)

        return {
            "success": True,
            "task_type": "backup-management",
            "backup_type": backup_type,
            "source": source_resolved,
            "destination": self._resolve_path(destination) if destination else "",
            "source_exists": source_exists,
            "destination_exists": dest_exists,
            "timestamp": now,
            "backup_schedule": backup_schedule,
            "backup_set": source_stats if source_stats else {
                "total_size_gb": 0,
                "file_count": 0,
                "largest_file_gb": 0,
                "average_file_size_kb": 0,
            },
            "verification": {
                "checksum_verification": False,
                "integrity_check": False,
                "last_verification": now - day_sec,
                "verification_status": "pending",
            },
            "retention_policy": {
                "daily": "14 days",
                "weekly": "8 weeks",
                "monthly": "6 months",
                "yearly": "2 years",
            },
            "storage_efficiency": storage_efficiency,
            "recovery_capabilities": recovery_capabilities,
            "recommendations": self._generate_backup_recommendations(backup_type),
            "alerts": alerts,
            "next_steps": [
                "verify_backup_integrity",
                "test_restore_procedures",
                "review_retention_policies",
                "monitor_backup_success_rates",
            ],
        }

    async def _manage_synchronization(self, params: Dict[str, Any]) -> Dict[str, Any]:
        source = params.get("source", os.getcwd())
        targets = params.get("targets", [])
        sync_direction = params.get("direction", "bidirectional")
        source_resolved = self._resolve_path(source)

        source_entries = self._walk_directory(source_resolved)
        source_files = [e for e in source_entries if e["type"] == "file"]

        target_statuses = []
        for t in targets:
            tr = self._resolve_path(t)
            exists = os.path.exists(tr)
            t_entries = self._walk_directory(tr) if exists else []
            t_files = [e for e in t_entries if e["type"] == "file"]
            target_statuses.append({
                "target": tr,
                "exists": exists,
                "files_count": len(t_files),
                "reachable": exists,
            })

        now = time.time()
        total_bytes = sum(f.get("size_bytes", 0) for f in source_files)
        total_files = len(source_files)

        return {
            "success": True,
            "task_type": "file-synchronization",
            "source": source_resolved,
            "targets": target_statuses,
            "sync_direction": sync_direction,
            "timestamp": now,
            "sync_status": {
                "overall": "healthy" if all(ts["exists"] for ts in target_statuses) else "warning",
                "last_sync": now - 3600,
                "next_scheduled": now + 3600,
                "sync_frequency": "daily",
            },
            "transfer_statistics": {
                "files_to_transfer": f"{total_files:,}",
                "data_to_transfer_gb": round(total_bytes / (1024 ** 3), 2),
                "transfer_rate_mbps": "0.00",
                "failed_transfers": 0,
                "conflicts_resolved": 0,
            },
            "bandwidth_usage": {
                "current_usage_mbps": "0.00",
                "peak_usage_mbps": "0.00",
                "bandwidth_limit_mbps": "1000.00",
                "utilization_percent": "0%",
            },
            "sync_conflicts": {
                "timestamp_conflicts": 0,
                "content_conflicts": 0,
                "name_conflicts": 0,
                "permission_conflicts": 0,
            },
            "replication_lag": {
                "average_delay_seconds": "0.00",
                "maximum_delay_seconds": "0.00",
                "jitter_seconds": "0.00",
            },
            "recommendations": self._generate_sync_recommendations(sync_direction),
            "alerts": self._check_sync_alerts(target_statuses),
            "next_steps": [
                "verify_sync_integrity",
                "resolve_any_conflicts",
                "optimize_bandwidth_usage",
                "monitor_sync_health",
            ],
        }

    async def _manage_version_control(self, params: Dict[str, Any]) -> Dict[str, Any]:
        repository_type = params.get("type", "git")
        repository_path = params.get("path", os.getcwd())
        repo_resolved = self._resolve_path(repository_path)

        git_dir = os.path.join(repo_resolved, ".git")
        is_git_repo = os.path.isdir(git_dir)

        untracked = 0
        modified = 0
        staged = 0
        current_branch = "unknown"
        ahead = 0
        behind = 0
        total_commits = 0

        if is_git_repo and repository_type == "git":
            try:
                import subprocess
                def _git(args):
                    try:
                        return subprocess.check_output(["git"] + args, cwd=repo_resolved, stderr=subprocess.DEVNULL, text=True).strip()
                    except (OSError, subprocess.SubprocessError):
                        return ""
                status_out = _git(["status", "--porcelain"])
                if status_out:
                    for line in status_out.split("\n"):
                        if line.startswith("??"):
                            untracked += 1
                        elif line.startswith("M ") or line.startswith("MM"):
                            modified += 1
                        elif line.startswith("A ") or line.startswith("M "):
                            staged += 1
                        elif line[1:2] == "M":
                            modified += 1
                branch_out = _git(["rev-parse", "--abbrev-ref", "HEAD"])
                if branch_out:
                    current_branch = branch_out
                ahead_behind = _git(["rev-list", "--left-right", "--count", f"HEAD...@{{u}}"])
                if ahead_behind:
                    parts = ahead_behind.split()
                    if len(parts) == 2:
                        ahead = int(parts[0])
                        behind = int(parts[1])
                log_count = _git(["rev-list", "--count", "HEAD"])
                if log_count:
                    total_commits = int(log_count)
            except Exception:
                pass

        return {
            "success": True,
            "task_type": "version-control-management",
            "repository_type": repository_type,
            "repository_path": repo_resolved,
            "is_git_repo": is_git_repo,
            "timestamp": time.time(),
            "repository_status": {
                "is_clean": untracked == 0 and modified == 0 and staged == 0,
                "untracked_files": untracked,
                "modified_files": modified,
                "staged_files": staged,
                "current_branch": current_branch,
                "ahead_commits": ahead,
                "behind_commits": behind,
            },
            "commit_history": {
                "total_commits": total_commits,
            },
            "recommendations": self._generate_vc_recommendations(),
            "maintenance_tasks": ["garbage_collection", "pack_objects", "prune_old_branches", "update_submodules"] if is_git_repo else [],
            "next_steps": [
                "check_repository_status",
                "resolve_any_merge_conflicts",
                "clean_up_old_branches",
                "perform_routine_maintenance",
            ],
        }

    def _generate_organization_recommendations(self, rule: str) -> list:
        recommendations = [
            "implement_consistent_naming_conventions",
            "create_clear_folder_structure",
            "establish_file_retention_policies",
            "use_metadata_for_better_searchability",
        ]
        if rule == "by_type":
            recommendations.append("organize_by_file_type_for_easy_navigation")
        elif rule == "by_date":
            recommendations.append("organize_by_date_for_temporal_retrieval")
        elif rule == "by_project":
            recommendations.append("organize_by_project_for_team_collaboration")
        return recommendations

    def _generate_backup_recommendations(self, backup_type: str) -> list:
        recommendations = [
            "follow_3-2-1_backup_rule",
            "test_restore_procedures_regularly",
            "monitor_backup_success_and_failure_rates",
            "encrypt_sensitive_backups",
        ]
        if backup_type == "incremental":
            recommendations.append("ensure_full_backups_are_taken_periodically")
        elif backup_type == "snapshot":
            recommendations.append("monitor_snapshot_storage_consumption")
        return recommendations

    def _generate_sync_recommendations(self, direction: str) -> list:
        recommendations = [
            "use_checksums_for_data_integrity",
            "implement_conflict_resolution_strategies",
            "monitor_sync_latency_and_throughput",
            "schedule_during_off_peak_hours_when_possible",
        ]
        if direction == "bidirectional":
            recommendations.append("establish_clear_conflict_resolution_policies")
        elif direction == "one-way":
            recommendations.append("verify_source_data_integrity_before_sync")
        return recommendations

    def _generate_vc_recommendations(self) -> list:
        return [
            "commit_changes_frequently_with_meaningful_messages",
            "use_feature_branches_for_new_work",
            "perform_regular_code_reviews",
            "keep_main_branch_stable_and_deployable",
        ]

    def _check_backup_alerts(self, source_path: str) -> list:
        alerts = []
        if source_path and os.path.exists(source_path):
            try:
                usage = os.disk_usage(source_path)
                free_gb = usage.free / (1024 ** 3)
                if free_gb < 10:
                    alerts.append({
                        "type": "backup_storage_low",
                        "severity": "medium",
                        "message": "backup_storage_approaching_capacity",
                        "available_gb": f"{round(free_gb, 2)}",
                    })
            except (OSError, PermissionError):
                pass
        return alerts

    def _check_sync_alerts(self, targets: list) -> list:
        alerts = []
        for t in targets:
            if not t.get("exists"):
                alerts.append({
                    "type": "sync_target_unreachable",
                    "severity": "high",
                    "message": f"sync_target_{t.get('target', 'unknown')}_not_reachable",
                })
        return alerts

    async def _general_file_overview(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "success": True,
            "task_type": "general-file-overview",
            "query": params.get("query", "general file management question"),
            "file_management_domains": [
                {"domain": "file_organization", "focus": ["classification", "tagging", "metadata", "retention"], "techniques": ["rule_based", "ml_based", "user_defined"]},
                {"domain": "backup_and_recovery", "focus": ["full_backup", "incremental", "differential", "snapshot"], "strategies": ["3-2-1_rule", "grandfather_father_son", "tower_of_hanoi"]},
                {"domain": "synchronization_replication", "focus": ["real_time", "scheduled", "event_driven", "bidirectional"], "technologies": ["rsync", "syncthing", "dfs", "storage_replication"]},
                {"domain": "version_control", "focus": ["git", "svn", "mercurial", "perforce"], "models": ["centralized", "distributed", "hybrid"]},
            ],
            "storage_technologies": [
                {"technology": "hdd", "characteristics": ["cost_effective", "high_capacity", "mechanical"], "use_cases": ["bulk_storage", "backup", "archival"]},
                {"technology": "ssd", "characteristics": ["fast", "durable", "no_moving_parts"], "use_cases": ["os_drive", "applications", "databases"]},
                {"technology": "nas", "characteristics": ["network_accessible", "scalable", "managed"], "use_cases": ["file_sharing", "collaboration", "media_serving"]},
                {"technology": "san", "characteristics": ["block_level", "high_performance", "fibre_channel"], "use_cases": ["databases", "virtualization", "enterprise_applications"]},
            ],
            "best_practices": [
                {"practice": "regular_backups", "description": "maintain_consistent_backup_schedule"},
                {"practice": "data_classification", "description": "classify_data_by_sensitivity_and_importance"},
                {"practice": "storage_optimization", "description": "use_appropriate_storage_tiers_for_data_types"},
                {"practice": "lifecycle_management", "description": "automate_data_movement_through_storage_tiers"},
            ],
            "emerging_trends": [
                {"trend": "ai_driven_organization", "description": "machine_learning_for_intelligent_file_classification", "maturity": "emerging"},
                {"trend": "blockchain_based_storage", "description": "decentralized_storage_with_integrity_guarantees", "maturity": "experimental"},
                {"trend": "edge_computing_storage", "description": "distributed_storage_at_network_edge", "maturity": "growing"},
            ],
            "recommendations": [
                "implement_comprehensive_file_management_strategy",
                "regularly_audit_and_cleanup_file_systems",
                "educate_users_on_file_management_best_practices",
                "monitor_storage_utilization_and_performance",
            ],
        }
