# config/settings.py - Advanced configuration management with environment-specific settings
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseSettings, Field, validator
from pydantic_settings import BaseSettings
import yaml
from functools import lru_cache

class DatabaseSettings(BaseSettings):
    """Database configuration with optimization settings"""
    url: str = Field(default="sqlite+aiosqlite:///./app.db", env="DATABASE_URL")
    pool_size: int = Field(default=20, env="DB_POOL_SIZE")
    max_overflow: int = Field(default=30, env="DB_MAX_OVERFLOW")
    pool_timeout: int = Field(default=30, env="DB_POOL_TIMEOUT")
    echo: bool = Field(default=False, env="DB_ECHO")
    
    # Performance optimizations
    query_cache_size: int = Field(default=1000, env="DB_QUERY_CACHE_SIZE")
    connection_pool_recycle: int = Field(default=3600, env="DB_CONNECTION_RECYCLE")

class RedisSettings(BaseSettings):
    """Redis configuration with clustering support"""
    url: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    cluster_mode: bool = Field(default=False, env="REDIS_CLUSTER_MODE")
    cluster_nodes: List[str] = Field(default_factory=list, env="REDIS_CLUSTER_NODES")
    max_connections: int = Field(default=50, env="REDIS_MAX_CONNECTIONS")
    socket_timeout: float = Field(default=5.0, env="REDIS_SOCKET_TIMEOUT")
    
    # Advanced settings
    compression_threshold: int = Field(default=1024, env="REDIS_COMPRESSION_THRESHOLD")
    key_prefix: str = Field(default="ai_aggregator:", env="REDIS_KEY_PREFIX")

class SecuritySettings(BaseSettings):
    """Security configuration with JWT and API key management"""
    secret_key: str = Field(env="SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", env="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(default=1440, env="JWT_EXPIRE_MINUTES")  # 24 hours
    
    # API Security
    api_key_header: str = Field(default="X-API-Key", env="API_KEY_HEADER")
    allowed_origins: List[str] = Field(default_factory=list, env="ALLOWED_ORIGINS")
    trusted_hosts: List[str] = Field(default_factory=list, env="TRUSTED_HOSTS")
    
    # Rate limiting
    rate_limit_per_minute: int = Field(default=60, env="RATE_LIMIT_PER_MINUTE")
    rate_limit_burst: int = Field(default=10, env="RATE_LIMIT_BURST")

class MonitoringSettings(BaseSettings):
    """Monitoring and observability configuration"""
    enable_metrics: bool = Field(default=True, env="ENABLE_METRICS")
    metrics_port: int = Field(default=9090, env="METRICS_PORT")
    
    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_format: str = Field(default="json", env="LOG_FORMAT")  # json or text
    
    # Tracing
    enable_tracing: bool = Field(default=False, env="ENABLE_TRACING")
    jaeger_endpoint: Optional[str] = Field(default=None, env="JAEGER_ENDPOINT")
    
    # Health checks
    health_check_interval: int = Field(default=30, env="HEALTH_CHECK_INTERVAL")

class AISettings(BaseSettings):
    """AI provider configuration with cost optimization"""
    default_provider: str = Field(default="ollama", env="AI_DEFAULT_PROVIDER")
    max_concurrent_requests: int = Field(default=20, env="AI_MAX_CONCURRENT")
    request_timeout: int = Field(default=60, env="AI_REQUEST_TIMEOUT")
    
    # Cost optimization
    cost_threshold_daily: float = Field(default=10.0, env="AI_COST_THRESHOLD_DAILY")
    cost_threshold_monthly: float = Field(default=300.0, env="AI_COST_THRESHOLD_MONTHLY")
    free_tier_prioritization: bool = Field(default=True, env="AI_FREE_TIER_PRIORITY")
    
    # Smart features
    auto_prompt_optimization: bool = Field(default=True, env="AI_AUTO_PROMPT_OPTIMIZATION")
    dynamic_provider_selection: bool = Field(default=True, env="AI_DYNAMIC_PROVIDER_SELECTION")

class AppSettings(BaseSettings):
    """Main application settings"""
    app_name: str = Field(default="AI Aggregator Pro", env="APP_NAME")
    version: str = Field(default="3.1.0", env="APP_VERSION")
    environment: str = Field(default="development", env="ENVIRONMENT")
    python_version: str = Field(default=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    debug: bool = Field(default=False, env="DEBUG")
    
    # Server settings
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT")
    workers: int = Field(default=1, env="WORKERS")
    
    # Feature flags
    enable_websockets: bool = Field(default=True, env="ENABLE_WEBSOCKETS")
    enable_graphql: bool = Field(default=False, env="ENABLE_GRAPHQL")
    enable_admin_panel: bool = Field(default=True, env="ENABLE_ADMIN_PANEL")
    
    # Sub-configurations
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    monitoring: MonitoringSettings = Field(default_factory=MonitoringSettings)
    ai: AISettings = Field(default_factory=AISettings)
    
    @validator('environment')
    def validate_environment(cls, v):
        allowed = ['development', 'staging', 'production']
        if v not in allowed:
            raise ValueError(f'Environment must be one of {allowed}')
        return v
    
    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
        case_sensitive = False

@lru_cache()
def get_settings() -> AppSettings:
    """Get cached application settings"""
    return AppSettings()

# Global settings instance
settings = get_settings()