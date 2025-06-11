# main.py - Production-Ready AI Aggregator Pro with Python 3.13 Compatibility
# main.py - Python 3.13 Compatible AI Aggregator Pro
# version -5 Claude-Copilot - 07.06.25 - (not finished!)
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
        """Fallback data discovery with realistic mock data"""
        categories = ["electronics", "books", "clothing", "home", "sports"]
        products = []
        
        for i in range(1, 21):  # Generate 20 mock products
            category = categories[i % len(categories)]
            products.append({
                "name": f"Sample {category.title()} Product {i}",
                "price": round(50 + (i * 15.5), 2),
                "category": category,
                "description": f"High-quality {category} item with excellent features",
                "source": "mock_discovery"
            })
        
        return products
    
    async def parse_and_standardize(raw_data, category="general"):
        """Fallback data parsing function with proper error handling"""
        if not raw_data:
            return []
            
        standardized = []
        for i, item in enumerate(raw_data, 1):
            try:
                standardized.append(StandardizedProduct(
                    id=i,
                    name=item.get("name", f"Product {i}"),
                    price=float(item.get("price", 0.0)),
                    category=item.get("category", category),
                    description=item.get("description", f"Description for {item.get('name', 'product')}"),
                    source=item.get("source", "fallback_parser"),
                    provider=f"Provider {(i % 3) + 1}"
                ))
            except Exception as e:
                logging.warning(f"Error parsing item {i}: {e}")
                continue
        
        return standardized
    
    async def store_standardized_data(session, data):
        """Fallback data storage function with validation"""
        if not data:
            logging.warning("No data provided for storage")
            return False
            
        logging.info(f"Fallback storage: would store {len(data)} items")
        return True
    
    async def search_and_filter_products(session=None, **filters):
        """Fallback product search with comprehensive mock data generation"""
        limit = filters.get('limit', 10)
        offset = filters.get('offset', 0)
        category = filters.get('product_type') or filters.get('category', 'general')
        min_price = filters.get('min_price', 0)
        max_price = filters.get('max_price', 1000)
        query = filters.get('query', '')
        
        # Generate realistic mock products based on filters
        products = []
        base_names = [
            "Premium", "Professional", "Advanced", "Deluxe", "Standard",
            "Economy", "Enterprise", "Ultimate", "Pro", "Basic"
        ]
        
        for i in range(offset + 1, offset + limit + 1):
            # Calculate price within range
            price_range = max_price - min_price
            price = min_price + ((i * 37) % price_range)
            
            # Generate name based on query and category
            base_name = base_names[(i - 1) % len(base_names)]
            if query:
                name = f"{base_name} {query.title()} {category.title()} {i}"
            else:
                name = f"{base_name} {category.title()} Product {i}"
            
            products.append(StandardizedProduct(
                id=i,
                name=name,
                description=f"High-quality {category} item featuring {query or 'advanced features'} with excellent performance and competitive pricing.",
                price=float(round(price, 2)),
                category=category,
                source="fallback_search",
                provider=f"Provider {((i - 1) % 5) + 1}"
            ))
        
        return products

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
    
    # Set specific logger levels for cleaner output
    logging.getLogger('uvicorn').setLevel(logging.WARNING)
    logging.getLogger('fastapi').setLevel(logging.INFO)

# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)

# Comprehensive import status logging
logger.info("=" * 80)
logger.info("AI AGGREGATOR PRO - STARTUP REPORT")
logger.info("=" * 80)
logger.info(f"Python Version: {sys.version}")
logger.info(f"Platform: {platform.platform()}")
logger.info(f"Current Time: {datetime.now().isoformat()}")
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
        Check if request is allowed based on rate limit using sliding window
        
        Args:
            key: Unique identifier for rate limiting (e.g., IP address)
            limit: Maximum requests allowed in window
            window: Time window in seconds (default: 60)
            
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
        """
        Get remaining requests in current window
        
        Args:
            key: Rate limit key
            limit: Request limit
            window: Time window in seconds
            
        Returns:
            Number of remaining requests
        """
        current_time = time.time()
        recent_requests = [
            req_time for req_time in self.requests.get(key, [])
            if current_time - req_time < window
        ]
        return max(0, limit - len(recent_requests))
    
    async def _periodic_cleanup(self, current_time: float):
        """Periodic cleanup of old rate limit data to prevent memory leaks"""
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
    Production-ready rate limiting decorator with comprehensive error handling
    
    Args:
        requests_per_minute: Maximum requests allowed per minute per client
        
    Returns:
        Decorator function for applying rate limiting
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
            
            # Generate rate limit key with proper IP extraction
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

# --- Configuration Management with Comprehensive Validation ---
@dataclass
class DatabaseConfig:
    """Database configuration with comprehensive validation and connection pooling"""
    url: str = os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./app.db')
    pool_size: int = int(os.getenv('DB_POOL_SIZE', '20'))
    max_overflow: int = int(os.getenv('DB_MAX_OVERFLOW', '30'))
    echo: bool = os.getenv('DB_ECHO', 'false').lower() == 'true'
    pool_timeout: int = int(os.getenv('DB_POOL_TIMEOUT', '30'))
    pool_recycle: int = int(os.getenv('DB_POOL_RECYCLE', '3600'))
    
    def __post_init__(self):
        """Validate database configuration with comprehensive checks"""
        if not self.url:
            raise ValueError("Database URL cannot be empty")
        if self.pool_size < 1:
            raise ValueError("Database pool size must be positive")
        if self.max_overflow < 0:
            raise ValueError("Database max overflow must be non-negative")
        if self.pool_timeout <= 0:
            raise ValueError("Database pool timeout must be positive")
        if self.pool_recycle <= 0:
            raise ValueError("Database pool recycle time must be positive")

@dataclass
class RedisConfig:
    """Redis configuration with connection validation and health monitoring"""
    url: str = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    max_connections: int = int(os.getenv('REDIS_MAX_CONNECTIONS', '20'))
    socket_timeout: float = float(os.getenv('REDIS_SOCKET_TIMEOUT', '5.0'))
    socket_connect_timeout: float = float(os.getenv('REDIS_CONNECT_TIMEOUT', '5.0'))
    health_check_interval: int = int(os.getenv('REDIS_HEALTH_CHECK_INTERVAL', '30'))
    encoding: str = 'utf-8'
    decode_responses: bool = False
    
    def __post_init__(self):
        """Validate Redis configuration with comprehensive parameter checking"""
        if self.max_connections < 1:
            raise ValueError("Redis max connections must be positive")
        if self.socket_timeout <= 0:
            raise ValueError("Redis socket timeout must be positive")
        if self.socket_connect_timeout <= 0:
            raise ValueError("Redis connect timeout must be positive")
        if self.health_check_interval < 10:
            raise ValueError("Redis health check interval must be at least 10 seconds")

@dataclass
class SecurityConfig:
    """Security configuration with comprehensive validation and best practices"""
    secret_key: str = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    api_key_header: str = os.getenv('API_KEY_HEADER', 'X-API-Key')
    allowed_origins: List[str] = field(default_factory=lambda: 
        [origin.strip() for origin in os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000,http://localhost:8080').split(',') if origin.strip()]
    )
    trusted_hosts: List[str] = field(default_factory=lambda: 
        [host.strip() for host in os.getenv('TRUSTED_HOSTS', '').split(',') if host.strip()]
    )
    cors_max_age: int = int(os.getenv('CORS_MAX_AGE', '3600'))
    enable_csrf_protection: bool = os.getenv('ENABLE_CSRF', 'false').lower() == 'true'
    
    def __post_init__(self):
        """Validate security configuration with production-ready checks"""
        environment = os.getenv('ENVIRONMENT', 'development')
        
        # Secret key validation
        if len(self.secret_key) < 16:
            if environment == 'production':
                raise ValueError("Secret key must be at least 16 characters in production")
            else:
                logger.warning("⚠️  Secret key is too short for production use")
        
        # Check for default secret key in production
        if environment == 'production' and 'dev-secret' in self.secret_key:
            raise ValueError("Default secret key cannot be used in production")
        
        # CORS validation
        if not self.allowed_origins:
            logger.warning("⚠️  No CORS origins configured - this may cause issues in browser clients")
        
        # Validate origin URLs format
        for origin in self.allowed_origins:
            if not (origin.startswith('http://') or origin.startswith('https://') or origin == '*'):
                logger.warning(f"⚠️  Potentially invalid CORS origin: {origin}")
        
        # Validate CORS max age
        if self.cors_max_age < 0:
            raise ValueError("CORS max age must be non-negative")

@dataclass
class AIConfig:
    """AI provider configuration with enhanced validation and cost management"""
    default_provider: str = os.getenv('AI_DEFAULT_PROVIDER', 'ollama')
    max_concurrent_requests: int = int(os.getenv('MAX_CONCURRENT_AI_REQUESTS', '15'))
    request_timeout: int = int(os.getenv('AI_REQUEST_TIMEOUT', '45'))
    max_prompt_length: int = int(os.getenv('MAX_PROMPT_LENGTH', '32000'))
    cost_budget_daily: float = float(os.getenv('AI_COST_BUDGET_DAILY', '10.0'))
    cost_budget_monthly: float = float(os.getenv('AI_COST_BUDGET_MONTHLY', '300.0'))
    enable_cost_tracking: bool = os.getenv('ENABLE_COST_TRACKING', 'true').lower() == 'true'
    
    # Free tier limits for different providers
    free_tier_limits: Dict[str, int] = field(default_factory=lambda: {
        'ollama': 999999,       # Local model - virtually unlimited
        'huggingface': 1000,    # HuggingFace free tier
        'together': 25,         # Together AI free tier
        'openai': 3,            # OpenAI free tier (very limited)
        'mock': 999999,         # Mock provider - unlimited
        'groq': 100,            # Groq free tier
    })
    
    def __post_init__(self):
        """Validate AI configuration with comprehensive parameter checking"""
        if self.max_concurrent_requests < 1:
            raise ValueError("Max concurrent requests must be positive")
        if self.max_concurrent_requests > 100:
            logger.warning("⚠️  Very high concurrent request limit may cause resource issues")
        
        if self.request_timeout < 5:
            raise ValueError("Request timeout must be at least 5 seconds")
        if self.request_timeout > 300:
            logger.warning("⚠️  Very high request timeout may cause user experience issues")
        
        if self.max_prompt_length < 100:
            raise ValueError("Max prompt length must be at least 100 characters")
        if self.max_prompt_length > 100000:
            logger.warning("⚠️  Very large max prompt length may cause memory issues")
        
        if self.cost_budget_daily <= 0:
            raise ValueError("Daily cost budget must be positive")
        if self.cost_budget_monthly <= 0:
            raise ValueError("Monthly cost budget must be positive")
        
        # Check if daily budget makes sense compared to monthly
        if self.cost_budget_daily * 30 > self.cost_budget_monthly * 2:
            logger.warning("⚠️  Daily budget seems high compared to monthly budget")

@dataclass
class AppConfig:
    """
    Main application configuration with comprehensive validation
    Optimized for Python 3.13 with enhanced error handling and monitoring
    """
    app_name: str = os.getenv('APP_NAME', 'AI Aggregator Pro')
    version: str = '3.3.0'  # Updated version with all fixes
    environment: str = os.getenv('ENVIRONMENT', 'development')
    debug: bool = os.getenv('DEBUG', 'false').lower() == 'true'
    python_version: str = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    
    # Server configuration
    host: str = os.getenv('HOST', '0.0.0.0')
    port: int = int(os.getenv('PORT', '8000'))
    workers: int = int(os.getenv('WORKERS', '1'))
    reload: bool = os.getenv('RELOAD', 'false').lower() == 'true'
    
    # Feature flags with intelligent defaults based on environment
    enable_cache: bool = REDIS_AVAILABLE and os.getenv('ENABLE_CACHE', 'true').lower() == 'true'
    enable_compression: bool = os.getenv('ENABLE_COMPRESSION', 'true').lower() == 'true'
    enable_metrics: bool = METRICS_AVAILABLE and os.getenv('ENABLE_METRICS', 'true').lower() == 'true'
    enable_docs: bool = os.getenv('ENABLE_DOCS', 'true' if os.getenv('ENVIRONMENT', 'development') != 'production' else 'false').lower() == 'true'
    enable_openapi: bool = os.getenv('ENABLE_OPENAPI', 'true').lower() == 'true'
    
    # Performance and caching settings
    cache_ttl_short: int = int(os.getenv('CACHE_TTL_SHORT', '900'))        # 15 minutes
    cache_ttl_long: int = int(os.getenv('CACHE_TTL_LONG', '3600'))         # 1 hour
    cache_ttl_fallback: int = int(os.getenv('CACHE_TTL_FALLBACK', '300'))  # 5 minutes
    
    # Request processing settings
    max_request_size: int = int(os.getenv('MAX_REQUEST_SIZE', '1048576'))  # 1MB
    request_timeout: int = int(os.getenv('REQUEST_TIMEOUT', '30'))         # 30 seconds
    
    # Sub-configurations
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    
    def __post_init__(self):
        """Comprehensive application configuration validation with environment-specific checks"""
        # Environment validation
        valid_environments = ['development', 'staging', 'production']
        if self.environment not in valid_environments:
            raise ValueError(f"Environment must be one of: {valid_environments}")
        
        # Server configuration validation
        if not 1 <= self.port <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        if self.workers < 1:
            raise ValueError("Workers count must be positive")
        if self.workers > 20:
            logger.warning("⚠️  High worker count may cause resource contention")
        
        # Performance settings validation
        if self.cache_ttl_short > self.cache_ttl_long:
            logger.warning("⚠️  Short cache TTL is greater than long cache TTL")
        if any(ttl <= 0 for ttl in [self.cache_ttl_short, self.cache_ttl_long, self.cache_ttl_fallback]):
            raise ValueError("All cache TTL values must be positive")
        
        if self.max_request_size < 1024:  # 1KB minimum
            raise ValueError("Max request size must be at least 1KB")
        if self.max_request_size > 100 * 1024 * 1024:  # 100MB maximum
            logger.warning("⚠️  Very large max request size may cause memory issues")
        
        if self.request_timeout < 1:
            raise ValueError("Request timeout must be positive")
        if self.request_timeout > 300:
            logger.warning("⚠️  Very high request timeout may cause poor user experience")
        
        # Production-specific validations
        if self.environment == 'production':
            if self.debug:
                logger.warning("⚠️  Debug mode is enabled in production - this is not recommended")
            if self.reload:
                logger.warning("⚠️  Reload is enabled in production - this is not recommended")
            if self.enable_docs and not os.getenv('FORCE_ENABLE_DOCS'):
                logger.warning("⚠️  API documentation is enabled in production")
        
        # Development-specific optimizations
        if self.environment == 'development':
            if not self.enable_docs:
                logger.info("📖 Consider enabling API docs for development")
        
        # Log configuration summary
        logger.info(f"✅ Application configured for {self.environment} environment")
        logger.info(f"   Server: {self.host}:{self.port} (workers: {self.workers})")
        logger.info(f"   Features: docs={self.enable_docs}, cache={self.enable_cache}, metrics={self.enable_metrics}")
        logger.info(f"   Debug mode: {self.debug}, Reload: {self.reload}")

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
    config.environment = 'development'
    logger.warning("⚠️  Using fallback configuration - some features may not work correctly")

# --- Circuit Breaker Implementation ---
@dataclass
class CircuitBreaker:
    """
    Production-ready circuit breaker implementing the circuit breaker pattern
    Provides automatic failure recovery and prevents cascade failures
    """
    failure_threshold: int = 5                    # Number of failures before opening
    recovery_timeout: int = 60                    # Seconds to wait before attempting recovery
    half_open_max_calls: int = 3                  # Max calls in half-open state
    failure_count: int = 0                        # Current failure count
    success_count: int = 0                        # Success count in half-open state
    last_failure_time: Optional[float] = None     # Timestamp of last failure
    state: str = "CLOSED"                         # Current state: CLOSED, OPEN, HALF_OPEN
    
    def is_request_allowed(self) -> bool:
        """
        Check if request is allowed based on current circuit breaker state
        
        Returns:
            True if request should be allowed, False otherwise
        """
        current_time = time.time()
        
        if self.state == "CLOSED":
            # Normal operation - all requests allowed
            return True
        elif self.state == "OPEN":
            # Circuit is open - check if recovery timeout has passed
            if current_time - (self.last_failure_time or 0) > self.recovery_timeout:
                self.state = "HALF_OPEN"
                self.success_count = 0
                logger.info(f"Circuit breaker transitioning to HALF_OPEN state")
                return True
            return False
        else:  # HALF_OPEN
            # Limited testing mode - allow limited requests
            return self.success_count < self.half_open_max_calls
    
    def record_success(self):
        """Record successful request and update circuit breaker state accordingly"""
        if self.state == "HALF_OPEN":
            self.success_count += 1
            if self.success_count >= self.half_open_max_calls:
                # Enough successful requests - circuit is healthy
                self.state = "CLOSED"
                self.failure_count = 0
                logger.info(f"Circuit breaker transitioning to CLOSED state after successful recovery")
        elif self.state == "CLOSED":
            # Gradual recovery of failure count on success
            self.failure_count = max(0, self.failure_count - 1)
    
    def record_failure(self):
        """Record failed request and update circuit breaker state accordingly"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == "CLOSED" and self.failure_count >= self.failure_threshold:
            # Too many failures - open the circuit
            self.state = "OPEN"
            logger.warning(f"Circuit breaker transitioning to OPEN state after {self.failure_count} failures")
        elif self.state == "HALF_OPEN":
            # Failure during recovery - back to open state
            self.state = "OPEN"
            logger.warning(f"Circuit breaker returning to OPEN state after failure during recovery")
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get comprehensive circuit breaker status for monitoring
        
        Returns:
            Dictionary containing detailed circuit breaker status
        """
        current_time = time.time()
        time_to_recovery = 0
        
        if self.state == "OPEN" and self.last_failure_time:
            time_to_recovery = max(0, self.recovery_timeout - (current_time - self.last_failure_time))
        
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "failure_threshold": self.failure_threshold,
            "last_failure_time": self.last_failure_time,
            "time_to_recovery_seconds": time_to_recovery,
            "is_healthy": self.state == "CLOSED"
        }

# --- Advanced Caching System ---
class AdvancedCache:
    """
    High-performance cache with compression, smart TTL, and comprehensive error handling
    Optimized for production use with memory-efficient storage
    """
    
    @staticmethod
    def compress_data(data: Any) -> bytes:
        """
        Compress data using gzip for storage efficiency with intelligent compression threshold
        
        Args:
            data: Any serializable data object
            
        Returns:
            Compressed bytes ready for storage
            
        Raises:
            Exception: If serialization or compression fails
        """
        try:
            # Serialize data using highest protocol for efficiency
            serialized = pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)
            
            # Only compress if data is larger than 1KB and compression is enabled
            if config.enable_compression and len(serialized) > 1024:
                compressed = gzip.compress(serialized, compresslevel=6)  # Balance between speed and compression
                
                # Only use compressed version if it's actually smaller
                if len(compressed) < len(serialized):
                    return compressed
            
            return serialized
            
        except Exception as e:
            logger.error(f"Data compression failed: {e}")
            raise
    
    @staticmethod
    def decompress_data(data: bytes) -> Any:
        """
        Decompress data with automatic format detection and fallback handling
        
        Args:
            data: Compressed or uncompressed bytes
            
        Returns:
            Deserialized data object
            
        Raises:
            Exception: If decompression or deserialization fails
        """
        try:
            # Try compression-aware decompression first
            if config.enable_compression:
                try:
                    # Attempt gzip decompression
                    decompressed = gzip.decompress(data)
                    return pickle.loads(decompressed)
                except (gzip.BadGzipFile, OSError):
                    # Data is not compressed - try direct unpickling
                    pass
            
            # Fallback to direct unpickling for uncompressed data
            return pickle.loads(data)
            
        except Exception as e:
            logger.error(f"Data decompression failed: {e}")
            raise
    
    @staticmethod
    async def get_cached(redis_client: Redis, key: str) -> Optional[Any]:
        """
        Get and decompress cached data with comprehensive error handling and metrics
        
        Args:
            redis_client: Active Redis client instance
            key: Cache key to retrieve
            
        Returns:
            Cached data or None if not found or error occurred
        """
        if not redis_client:
            return None
            
        try:
            # Retrieve data from Redis
            data = await redis_client.get(key)
            if data:
                # Record cache hit metrics
                if config.enable_metrics and METRICS_AVAILABLE:
                    CACHE_HITS.labels(cache_type='redis').inc()
                
                # Decompress and return data
                result = AdvancedCache.decompress_data(data)
                logger.debug(f"Cache hit for key: {key[:50]}... (size: {len(data)} bytes)")
                return result
            else:
                logger.debug(f"Cache miss for key: {key[:50]}...")
                return None
                
        except Exception as e:
            logger.warning(f"Cache read error for key {key[:50]}...: {e}")
            # Don't raise exception - graceful degradation
            return None
    
    @staticmethod
    async def set_cached(redis_client: Redis, key: str, value: Any, ttl: int):
        """
        Compress and cache data with error handling and size optimization
        
        Args:
            redis_client: Active Redis client instance
            key: Cache key to store under
            value: Data to cache
            ttl: Time to live in seconds
        """
        if not redis_client:
            return
            
        try:
            # Compress data for storage
            compressed_data = AdvancedCache.compress_data(value)
            
            # Store in Redis with TTL
            await redis_client.setex(key, ttl, compressed_data)
            
            logger.debug(f"Cached data for key: {key[:50]}... (TTL: {ttl}s, Size: {len(compressed_data)} bytes)")
            
        except Exception as e:
            logger.warning(f"Cache write error for key {key[:50]}...: {e}")
            # Don't raise exception - graceful degradation
    
    @staticmethod
    async def delete_cached(redis_client: Redis, pattern: str = None, key: str = None):
        """
        Delete cached data by specific key or pattern matching
        
        Args:
            redis_client: Active Redis client instance
            pattern: Pattern to match keys for deletion (e.g., "user:*")
            key: Specific key to delete
        """
        if not redis_client:
            return
            
        try:
            if key:
                # Delete specific key
                result = await redis_client.delete(key)
                if result:
                    logger.debug(f"Deleted cache key: {key}")
                    
            elif pattern:
                # Delete keys matching pattern
                keys = await redis_client.keys(pattern)
                if keys:
                    await redis_client.delete(*keys)
                    logger.debug(f"Deleted {len(keys)} cache keys matching pattern: {pattern}")
                    
        except Exception as e:
            logger.warning(f"Cache deletion error: {e}")
    
    @staticmethod
    async def get_cache_stats(redis_client: Redis) -> Dict[str, Any]:
        """
        Get comprehensive cache statistics for monitoring
        
        Args:
            redis_client: Active Redis client instance
            
        Returns:
            Dictionary containing cache statistics
        """
        if not redis_client:
            return {"available": False}
        
        try:
            info = await redis_client.info()
            
            return {
                "available": True,
                "memory_used": info.get('used_memory', 0),
                "memory_used_human": info.get('used_memory_human', 'N/A'),
                "connected_clients": info.get('connected_clients', 0),
                "total_commands_processed": info.get('total_commands_processed', 0),
                "keyspace_hits": info.get('keyspace_hits', 0),
                "keyspace_misses": info.get('keyspace_misses', 0),
                "uptime_seconds": info.get('uptime_in_seconds', 0)
            }
            
        except Exception as e:
            logger.warning(f"Error getting cache stats: {e}")
            return {"available": False, "error": str(e)}

# --- Advanced Token Optimization System ---
class TokenOptimizer:
    """
    Advanced token counting and optimization utilities supporting multiple AI providers
    Provides accurate cost estimation and intelligent prompt optimization
    """
    
    # Token multipliers based on empirical testing with different providers
    TOKEN_MULTIPLIERS = {
        "openai": 4.0,          # GPT models (GPT-3.5, GPT-4)
        "anthropic": 3.8,       # Claude models
        "claude": 3.8,          # Claude models (alternative naming)
        "moonshot": 4.0,        # Similar tokenization to GPT
        "together": 3.6,        # Various open-source models
        "huggingface": 3.2,     # Transformer models on HuggingFace
        "ollama": 2.8,          # Local models (often more efficient tokenization)
        "groq": 3.5,            # Fast inference models
        "cohere": 3.7,          # Cohere models
        "ai21": 3.9,            # AI21 models
        "mock": 1.0,            # No real tokenization needed
    }
    
    # Provider-specific costs per 1K tokens (input/output pricing)
    PROVIDER_COSTS = {
        "openai": {"input": 0.0015, "output": 0.002},
        "anthropic": {"input": 0.0008, "output": 0.0024},
        "claude": {"input": 0.0008, "output": 0.0024},
        "together": {"input": 0.0002, "output": 0.0002},
        "moonshot": {"input": 0.012, "output": 0.012},
        "groq": {"input": 0.0001, "output": 0.0001},
        "cohere": {"input": 0.0015, "output": 0.002},
        "ai21": {"input": 0.0025, "output": 0.0025},
        # Free providers (no cost)
        "ollama": {"input": 0.0, "output": 0.0},
        "huggingface": {"input": 0.0, "output": 0.0},
        "mock": {"input": 0.0, "output": 0.0},
    }
    
    @staticmethod
    def estimate_tokens(text: str, provider: str = "openai") -> int:
        """
        Estimate token count for different providers with improved accuracy
        
        Args:
            text: Input text to analyze
            provider: AI provider name for provider-specific estimation
            
        Returns:
            Estimated token count (minimum 1)
        """
        if not text or not isinstance(text, str):
            return 0
        
        # Try to use tiktoken for OpenAI-compatible models if available
        if provider in ["openai", "moonshot", "together"] and provider.startswith("gpt"):
            try:
                import tiktoken
                # Use appropriate encoding based on model
                if "gpt-4" in provider.lower():
                    encoding = tiktoken.get_encoding("cl100k_base")
                else:
                    encoding = tiktoken.get_encoding("p50k_base")
                return len(encoding.encode(text))
            except ImportError:
                pass  # Fall back to estimation
        
        # Character-based estimation with complexity adjustments
        multiplier = TokenOptimizer.TOKEN_MULTIPLIERS.get(provider, 4.0)
        
        # Analyze text characteristics for better estimation
        word_count = len(text.split())
        char_count = len(text)
        
        if word_count > 0:
            avg_word_length = char_count / word_count
            
            # Adjust multiplier based on text complexity
            if avg_word_length > 7:  # Technical/code text
                multiplier *= 0.85  # More tokens per character
            elif avg_word_length > 5:  # Complex text
                multiplier *= 0.9
            elif avg_word_length < 4:  # Simple text
                multiplier *= 1.1   # Fewer tokens per character
            
            # Additional adjustments for special content
            if any(indicator in text.lower() for indicator in ['```', 'def ', 'class ', 'import ', '{', '}']):
                multiplier *= 0.8  # Code typically has more tokens
            
            if text.count('\n') > char_count * 0.05:  # Many line breaks
                multiplier *= 0.9  # Structured text adjustment
        
        estimated_tokens = max(1, int(char_count / multiplier))
        return estimated_tokens
    
    @staticmethod
    def calculate_cost(input_tokens: int, output_tokens: int, provider: str) -> float:
        """
        Calculate estimated cost based on token usage and provider pricing
        
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
        
        total_cost = input_cost + output_cost
        
        # Log high costs for monitoring
        if total_cost > 0.1:  # More than 10 cents
            logger.info(f"High cost request: ${total_cost:.4f} for {provider} ({input_tokens}+{output_tokens} tokens)")
        
        return total_cost
    
    @staticmethod
    def optimize_prompt(prompt: str, max_tokens: int = 4000, provider: str = "openai") -> str:
        """
        Intelligent prompt optimization to reduce token usage while preserving meaning
        
        Args:
            prompt: Original prompt text
            max_tokens: Maximum allowed tokens
            provider: AI provider for token estimation
            
        Returns:
            Optimized prompt that fits within token limits
        """
        original_tokens = TokenOptimizer.estimate_tokens(prompt, provider)
        
        if original_tokens <= max_tokens:
            return prompt
        
        logger.info(f"Optimizing prompt: {original_tokens} -> {max_tokens} tokens for {provider}")
        
        # Calculate how much we need to reduce
        reduction_ratio = max_tokens / original_tokens
        
        # Multi-stage optimization process
        optimized = prompt
        
        # Stage 1: Clean up whitespace and formatting
        import re
        optimized = re.sub(r'\s+', ' ', optimized.strip())
        optimized = re.sub(r'\n\s*\n', '\n', optimized)  # Remove multiple newlines
        
        # Stage 2: Remove redundant phrases if still too long
        current_tokens = TokenOptimizer.estimate_tokens(optimized, provider)
        if current_tokens > max_tokens:
            optimized = TokenOptimizer._remove_redundancy(optimized)
        
        # Stage 3: Intelligent truncation with content preservation
        current_tokens = TokenOptimizer.estimate_tokens(optimized, provider)
        if current_tokens > max_tokens:
            optimized = TokenOptimizer._intelligent_truncate(optimized, reduction_ratio)
        
        # Stage 4: Emergency character-based truncation if needed
        final_tokens = TokenOptimizer.estimate_tokens(optimized, provider)
        if final_tokens > max_tokens:
            # Last resort - character-based truncation
            char_ratio = max_tokens / final_tokens * 0.95  # Leave some safety margin
            target_length = int(len(optimized) * char_ratio)
            optimized = optimized[:target_length].rstrip() + "..."
        
        final_tokens = TokenOptimizer.estimate_tokens(optimized, provider)
        reduction_percentage = ((original_tokens - final_tokens) / original_tokens) * 100
        
        logger.info(f"Prompt optimized: {original_tokens} -> {final_tokens} tokens ({reduction_percentage:.1f}% reduction)")
        
        return optimized
    
    @staticmethod
    def _remove_redundancy(text: str) -> str:
        """
        Remove redundant phrases and unnecessary words to reduce token count
        
        Args:
            text: Input text to optimize
            
        Returns:
            Text with redundancy removed
        """
        # Common redundant phrases that can be removed or simplified
        redundancy_patterns = [
            (r'\bthat is to say\b', ''),
            (r'\bin other words\b', ''),
            (r'\bto put it simply\b', ''),
            (r'\bbasically\b', ''),
            (r'\bessentially\b', ''),
            (r'\bplease note that\b', ''),
            (r'\bit should be noted that\b', ''),
            (r'\bit is important to understand that\b', ''),
            (r'\blet me be clear\b', ''),
            (r'\bto be honest\b', ''),
        ]
        
        optimized = text
        for pattern, replacement in redundancy_patterns:
            optimized = re.sub(pattern, replacement, optimized, flags=re.IGNORECASE)
        
        # Clean up any double spaces created
        optimized = re.sub(r'\s+', ' ', optimized).strip()
        
        return optimized
    
    @staticmethod
    def _intelligent_truncate(text: str, ratio: float) -> str:
        """
        Intelligent text truncation that preserves important content structure
        
        Args:
            text: Input text to truncate
            ratio: Reduction ratio (0-1) indicating how much to keep
            
        Returns:
            Truncated text preserving key information
        """
        if ratio >= 0.95:
            return text
        
        # Split into sentences for better preservation
        sentences = [s.strip() for s in text.split('.') if s.strip()]
        
        if len(sentences) <= 1:
            # Single sentence or no sentences - character truncation
            target_length = int(len(text) * ratio)
            if target_length < 100:
                return text[:100] + "..."
            return text[:target_length].rstrip() + "..."
        
        # Multi-sentence text - preserve structure
        keep_sentences = max(1, int(len(sentences) * ratio))
        
        if keep_sentences >= len(sentences):
            return text
        
        # Strategy: Keep beginning and end, summarize middle if necessary
        if keep_sentences <= 2:
            # Very aggressive reduction - keep first and last sentence
            if len(sentences) >= 2:
                return f"{sentences[0]}. ... {sentences[-1]}."
            else:
                return sentences[0] + "."
        
        # Balanced approach: keep more from beginning, some from end
        first_count = max(1, int(keep_sentences * 0.7))
        last_count = keep_sentences - first_count
        
        first_part = '. '.join(sentences[:first_count])
        last_part = '. '.join(sentences[-last_count:]) if last_count > 0 else ""
        
        if last_part:
            return f"{first_part}. ... {last_part}."
        else:
            return f"{first_part}..."

# --- Resource Management System ---
class ResourceManager:
    """
    Centralized resource management with comprehensive lifecycle handling
    Provides health monitoring, graceful degradation, and proper cleanup
    """
    
    def __init__(self):
        # Core resource instances
        self.ai_config_cache: Optional[Dict[str, Any]] = None
        self.config_last_modified: Optional[float] = None
        self.ai_client_instance: Optional[AIAsyncClient] = None
        self.redis_client: Optional[Redis] = None
        self.ai_semaphore: Optional[asyncio.Semaphore] = None
        
        # Provider management
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.request_stats: Dict[str, Dict[str, Any]] = {}
        
        # System monitoring
        self.startup_time = time.time()
        self.redis_healthy = False
        self.ai_client_healthy = False
        self.last_health_check = 0
        self.health_check_interval = 30  # seconds
        
        # Performance tracking
        self.total_requests = 0
        self.total_errors = 0
        self.avg_response_time = 0.0
        
    async def initialize_redis(self) -> Optional[Redis]:
        """
        Initialize Redis client with comprehensive error handling and health validation
        
        Returns:
            Redis client instance or None if initialization failed
        """
        if not REDIS_AVAILABLE or not config.enable_cache:
            logger.info("Redis not available or caching disabled")
            return None
        
        try:
            # Create Redis client with optimized configuration for production use
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
            
            # Comprehensive connection testing
            await redis_client.ping()
            
            # Test basic operations to ensure full functionality
            test_key = f"health_check_{int(time.time())}"
            test_value = "connection_test"
            
            await redis_client.set(test_key, test_value, ex=10)
            retrieved_value = await redis_client.get(test_key)
            await redis_client.delete(test_key)
            
            if retrieved_value != test_value.encode() if not config.redis.decode_responses else test_value:
                raise Exception("Redis read/write test failed - data integrity issue")
            
            # Get Redis info for logging
            info = await redis_client.info()
            redis_version = info.get('redis_version', 'unknown')
            memory_used = info.get('used_memory_human', 'unknown')
            
            self.redis_client = redis_client
            self.redis_healthy = True
            
            logger.info(f"✅ Redis connection established successfully")
            logger.info(f"   Version: {redis_version}, Memory: {memory_used}")
            logger.info(f"   Max connections: {config.redis.max_connections}")
            
            return redis_client
            
        except Exception as e:
            logger.warning(f"Redis initialization failed: {e}")
            logger.info("   Application will continue without Redis caching")
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
            logger.warning("AIAsyncClient not available - AI features will use fallback implementations")
            return None
        
        try:
            # Load and validate AI