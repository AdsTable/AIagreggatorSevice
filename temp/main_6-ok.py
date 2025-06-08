# main.py - Python 3.13 Compatible AI Aggregator Pro
from __future__ import annotations

import os
import sys
import requests
import streamlit as st
import json
import sqlite3
from aiohttp import ClientSession
from bs4 import BeautifulSoup
import logging

import platform
import time
import asyncio
import gzip
import pickle
from contextlib import asynccontextmanager
from functools import lru_cache, wraps
from typing import Any, Dict, List, Optional, Union, AsyncGenerator, Callable
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import hashlib
import yaml
import aiofiles
from enum import Enum
#from config.settings import settings, METRICS_AVAILABLE, REDIS_AVAILABLE, database_settings, DatabaseSettings

# Enhanced imports with performance monitoring
from performance_monitor import (
    PerformanceMonitor, PerformanceThresholds, OperationType,
    monitor_performance, monitor_ai_operation, monitor_cache_operation,
    get_performance_monitor, set_performance_monitor, get_performance_stats
)

# Redis imports with Python 3.13 compatibility
try:
    from redis.asyncio import Redis
    REDIS_AVAILABLE = True
except ImportError:
    try:
        import aioredis
        Redis = aioredis.Redis
        REDIS_AVAILABLE = True
    except ImportError:
        REDIS_AVAILABLE = False
        Redis = None

from dotenv import load_dotenv

# FastAPI and middleware imports
from fastapi import (
    FastAPI, HTTPException, Query, Body, Depends, Request, 
    BackgroundTasks, status, Response
)
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import Field, validator, ValidationError, BaseModel, ConfigDict, field_validator, computed_field
from pydantic_settings import  BaseSettings

# Database and async imports
from sqlalchemy.ext.asyncio import AsyncSession

# Modern rate limiting implementation - replacing SlowAPI
import asyncio
from collections import defaultdict
from typing import Dict, Tuple
import time

# Import business logic modules with error handling
try:
    from services.ai_async_client import AIAsyncClient
except ImportError as e:
    logging.warning(f"AI client import failed: {e}")
    AIAsyncClient = None

try:
    from product_schema import Product, ApiResponse
    from models import StandardizedProduct
    from database import create_db_and_tables, get_session
    from data_discoverer import discover_and_extract_data
    from data_parser import parse_and_standardize
    from data_storage import store_standardized_data
    from data_search import search_and_filter_products
except ImportError as e:
    logging.warning(f"Business logic import failed: {e}")

# Enhanced logging with structured format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
    handlers=[
        logging.FileHandler('app.log', mode='a', encoding='utf-8'),  # Use utf-8 for emoji support
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables from a .env file
load_dotenv()

# --- Modern Rate Limiter Implementation ---
class ModernRateLimiter:
    """
    Python 3.13 compatible rate limiter with sliding window algorithm
    """
    
    def __init__(self):
        self.requests: Dict[str, List[float]] = defaultdict(list)
        self.locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
    
    async def is_allowed(self, key: str, limit: int, window: int = 60) -> bool:
        """
        Check if request is allowed based on rate limit
        
        Args:
            key: Unique identifier (IP, user ID, etc.)
            limit: Maximum requests allowed
            window: Time window in seconds
        
        Returns:
            True if request is allowed, False otherwise
        """
        current_time = time.time()
        
        async with self.locks[key]:
            # Clean old requests outside the window
            self.requests[key] = [
                req_time for req_time in self.requests[key]
                if current_time - req_time < window
            ]
            
            # Check if under limit
            if len(self.requests[key]) < limit:
                self.requests[key].append(current_time)
                return True
            
            return False
    
    def get_remaining(self, key: str, limit: int, window: int = 60) -> int:
        """Get remaining requests in current window"""
        current_time = time.time()
        recent_requests = [
            req_time for req_time in self.requests.get(key, [])
            if current_time - req_time < window
        ]
        return max(0, limit - len(recent_requests))

# Global rate limiter instance
rate_limiter = ModernRateLimiter()

# --- Rate Limiting Decorator ---
def rate_limit(requests_per_minute: int = 60):
    """
    Modern rate limiting decorator compatible with Python 3.13
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request from args
            request: Optional[Request] = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if not request:
                # If no request found, allow the call
                return await func(*args, **kwargs)
            
            # Get client identifier
            client_ip = request.client.host if request.client else "unknown"
            rate_limit_key = f"rate_limit:{client_ip}:{func.__name__}"
            
            # Check rate limit
            is_allowed = await rate_limiter.is_allowed(
                rate_limit_key, 
                requests_per_minute, 
                60
            )
            
            if not is_allowed:
                remaining = rate_limiter.get_remaining(rate_limit_key, requests_per_minute, 60)
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Try again later. Remaining: {remaining}",
                    headers={"Retry-After": "60"}
                )
            
            # Record metrics if available
            if METRICS_AVAILABLE:
                REQUEST_COUNT.labels(provider='system', status='allowed').inc()
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator

# --- Enhanced Configuration Management ---
@dataclass
class DatabaseConfig:
    """Database configuration with connection pooling"""
    url: str = os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./database.db')
    pool_size: int = int(os.getenv('DB_POOL_SIZE', '20'))
    max_overflow: int = int(os.getenv('DB_MAX_OVERFLOW', '30'))
    echo: bool = os.getenv('DB_ECHO', 'false').lower() == 'true'

@dataclass
class RedisConfig:
    """Redis configuration with fallback options"""
    url: str = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    max_connections: int = int(os.getenv('REDIS_MAX_CONNECTIONS', '20'))
    socket_timeout: float = float(os.getenv('REDIS_SOCKET_TIMEOUT', '5.0'))
    encoding: str = 'utf-8'
    decode_responses: bool = False

@dataclass
class SecurityConfig:
    """Security configuration"""
    secret_key: str = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    api_key_header: str = os.getenv('API_KEY_HEADER', 'X-API-Key')
    allowed_origins: List[str] = field(default_factory=lambda: 
        os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000,http://localhost:8080').split(',')
    )
    trusted_hosts: List[str] = field(default_factory=lambda: 
        os.getenv('TRUSTED_HOSTS', '').split(',') if os.getenv('TRUSTED_HOSTS') else []
    )

@dataclass
class AIConfig:
    """AI provider configuration"""
    default_provider: str = os.getenv('AI_DEFAULT_PROVIDER', 'ollama')
    max_concurrent_requests: int = int(os.getenv('MAX_CONCURRENT_AI_REQUESTS', '15'))
    request_timeout: int = int(os.getenv('AI_REQUEST_TIMEOUT', '45'))
    max_prompt_length: int = int(os.getenv('MAX_PROMPT_LENGTH', '32000'))
    
    free_tier_limits: Dict[str, int] = field(default_factory=lambda: {
        'ollama': 999999,
        'huggingface': 1000,
        'together': 25,
        'openai': 3,
    })

@dataclass
class AppConfig:
    """Main application configuration with Python 3.13 optimizations"""
    app_name: str = os.getenv('APP_NAME', 'AI Aggregator Pro')
    version: str = platform.python_version()
    print(version)
    environment: str = os.getenv('ENVIRONMENT', 'development')
    debug: bool = os.getenv('DEBUG', 'false').lower() == 'true'
    
    # Корректное получение версии Python
    python_version: str = f"{sys.version_info.major}.{sys.version_info.minor}"

    # Feature flags
    enable_cache: bool = REDIS_AVAILABLE and os.getenv('ENABLE_CACHE', 'true').lower() == 'true'
    enable_compression: bool = os.getenv('ENABLE_COMPRESSION', 'true').lower() == 'true'
    enable_metrics: bool = os.getenv('ENABLE_METRICS', 'true').lower() == 'true'
    
    # Cache settings
    cache_ttl_short: int = int(os.getenv('CACHE_TTL_SHORT', '900'))
    cache_ttl_long: int = int(os.getenv('CACHE_TTL_LONG', '3600'))

    # Sub-configurations
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    ai: AIConfig = field(default_factory=AIConfig)

# Global configuration instance
config = AppConfig()

# --- Circuit Breaker Pattern ---
@dataclass
class CircuitBreaker:
    """Circuit breaker for provider failure handling"""
    failure_threshold: int = 5
    recovery_timeout: int = 60
    failure_count: int = 0
    last_failure_time: Optional[float] = None
    state: str = "CLOSED"
    
    def is_request_allowed(self) -> bool:
        """Check if request is allowed based on circuit breaker state"""
        if self.state == "CLOSED":
            return True
        elif self.state == "OPEN":
            if time.time() - (self.last_failure_time or 0) > self.recovery_timeout:
                self.state = "HALF_OPEN"
                return True
            return False
        else:  # HALF_OPEN
            return True
    
    def record_success(self):
        """Record successful request"""
        self.failure_count = 0
        self.state = "CLOSED"
    
    def record_failure(self):
        """Record failed request"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"

# --- Advanced Caching System ---
class AdvancedCache:
    """High-performance cache with compression and smart TTL"""
    
    @staticmethod
    def compress_data(data: Any) -> bytes:
        """Compress data using gzip for storage efficiency"""
        serialized = pickle.dumps(data)
        if config.enable_compression:
            return gzip.compress(serialized)
        return serialized
    
    @staticmethod
    def decompress_data(data: bytes) -> Any:
        """Decompress data"""
        if config.enable_compression:
            try:
                decompressed = gzip.decompress(data)
                return pickle.loads(decompressed)
            except gzip.BadGzipFile:
                return pickle.loads(data)
        return pickle.loads(data)
    
    @staticmethod
    async def get_cached(redis_client: Redis, key: str) -> Optional[Any]:
        """Get and decompress cached data"""
        if not redis_client:
            return None
            
        try:
            data = await redis_client.get(key)
            if data:
                if config.enable_metrics:
                    CACHE_HITS.labels(cache_type='redis').inc()
                return AdvancedCache.decompress_data(data)
        except Exception as e:
            logger.warning(f"Cache read error for key {key}: {e}")
        return None
    
    @staticmethod
    async def set_cached(redis_client: Redis, key: str, value: Any, ttl: int):
        """Compress and cache data"""
        if not redis_client:
            return
            
        try:
            compressed_data = AdvancedCache.compress_data(value)
            await redis_client.setex(key, ttl, compressed_data)
        except Exception as e:
            logger.warning(f"Cache write error for key {key}: {e}")

# --- Token Optimization ---
class TokenOptimizer:
    """Advanced token counting and optimization utilities"""
    
    TOKEN_MULTIPLIERS = {
        "openai": 4.0,
        "moonshot": 4.0,
        "together": 3.6,
        "huggingface": 3.2,
        "ollama": 2.8,
        "claude": 4.2,
    }
    
    @staticmethod
    def estimate_tokens(text: str, provider: str = "openai") -> int:
        """Estimate token count for different providers"""
        if not text:
            return 0
        
        multiplier = TokenOptimizer.TOKEN_MULTIPLIERS.get(provider, 4.0)
        return max(1, int(len(text) / multiplier))
    
    @staticmethod
    def optimize_prompt(prompt: str, max_tokens: int = 4000, provider: str = "openai") -> str:
        """Optimize prompt to reduce token usage"""
        estimated_tokens = TokenOptimizer.estimate_tokens(prompt, provider)
        
        if estimated_tokens <= max_tokens:
            return prompt
        
        reduction_ratio = max_tokens / estimated_tokens
        keep_length = int(len(prompt) * reduction_ratio)
        
        if keep_length < 200:
            return prompt[:200] + "..."
        
        first_part_len = int(keep_length * 0.6)
        last_part_len = int(keep_length * 0.4)
        
        first_part = prompt[:first_part_len]
        last_part = prompt[-last_part_len:]
        
        return f"{first_part}...[optimized]...{last_part}"

# --- Resource Management ---
class ResourceManager:
    """Centralized resource management with proper cleanup"""
    
    def __init__(self):
        self.ai_config_cache: Optional[Dict[str, Any]] = None
        self.config_last_modified: Optional[float] = None
        self.ai_client_instance: Optional[AIAsyncClient] = None
        self.redis_client: Optional[Redis] = None
        self.ai_semaphore: Optional[asyncio.Semaphore] = None
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.request_stats: Dict[str, Dict[str, Any]] = {}
    
    async def initialize_redis(self) -> Optional[Redis]:
        """Initialize Redis client with proper error handling"""
        if not REDIS_AVAILABLE or not config.enable_cache:
            logger.info("Redis not available or disabled")
            return None
        
        try:
            if hasattr(Redis, 'from_url'):
                redis_client = Redis.from_url(
                    config.redis.url,
                    encoding=config.redis.encoding,
                    decode_responses=config.redis.decode_responses,
                    max_connections=config.redis.max_connections,
                    socket_timeout=config.redis.socket_timeout
                )
            else:
                redis_client = Redis(
                    host='localhost',
                    port=6379,
                    db=0,
                    encoding=config.redis.encoding,
                    decode_responses=config.redis.decode_responses
                )
            
            await redis_client.ping()
            self.redis_client = redis_client
            logger.info("✅ Redis connection established")
            return redis_client
            
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}, proceeding without cache")
            self.redis_client = None
            return None
    
    async def initialize_ai_client(self) -> Optional[AIAsyncClient]:
        """Initialize AI client with enhanced error handling"""
        if not AIAsyncClient:
            logger.error("AIAsyncClient not available")
            return None
        
        try:
            ai_config = await self.load_ai_config()
            if not ai_config:
                logger.error("No AI configuration available")
                return None
            
            self.ai_client_instance = AIAsyncClient(ai_config)
            
            for provider in ai_config.keys():
                self.circuit_breakers[provider] = CircuitBreaker()
                self.request_stats[provider] = {
                    'total_requests': 0,
                    'successful_requests': 0,
                    'failed_requests': 0,
                    'total_tokens': 0,
                    'total_cost': 0.0,
                    'average_latency': 0.0
                }
            
            logger.info(f"✅ AI client initialized with {len(ai_config)} providers")
            return self.ai_client_instance
            
        except Exception as e:
            logger.error(f"Failed to initialize AI client: {e}")
            return None
    
    async def load_ai_config(self, force_reload: bool = False) -> Dict[str, Any]:
        """Load AI configuration with enhanced validation"""
        config_path = Path("ai_integrations.yaml")
        
        if not config_path.exists():
            logger.error(f"Configuration file {config_path} not found")
            return {}
        
        current_mtime = config_path.stat().st_mtime
        
        if (not force_reload and self.ai_config_cache and 
            self.config_last_modified == current_mtime):
            return self.ai_config_cache
        
        try:
            async with aiofiles.open(config_path, mode='r', encoding='utf-8') as f:
                content = await f.read()
            
            cfg = yaml.safe_load(content) or {}
            
            for provider, settings in cfg.items():
                if not isinstance(settings, dict):
                    continue
                
                if provider in config.ai.free_tier_limits:
                    settings.setdefault('daily_limit', str(config.ai.free_tier_limits[provider]))
                    settings.setdefault('priority', 'high' if provider == 'ollama' else 'medium')
                
                for key, value in list(settings.items()):
                    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                        env_key = value[2:-1]
                        env_value = os.getenv(env_key)
                        if env_value is None:
                            logger.warning(f"Environment variable {env_key} not found for {provider}.{key}")
                            del settings[key]
                        else:
                            settings[key] = env_value
                    
                    elif key in ['max_tokens', 'timeout', 'rate_limit', 'priority_score']:
                        try:
                            settings[key] = int(value) if isinstance(value, str) else value
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid numeric value for {provider}.{key}: {value}")
                    
                    elif key in ['cost_per_1k_tokens', 'temperature']:
                        try:
                            settings[key] = float(value) if isinstance(value, str) else value
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid float value for {provider}.{key}: {value}")
            
            self.ai_config_cache = cfg
            self.config_last_modified = current_mtime
            logger.info(f"✅ AI configuration loaded with {len(cfg)} providers")
            return cfg
            
        except (yaml.YAMLError, ValueError, IOError) as e:
            logger.error(f"Failed to load AI configuration: {e}")
            return {}
    
    def get_ai_semaphore(self) -> asyncio.Semaphore:
        """Get or create AI request semaphore"""
        if self.ai_semaphore is None:
            self.ai_semaphore = asyncio.Semaphore(config.ai.max_concurrent_requests)
        return self.ai_semaphore
    
    async def cleanup(self):
        """Cleanup all resources with Python 3.13 exception handling"""
        cleanup_tasks = []
        
        if self.ai_client_instance and hasattr(self.ai_client_instance, 'aclose'):
            cleanup_tasks.append(self.ai_client_instance.aclose())
        
        if self.redis_client and hasattr(self.redis_client, 'close'):
            cleanup_tasks.append(self.redis_client.close())
        
        if cleanup_tasks:
            try:
                # Python 3.13 compatible exception handling
                results = await asyncio.gather(*cleanup_tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, Exception):
                        logger.error(f"Error during cleanup: {result}")
            except* Exception as eg:  # Python 3.13 exception groups
                for exc in eg.exceptions:
                    logger.error(f"Cleanup exception: {exc}")
        
        logger.info("✅ Resource cleanup completed")

class OperationType(Enum):
    """Types of operations for specialized monitoring"""
    AI_REQUEST = "ai_request"
    CACHE_OPERATION = "cache_operation"
    DATABASE_OPERATION = "database_operation"
    NETWORK_OPERATION = "network_operation"
    COMPUTATION = "computation"

@dataclass
class OperationMetrics:
    """Comprehensive operation metrics"""
    operation_name: str
    operation_type: OperationType
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    success: bool = False
    error: Optional[Exception] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def finalize(self, success: bool = True, error: Optional[Exception] = None) -> None:
        """Finalize metrics calculation"""
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        self.success = success
        self.error = error

class Metrics:
    def __init__(self, app_name: str):
        self.app_name = app_name
        self.active_operations = {}

    def record_operation(self, metrics: OperationMetrics) -> None:
        # Логика для записи операционных метрик
        print(f"Recording metrics for operation: {metrics.operation_name}")

    def increment_counter(self, name: str, labels: Dict[str, str]) -> None:
        # Логика для увеличения счетчика метрик
        pass

    def observe_histogram(self, name: str, value: float, labels: Dict[str, str]) -> None:
        # Логика для наблюдения за значениями гистограммы
         pass

# Пример использования класса Metrics с правильным аргументом
metrics_collector = Metrics(app_name="AI Aggregator Pro")  

# Создаем экземпляр мониторинга производительности
monitor = PerformanceMonitor(metrics_collector)

# Пример вызова monitor_operation
async def main():
    async with monitor.monitor_operation("example_operation", OperationType.COMPUTATION):
        pass  # Здесь можно выполнять какую-либо логику операции

# Запускаем асинхронную функцию
# asyncio.run(main())  # Раскомментарьте, чтобы запустить при необходимости
        

class PerformanceMonitor:
    def __init__(self, metrics_collector: Metrics):
        self.metrics_collector = metrics_collector
        self.active_operations = {}

    def _generate_operation_id(self) -> str:
        return str(id(self))

    async def monitor_operation(self, 
                                operation_name: str,
                                operation_type: OperationType = OperationType.COMPUTATION,
                                metadata: Dict[str, Any] = None):
        """Context manager for monitoring operations"""
        operation_id = self._generate_operation_id()
        
        metrics = OperationMetrics(
            operation_name=operation_name,
            operation_type=operation_type,
            start_time=time.time(),
            metadata=metadata or {}
        )
        
        self.active_operations[operation_id] = metrics
        
        try:
            if hasattr(self.metrics_collector, 'active_operations'):
                self.metrics_collector.active_operations[operation_type.value] = self.metrics_collector.active_operations.get(operation_type.value, 0) + 1
            
            yield metrics
            
            metrics.finalize(success=True)
            
        except Exception as e:
            logger.error(f"Exception in {operation_name}: {e}")
            metrics.finalize(success=False, error=e)
            raise
            
        finally:
            self.active_operations.pop(operation_id, None)
            if hasattr(self.metrics_collector, 'active_operations'):
                self.metrics_collector.active_operations[operation_type.value] -= 1
            
            self.metrics_collector.record_operation(metrics)


metrics_collector = Metrics(app_name="AI Aggregator Pro")
monitor = PerformanceMonitor(metrics_collector)


# Global resource manager
resources = ResourceManager()

# --- Utility Functions ---
def generate_cache_key(prefix: str, *args, **kwargs) -> str:
    """Generate consistent cache key"""
    args_str = ':'.join(str(arg) for arg in args)
    kwargs_str = ':'.join(f'{k}={v}' for k, v in sorted(kwargs.items()))
    
    key_data = f"{prefix}:{args_str}:{kwargs_str}"
    return hashlib.sha256(key_data.encode()).hexdigest()[:32]

def monitor_performance(operation_name: str):
    """Decorator for performance monitoring"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            operation_success = False
            
            try:
                result = await func(*args, **kwargs)
                operation_success = True
                return result
            except Exception as e:
                # Обработка исключений. Это блок обработает как обычные, так и исключения групп
                if config.enable_metrics:
                    provider = kwargs.get('provider', 'unknown')
                    Metrics.REQUEST_COUNT['labels'](provider=provider, status='error')
                
                # Логируем неуспех операции
                logger.error(f"Operation {operation_name} failed with exception: {e}")
                raise  # Перекидываем вверх исключение для дальнейшей обработки
            
            finally:
                duration = time.time() - start_time
                
                if config.enable_metrics:
                    Metrics.REQUEST_DURATION['observe'](duration)
                    if operation_success:
                        provider = kwargs.get('provider', 'unknown')
                        Metrics.REQUEST_COUNT['labels'](provider=provider, status='success')
                
                if duration > 5.0:
                    logger.warning(f"Slow operation {operation_name}: {duration:.2f}s")
        
        return wrapper
    return decorator

# --- Enhanced Pydantic Models ---
class AIRequest(BaseModel):
    """Enhanced AI request model with comprehensive validation"""
    prompt: str
    provider: str = "auto"
    max_tokens: Optional[int] = None
    temperature: float = 0.7
    use_cache: bool = True
    optimize_tokens: bool = True
    priority: str = "medium"
    
    model_config = ConfigDict(frozen=True)

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Prompt cannot be empty")
        if len(v) > config.ai.max_prompt_length:
            raise ValueError(f"Prompt too long (max {config.ai.max_prompt_length} characters)")
        return v.strip()

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        allowed = frozenset([
            "auto", "openai", "moonshot", "together", "huggingface", 
            "ollama", "claude", "minimax", "local"
        ])
        if v not in allowed:
            raise ValueError(f"Provider must be one of: {list(allowed)}")
        return v

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        if not 0.0 <= v <= 2.0:
            raise ValueError("Temperature must be between 0.0 and 2.0")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        if v not in ["low", "medium", "high"]:
            raise ValueError("Priority must be one of: low, medium, high")
        return v

    @computed_field
    @property
    def estimated_cost(self) -> float:
        """Estimate request cost based on provider and prompt length"""
        if self.provider in ["ollama", "huggingface", "local"]:
            return 0.0
        
        token_count = TokenOptimizer.estimate_tokens(self.prompt, self.provider)
        
        costs = {
            "openai": 0.002,
            "claude": 0.0015,
            "together": 0.0008,
            "moonshot": 0.0012,
            "minimax": 0.001,
        }
        
        return (token_count / 1000) * costs.get(self.provider, 0.01)

class HealthResponse(BaseModel):
    """Comprehensive health check response"""
    status: str
    version: str
    python_version: str
    timestamp: datetime
    ai_client_ready: bool
    ai_providers_status: Dict[str, str]
    redis_available: bool
    database_connected: bool
    uptime_seconds: float
    cache_hit_rate: float = 0.0
    total_requests: int = 0
    active_connections: int = 0
    features_enabled: Dict[str, bool] = {}
    
    model_config = ConfigDict(frozen=True)

# --- Smart Provider Selection ---
async def select_optimal_provider(request: AIRequest, available_providers: List[str]) -> str:
    """Select optimal provider based on multiple factors"""
    
    if request.provider != "auto":
        if request.provider in available_providers:
            return request.provider
        else:
            logger.warning(f"Requested provider {request.provider} not available, using auto-selection")
    
    healthy_providers = []
    for provider in available_providers:
        circuit_breaker = resources.circuit_breakers.get(provider)
        if not circuit_breaker or circuit_breaker.is_request_allowed():
            healthy_providers.append(provider)
    
    if not healthy_providers:
        raise HTTPException(
            status_code=503, 
            detail="No healthy AI providers available"
        )
    
    scores = {}
    for provider in healthy_providers:
        score = 0
        
        if provider in config.ai.free_tier_limits:
            if config.ai.free_tier_limits[provider] > 1000:
                score += 100
            else:
                score += 80
        else:
            score += 20
        
        performance_scores = {
            'ollama': 90,
            'huggingface': 75,
            'together': 70,
            'claude': 65,
            'openai': 60,
            'moonshot': 55,
        }
        score += performance_scores.get(provider, 40)
        
        if request.priority == "high":
            if provider in ['openai', 'claude']:
                score += 30
        elif request.priority == "low":
            if provider in ['ollama', 'huggingface']:
                score += 40
        
        circuit_breaker = resources.circuit_breakers.get(provider)
        if circuit_breaker and circuit_breaker.failure_count > 0:
            score -= circuit_breaker.failure_count * 10
        
        scores[provider] = score
    
    optimal_provider = max(scores, key=scores.get)
    logger.info(f"🎯 Selected provider: {optimal_provider} (score: {scores[optimal_provider]})")
    
    return optimal_provider

# --- Application Lifecycle with Python 3.13 Support ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Enhanced application lifecycle management with Python 3.13 compatibility"""
    start_time = time.time()
    app.state.start_time = start_time
    
    logger.info(f"🚀 Starting {config.app_name} v{config.version}")
    logger.info(f"Environment: {config.environment}")
    logger.info(f"Python version: {config.python_version}")
    logger.info(f"Features: Cache={config.enable_cache}, Metrics={config.enable_metrics}, Compression={config.enable_compression}")

    try:
        # Initialize database
        if 'create_db_and_tables' in globals():
            await create_db_and_tables()
            logger.info("✅ Database initialized")
        
        # Initialize Redis cache
        if config.enable_cache:
            await resources.initialize_redis()
        
        # Initialize AI client
        await resources.initialize_ai_client()
        
        logger.info("🎉 All services ready!")
        yield
        
    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
        raise
    finally:
        logger.info("🔄 Shutting down services...")
        await resources.cleanup()
        logger.info("✅ Shutdown completed")

# --- FastAPI Application ---

print(vars(metrics_collector))

app = FastAPI(
    title=config.app_name,
    description=f"Next-generation AI service optimized for Python {config.python_version}",
    version=config.version,
    lifespan=lifespan,
    docs_url="/docs" if config.environment != 'production' else None,
    redoc_url="/redoc" if config.environment != 'production' else None
)

# --- Middleware Stack (Fixed Order) ---

# Compression middleware (first for response processing)
if config.enable_compression:
    app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.security.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    max_age=3600,
)

# Trusted hosts middleware
if config.security.trusted_hosts:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=config.security.trusted_hosts
    )

# --- Core API Endpoints ---

@app.post("/ai/ask")
@rate_limit(50)  # Using our custom rate limiter
@monitor_performance("ai_ask")
async def ai_ask(
    request: Request,
    ai_request: AIRequest,
    background_tasks: BackgroundTasks,
    stream: bool = Query(False, description="Enable streaming response")
):
    """Ultra-optimized AI query with smart provider selection and Python 3.13 compatibility"""
    
    optimized_prompt = ai_request.prompt
    if ai_request.optimize_tokens:
        optimized_prompt = TokenOptimizer.optimize_prompt(
            ai_request.prompt, 
            provider=ai_request.provider
        )
    
    cache_key = None
    if config.enable_cache and ai_request.use_cache:
        cache_key = generate_cache_key(
            "ai_ask_v3",  # Updated version for Python 3.13
            optimized_prompt,
            ai_request.provider,
            ai_request.temperature,
            ai_request.max_tokens or 0
        )
    
    if cache_key and resources.redis_client:
        cached_result = await AdvancedCache.get_cached(resources.redis_client, cache_key)
        if cached_result:
            logger.info("💾 Cache hit for AI request")
            cached_result['cached'] = True
            return cached_result

    ai_client = resources.ai_client_instance
    if not ai_client:
        raise HTTPException(status_code=503, detail="AI service not available")
    
    ai_config = await resources.load_ai_config()
    available_providers = list(ai_config.keys())
    
    if not available_providers:
        raise HTTPException(status_code=503, detail="No AI providers configured")
    
    selected_provider = await select_optimal_provider(ai_request, available_providers)
    
    circuit_breaker = resources.circuit_breakers.get(selected_provider)
    if circuit_breaker and not circuit_breaker.is_request_allowed():
        raise HTTPException(
            status_code=503,
            detail=f"Provider {selected_provider} temporarily unavailable"
        )

    semaphore = resources.get_ai_semaphore()
    async with semaphore:
        try:
            answer = await asyncio.wait_for(
                ai_client.ask(
                    optimized_prompt,
                    provider=selected_provider,
                    max_tokens=ai_request.max_tokens,
                    temperature=ai_request.temperature
                ),
                timeout=config.ai.request_timeout
            )

            if circuit_breaker:
                circuit_breaker.record_success()
            
            if selected_provider in resources.request_stats:
                stats = resources.request_stats[selected_provider]
                stats['total_requests'] += 1
                stats['successful_requests'] += 1
            
            token_count = TokenOptimizer.estimate_tokens(answer, selected_provider)
            estimated_cost = (token_count / 1000) * ai_request.estimated_cost
            
            response = {
                "provider": selected_provider,
                "prompt": optimized_prompt,
                "answer": answer,
                "cached": False,
                "tokens_used": token_count,
                "estimated_cost": estimated_cost,
                "optimized": ai_request.optimize_tokens,
                "python_version": config.python_version
            }

            if config.enable_metrics:
                TOKEN_USAGE.labels(provider=selected_provider).inc(token_count)
                REQUEST_COUNT.labels(provider=selected_provider, status='success').inc()

            if cache_key and resources.redis_client:
                cache_ttl = (config.cache_ttl_short if token_count < 1000 
                           else config.cache_ttl_long)
                background_tasks.add_task(
                    _cache_ai_response, cache_key, response, cache_ttl
                )

            return response

        except asyncio.TimeoutError:
            if circuit_breaker:
                circuit_breaker.record_failure()
            
            if selected_provider in resources.request_stats:
                resources.request_stats[selected_provider]['failed_requests'] += 1
            
            logger.error(f"AI request timeout for provider {selected_provider}")
            raise HTTPException(status_code=408, detail="AI request timeout")
            
        except Exception as e:
            if circuit_breaker:
                circuit_breaker.record_failure()
            
            if selected_provider in resources.request_stats:
                resources.request_stats[selected_provider]['failed_requests'] += 1
            
            logger.error(f"AI service error with {selected_provider}: {e}")
            raise HTTPException(status_code=500, detail=f"AI service error: {str(e)}")

async def _cache_ai_response(cache_key: str, response: Dict[str, Any], ttl: int):
    """Background task to cache AI responses"""
    if resources.redis_client:
        try:
            await AdvancedCache.set_cached(resources.redis_client, cache_key, response, ttl)
        except Exception as e:
            logger.warning(f"Cache write error: {e}")

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Comprehensive health check with Python 3.13 compatibility"""
    app_start_time = getattr(app.state, 'start_time', time.time())
    uptime = time.time() - app_start_time

    ai_providers_status = {}
    ai_client_ready = resources.ai_client_instance is not None
    
    if ai_client_ready:
        ai_config = await resources.load_ai_config()
        for provider in ai_config.keys():
            circuit_breaker = resources.circuit_breakers.get(provider)
            
            if circuit_breaker and circuit_breaker.state == "OPEN":
                ai_providers_status[provider] = f"circuit_open (failures: {circuit_breaker.failure_count})"
                continue
                
            try:
                ai_providers_status[provider] = "configured"
                if circuit_breaker:
                    circuit_breaker.record_success()
            except Exception as e:
                error_msg = str(e)[:50]
                ai_providers_status[provider] = f"error: {error_msg}"
                if circuit_breaker:
                    circuit_breaker.record_failure()
    else:
        ai_providers_status = {"error": "AI client not initialized"}

    redis_available = False
    cache_hit_rate = 0.0
    
    if config.enable_cache and resources.redis_client:
        try:
            await resources.redis_client.ping()
            redis_available = True
            
            info = await resources.redis_client.info()
            hits = int(info.get('keyspace_hits', 0))
            misses = int(info.get('keyspace_misses', 0))
            if hits + misses > 0:
                cache_hit_rate = hits / (hits + misses)
        except Exception as e:
            logger.warning(f"Redis health check failed: {e}")

    total_requests = sum(
        stats.get('total_requests', 0) 
        for stats in resources.request_stats.values()
    )

    return HealthResponse(
        status="healthy",
        version=config.version,
        python_version=config.python_version,
        timestamp=datetime.now(),
        ai_client_ready=ai_client_ready,
        ai_providers_status=ai_providers_status,
        redis_available=redis_available,
        database_connected=True,
        uptime_seconds=uptime,
        cache_hit_rate=cache_hit_rate,
        total_requests=total_requests,
        active_connections=0,
        features_enabled={
            "cache": config.enable_cache,
            "compression": config.enable_compression,
            "metrics": config.enable_metrics,
            "redis": redis_available,
            "python_313_optimized": True
        }
    )

# Metrics endpoint
if config.enable_metrics:
    @app.get("/metrics")
    async def metrics():
        """Prometheus metrics endpoint"""
        return Response(generate_latest(), media_type="text/plain")

# --- Admin Endpoints ---

@app.post("/admin/reload-config")
@rate_limit(3)  # 3 per minute
async def reload_config(request: Request):
    """Hot reload AI configuration"""
    try:
        await resources.load_ai_config(force_reload=True)
        
        if resources.ai_client_instance and hasattr(resources.ai_client_instance, 'aclose'):
            await resources.ai_client_instance.aclose()
        
        resources.ai_client_instance = None
        await resources.initialize_ai_client()
        
        logger.info("🔄 Configuration reloaded successfully")
        return {"status": "success", "message": "Configuration reloaded", "python_version": config.python_version}
        
    except Exception as e:
        logger.error(f"Config reload error: {e}")
        raise HTTPException(status_code=500, detail=f"Config reload failed: {str(e)}")

@app.get("/admin/stats")
@rate_limit(10)  # 10 per minute
async def get_service_stats(request: Request):
    """Get comprehensive service statistics"""
    
    stats = {
        "service": {
            "name": config.app_name,
            "version": config.version,
            "python_version": config.python_version,
            "environment": config.environment,
            "uptime_seconds": time.time() - getattr(app.state, 'start_time', time.time())
        },
        "features": {
            "cache_enabled": config.enable_cache,
            "compression_enabled": config.enable_compression,
            "metrics_enabled": config.enable_metrics,
            "redis_available": resources.redis_client is not None,
            "python_313_optimized": True
        },
        "ai_providers": {},
        "performance": {
            "cache_hit_rate": 0.0,
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0
        }
    }
    
    for provider, provider_stats in resources.request_stats.items():
        circuit_breaker = resources.circuit_breakers.get(provider)
        stats["ai_providers"][provider] = {
            **provider_stats,
            "circuit_breaker_state": circuit_breaker.state if circuit_breaker else "unknown",
            "failure_count": circuit_breaker.failure_count if circuit_breaker else 0
        }
    
    stats["performance"]["total_requests"] = sum(
        s.get('total_requests', 0) for s in resources.request_stats.values()
    )
    stats["performance"]["successful_requests"] = sum(
        s.get('successful_requests', 0) for s in resources.request_stats.values()
    )
    stats["performance"]["failed_requests"] = sum(
        s.get('failed_requests', 0) for s in resources.request_stats.values()
    )
    
    if resources.redis_client:
        try:
            info = await resources.redis_client.info()
            hits = int(info.get('keyspace_hits', 0))
            misses = int(info.get('keyspace_misses', 0))
            if hits + misses > 0:
                stats["performance"]["cache_hit_rate"] = hits / (hits + misses)
            
            stats["redis"] = {
                "memory_used": info.get('used_memory_human', 'N/A'),
                "connected_clients": info.get('connected_clients', 0),
                "keyspace_hits": hits,
                "keyspace_misses": misses
            }
        except Exception as e:
            logger.warning(f"Error getting Redis stats: {e}")
    
    return stats

# --- Root Endpoint ---

@app.get("/")
async def root():
    """Service information with comprehensive feature overview"""
    return {
        "service": config.app_name,
        "version": config.version,
        "python_version": config.python_version,
        "status": "🚀 Ready",
        "environment": config.environment,
        "features": [
            "🎯 Smart provider selection",
            "💰 Cost optimization", 
            "⚡ High-performance caching",
            "🔄 Circuit breaker protection",
            "📊 Performance monitoring",
            "🗜️ Response compression",
            "🔧 Hot configuration reload",
            "🐍 Python 3.13 optimized"
        ],
        "ai_providers": {
            "free_tier": [provider for provider, limit in config.ai.free_tier_limits.items() 
                         if limit > 100],
            "total_configured": len(resources.ai_config_cache or {})
        },
        "capabilities": {
            "max_concurrent_requests": config.ai.max_concurrent_requests,
            "request_timeout": config.ai.request_timeout,
            "cache_enabled": config.enable_cache,
            "compression_enabled": config.enable_compression,
            "metrics_enabled": config.enable_metrics,
            "modern_rate_limiting": True,
            "exception_groups_support": True
        },
        "endpoints": {
            "docs": "/docs" if config.environment != 'production' else "disabled",
            "health": "/health",
            "metrics": "/metrics" if config.enable_metrics else "disabled",
            "admin": "/admin/stats"
        }
    }

# --- Application Entry Point ---

if __name__ == "__main__":
    import uvicorn
    
    uvicorn_config = {
        "app": app,
        "host": "0.0.0.0",
        "port": int(os.getenv('PORT', '8000')),
        "workers": 1,
        "access_log": config.environment != 'production',
        "reload": config.environment == 'development'
    }
    
    if config.environment == 'production':
        try:
            uvicorn_config.update({
                "loop": "uvloop",
                "http": "httptools",
            })
        except ImportError:
            logger.warning("uvloop/httptools not available, using default implementations")
    
    logger.info(f"🚀 Starting {config.app_name} v{config.version}")
    logger.info(f"Environment: {config.environment}")
    logger.info(f"Python version: {config.python_version}")
    logger.info(f"Configuration: {uvicorn_config}")
    
    uvicorn.run(**uvicorn_config)