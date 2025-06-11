# config/settings.py - Advanced configuration management with environment-specific settings
from __future__ import annotations
import os
import sys
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
#from pydantic import BaseModel, BaseSettings, Field, validator, ValidationError, BaseModel, ConfigDict, field_validator, computed_field
from pydantic_settings import  BaseSettings, SettingsConfigDict, Field, validator, ValidationError, BaseModel, ConfigDict, field_validator, computed_field 
import yaml
from functools import lru_cache
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Check for optional dependencies
try:
    import prometheus_client
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

# Configuration file paths
CONFIG_PATHS = [
    Path("config.yaml"),
    Path("config.json"),
    Path(".env")
]

# ----------------------------------------
# Utility Functions
# ----------------------------------------
def is_env_true(key: str, default: str = "true") -> bool:
    """
    Returns True if the environment variable is set to a truthy value.
    Accepted truthy values: "1", "true", "yes"
    """
    return os.getenv(key, default).lower() in ("1", "true", "yes")

def load_config_file() -> Dict[str, Any]:
    """Load configuration from YAML or JSON files"""
    for path in CONFIG_PATHS:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                if path.suffix in [".yaml", ".yml"]:
                    return yaml.safe_load(f)
                elif path.suffix == ".json":
                    return json.load(f)
    return {}

# ----------------------------------------
# Configuration Classes
# ----------------------------------------
class DatabaseSettings(BaseSettings):
    """Database configuration with optimization settings"""
    model_config = SettingsConfigDict(
        env_prefix="DB_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )
    
    url: str = Field(
        default="sqlite+aiosqlite:///./database.db",
        description="Database connection URL"
    )
    pool_size: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Connection pool size"
    )
    max_overflow: int = Field(
        default=30,
        ge=0,
        le=100,
        description="Maximum pool overflow"
    )
    pool_timeout: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Pool timeout in seconds"
    )
    echo: bool = Field(
        default=False,
        description="Enable SQL query logging"
    )
    query_cache_size: int = Field(
        default=1000,
        ge=0,
        description="Query cache size"
    )
    connection_pool_recycle: int = Field(
        default=3600,
        ge=60,
        description="Connection recycle time in seconds"
    )

class RedisSettings(BaseSettings):
    """Redis configuration with clustering support"""
    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )
    
    url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL"
    )
    cluster_mode: bool = Field(
        default=False,
        description="Enable Redis cluster mode"
    )
    cluster_nodes: List[str] = Field(
        default_factory=list,
        description="Redis cluster node addresses"
    )
    max_connections: int = Field(
        default=50,
        ge=1,
        le=1000,
        description="Maximum Redis connections"
    )
    socket_timeout: float = Field(
        default=5.0,
        ge=0.1,
        le=60.0,
        description="Socket timeout in seconds"
    )
    compression_threshold: int = Field(
        default=1024,
        ge=0,
        description="Compression threshold in bytes"
    )
    key_prefix: str = Field(
        default="ai_aggregator:",
        description="Redis key prefix"
    )

class SecuritySettings(BaseSettings):
    """Security configuration with JWT and API key management"""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )
    
    secret_key: str = Field(
        description="Secret key for JWT signing"
    )
    jwt_algorithm: str = Field(
        default="HS256",
        description="JWT signing algorithm"
    )
    jwt_expire_minutes: int = Field(
        default=1440,  # 24 hours
        ge=1,
        le=43200,  # 30 days
        description="JWT expiration time in minutes"
    )
    api_key_header: str = Field(
        default="X-API-Key",
        description="API key header name"
    )
    allowed_origins: List[str] = Field(
        default_factory=list,
        description="CORS allowed origins"
    )
    trusted_hosts: List[str] = Field(
        default_factory=list,
        description="Trusted host list"
    )
    rate_limit_per_minute: int = Field(
        default=60,
        ge=1,
        le=10000,
        description="Rate limit per minute"
    )
    rate_limit_burst: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Rate limit burst allowance"
    )
    
    @field_validator('secret_key')
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError('Secret key must be at least 32 characters long')
        return v

class MonitoringSettings(BaseSettings):
    """Monitoring and observability configuration"""
    model_config = SettingsConfigDict(
        env_prefix="MONITORING_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )
    
    enable_metrics: bool = Field(
        default=True,
        description="Enable metrics collection"
    )
    perf_threshold_warning: float = Field(
        default=5.0,
        ge=0.1,
        description="Performance warning threshold in seconds"
    )
    perf_threshold_error: float = Field(
        default=30.0,
        ge=1.0,
        description="Performance error threshold in seconds"
    )
    threshold_high_latency: float = Field(
        default=5.0,
        ge=0.1,
        description="High latency threshold in seconds"
    )
    threshold_high_error_rate: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="High error rate threshold (0-1)"
    )
    threshold_low_cache_hit_ratio: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Low cache hit ratio threshold (0-1)"
    )
    threshold_high_ai_cost_hourly: float = Field(
        default=50.0,
        ge=0.0,
        description="High AI cost threshold per hour in USD"
    )
    metrics_port: int = Field(
        default=9090,
        ge=1024,
        le=65535,
        description="Metrics server port"
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level"
    )
    log_format: str = Field(
        default="json",
        description="Log format (json or text)"
    )
    enable_tracing: bool = Field(
        default=False,
        description="Enable distributed tracing"
    )
    jaeger_endpoint: Optional[str] = Field(
        default=None,
        description="Jaeger collector endpoint"
    )
    health_check_interval: int = Field(
        default=30,
        ge=5,
        le=300,
        description="Health check interval in seconds"
    )
    
    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in allowed_levels:
            raise ValueError(f'Log level must be one of {allowed_levels}')
        return v.upper()
    
    @field_validator('log_format')
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        allowed_formats = ['json', 'text']
        if v.lower() not in allowed_formats:
            raise ValueError(f'Log format must be one of {allowed_formats}')
        return v.lower()

class AISettings(BaseSettings):
    """AI provider configuration with cost optimization"""
    model_config = SettingsConfigDict(
        env_prefix="AI_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )
    
    default_provider: str = Field(
        default="ollama",
        description="Default AI provider"
    )
    max_concurrent_requests: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum concurrent AI requests"
    )
    request_timeout: int = Field(
        default=60,
        ge=1,
        le=300,
        description="AI request timeout in seconds"
    )
    cost_threshold_daily: float = Field(
        default=10.0,
        ge=0.0,
        description="Daily cost threshold in USD"
    )
    cost_threshold_monthly: float = Field(
        default=300.0,
        ge=0.0,
        description="Monthly cost threshold in USD"
    )
    free_tier_prioritization: bool = Field(
        default=True,
        description="Prioritize free tier providers"
    )
    auto_prompt_optimization: bool = Field(
        default=True,
        description="Enable automatic prompt optimization"
    )
    dynamic_provider_selection: bool = Field(
        default=True,
        description="Enable dynamic provider selection"
    )

class AppSettings(BaseSettings):
    """Main application settings"""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )
    
    app_name: str = Field(
        default="AI Aggregator Pro",
        description="Application name"
    )
    version: str = Field(
        default="3.1.0",
        description="Application version"
    )
    environment: str = Field(
        default="development",
        description="Deployment environment"
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode"
    )
    host: str = Field(
        default="0.0.0.0",
        description="Server host address"
    )
    port: int = Field(
        default=8000,
        ge=1024,
        le=65535,
        description="Server port"
    )
    workers: int = Field(
        default=1,
        ge=1,
        le=32,
        description="Number of worker processes"
    )
    enable_websockets: bool = Field(
        default=True,
        description="Enable WebSocket support"
    )
    enable_graphql: bool = Field(
        default=False,
        description="Enable GraphQL endpoint"
    )
    enable_admin_panel: bool = Field(
        default=True,
        description="Enable admin panel"
    )
    
    # Sub-configurations
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)
    ai: AISettings = Field(default_factory=AISettings)
    
    @computed_field
    @property
    def python_version(self) -> str:
        """Get current Python version"""
        return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    
    @computed_field
    @property
    def enable_metrics(self) -> bool:
        """Check if metrics are available and enabled"""
        return METRICS_AVAILABLE and self.monitoring.enable_metrics
    
    @field_validator('environment')
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = ['development', 'staging', 'production']
        if v not in allowed:
            raise ValueError(f'Environment must be one of {allowed}')
        return v

# ----------------------------------------
# Settings Factory
# ----------------------------------------
@lru_cache()
def get_settings() -> AppSettings:
    """Get cached application settings"""
    try:
        file_config = load_config_file()
        return AppSettings(**file_config)
    except Exception as e:
        print(f"❌ Failed to load configuration: {str(e)}")
        raise SystemExit(1)

# Global settings instance
settings = get_settings()

# Export commonly used settings
__all__ = [
    'settings',
    'AppSettings',
    'DatabaseSettings', 
    'RedisSettings',
    'SecuritySettings',
    'MonitoringSettings',
    'AISettings',
    'get_settings'
]