# main.py - Python 3.13 Compatible AI Aggregator Pro with Enhanced Error Handling
# main.py - Python 3.13 Compatible AI Aggregator Pro
# version -2 Claude-Copilot - 07.06.25
# https://github.com/copilot/c/8b8c397d-00fb-4ec3-be1a-bbf971e674b6
from __future__ import annotations

# Standard library imports
import os
import sys
import json
import logging
import time
import asyncio
import gzip
import pickle
import hashlib
import platform
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
from functools import lru_cache, wraps
from typing import Any, Dict, List, Optional, Union, AsyncGenerator, Callable
from collections import defaultdict
from enum import Enum

# Third-party imports with error handling
try:
    import yaml
    import aiofiles
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    yaml = None
    aiofiles = None

try:
    from dotenv import load_dotenv
    load_dotenv()
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False

# FastAPI and related imports
try:
    from fastapi import (
        FastAPI, HTTPException, Query, Body, Depends, Request, 
        BackgroundTasks, status, Response
    )
    from fastapi.responses import StreamingResponse, JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.middleware.trustedhost import TrustedHostMiddleware
    from fastapi.middleware.gzip import GZipMiddleware
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    raise ImportError("FastAPI is required but not installed. Run: pip install fastapi")

# Pydantic imports with version compatibility
try:
    from pydantic import BaseModel, ConfigDict, field_validator, computed_field
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    raise ImportError("Pydantic is required but not installed. Run: pip install pydantic")

# Redis imports with fallback
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

# Database imports with fallback
try:
    from sqlalchemy.ext.asyncio import AsyncSession
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    AsyncSession = None

# Prometheus metrics (optional)
try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest
    METRICS_AVAILABLE = True
    
    # Define metrics
    REQUEST_COUNT = Counter('ai_requests_total', 'Total AI requests', ['provider', 'status'])
    REQUEST_DURATION = Histogram('ai_request_duration_seconds', 'AI request duration')
    CACHE_HITS = Counter('cache_hits_total', 'Cache hits', ['cache_type'])
    ACTIVE_CONNECTIONS = Gauge('active_connections', 'Active connections')
    TOKEN_USAGE = Counter('tokens_used_total', 'Total tokens used', ['provider'])
    
except ImportError:
    METRICS_AVAILABLE = False

# Performance monitoring imports with fallback
try:
    from performance_monitor import (
        PerformanceMonitor, PerformanceThresholds, OperationType,
        monitor_performance as external_monitor_performance, 
        monitor_ai_operation, monitor_cache_operation,
        get_performance_monitor, set_performance_monitor, get_performance_stats
    )
    PERFORMANCE_MONITOR_AVAILABLE = True
except ImportError:
    PERFORMANCE_MONITOR_AVAILABLE = False
    
    # Fallback implementations
    class OperationType(Enum):
        AI_REQUEST = "ai_request"
        CACHE_OPERATION = "cache_operation"
        DATABASE_OPERATION = "database_operation"
        NETWORK_OPERATION = "network_operation"
        COMPUTATION = "computation"

# AI client imports with fallback
try:
    from services.ai_async_client import AIAsyncClient
    AI_CLIENT_AVAILABLE = True
except ImportError:
    AI_CLIENT_AVAILABLE = False
    AIAsyncClient = None

# Business logic imports with comprehensive fallbacks
try:
    from product_schema import Product, ApiResponse
    from models import StandardizedProduct
    PRODUCT_MODELS_AVAILABLE = True
except ImportError:
    PRODUCT_MODELS_AVAILABLE = False
    
    # Fallback product models
    class Product(BaseModel):
        """Fallback Product model"""
        id: Optional[int] = None
        name: str
        description: Optional[str] = None
        price: Optional[float] = None
        category: Optional[str] = None
        
        model_config = ConfigDict(from_attributes=True)
    
    class StandardizedProduct(BaseModel):
        """Fallback StandardizedProduct model"""
        id: Optional[int] = None
        name: str
        description: Optional[str] = None
        price: Optional[float] = None
        category: Optional[str] = None
        source: Optional[str] = None
        
        model_config = ConfigDict(from_attributes=True)
    
    class ApiResponse(BaseModel):
        """Fallback ApiResponse model"""
        success: bool = True
        message: str = "Success"
        data: Optional[Any] = None

# Database functions with fallback
try:
    from database import create_db_and_tables, get_session
    DATABASE_FUNCTIONS_AVAILABLE = True
except ImportError:
    DATABASE_FUNCTIONS_AVAILABLE = False
    
    async def create_db_and_tables():
        """Fallback database creation"""
        logging.warning("Database functions not available - using fallback")
        pass
    
    async def get_session():
        """Fallback session getter"""
        return None

# Data processing imports with fallback
try:
    from data_discoverer import discover_and_extract_data
    from data_parser import parse_and_standardize
    from data_storage import store_standardized_data
    from data_search import search_and_filter_products
    DATA_PROCESSING_AVAILABLE = True
except ImportError:
    DATA_PROCESSING_AVAILABLE = False
    
    # Fallback data processing functions
    async def discover_and_extract_data(*args, **kwargs):
        """Fallback data discovery"""
        return []
    
    async def parse_and_standardize(*args, **kwargs):
        """Fallback data parsing"""
        return []
    
    async def store_standardized_data(*args, **kwargs):
        """Fallback data storage"""
        return True
    
    async def search_and_filter_products(*args, **kwargs):
        """Fallback product search"""
        return []

# Enhanced logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
    handlers=[
        logging.FileHandler('app.log', mode='a', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Log import status
logger.info(f"Import status - FastAPI: {FASTAPI_AVAILABLE}, Pydantic: {PYDANTIC_AVAILABLE}")
logger.info(f"Redis: {REDIS_AVAILABLE}, Database: {DATABASE_AVAILABLE}")
logger.info(f"AI Client: {AI_CLIENT_AVAILABLE}, Metrics: {METRICS_AVAILABLE}")
logger.info(f"Data Processing: {DATA_PROCESSING_AVAILABLE}")

# --- Modern Rate Limiter Implementation ---
class ModernRateLimiter:
    """Python 3.13 compatible rate limiter with sliding window algorithm"""
    
    def __init__(self):
        self.requests: Dict[str, List[float]] = defaultdict(list)
        self.locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
    
    async def is_allowed(self, key: str, limit: int, window: int = 60) -> bool:
        """Check if request is allowed based on rate limit"""
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
    """Modern rate limiting decorator compatible with Python 3.13"""
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
    url: str = os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./app.db')
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
    version: str = '3.2.1'  # Updated version
    environment: str = os.getenv('ENVIRONMENT', 'development')
    debug: bool = os.getenv('DEBUG', 'false').lower() == 'true'
    python_version: str = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    
    # Feature flags with proper defaults
    enable_cache: bool = REDIS_AVAILABLE and os.getenv('ENABLE_CACHE', 'true').lower() == 'true'
    enable_compression: bool = os.getenv('ENABLE_COMPRESSION', 'true').lower() == 'true'
    enable_metrics: bool = METRICS_AVAILABLE and os.getenv('ENABLE_METRICS', 'true').lower() == 'true'
    enable_docs: bool = os.getenv('ENABLE_DOCS', 'true').lower() == 'true'  # FIX: Added missing enable_docs
    
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

# Log configuration status
logger.info(f"Configuration loaded - Docs enabled: {config.enable_docs}")
logger.info(f"Environment: {config.environment}, Debug: {config.debug}")

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
                if config.enable_metrics and METRICS_AVAILABLE:
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
        if not AI_CLIENT_AVAILABLE or not AIAsyncClient:
            logger.warning("AIAsyncClient not available")
            return None
        
        try:
            ai_config = await self.load_ai_config()
            if not ai_config:
                logger.warning("No AI configuration available, using fallback")
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
            logger.warning(f"Failed to initialize AI client: {e}")
            return None
    
    async def load_ai_config(self, force_reload: bool = False) -> Dict[str, Any]:
        """Load AI configuration with enhanced validation"""
        if not YAML_AVAILABLE:
            logger.warning("YAML not available, using default config")
            return {
                "ollama": {
                    "base_url": "http://localhost:11434",
                    "model": "llama2",
                    "priority": "high"
                }
            }
            
        config_path = Path("ai_integrations.yaml")
        
        if not config_path.exists():
            logger.warning(f"Configuration file {config_path} not found, using default config")
            return {
                "ollama": {
                    "base_url": "http://localhost:11434",
                    "model": "llama2",
                    "priority": "high"
                }
            }
        
        current_mtime = config_path.stat().st_mtime
        
        if (not force_reload and self.ai_config_cache and 
            self.config_last_modified == current_mtime):
            return self.ai_config_cache
        
        try:
            if aiofiles:
                async with aiofiles.open(config_path, mode='r', encoding='utf-8') as f:
                    content = await f.read()
            else:
                with open(config_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            
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
            
        except Exception as e:
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
                results = await asyncio.gather(*cleanup_tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, Exception):
                        logger.error(f"Error during cleanup: {result}")
            except Exception as e:
                logger.error(f"Cleanup exception: {e}")
        
        logger.info("✅ Resource cleanup completed")

# --- Performance Monitoring Fallback ---
class Metrics:
    """Fallback metrics collector"""
    def __init__(self, app_name: str):
        self.app_name = app_name
        self.active_operations = {}

    def record_operation(self, metrics) -> None:
        """Record operation metrics"""
        pass

    def increment_counter(self, name: str, labels: Dict[str, str]) -> None:
        """Increment counter metrics"""
        pass

    def observe_histogram(self, name: str, value: float, labels: Dict[str, str]) -> None:
        """Observe histogram values"""
        pass

# Initialize performance monitoring
if PERFORMANCE_MONITOR_AVAILABLE:
    try:
        metrics_collector = Metrics(app_name="AI Aggregator Pro")
        monitor = PerformanceMonitor(metrics_collector)
    except Exception as e:
        logger.warning(f"Failed to initialize performance monitor: {e}")
        PERFORMANCE_MONITOR_AVAILABLE = False

if not PERFORMANCE_MONITOR_AVAILABLE:
    class PerformanceMonitor:
        def __init__(self, metrics_collector):
            self.metrics_collector = metrics_collector
            self.active_operations = {}

        async def monitor_operation(self, operation_name: str, operation_type=None):
            """Context manager for monitoring operations"""
            yield None

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
                if config.enable_metrics and METRICS_AVAILABLE:
                    provider = kwargs.get('provider', 'unknown')
                    REQUEST_COUNT.labels(provider=provider, status='error').inc()
                
                logger.error(f"Operation {operation_name} failed with exception: {e}")
                raise
            
            finally:
                duration = time.time() - start_time
                
                if config.enable_metrics and METRICS_AVAILABLE:
                    REQUEST_DURATION.observe(duration)
                    if operation_success:
                        provider = kwargs.get('provider', 'unknown')
                        REQUEST_COUNT.labels(provider=provider, status='success').inc()
                
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

class ProductSearchRequest(BaseModel):
    """Product search request model"""
    query: Optional[str] = None
    category: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    limit: int = 10
    offset: int = 0
    
    @field_validator("limit")
    @classmethod
    def validate_limit(cls, v: int) -> int:
        if not 1 <= v <= 100:
            raise ValueError("Limit must be between 1 and 100")
        return v
    
    @field_validator("offset")
    @classmethod
    def validate_offset(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Offset must be non-negative")
        return v
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "laptop",
                "category": "electronics",
                "min_price": 100.0,
                "max_price": 2000.0,
                "limit": 10,
                "offset": 0
            }
        }
    )

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
    logger.info(f"Documentation: {config.enable_docs}")

    try:
        # Initialize database
        if DATABASE_FUNCTIONS_AVAILABLE:
            await create_db_and_tables()
            logger.info("✅ Database initialized")
        else:
            logger.warning("⚠️ Database functions not available")
        
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

# --- FastAPI Application with Fixed Configuration ---
app = FastAPI(
    title=config.app_name,
    description=f"Next-generation AI service optimized for Python {config.python_version}",
    version=config.version,
    lifespan=lifespan,
    docs_url="/docs" if config.enable_docs else None,  # FIX: Proper conditional docs
    redoc_url="/redoc" if config.enable_docs else None,  # FIX: Proper conditional redoc
    openapi_url="/openapi.json" if config.enable_docs else None,  # FIX: Proper conditional OpenAPI
    debug=config.debug
)

# Log app initialization
logger.info(f"FastAPI app initialized with docs_url: {app.docs_url}")

# --- Middleware Stack (Fixed Order) ---

# Compression middleware (first for response processing)
if config.enable_compression:
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    logger.info("✅ Compression middleware enabled")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.security.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    max_age=3600,
)
logger.info("✅ CORS middleware enabled")

# Trusted hosts middleware
if config.security.trusted_hosts:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=config.security.trusted_hosts
    )
    logger.info("✅ Trusted hosts middleware enabled")

# --- Core API Endpoints ---

@app.post("/ai/ask", 
          summary="Ask AI", 
          description="Submit a question to AI with smart provider selection",
          tags=["AI"])
@rate_limit(50)
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
            "ai_ask_v3",
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
        # Fallback response when AI client is not available
        return {
            "provider": "fallback",
            "prompt": optimized_prompt,
            "answer": "AI service is currently not available. This is a fallback response.",
            "cached": False,
            "tokens_used": 0,
            "estimated_cost": 0.0,
            "optimized": ai_request.optimize_tokens,
            "python_version": config.python_version,
            "status": "fallback"
        }
    
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

            if config.enable_metrics and METRICS_AVAILABLE:
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

# --- Product Search Endpoints ---

@app.get("/products/search", 
         response_model=ApiResponse,
         summary="Search Products",
         description="Search for products with optional filters",
         tags=["Products"])
@rate_limit(100)
async def search_products(
    request: Request,
    query: Optional[str] = Query(None, description="Search query"),
    category: Optional[str] = Query(None, description="Product category"),
    min_price: Optional[float] = Query(None, ge=0, description="Minimum price"),
    max_price: Optional[float] = Query(None, ge=0, description="Maximum price"),
    limit: int = Query(10, ge=1, le=100, description="Number of results"),
    offset: int = Query(0, ge=0, description="Results offset"),
    session: AsyncSession = Depends(get_session) if DATABASE_FUNCTIONS_AVAILABLE else None
):
    """Search for products with comprehensive filtering options"""
    
    try:
        if DATA_PROCESSING_AVAILABLE and session:
            products = await search_and_filter_products(
                session=session,
                query=query,
                category=category,
                min_price=min_price,
                max_price=max_price,
                limit=limit,
                offset=offset
            )
        else:
            # Fallback mock data
            products = [
                StandardizedProduct(
                    id=1,
                    name=f"Sample Product {i}",
                    description=f"Description for product {i}",
                    price=100.0 + i * 10,
                    category=category or "general",
                    source="fallback"
                )
                for i in range(1, min(limit + 1, 6))
            ]
        
        return ApiResponse(
            success=True,
            message=f"Found {len(products)} products",
            data={
                "products": products,
                "count": len(products),
                "limit": limit,
                "offset": offset,
                "filters": {
                    "query": query,
                    "category": category,
                    "min_price": min_price,
                    "max_price": max_price
                }
            }
        )
        
    except Exception as e:
        logger.error(f"Product search error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Product search failed: {str(e)}"
        )

@app.post("/products/search-detailed",
          response_model=ApiResponse,
          summary="Detailed Product Search",
          description="Advanced product search with detailed filtering",
          tags=["Products"])
@rate_limit(50)
async def search_products_detailed(
    request: Request,
    search_request: ProductSearchRequest,
    session: AsyncSession = Depends(get_session) if DATABASE_FUNCTIONS_AVAILABLE else None
):
    """Detailed product search with advanced filtering capabilities"""
    
    try:
        if DATA_PROCESSING_AVAILABLE and session:
            products = await search_and_filter_products(
                session=session,
                query=search_request.query,
                category=search_request.category,
                min_price=search_request.min_price,
                max_price=search_request.max_price,
                limit=search_request.limit,
                offset=search_request.offset
            )
        else:
            # Enhanced fallback with search request parameters
            products = [
                StandardizedProduct(
                    id=i,
                    name=f"Product {i} - {search_request.query or 'Sample'}",
                    description=f"Detailed description for {search_request.query or 'sample'} product {i}",
                    price=float((search_request.min_price or 50) + i * 25),
                    category=search_request.category or "electronics",
                    source="detailed_fallback"
                )
                for i in range(1, min(search_request.limit + 1, 11))
                if not search_request.max_price or 
                   ((search_request.min_price or 50) + i * 25) <= search_request.max_price
            ]
        
        return ApiResponse(
            success=True,
            message=f"Detailed search completed. Found {len(products)} products",
            data={
                "products": products,
                "search_parameters": search_request.model_dump(),
                "total_found": len(products),
                "search_metadata": {
                    "query_processed": search_request.query,
                    "filters_applied": sum([
                        1 for x in [search_request.category, search_request.min_price, search_request.max_price]
                        if x is not None
                    ]),
                    "fallback_used": not DATA_PROCESSING_AVAILABLE
                }
            }
        )
        
    except Exception as e:
        logger.error(f"Detailed product search error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Detailed product search failed: {str(e)}"
        )

# --- Health Check ---

@app.get("/health", 
         response_model=HealthResponse,
         summary="Health Check",
         description="Comprehensive service health status",
         tags=["System"])
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
        ai_providers_status = {"status": "AI client not initialized (fallback mode)"}

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
        database_connected=DATABASE_FUNCTIONS_AVAILABLE,
        uptime_seconds=uptime,
        cache_hit_rate=cache_hit_rate,
        total_requests=total_requests,
        active_connections=0,
        features_enabled={
            "cache": config.enable_cache,
            "compression": config.enable_compression,
            "metrics": config.enable_metrics,
            "docs": config.enable_docs,
            "redis": redis_available,
            "database": DATABASE_FUNCTIONS_AVAILABLE,
            "ai_client": AI_CLIENT_AVAILABLE,
            "data_processing": DATA_PROCESSING_AVAILABLE,
            "python_313_optimized": True
        }
    )

# Metrics endpoint
if config.enable_metrics and METRICS_AVAILABLE:
    @app.get("/metrics", 
             summary="Prometheus Metrics", 
             include_in_schema=False,
             tags=["System"])
    async def metrics():
        """Prometheus metrics endpoint"""
        return Response(generate_latest(), media_type="text/plain")

# --- Admin Endpoints ---

@app.post("/admin/reload-config",
          summary="Reload Configuration", 
          description="Hot reload AI configuration",
          tags=["Admin"])
@rate_limit(3)
async def reload_config(request: Request):
    """Hot reload AI configuration"""
    try:
        await resources.load_ai_config(force_reload=True)
        
        if resources.ai_client_instance and hasattr(resources.ai_client_instance, 'aclose'):
            await resources.ai_client_instance.aclose()
        
        resources.ai_client_instance = None
        await resources.initialize_ai_client()
        
        logger.info("🔄 Configuration reloaded successfully")
        return {
            "status": "success", 
            "message": "Configuration reloaded", 
            "python_version": config.python_version,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Config reload error: {e}")
        raise HTTPException(status_code=500, detail=f"Config reload failed: {str(e)}")

@app.get("/admin/stats",
         summary="Service Statistics",
         description="Comprehensive service statistics and metrics",
         tags=["Admin"])
@rate_limit(10)
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
            "docs_enabled": config.enable_docs,
            "redis_available": resources.redis_client is not None,
            "ai_client_available": AI_CLIENT_AVAILABLE,
            "database_available": DATABASE_FUNCTIONS_AVAILABLE,
            "data_processing_available": DATA_PROCESSING_AVAILABLE,
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

@app.get("/", 
         summary="Service Information",
         description="Service overview and capabilities",
         tags=["System"])
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
            "🐍 Python 3.13 optimized",
            "📚 Comprehensive API documentation",
            "🔍 Advanced product search"
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
            "docs_enabled": config.enable_docs,
            "modern_rate_limiting": True,
            "exception_groups_support": True,
            "fallback_mode": not all([AI_CLIENT_AVAILABLE, DATABASE_FUNCTIONS_AVAILABLE, DATA_PROCESSING_AVAILABLE])
        },
        "endpoints": {
            "docs": "/docs" if config.enable_docs else "disabled",
            "redoc": "/redoc" if config.enable_docs else "disabled",
            "health": "/health",
            "metrics": "/metrics" if config.enable_metrics else "disabled",
            "admin": "/admin/stats",
            "ai_chat": "/ai/ask",
            "product_search": "/products/search",
            "detailed_search": "/products/search-detailed"
        },
        "documentation_note": "Visit /docs for interactive API documentation" if config.enable_docs else "Documentation disabled in production"
    }

# --- Application Entry Point ---

if __name__ == "__main__":
    import uvicorn
    
    # Determine port from environment or use default
    port = int(os.getenv('PORT', '8000'))
    
    uvicorn_config = {
        "app": "main:app",  # Use string reference for better reloading
        "host": "0.0.0.0",
        "port": port,
        "workers": 1,
        "access_log": config.environment != 'production',
        "reload": config.environment == 'development',
        "log_level": "info"
    }
    
    # Performance optimizations for production
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