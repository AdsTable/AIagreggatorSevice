# main.py - Updated with integrated performance monitoring
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
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
from pydantic import BaseModel, ConfigDict, field_validator, computed_field

# Database and async imports
from sqlalchemy.ext.asyncio import AsyncSession

# Modern rate limiting implementation
import asyncio
from collections import defaultdict
from typing import Dict, Tuple
import time

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
        logging.FileHandler('app.log', mode='a'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# --- Legacy Compatibility Layer ---
# Keep the old function signature for backward compatibility
def monitor_performance_legacy(operation_name: str):
    """
    Legacy performance monitoring decorator - DEPRECATED
    
    This function is kept for backward compatibility with existing code.
    New code should use the enhanced performance_monitor module directly.
    
    Args:
        operation_name: Name of the operation to monitor
    
    Returns:
        Decorator function
    
    Note:
        This will be removed in a future version. Please migrate to:
        - monitor_ai_operation() for AI-related operations
        - monitor_cache_operation() for cache operations  
        - monitor_performance() from performance_monitor module for general use
    """
    import warnings
    warnings.warn(
        "monitor_performance_legacy is deprecated. Use performance_monitor module instead.",
        DeprecationWarning,
        stacklevel=2
    )
    
    # Delegate to the new enhanced monitoring system
    return monitor_performance(
        operation_name=operation_name,
        operation_type=OperationType.COMPUTATION
    )

# --- Modern Rate Limiter Implementation ---
class ModernRateLimiter:
    """Python 3.13 compatible rate limiter with sliding window algorithm"""
    
    def __init__(self):
        self.requests: Dict[str, List[float]] = defaultdict(list)
        self.locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
    
    @monitor_cache_operation(cache_type="rate_limiter")
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

# --- Enhanced Configuration Management ---
@dataclass
class DatabaseConfig:
    """Database configuration with connection pooling"""
    url: str = os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./app.db')
    pool_size: int = int(os.getenv('DB_POOL_SIZE', '20'))
    max_overflow: int = int(os.getenv('DB_MAX_OVERFLOW', '30'))
    echo: bool = os.getenv('DB_ECHO', 'false').lower() == 'true'

@dataclass
class AppConfig:
    """Main application configuration with performance monitoring"""
    app_name: str = os.getenv('APP_NAME', 'AI Aggregator Pro')
    version: str = '3.3.0'  # Updated version with enhanced monitoring
    environment: str = os.getenv('ENVIRONMENT', 'development')
    debug: bool = os.getenv('DEBUG', 'false').lower() == 'true'
    python_version: str = f"{__import__('sys').version_info.major}.{__import__('sys').version_info.minor}"
    
    # Performance monitoring configuration
    monitoring_enabled: bool = os.getenv('MONITORING_ENABLED', 'true').lower() == 'true'
    performance_threshold_warning: float = float(os.getenv('PERF_THRESHOLD_WARNING', '5.0'))
    performance_threshold_error: float = float(os.getenv('PERF_THRESHOLD_ERROR', '30.0'))
    
    # Feature flags
    enable_cache: bool = REDIS_AVAILABLE and os.getenv('ENABLE_CACHE', 'true').lower() == 'true'
    enable_compression: bool = os.getenv('ENABLE_COMPRESSION', 'true').lower() == 'true'
    enable_metrics: bool = METRICS_AVAILABLE and os.getenv('ENABLE_METRICS', 'true').lower() == 'true'
    
    # Cache settings
    cache_ttl_short: int = int(os.getenv('CACHE_TTL_SHORT', '900'))
    cache_ttl_long: int = int(os.getenv('CACHE_TTL_LONG', '3600'))
    
    # Sub-configurations
    database: DatabaseConfig = field(default_factory=DatabaseConfig)

# Global configuration instance
config = AppConfig()

# --- Performance Monitor Setup ---
def setup_performance_monitoring() -> None:
    """Setup and configure the performance monitoring system"""
    if not config.monitoring_enabled:
        logger.info("Performance monitoring disabled by configuration")
        return
    
    # Create custom thresholds based on configuration
    thresholds = PerformanceThresholds(
        warning_threshold=config.performance_threshold_warning,
        error_threshold=config.performance_threshold_error,
        operation_thresholds={
            OperationType.AI_REQUEST: 10.0,  # AI operations can be slower
            OperationType.CACHE_OPERATION: 0.1,  # Cache should be fast
            OperationType.DATABASE_OPERATION: 2.0,  # DB operations moderate
            OperationType.NETWORK_OPERATION: 5.0,  # Network can vary
            OperationType.COMPUTATION: 1.0,  # Computations should be quick
        }
    )
    
    # Create and set up the performance monitor
    monitor = PerformanceMonitor(thresholds=thresholds)
    set_performance_monitor(monitor)
    
    logger.info("✅ Performance monitoring system initialized")
    logger.info(f"   Warning threshold: {config.performance_threshold_warning}s")
    logger.info(f"   Error threshold: {config.performance_threshold_error}s")

# --- Enhanced Resource Management ---
class ResourceManager:
    """Centralized resource management with integrated performance monitoring"""
    
    def __init__(self):
        self.ai_config_cache: Optional[Dict[str, Any]] = None
        self.config_last_modified: Optional[float] = None
        self.ai_client_instance: Optional[AIAsyncClient] = None
        self.redis_client: Optional[Redis] = None
        self.ai_semaphore: Optional[asyncio.Semaphore] = None
        self.circuit_breakers: Dict[str, Any] = {}
        self.request_stats: Dict[str, Dict[str, Any]] = {}
    
    @monitor_cache_operation(cache_type="redis")
    async def initialize_redis(self) -> Optional[Redis]:
        """Initialize Redis client with performance monitoring"""
        if not REDIS_AVAILABLE or not config.enable_cache:
            logger.info("Redis not available or disabled")
            return None
        
        try:
            if hasattr(Redis, 'from_url'):
                redis_client = Redis.from_url(
                    os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
                    encoding='utf-8',
                    decode_responses=False,
                    max_connections=20,
                    socket_timeout=5.0
                )
            else:
                redis_client = Redis(
                    host='localhost',
                    port=6379,
                    db=0,
                    encoding='utf-8',
                    decode_responses=False
                )
            
            await redis_client.ping()
            self.redis_client = redis_client
            logger.info("✅ Redis connection established")
            return redis_client
            
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}, proceeding without cache")
            self.redis_client = None
            return None
    
    @monitor_ai_operation()
    async def initialize_ai_client(self) -> Optional[AIAsyncClient]:
        """Initialize AI client with performance monitoring"""
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
                self.circuit_breakers[provider] = {"state": "CLOSED", "failures": 0}
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
    
    @monitor_performance("load_ai_config", OperationType.COMPUTATION)
    async def load_ai_config(self, force_reload: bool = False) -> Dict[str, Any]:
        """Load AI configuration with performance monitoring"""
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
            
            # Process configuration with environment variable substitution
            for provider, settings in cfg.items():
                if not isinstance(settings, dict):
                    continue
                
                for key, value in list(settings.items()):
                    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                        env_key = value[2:-1]
                        env_value = os.getenv(env_key)
                        if env_value is None:
                            logger.warning(f"Environment variable {env_key} not found for {provider}.{key}")
                            del settings[key]
                        else:
                            settings[key] = env_value
            
            self.ai_config_cache = cfg
            self.config_last_modified = current_mtime
            logger.info(f"✅ AI configuration loaded with {len(cfg)} providers")
            return cfg
            
        except (yaml.YAMLError, ValueError, IOError) as e:
            logger.error(f"Failed to load AI configuration: {e}")
            return {}

# Global resource manager
resources = ResourceManager()

# --- Rate Limiting Decorator with Performance Monitoring ---
def rate_limit(requests_per_minute: int = 60):
    """Modern rate limiting decorator with performance monitoring"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        @monitor_performance(f"rate_limited_{func.__name__}", OperationType.NETWORK_OPERATION)
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

# --- Enhanced Cache System with Performance Monitoring ---
class AdvancedCache:
    """High-performance cache with integrated monitoring"""
    
    @staticmethod
    @monitor_cache_operation(cache_type="compression")
    def compress_data(data: Any) -> bytes:
        """Compress data using gzip for storage efficiency"""
        serialized = pickle.dumps(data)
        if config.enable_compression:
            return gzip.compress(serialized)
        return serialized
    
    @staticmethod
    @monitor_cache_operation(cache_type="decompression")
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
    @monitor_cache_operation(cache_type="redis_get")
    async def get_cached(redis_client: Redis, key: str) -> Optional[Any]:
        """Get and decompress cached data with monitoring"""
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
    @monitor_cache_operation(cache_type="redis_set")
    async def set_cached(redis_client: Redis, key: str, value: Any, ttl: int):
        """Compress and cache data with monitoring"""
        if not redis_client:
            return
            
        try:
            compressed_data = AdvancedCache.compress_data(value)
            await redis_client.setex(key, ttl, compressed_data)
        except Exception as e:
            logger.warning(f"Cache write error for key {key}: {e}")

# --- Application Lifecycle with Enhanced Monitoring ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Enhanced application lifecycle management with performance monitoring"""
    start_time = time.time()
    app.state.start_time = start_time
    
    logger.info(f"🚀 Starting {config.app_name} v{config.version}")
    logger.info(f"Environment: {config.environment}")
    logger.info(f"Python version: {config.python_version}")
    
    try:
        # Setup performance monitoring first
        setup_performance_monitoring()
        
        # Initialize database
        if 'create_db_and_tables' in globals():
            with get_performance_monitor().monitor_operation(
                "database_init", OperationType.DATABASE_OPERATION
            ):
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
        
        # Log final performance statistics
        if config.monitoring_enabled:
            stats = get_performance_stats()
            logger.info(f"📊 Final performance stats: {stats}")
        
        # Cleanup resources
        cleanup_tasks = []
        
        if resources.ai_client_instance and hasattr(resources.ai_client_instance, 'aclose'):
            cleanup_tasks.append(resources.ai_client_instance.aclose())
        
        if resources.redis_client and hasattr(resources.redis_client, 'close'):
            cleanup_tasks.append(resources.redis_client.close())
        
        if cleanup_tasks:
            try:
                await asyncio.gather(*cleanup_tasks, return_exceptions=True)
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")
        
        logger.info("✅ Shutdown completed")

# --- FastAPI Application ---
app = FastAPI(
    title=config.app_name,
    description=f"AI service with advanced performance monitoring (Python {config.python_version})",
    version=config.version,
    lifespan=lifespan,
    docs_url="/docs" if config.environment != 'production' else None,
    redoc_url="/redoc" if config.environment != 'production' else None
)

# --- Enhanced API Endpoints ---

@app.post("/ai/ask")
@rate_limit(50)
@monitor_ai_operation()
async def ai_ask(
    request: Request,
    ai_request: dict,  # Simplified for example
    background_tasks: BackgroundTasks,
    stream: bool = Query(False, description="Enable streaming response")
):
    """Enhanced AI query with integrated performance monitoring"""
    
    prompt = ai_request.get('prompt', '')
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")
    
    # The performance monitoring is now handled by the decorator
    # and the performance_monitor module
    
    ai_client = resources.ai_client_instance
    if not ai_client:
        raise HTTPException(status_code=503, detail="AI service not available")
    
    try:
        # This will be automatically monitored by the decorator
        answer = await ai_client.ask(
            prompt,
            provider=ai_request.get('provider'),
            max_tokens=ai_request.get('max_tokens'),
            temperature=ai_request.get('temperature', 0.7)
        )
        
        response = {
            "provider": ai_request.get('provider', 'auto'),
            "prompt": prompt,
            "answer": answer,
            "cached": False,
            "monitoring_enabled": config.monitoring_enabled
        }
        
        return response
        
    except Exception as e:
        logger.error(f"AI service error: {e}")
        raise HTTPException(status_code=500, detail=f"AI service error: {str(e)}")

@app.get("/health")
@monitor_performance("health_check", OperationType.COMPUTATION)
async def health_check():
    """Enhanced health check with performance monitoring"""
    app_start_time = getattr(app.state, 'start_time', time.time())
    uptime = time.time() - app_start_time
    
    # Get performance statistics
    perf_stats = get_performance_stats() if config.monitoring_enabled else {}
    
    return {
        "status": "healthy",
        "version": config.version,
        "python_version": config.python_version,
        "timestamp": datetime.now(),
        "uptime_seconds": uptime,
        "monitoring_enabled": config.monitoring_enabled,
        "performance_stats": perf_stats,
        "features_enabled": {
            "cache": config.enable_cache,
            "compression": config.enable_compression,
            "metrics": config.enable_metrics,
            "performance_monitoring": config.monitoring_enabled
        }
    }

# Performance monitoring endpoints
if config.monitoring_enabled:
    @app.get("/admin/performance/stats")
    @rate_limit(10)
    @monitor_performance("get_perf_stats", OperationType.COMPUTATION)
    async def get_performance_statistics(request: Request):
        """Get detailed performance statistics"""
        return {
            "performance_stats": get_performance_stats(),
            "monitoring_config": {
                "warning_threshold": config.performance_threshold_warning,
                "error_threshold": config.performance_threshold_error,
                "enabled": config.monitoring_enabled
            }
        }
    
    @app.post("/admin/performance/reset")
    @rate_limit(3)
    @monitor_performance("reset_perf_stats", OperationType.COMPUTATION)
    async def reset_performance_statistics(request: Request):
        """Reset performance statistics"""
        from performance_monitor import reset_performance_stats
        reset_performance_stats()
        return {"status": "success", "message": "Performance statistics reset"}

# Metrics endpoint
if config.enable_metrics:
    @app.get("/metrics")
    @monitor_performance("prometheus_metrics", OperationType.COMPUTATION)
    async def metrics():
        """Prometheus metrics endpoint with performance monitoring"""
        return Response(generate_latest(), media_type="text/plain")

# --- Root Endpoint ---
@app.get("/")
@monitor_performance("root_endpoint", OperationType.COMPUTATION)
async def root():
    """Service information with performance monitoring details"""
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
            "📊 Advanced performance monitoring",
            "🗜️ Response compression",
            "🔧 Hot configuration reload",
            "🐍 Python 3.13 optimized"
        ],
        "monitoring": {
            "enabled": config.monitoring_enabled,
            "warning_threshold": config.performance_threshold_warning,
            "error_threshold": config.performance_threshold_error,
            "endpoints": [
                "/admin/performance/stats",
                "/admin/performance/reset"
            ] if config.monitoring_enabled else []
        },
        "endpoints": {
            "docs": "/docs" if config.environment != 'production' else "disabled",
            "health": "/health",
            "metrics": "/metrics" if config.enable_metrics else "disabled"
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
    
    logger.info(f"🚀 Starting {config.app_name} v{config.version}")
    logger.info(f"Performance monitoring: {'enabled' if config.monitoring_enabled else 'disabled'}")
    
    uvicorn.run(**uvicorn_config)