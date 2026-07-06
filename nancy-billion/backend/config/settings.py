"""
Configuration Settings for Nancy/Billion AI Assistant
"""

try:
    from pydantic import BaseSettings, Field
except ImportError:
    from pydantic_settings import BaseSettings
    from pydantic import Field

from typing import Optional, List, Dict, Any
import os
from pathlib import Path

class SystemSettings(BaseSettings):
    """System monitoring and maintenance settings"""
    log_dir: str = Field(default="./logs/system", env="SYSTEM_LOG_DIR")
    recovery_log_dir: str = Field(default="./logs/recovery", env="SYSTEM_RECOVERY_LOG_DIR")
    monitoring_interval: int = Field(default=10, env="SYSTEM_MONITORING_INTERVAL")  # seconds
    logging_interval: int = Field(default=60, env="SYSTEM_LOGGING_INTERVAL")  # seconds
    auto_recovery_enabled: bool = Field(default=True, env="SYSTEM_AUTO_RECOVERY_ENABLED")
    diagnostics_on_startup: bool = Field(default=False, env="SYSTEM_DIAGNOSTICS_ON_STARTUP")

class APISettings(BaseSettings):
    """API server settings"""
    enabled: bool = Field(default=True, env="API_ENABLED")
    host: str = Field(default="localhost", env="API_HOST")
    port: int = Field(default=8000, env="API_PORT")
    cors_origins: List[str] = Field(default=["*"], env="API_CORS_ORIGINS")
    api_v1_prefix: str = Field(default="/api/v1", env="API_V1_PREFIX")

class AgentSettings(BaseSettings):
    """AI Agent settings"""
    max_concurrent_agents: int = Field(default=10, env="AGENT_MAX_CONCURRENT")
    agent_timeout: int = Field(default=30, env="AGENT_TIMEOUT_SECONDS")
    memory_cache_size: int = Field(default=1000, env="AGENT_MEMORY_CACHE_SIZE")

class SecuritySettings(BaseSettings):
    """Security and privacy settings"""
    encrypt_logs: bool = Field(default=False, env="SECURITY_ENCRYPT_LOGS")
    audit_trail_enabled: bool = Field(default=True, env="SECURITY_AUDIT_TRAIL_ENABLED")
    data_retention_days: int = Field(default=30, env="SECURITY_DATA_RETENTION_DAYS")
    allow_external_api: bool = Field(default=True, env="SECURITY_ALLOW_EXTERNAL_API")

class NancyBillionSettings(BaseSettings):
    """Main settings container"""
    
    # System settings
    system: SystemSettings = SystemSettings()
    
    # API settings
    api: APISettings = APISettings()
    
    # Agent settings
    agents: AgentSettings = AgentSettings()
    
    # Security settings
    security: SecuritySettings = SecuritySettings()
    
    # Application info
    app_name: str = Field(default="Nancy/Billion AI Assistant", env="APP_NAME")
    version: str = Field(default="0.1.0", env="APP_VERSION")
    debug: bool = Field(default=False, env="APP_DEBUG")
    
    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'
        case_sensitive = False

# Global settings instance
_settings_instance = None

def get_settings() -> NancyBillionSettings:
    """Get the global settings instance"""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = NancyBillionSettings()
    return _settings_instance

# For backward compatibility
Settings = NancyBillionSettings
