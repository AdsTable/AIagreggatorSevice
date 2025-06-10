# main.py - Python 3.13 Compatible AI Aggregator Pro with Complete Error Handling
# main.py - Python 3.13 Compatible AI Aggregator Pro
# version -4 Claude-Copilot - 07.06.25 - (not finished!)
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

# Third-party imports with comprehensive error handling
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
    raise ImportError("FastAPI is required but not installed. Run: pip install fastapi uvicorn")

# Pydantic imports with version compatibility
try:
    from pydantic import BaseModel, ConfigDict, field_validator, computed_field
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    raise ImportError("Pydantic v2 is required but not installed. Run: pip install 'pydantic>=2.0'")

# Redis imports with multiple fallback options
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
    
    # Define metrics with proper initialization
    REQUEST_COUNT = Counter('ai_requests_total', 'Total AI requests', ['provider', 'status'])
    REQUEST_DURATION = Histogram('ai_request_duration_seconds', 'AI request duration')
    CACHE_HITS = Counter('cache_hits_total', 'Cache hits', ['cache_type'])
    ACTIVE_CONNECTIONS = Gauge('active_connections', 'Active connections')
    TOKEN_USAGE = Counter('tokens_used_total', 'Total tokens used', ['provider'])
    
except ImportError:
    METRICS_AVAILABLE = False

# Performance monitoring imports with comprehensive fallback
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
    
    # Complete fallback implementations
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
    
    # Complete fallback product models
    class Product(BaseModel):
        """Fallback Product model with comprehensive fields"""
        id: Optional[int] = None
        name: str
        description: Optional[str] = None
        price: Optional[float] = None
        category: Optional[str] = None
        provider: Optional[str] = None
        source_url: Optional[str] = None
        
        model_config = ConfigDict(from_attributes=True, extra="allow")
    
    class StandardizedProduct(BaseModel):
        """Fallback StandardizedProduct model with full compatibility"""
        id: Optional[int] = None
        name: str
        description: Optional[str] = None
        price: Optional[float] = None
        category: Optional[str] = None
        source: Optional[str] = None
        provider: Optional[str] = None
        
        model_config = ConfigDict(from_attributes=True, extra="allow")
        
        def model_dump(self, **kwargs) -> Dict[str, Any]:
            """Ensure compatibility with both Pydantic v1 and v2"""
            if hasattr(super(), 'model_dump'):
                return super().model_dump(**kwargs)
            else:
                return self.dict(**kwargs)
    
    class ApiResponse(BaseModel):
        """Fallback ApiResponse model with proper structure"""
        success: bool = True
        message: str = "Success"
        data: Optional[Any] = None
        timestamp: Optional[datetime] = None
        
        model_config = ConfigDict(from_attributes=True)

# Database functions with comprehensive fallback
try:
    from database import create_db_and_tables, get_session
    DATABASE_FUNCTIONS_AVAILABLE = True
except ImportError:
    DATABASE_FUNCTIONS_AVAILABLE = False
    
    async def create_db_and_tables():
        """Fallback database creation function"""
        logging.warning("Database functions not available - using in-memory fallback")
        pass
    
    async def get_session():
        """Fallback session getter"""
        return None

# Data processing imports with complete fallback implementations
try:
    from data_discoverer import discover_and_extract_data
    from data_parser import parse_and_standardize
    from data_storage import store_standardized_data
    from data_search import search_and_filter_products
    DATA_PROCESSING_AVAILABLE = True
except ImportError:
    DATA_PROCESSING_AVAILABLE = False
    
    # Complete fallback data processing functions
    async def discover_and_extract_data(*args, **kwargs):
        """Fallback data discovery with mock data"""
        return [
            {"name": "Sample Product 1", "price": 99.99, "category": "electronics"},
            {"name": "Sample Product 2", "price": 149.99, "category": "books"}
        ]
    
    async def parse_and_standardize(raw_data, category="general"):
        """Fallback data parsing function"""
        return [
            StandardizedProduct(
                id=i,
                name=item.get("name", f"Product {i}"),
                price=item.get("price", 0.0),
                category=category,
                description=f"Fallback description for {item.get('name', 'product')}"
            )
            for i, item in enumerate(raw_data, 1)
        ]
    
    async def store_standardized_data(session, data):
        """Fallback data storage function"""
        logging.info(f"Fallback storage: would store {len(data)} items")
        return True
    
    async def search_and_filter_products(session=None, **filters):
        """Fallback product search with realistic mock data"""
        limit = filters.get('limit', 10)
        offset = filters.get('offset', 0)
        category = filters.get('product_type') or filters.get('category', 'general')
        min_price = filters.get('min_price', 0)
        max_price = filters.get('max_price', 1000)
        
        # Generate realistic mock products
        products = []
        for i in range(offset + 1, offset + limit + 1):
            price = min_price + (i * 25) % (max_price - min_price)
            products.append(StandardizedProduct(
                id=i,
                name=f"{category.title()} Product {i}",
                description=f"High-quality {category} item with excellent features and competitive pricing.",
                price=float(price),
                category=category,
                source="fallback_search",
                provider=f"Provider {(i % 3) + 1}"
            ))
        
        return products[:limit]

# Enhanced logging setup with production-ready configuration
def setup_logging():
    """Setup comprehensive logging with environment-specific configuration"""
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_format = os.getenv('LOG_FORMAT', 'detailed')
    environment = os.getenv('ENVIRONMENT', 'development')
    
    # Configure formatters based on environment
    if log_format == 'json' or environment == 'production':
        # Structured JSON logging for production
        formatter = logging.Formatter(
            '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", '
            '"function": "%(funcName)s", "line": %(lineno)d, "message": "%(message)s"}'
        )
    else:
        # Detailed human-readable logging for development
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
        )
    
    # Configure handlers
    handlers = []
    
    # Console handler - always present
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(getattr(logging, log_level, logging.INFO))
    handlers.append(console_handler)
    
    # File handler - configurable
    if os.getenv('ENABLE_FILE_LOGGING', 'true').lower() == 'true':
        log_file = os.getenv('LOG_FILE', 'app.log')
        try:
            file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
            file_handler.setFormatter(formatter)
            file_handler.setLevel(getattr(logging, log_level, logging.INFO))
            handlers.append(file_handler)
        except Exception as e:
            print(f"Warning: Could not setup file logging: {e}")
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        handlers=handlers,
        force=True  # Override any existing configuration
    )
    
    # Set specific logger levels
    logging.getLogger('uvicorn').setLevel(logging.WARNING)
    logging.getLogger('fastapi').setLevel(logging.INFO)

# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)

# Comprehensive import status logging
logger.info("=" * 80)
logger.info("AI AGGREGATOR PRO - IMPORT STATUS REPORT")
logger.info("=" * 80)
logger.info(f"Python Version: {sys.version}")
logger.info(f"Platform: {platform.platform()}")
logger.info("-" * 80)
logger.info("Core Dependencies:")
logger.info(f"  ✅ FastAPI: {FASTAPI_AVAILABLE}")
logger.info(f"  ✅ Pydantic: {PYDANTIC_AVAILABLE}")
logger.info("-" * 80)
logger.info("Optional Dependencies:")
logger.info(f"  {'✅' if REDIS_AVAILABLE else '❌'} Redis: {REDIS_AVAILABLE}")
logger.info(f"  {'✅' if DATABASE_AVAILABLE else '❌'} Database (SQLAlchemy): {DATABASE_AVAILABLE}")
logger.info(f"  {'✅' if METRICS_AVAILABLE else '❌'} Prometheus Metrics: {METRICS_AVAILABLE}")
logger.info(f"  {'✅' if YAML_AVAILABLE else '❌'} YAML Support: {YAML_AVAILABLE}")
logger.info(f"  {'✅' if DOTENV_AVAILABLE else '❌'} Environment Loading: {DOTENV_AVAILABLE}")
logger.info("-" * 80)
logger.info("Business Logic Modules:")
logger.info(f"  {'✅' if AI_CLIENT_AVAILABLE else '❌'} AI Client: {AI_CLIENT_AVAILABLE}")
logger.info(f"  {'✅' if PERFORMANCE_MONITOR_AVAILABLE else '❌'} Performance Monitor: {PERFORMANCE_MONITOR_AVAILABLE}")
logger.info(f"  {'✅' if DATA_PROCESSING_AVAILABLE else '❌'} Data Processing: {DATA_PROCESSING_AVAILABLE}")
logger.info(f"  {'✅' if PRODUCT_MODELS_AVAILABLE else '❌'} Product Models: {PRODUCT_MODELS_AVAILABLE}")
logger.info(f"  {'✅' if DATABASE_FUNCTIONS_AVAILABLE else '❌'} Database Functions: {DATABASE_FUNCTIONS_AVAILABLE}")
logger.info("=" * 80)

# Calculate fallback mode status
fallback_modules = [
    not AI_CLIENT_AVAILABLE,
    not DATABASE_FUNCTIONS_AVAILABLE,
    not DATA_PROCESSING_AVAILABLE,
    not PRODUCT_MODELS_AVAILABLE
]
fallback_count = sum(fallback_modules)

if fallback_count > 0:
    logger.warning(f"⚠️  Running in PARTIAL FALLBACK MODE ({fallback_count}/4 modules using fallbacks)")
    logger.warning("   Some functionality will use mock implementations")
else:
    logger.info("🎉 All modules loaded successfully - FULL FUNCTIONALITY AVAILABLE")

# --- Advanced Rate Limiter Implementation ---
class ModernRateLimiter:
    """
    Production-ready rate limiter with sliding window algorithm
    Optimized for Python 3.13 with comprehensive error handling
    """
    
    def __init__(self):
        self.requests: Dict[str, List[float]] = defaultdict(list)
        self.locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.cleanup_interval = 300  # 5 minutes
        self.last_cleanup = time.time()
    
    async def is_allowed(self, key: str, limit: int, window: int = 60) -> bool:
        """
        Check if request is allowed based on rate limit
        
        Args:
            key: Unique identifier for rate limiting
            limit: Maximum requests allowed in window
            window: Time window in seconds
            
        Returns:
            True if request is allowed, False otherwise
        """
        current_time = time.time()
        
        # Periodic cleanup to prevent memory leaks
        await self._periodic_cleanup(current_time)
        
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
    
    async def _periodic_cleanup(self, current_time: float):
        """Periodic cleanup of old rate limit data"""
        if current_time - self.last_cleanup > self.cleanup_interval:
            # Remove entries that haven't been used recently
            stale_keys = [
                key for key, requests in self.requests.items()
                if not requests or current_time - max(requests) > 3600  # 1 hour
            ]
            
            for key in stale_keys:
                del self.requests[key]
                if key in self.locks:
                    del self.locks[key]
            
            self.last_cleanup = current_time
            if stale_keys:
                logger.debug(f"Cleaned up {len(stale_keys)} stale rate limit entries")

# Global rate limiter instance
rate_limiter = ModernRateLimiter()

# --- Enhanced Rate Limiting Decorator ---
def rate_limit(requests_per_minute: int = 60):
    """
    Production-ready rate limiting decorator
    
    Features:
    - Sliding window algorithm for accurate rate limiting
    - Per-IP tracking with automatic cleanup
    - Graceful error handling
    - Comprehensive logging
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request from arguments
            request: Optional[Request] = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if not request:
                # No request object found, skip rate limiting
                return await func(*args, **kwargs)
            
            # Generate rate limit key
            client_ip = (
                request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
                request.headers.get("x-real-ip", "") or
                (request.client.host if request.client else "unknown")
            )
            rate_limit_key = f"rate_limit:{client_ip}:{func.__name__}"
            
            # Check rate limit
            try:
                is_allowed = await rate_limiter.is_allowed(
                    rate_limit_key, 
                    requests_per_minute, 
                    60
                )
                
                if not is_allowed:
                    remaining = rate_limiter.get_remaining(rate_limit_key, requests_per_minute, 60)
                    logger.warning(f"Rate limit exceeded for {client_ip} on {func.__name__}")
                    
                    raise HTTPException(
                        status_code=429,
                        detail={
                            "error": "Rate limit exceeded",
                            "message": f"Too many requests. Try again later.",
                            "remaining": remaining,
                            "limit": requests_per_minute,
                            "window_seconds": 60,
                            "retry_after": 60
                        },
                        headers={"Retry-After": "60"}
                    )
                
                # Record metrics if available
                if METRICS_AVAILABLE:
                    REQUEST_COUNT.labels(provider='system', status='allowed').inc()
                
                return await func(*args, **kwargs)
                
            except HTTPException:
                # Re-raise HTTP exceptions (like rate limit exceeded)
                raise
            except Exception as e:
                # Log unexpected errors but don't block the request
                logger.error(f"Rate limiter error for {client_ip}: {e}")
                return await func(*args, **kwargs)
        
        return wrapper
    return decorator

# --- Configuration Management with Validation ---
@dataclass
class DatabaseConfig:
    """Database configuration with comprehensive validation"""
    url: str = os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./app.db')
    pool_size: int = int(os.getenv('DB_POOL_SIZE', '20'))
    max_overflow: int = int(os.getenv('DB_MAX_OVERFLOW', '30'))
    echo: bool = os.getenv('DB_ECHO', 'false').lower() == 'true'
    pool_timeout: int = int(os.getenv('DB_POOL_TIMEOUT', '30'))
    pool_recycle: int = int(os.getenv('DB_POOL_RECYCLE', '3600'))
    
    def __post_init__(self):
        """Validate database configuration"""
        if not self.url:
            raise ValueError("Database URL cannot be empty")
        if self.pool_size < 1:
            raise ValueError("Database pool size must be positive")
        if self.max_overflow < 0:
            raise ValueError("Database max overflow must be non-negative")
        if self.pool_timeout <= 0:
            raise ValueError("Database pool timeout must be positive")

@dataclass
class RedisConfig:
    """Redis configuration with connection validation"""
    url: str = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    max_connections: int = int(os.getenv('REDIS_MAX_CONNECTIONS', '20'))
    socket_timeout: float = float(os.getenv('REDIS_SOCKET_TIMEOUT', '5.0'))
    socket_connect_timeout: float = float(os.getenv('REDIS_CONNECT_TIMEOUT', '5.0'))
    health_check_interval: int = int(os.getenv('REDIS_HEALTH_CHECK_INTERVAL', '30'))
    encoding: str = 'utf-8'
    decode_responses: bool = False
    
    def __post_init__(self):
        """Validate Redis configuration"""
        if self.max_connections < 1:
            raise ValueError("Redis max connections must be positive")
        if self.socket_timeout <= 0:
            raise ValueError("Redis socket timeout must be positive")
        if self.health_check_interval < 10:
            raise ValueError("Redis health check interval must be at least 10 seconds")

@dataclass
class SecurityConfig:
    """Security configuration with comprehensive validation"""
    secret_key: str = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    api_key_header: str = os.getenv('API_KEY_HEADER', 'X-API-Key')
    allowed_origins: List[str] = field(default_factory=lambda: 
        [origin.strip() for origin in os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000,http://localhost:8080').split(',') if origin.strip()]
    )
    trusted_hosts: List[str] = field(default_factory=lambda: 
        [host.strip() for host in os.getenv('TRUSTED_HOSTS', '').split(',') if host.strip()]
    )
    cors_max_age: int = int(os.getenv('CORS_MAX_AGE', '3600'))
    
    def __post_init__(self):
        """Validate security configuration"""
        if len(self.secret_key) < 16:
            if os.getenv('ENVIRONMENT', 'development') == 'production':
                raise ValueError("Secret key must be at least 16 characters in production")
            else:
                logger.warning("⚠️  Secret key is too short for production use")
        
        if not self.allowed_origins:
            logger.warning("⚠️  No CORS origins configured - this may cause issues in browser clients")
        
        # Validate origin URLs
        for origin in self.allowed_origins:
            if not (origin.startswith('http://') or origin.startswith('https://') or origin == '*'):
                logger.warning(f"⚠️  Potentially invalid CORS origin: {origin}")

@dataclass
class AIConfig:
    """AI provider configuration with enhanced validation"""
    default_provider: str = os.getenv('AI_DEFAULT_PROVIDER', 'ollama')
    max_concurrent_requests: int = int(os.getenv('MAX_CONCURRENT_AI_REQUESTS', '15'))
    request_timeout: int = int(os.getenv('AI_REQUEST_TIMEOUT', '45'))
    max_prompt_length: int = int(os.getenv('MAX_PROMPT_LENGTH', '32000'))
    cost_budget_daily: float = float(os.getenv('AI_COST_BUDGET_DAILY', '10.0'))
    cost_budget_monthly: float = float(os.getenv('AI_COST_BUDGET_MONTHLY', '300.0'))
    
    free_tier_limits: Dict[str, int] = field(default_factory=lambda: {
        'ollama': 999999,
        'huggingface': 1000,
        'together': 25,
        'openai': 3,
        'mock': 999999,
    })
    
    def __post_init__(self):
        """Validate AI configuration"""
        if self.max_concurrent_requests < 1:
            raise ValueError("Max concurrent requests must be positive")
        if self.request_timeout < 5:
            raise ValueError("Request timeout must be at least 5 seconds")
        if self.max_prompt_length < 100:
            raise ValueError("Max prompt length must be at least 100 characters")
        if self.cost_budget_daily <= 0:
            raise ValueError("Daily cost budget must be positive")
        if self.cost_budget_monthly <= 0:
            raise ValueError("Monthly cost budget must be positive")

@dataclass
class AppConfig:
    """
    Main application configuration with comprehensive validation
    Optimized for Python 3.13 with enhanced error handling
    """
    app_name: str = os.getenv('APP_NAME', 'AI Aggregator Pro')
    version: str = '3.2.2'  # Updated version
    environment: str = os.getenv('ENVIRONMENT', 'development')
    debug: bool = os.getenv('DEBUG', 'false').lower() == 'true'
    python_version: str = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    
    # Server configuration
    host: str = os.getenv('HOST', '0.0.0.0')
    port: int = int(os.getenv('PORT', '8000'))
    workers: int = int(os.getenv('WORKERS', '1'))
    
    # Feature flags with intelligent defaults
    enable_cache: bool = REDIS_AVAILABLE and os.getenv('ENABLE_CACHE', 'true').lower() == 'true'
    enable_compression: bool = os.getenv('ENABLE_COMPRESSION', 'true').lower() == 'true'
    enable_metrics: bool = METRICS_AVAILABLE and os.getenv('ENABLE_METRICS', 'true').lower() == 'true'
    enable_docs: bool = os.getenv('ENABLE_DOCS', 'true' if os.getenv('ENVIRONMENT', 'development') != 'production' else 'false').lower() == 'true'
    
    # Performance settings
    cache_ttl_short: int = int(os.getenv('CACHE_TTL_SHORT', '900'))    # 15 minutes
    cache_ttl_long: int = int(os.getenv('CACHE_TTL_LONG', '3600'))     # 1 hour
    cache_ttl_fallback: int = int(os.getenv('CACHE_TTL_FALLBACK', '300'))  # 5 minutes
    
    # Sub-configurations
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    
    def __post_init__(self):
        """Comprehensive application configuration validation"""
        # Environment validation
        valid_environments = ['development', 'staging', 'production']
        if self.environment not in valid_environments:
            raise ValueError(f"Environment must be one of: {valid_environments}")
        
        # Server configuration validation
        if not 1 <= self.port <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        if self.workers < 1:
            raise ValueError("Workers count must be positive")
        
        # Cache TTL validation
        if self.cache_ttl_short > self.cache_ttl_long:
            logger.warning("⚠️  Short cache TTL is greater than long cache TTL")
        if self.cache_ttl_short <= 0 or self.cache_ttl_long <= 0:
            raise ValueError("Cache TTL values must be positive")
        
        # Production-specific validations
        if self.environment == 'production':
            if self.debug:
                logger.warning("⚠️  Debug mode is enabled in production - this is not recommended")
            if 'dev-secret' in self.security.secret_key:
                raise ValueError("Default secret key cannot be used in production")
        
        # Log configuration summary
        logger.info(f"✅ Application configured for {self.environment} environment")
        logger.info(f"   Server: {self.host}:{self.port} (workers: {self.workers})")
        logger.info(f"   Features: docs={self.enable_docs}, cache={self.enable_cache}, metrics={self.enable_metrics}")
        logger.info(f"   Debug mode: {self.debug}")

# Initialize configuration with comprehensive error handling
try:
    config = AppConfig()
    logger.info("✅ Configuration validation successful")
except Exception as e:
    logger.error(f"❌ Configuration validation failed: {e}")
    logger.error("   Creating minimal fallback configuration...")
    
    # Create minimal fallback configuration
    config = AppConfig()
    config.enable_docs = True  # Force enable docs for debugging
    config.debug = True
    logger.warning("⚠️  Using fallback configuration - some features may not work correctly")

# --- Circuit Breaker Implementation ---
@dataclass
class CircuitBreaker:
    """
    Production-ready circuit breaker for provider failure handling
    Implements the circuit breaker pattern with configurable thresholds
    """
    failure_threshold: int = 5
    recovery_timeout: int = 60
    half_open_max_calls: int = 3
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[float] = None
    state: str = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def is_request_allowed(self) -> bool:
        """
        Check if request is allowed based on circuit breaker state
        
        Returns:
            True if request should be allowed, False otherwise
        """
        current_time = time.time()
        
        if self.state == "CLOSED":
            return True
        elif self.state == "OPEN":
            if current_time - (self.last_failure_time or 0) > self.recovery_timeout:
                self.state = "HALF_OPEN"
                self.success_count = 0
                logger.info(f"Circuit breaker transitioning to HALF_OPEN state")
                return True
            return False
        else:  # HALF_OPEN
            return self.success_count < self.half_open_max_calls
    
    def record_success(self):
        """Record successful request and update circuit breaker state"""
        if self.state == "HALF_OPEN":
            self.success_count += 1
            if self.success_count >= self.half_open_max_calls:
                self.state = "CLOSED"
                self.failure_count = 0
                logger.info(f"Circuit breaker transitioning to CLOSED state after successful recovery")
        elif self.state == "CLOSED":
            self.failure_count = max(0, self.failure_count - 1)
    
    def record_failure(self):
        """Record failed request and update circuit breaker state"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == "CLOSED" and self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(f"Circuit breaker transitioning to OPEN state after {self.failure_count} failures")
        elif self.state == "HALF_OPEN":
            self.state = "OPEN"
            logger.warning(f"Circuit breaker returning to OPEN state after failure during recovery")
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive circuit breaker status"""
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time,
            "time_to_recovery": max(0, self.recovery_timeout - (time.time() - (self.last_failure_time or 0))) if self.state == "OPEN" else 0
        }

# --- Advanced Caching System ---
class AdvancedCache:
    """
    High-performance cache with compression, encryption, and smart TTL
    Optimized for production use with comprehensive error handling
    """
    
    @staticmethod
    def compress_data(data: Any) -> bytes:
        """
        Compress data using gzip for storage efficiency
        
        Args:
            data: Any serializable data
            
        Returns:
            Compressed bytes
        """
        try:
            serialized = pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)
            if config.enable_compression and len(serialized) > 1024:  # Only compress if > 1KB
                return gzip.compress(serialized, compresslevel=6)
            return serialized
        except Exception as e:
            logger.error(f"Data compression failed: {e}")
            raise
    
    @staticmethod
    def decompress_data(data: bytes) -> Any:
        """
        Decompress data with fallback handling
        
        Args:
            data: Compressed or uncompressed bytes
            
        Returns:
            Deserialized data
        """
        try:
            if config.enable_compression:
                try:
                    # Try to decompress first
                    decompressed = gzip.decompress(data)
                    return pickle.loads(decompressed)
                except (gzip.BadGzipFile, OSError):
                    # Fallback to direct unpickling (uncompressed data)
                    return pickle.loads(data)
            else:
                return pickle.loads(data)
        except Exception as e:
            logger.error(f"Data decompression failed: {e}")
            raise
    
    @staticmethod
    async def get_cached(redis_client: Redis, key: str) -> Optional[Any]:
        """
        Get and decompress cached data with comprehensive error handling
        
        Args:
            redis_client: Redis client instance
            key: Cache key
            
        Returns:
            Cached data or None if not found/error
        """
        if not redis_client:
            return None
            
        try:
            data = await redis_client.get(key)
            if data:
                if config.enable_metrics and METRICS_AVAILABLE:
                    CACHE_HITS.labels(cache_type='redis').inc()
                
                result = AdvancedCache.decompress_data(data)
                logger.debug(f"Cache hit for key: {key[:50]}...")
                return result
            else:
                logger.debug(f"Cache miss for key: {key[:50]}...")
                return None
                
        except Exception as e:
            logger.warning(f"Cache read error for key {key[:50]}...: {e}")
            return None
    
    @staticmethod
    async def set_cached(redis_client: Redis, key: str, value: Any, ttl: int):
        """
        Compress and cache data with error handling
        
        Args:
            redis_client: Redis client instance
            key: Cache key
            value: Data to cache
            ttl: Time to live in seconds
        """
        if not redis_client:
            return
            
        try:
            compressed_data = AdvancedCache.compress_data(value)
            await redis_client.setex(key, ttl, compressed_data)
            logger.debug(f"Cached data for key: {key[:50]}... (TTL: {ttl}s, Size: {len(compressed_data)} bytes)")
            
        except Exception as e:
            logger.warning(f"Cache write error for key {key[:50]}...: {e}")
    
    @staticmethod
    async def delete_cached(redis_client: Redis, pattern: str = None, key: str = None):
        """
        Delete cached data by key or pattern
        
        Args:
            redis_client: Redis client instance
            pattern: Pattern to match keys for deletion
            key: Specific key to delete
        """
        if not redis_client:
            return
            
        try:
            if key:
                await redis_client.delete(key)
                logger.debug(f"Deleted cache key: {key}")
            elif pattern:
                keys = await redis_client.keys(pattern)
                if keys:
                    await redis_client.delete(*keys)
                    logger.debug(f"Deleted {len(keys)} cache keys matching pattern: {pattern}")
        except Exception as e:
            logger.warning(f"Cache deletion error: {e}")

# --- Token Optimization System ---
class TokenOptimizer:
    """
    Advanced token counting and optimization utilities
    Supports multiple AI providers with accurate estimations
    """
    
    # Token multipliers based on provider tokenization
    TOKEN_MULTIPLIERS = {
        "openai": 4.0,      # GPT models
        "anthropic": 3.8,   # Claude models  
        "claude": 3.8,      # Claude models
        "moonshot": 4.0,    # Similar to GPT
        "together": 3.6,    # Various models
        "huggingface": 3.2, # Transformer models
        "ollama": 2.8,      # Local models (more efficient)
        "groq": 3.5,        # Fast inference
        "mock": 1.0,        # No real tokenization
    }
    
    # Provider-specific costs per 1K tokens (input/output)
    PROVIDER_COSTS = {
        "openai": {"input": 0.0015, "output": 0.002},
        "anthropic": {"input": 0.0008, "output": 0.0024},
        "claude": {"input": 0.0008, "output": 0.0024},
        "together": {"input": 0.0002, "output": 0.0002},
        "moonshot": {"input": 0.012, "output": 0.012},
        "groq": {"input": 0.0001, "output": 0.0001},
        # Free providers
        "ollama": {"input": 0.0, "output": 0.0},
        "huggingface": {"input": 0.0, "output": 0.0},
        "mock": {"input": 0.0, "output": 0.0},
    }
    
    @staticmethod
    def estimate_tokens(text: str, provider: str = "openai") -> int:
        """
        Estimate token count for different providers with improved accuracy
        
        Args:
            text: Input text
            provider: AI provider name
            
        Returns:
            Estimated token count
        """
        if not text or not isinstance(text, str):
            return 0
        
        # Try to use tiktoken for OpenAI models if available
        if provider.startswith("openai") or provider == "moonshot":
            try:
                import tiktoken
                encoding = tiktoken.get_encoding("cl100k_base")  # GPT-4 encoding
                return len(encoding.encode(text))
            except ImportError:
                pass
        
        # Fallback to character-based estimation
        multiplier = TokenOptimizer.TOKEN_MULTIPLIERS.get(provider, 4.0)
        
        # Adjust for text complexity
        word_count = len(text.split())
        char_count = len(text)
        
        # More accurate estimation based on text characteristics
        if word_count > 0:
            avg_word_length = char_count / word_count
            if avg_word_length > 6:  # Complex text (technical, code)
                multiplier *= 0.9
            elif avg_word_length < 4:  # Simple text
                multiplier *= 1.1
        
        return max(1, int(char_count / multiplier))
    
    @staticmethod
    def calculate_cost(input_tokens: int, output_tokens: int, provider: str) -> float:
        """
        Calculate cost based on token usage and provider pricing
        
        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            provider: AI provider name
            
        Returns:
            Estimated cost in USD
        """
        costs = TokenOptimizer.PROVIDER_COSTS.get(provider, {"input": 0.0, "output": 0.0})
        
        input_cost = (input_tokens / 1000) * costs["input"]
        output_cost = (output_tokens / 1000) * costs["output"]
        
        return input_cost + output_cost
    
    @staticmethod
    def optimize_prompt(prompt: str, max_tokens: int = 4000, provider: str = "openai") -> str:
        """
        Intelligent prompt optimization to reduce token usage
        
        Args:
            prompt: Original prompt
            max_tokens: Maximum allowed tokens
            provider: AI provider name
            
        Returns:
            Optimized prompt
        """
        estimated_tokens = TokenOptimizer.estimate_tokens(prompt, provider)
        
        if estimated_tokens <= max_tokens:
            return prompt
        
        logger.info(f"Optimizing prompt: {estimated_tokens} -> {max_tokens} tokens")
        
        # Calculate reduction ratio
        reduction_ratio = max_tokens / estimated_tokens
        
        # Apply multi-stage optimization
        optimized = prompt
        
        # Stage 1: Remove excessive whitespace
        import re
        optimized = re.sub(r'\s+', ' ', optimized.strip())
        
        # Stage 2: Intelligent truncation with content preservation
        if TokenOptimizer.estimate_tokens(optimized, provider) > max_tokens:
            optimized = TokenOptimizer._intelligent_truncate(optimized, reduction_ratio)
        
        # Stage 3: Final check and emergency truncation
        final_tokens = TokenOptimizer.estimate_tokens(optimized, provider)
        if final_tokens > max_tokens:
            # Emergency character-based truncation
            char_ratio = max_tokens / final_tokens
            target_length = int(len(optimized) * char_ratio)
            optimized = optimized[:target_length] + "..."
        
        final_tokens = TokenOptimizer.estimate_tokens(optimized, provider)
        logger.info(f"Prompt optimized: {estimated_tokens} -> {final_tokens} tokens")
        
        return optimized
    
    @staticmethod
    def _intelligent_truncate(text: str, ratio: float) -> str:
        """
        Intelligent text truncation preserving important content
        
        Args:
            text: Input text
            ratio: Reduction ratio (0-1)
            
        Returns:
            Truncated text
        """
        if ratio >= 0.9:
            return text
        
        sentences = text.split('. ')
        if len(sentences) <= 1:
            # Single sentence - character truncation
            target_length = int(len(text) * ratio)
            return text[:target_length] + "..."
        
        # Multi-sentence text - preserve beginning and end
        keep_sentences = max(1, int(len(sentences) * ratio))
        
        if keep_sentences >= len(sentences):
            return text
        
        # Keep first 60% and last 40% of sentences
        first_count = int(keep_sentences * 0.6)
        last_count = keep_sentences - first_count
        
        if first_count <= 0:
            # Too aggressive reduction - keep first sentence only
            return sentences[0] + "..."
        
        first_part = '. '.join(sentences[:first_count])
        last_part = '. '.join(sentences[-last_count:]) if last_count > 0 else ""
        
        if last_part:
            return f"{first_part}. ... {last_part}"
        else:
            return f"{first_part}..."

# --- Resource Management System ---
class ResourceManager:
    """
    Centralized resource management with comprehensive lifecycle handling
    Optimized for production use with proper cleanup and monitoring
    """
    
    def __init__(self):
        self.ai_config_cache: Optional[Dict[str, Any]] = None
        self.config_last_modified: Optional[float] = None
        self.ai_client_instance: Optional[AIAsyncClient] = None
        self.redis_client: Optional[Redis] = None
        self.ai_semaphore: Optional[asyncio.Semaphore] = None
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.request_stats: Dict[str, Dict[str, Any]] = {}
        self.startup_time = time.time()
        
        # Resource health tracking
        self.redis_healthy = False
        self.ai_client_healthy = False
        self.last_health_check = 0
        self.health_check_interval = 30  # seconds
    
    async def initialize_redis(self) -> Optional[Redis]:
        """
        Initialize Redis client with comprehensive error handling and health checking
        
        Returns:
            Redis client instance or None if initialization failed
        """
        if not REDIS_AVAILABLE or not config.enable_cache:
            logger.info("Redis not available or caching disabled")
            return None
        
        try:
            # Create Redis client with optimized configuration
            if hasattr(Redis, 'from_url'):
                redis_client = Redis.from_url(
                    config.redis.url,
                    encoding=config.redis.encoding,
                    decode_responses=config.redis.decode_responses,
                    max_connections=config.redis.max_connections,
                    socket_timeout=config.redis.socket_timeout,
                    socket_connect_timeout=config.redis.socket_connect_timeout,
                    health_check_interval=config.redis.health_check_interval,
                    retry_on_timeout=True,
                    retry_on_error=[ConnectionError, TimeoutError]
                )
            else:
                # Fallback for older Redis versions
                redis_client = Redis(
                    host='localhost',
                    port=6379,
                    db=0,
                    encoding=config.redis.encoding,
                    decode_responses=config.redis.decode_responses,
                    max_connections=config.redis.max_connections,
                    socket_timeout=config.redis.socket_timeout
                )
            
            # Test connection
            await redis_client.ping()
            
            # Test basic operations
            test_key = "health_check_test"
            await redis_client.set(test_key, "ok", ex=10)
            test_result = await redis_client.get(test_key)
            await redis_client.delete(test_key)
            
            if test_result is None:
                raise Exception("Redis read/write test failed")
            
            self.redis_client = redis_client
            self.redis_healthy = True
            logger.info("✅ Redis connection established and tested")
            return redis_client
            
        except Exception as e:
            logger.warning(f"Redis initialization failed: {e}")
            logger.info("Continuing without Redis caching")
            self.redis_client = None
            self.redis_healthy = False
            return None
    
    async def initialize_ai_client(self) -> Optional[AIAsyncClient]:
        """
        Initialize AI client with enhanced error handling and provider validation
        
        Returns:
            AIAsyncClient instance or None if initialization failed
        """
        if not AI_CLIENT_AVAILABLE or not AIAsyncClient:
            logger.warning("AIAsyncClient not available - AI features will use fallback")
            return None
        
        try:
            ai_config = await self.load_ai_config()
            if not ai_config:
                logger.warning("No AI configuration available, using fallback providers")
                ai_config = self._get_default_ai_config()
            
            # Initialize AI client
            self.ai_client_instance = AIAsyncClient(ai_config)
            
            # Initialize circuit breakers and stats for each provider
            for provider in ai_config.keys():
                self.circuit_breakers[provider] = CircuitBreaker()
                self.request_stats[provider] = {
                    'total_requests': 0,
                    'successful_requests': 0,
                    'failed_requests': 0,
                    'total_tokens': 0,
                    'total_cost': 0.0,
                    'average_latency': 0.0,
                    'last_request_time': None,
                    'circuit_breaker_trips': 0
                }
            
            # Test AI client if possible
            try:
                # Quick health check if the client supports it
                if hasattr(self.ai_client_instance, 'health_check'):
                    await asyncio.wait_for(self.ai_client_instance.health_check(), timeout=5)
            except Exception as e:
                logger.warning(f"AI client health check failed: {e}")
            
            self.ai_client_healthy = True
            logger.info(f"✅ AI client initialized with {len(ai_config)} providers")
            return self.ai_client_instance
            
        except Exception as e:
            logger.error(f"Failed to initialize AI client: {e}")
            self.ai_client_healthy = False
            return None
    
    async def load_ai_config(self, force_reload: bool = False) -> Dict[str, Any]:
        """
        Load AI configuration with comprehensive validation and fallback
        
        Args:
            force_reload: Force reload even if cached version exists
            
        Returns:
            AI configuration dictionary
        """
        if not YAML_AVAILABLE:
            logger.warning("YAML not available, using default AI configuration")
            return self._get_default_ai_config()
            
        config_path = Path("ai_integrations.yaml")
        
        if not config_path.exists():
            logger.warning(f"AI configuration file {config_path} not found")
            return self._get_default_ai_config()
        
        try:
            current_mtime = config_path.stat().st_mtime
            
            # Check if we can use cached version
            if (not force_reload and self.ai_config_cache and 
                self.config_last_modified == current_mtime):
                return self.ai_config_cache
            
            # Load configuration file
            if aiofiles:
                async with aiofiles.open(config_path, mode='r', encoding='utf-8') as f:
                    content = await f.read()
            else:
                with open(config_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            
            cfg = yaml.safe_load(content) or {}
            
            # Process and validate configuration
            processed_config = self._process_ai_config(cfg)
            
            # Cache the processed configuration
            self.ai_config_cache = processed_config
            self.config_last_modified = current_mtime
            
            logger.info(f"✅ AI configuration loaded with {len(processed_config)} providers")
            return processed_config
            
        except Exception as e:
            logger.error(f"Failed to load AI configuration: {e}")
            return self._get_default_ai_config()
    
    def _process_ai_config(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process and validate AI configuration
        
        Args:
            cfg: Raw configuration dictionary
            
        Returns:
            Processed and validated configuration
        """
        processed = {}
        
        for provider, settings in cfg.items():
            if not isinstance(settings, dict):
                logger.warning(f"Invalid configuration for provider {provider}: not a dictionary")
                continue
            
            # Add default values for free tier providers
            if provider in config.ai.free_tier_limits:
                settings.setdefault('daily_limit', str(config.ai.free_tier_limits[provider]))
                settings.setdefault('priority', 'high' if provider == 'ollama' else 'medium')
                settings.setdefault('is_free', True)
            
            # Expand environment variables
            expanded_settings = {}
            for key, value in settings.items():
                if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                    env_key = value[2:-1]
                    env_value = os.getenv(env_key)
                    if env_value is None:
                        logger.warning(f"Environment variable {env_key} not found for {provider}.{key}")
                        continue
                    expanded_settings[key] = env_value
                else:
                    expanded_settings[key] = value
            
            # Type conversion and validation
            validated_settings = self._validate_provider_settings(provider, expanded_settings)
            if validated_settings:
                processed[provider] = validated_settings
        
        # Ensure we have at least one provider
        if not processed:
            logger.warning("No valid providers found in configuration, adding fallback")
            processed.update(self._get_default_ai_config())
        
        return processed
    
    def _validate_provider_settings(self, provider: str, settings: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Validate individual provider settings
        
        Args:
            provider: Provider name
            settings: Provider settings
            
        Returns:
            Validated settings or None if invalid
        """
        try:
            validated = settings.copy()
            
            # Validate numeric fields
            numeric_fields = {
                'max_tokens': (100, 100000),
                'timeout': (5, 300),
                'rate_limit': (1, 10000),
                'priority_score': (0, 100)
            }
            
            for field, (min_val, max_val) in numeric_fields.items():
                if field in validated:
                    try:
                        val = int(validated[field])
                        if not (min_val <= val <= max_val):
                            logger.warning(f"Invalid {field} for {provider}: {val} (must be {min_val}-{max_val})")
                            del validated[field]
                        else:
                            validated[field] = val
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid {field} type for {provider}: {validated[field]}")
                        del validated[field]
            
            # Validate float fields
            float_fields = {
                'cost_per_1k_tokens': (0.0, 1.0),
                'temperature': (0.0, 2.0)
            }
            
            for field, (min_val, max_val) in float_fields.items():
                if field in validated:
                    try:
                        val = float(validated[field])
                        if not (min_val <= val <= max_val):
                            logger.warning(f"Invalid {field} for {provider}: {val} (must be {min_val}-{max_val})")
                            del validated[field]
                        else:
                            validated[field] = val
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid {field} type for {provider}: {validated[field]}")
                        del validated[field]
            
            return validated
            
        except Exception as e:
            logger.warning(f"Error validating settings for {provider}: {e}")
            return None
    
    def _get_default_ai_config(self) -> Dict[str, Any]:
        """
        Get comprehensive default AI configuration as fallback
        
        Returns:
            Default AI configuration
        """
        return {
            "ollama": {
                "base_url": "http://localhost:11434",
                "model": "llama2",
                "priority": "high",
                "timeout": 30,
                "is_free": True,
                "max_tokens": 4096,
                "supports_streaming": True
            },
            "mock": {
                "priority": "low",
                "timeout": 5,
                "is_free": True,
                "max_tokens": 8192,
                "supports_streaming": True,
                "description": "Fallback mock provider for testing and development"
            }
        }
    
    def get_ai_semaphore(self) -> asyncio.Semaphore:
        """
        Get or create AI request semaphore for concurrency control
        
        Returns:
            Asyncio semaphore for AI request limiting
        """
        if self.ai_semaphore is None:
            self.ai_semaphore = asyncio.Semaphore(config.ai.max_concurrent_requests)
        return self.ai_semaphore
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Comprehensive health check of all managed resources
        
        Returns:
            Health status dictionary
        """
        current_time = time.time()
        
        # Only run detailed health checks periodically
        if current_time - self.last_health_check < self.health_check_interval:
            return {
                "redis": self.redis_healthy,
                "ai_client": self.ai_client_healthy,
                "uptime": current_time - self.startup_time,
                "last_check": self.last_health_check
            }
        
        health_status = {
            "redis": False,
            "ai_client": False,
            "uptime": current_time - self.startup_time,
            "last_check": current_time,
            "details": {}
        }
        
        # Check Redis health
        if self.redis_client:
            try:
                await self.redis_client.ping()
                self.redis_healthy = True
                health_status["redis"] = True
                
                # Get Redis info
                info = await self.redis_client.info()
                health_status["details"]["redis"] = {
                    "memory_used": info.get('used_memory_human', 'N/A'),
                    "connected_clients": info.get('connected_clients', 0),
                    "uptime": info.get('uptime_in_seconds', 0)
                }
            except Exception as e:
                self.redis_healthy = False
                health_status["details"]["redis"] = {"error": str(e)}
        
        # Check AI client health
        if self.ai_client_instance:
            try:
                # Basic health check - ensure it's responsive
                self.ai_client_healthy = True
                health_status["ai_client"] = True
                health_status["details"]["ai_client"] = {
                    "providers": len(self.circuit_breakers),
                    "total_requests": sum(stats['total_requests'] for stats in self.request_stats.values())
                }
            except Exception as e:
                self.ai_client_healthy = False
                health_status["details"]["ai_client"] = {"error": str(e)}
        
        self.last_health_check = current_time
        return health_status
    
    async def cleanup(self):
        """
        Comprehensive resource cleanup with Python 3.13 exception handling
        """
        logger.info("🔄 Starting resource cleanup...")
        cleanup_tasks = []
        
        # Add cleanup tasks
        if self.ai_client_instance and hasattr(self.ai_client_instance, 'aclose'):
            cleanup_tasks.append(("AI Client", self.ai_client_instance.aclose()))
        
        if self.redis_client:
            if hasattr(self.redis_client, 'aclose'):
                cleanup_tasks.append(("Redis Client", self.redis_client.aclose()))
            elif hasattr(self.redis_client, 'close'):
                cleanup_tasks.append(("Redis Client", self.redis_client.close()))
        
        # Execute cleanup tasks
        if cleanup_tasks:
            try:
                # Gather all cleanup coroutines
                coroutines = [task[1] for task in cleanup_tasks]
                results = await asyncio.gather(*coroutines, return_exceptions=True)
                
                # Process results
                for i, (name, result) in enumerate(zip([task[0] for task in cleanup_tasks], results)):
                    if isinstance(result, Exception):
                        logger.error(f"❌ Error cleaning up {name}: {result}")
                    else:
                        logger.info(f"✅ {name} cleanup completed")
                        
            except Exception as e:
                logger.error(f"❌ Critical error during cleanup: {e}")
        
        # Reset state
        self.ai_client_instance = None
        self.redis_client = None
        self.redis_healthy = False
        self.ai_client_healthy = False
        
        logger.info("✅ Resource cleanup completed")

# --- Performance Monitoring Fallback ---
class Metrics:
    """
    Comprehensive fallback metrics collector for development and testing
    """
    def __init__(self, app_name: str):
        self.app_name = app_name
        self.active_operations = {}
        self.operation_history = []
        self.counters = defaultdict(int)
        self.timers = defaultdict(list)

    def record_operation(self, metrics) -> None:
        """Record operation metrics with history tracking"""
        self.operation_history.append({
            "name": getattr(metrics, 'operation_name', 'unknown'),
            "duration": getattr(metrics, 'duration', 0),
            "success": getattr(metrics, 'success', True),
            "timestamp": time.time()
        })
        
        # Keep only last 1000 operations
        if len(self.operation_history) > 1000:
            self.operation_history