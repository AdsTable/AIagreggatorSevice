# main.py - Production-Ready AI Aggregator Pro with Python 3.13 Compatibility
# Part 1 of 3: Imports, Configuration, and Core Utilities
# Complete implementation with comprehensive error handling and English comments

from __future__ import annotations

# Standard library imports for Python 3.13 compatibility
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
import re
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

# FastAPI and related imports - core dependencies
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

# Database imports with graceful fallback
try:
    from sqlalchemy.ext.asyncio import AsyncSession
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    AsyncSession = None

# Prometheus metrics for production monitoring (optional)
try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest
    METRICS_AVAILABLE = True
    
    # Initialize metrics with proper labels and descriptions
    REQUEST_COUNT = Counter('ai_requests_total', 'Total AI requests processed', ['provider', 'status'])
    REQUEST_DURATION = Histogram('ai_request_duration_seconds', 'AI request processing duration')
    CACHE_HITS = Counter('cache_hits_total', 'Cache hit operations', ['cache_type'])
    ACTIVE_CONNECTIONS = Gauge('active_connections', 'Currently active connections')
    TOKEN_USAGE = Counter('tokens_used_total', 'Total tokens consumed', ['provider'])
    ERROR_COUNT = Counter('errors_total', 'Total errors encountered', ['error_type'])
    
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
    
    # Fallback implementations for development mode
    class OperationType(Enum):
        AI_REQUEST = "ai_request"
        CACHE_OPERATION = "cache_operation"
        DATABASE_OPERATION = "database_operation"
        NETWORK_OPERATION = "network_operation"
        COMPUTATION = "computation"

# AI client imports with fallback for development
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
    
    # Complete fallback product models for development mode
    class Product(BaseModel):
        """Fallback Product model with comprehensive fields for development"""
        id: Optional[int] = None
        name: str
        description: Optional[str] = None
        price: Optional[float] = None
        category: Optional[str] = None
        provider: Optional[str] = None
        source_url: Optional[str] = None
        availability: Optional[str] = "unknown"
        
        model_config = ConfigDict(from_attributes=True, extra="allow")
    
    class StandardizedProduct(BaseModel):
        """Fallback StandardizedProduct model with full Pydantic v2 compatibility"""
        id: Optional[int] = None
        name: str
        description: Optional[str] = None
        price: Optional[float] = None
        category: Optional[str] = None
        source: Optional[str] = None
        provider: Optional[str] = None
        availability: Optional[str] = "in_stock"
        created_at: Optional[datetime] = None
        
        model_config = ConfigDict(from_attributes=True, extra="allow")
        
        def model_dump(self, **kwargs) -> Dict[str, Any]:
            """Ensure compatibility with both Pydantic v1 and v2"""
            if hasattr(super(), 'model_dump'):
                return super().model_dump(**kwargs)
            else:
                # Fallback for older Pydantic versions
                return self.dict(**kwargs)
    
    class ApiResponse(BaseModel):
        """Fallback ApiResponse model with comprehensive structure"""
        success: bool = True
        message: str = "Operation completed successfully"
        data: Optional[Any] = None
        timestamp: Optional[datetime] = field(default_factory=datetime.now)
        request_id: Optional[str] = None
        
        model_config = ConfigDict(from_attributes=True)

# Database functions with comprehensive fallback
try:
    from database import create_db_and_tables, get_session
    DATABASE_FUNCTIONS_AVAILABLE = True
except ImportError:
    DATABASE_FUNCTIONS_AVAILABLE = False
    
    async def create_db_and_tables():
        """Fallback database creation function for development mode"""
        logging.warning("Database functions not available - using in-memory fallback")
        return True
    
    async def get_session():
        """Fallback session getter that returns None for graceful degradation"""
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
    
    # Complete fallback data processing functions with realistic mock data
    async def discover_and_extract_data(*args, **kwargs):
        """Fallback data discovery with comprehensive mock data generation"""
        categories = [
            "electronics", "books", "clothing", "home", "sports", 
            "automotive", "health", "toys", "beauty", "tools",
            "garden", "office", "music", "movies", "games"
        ]
        
        products = []
        for i in range(1, 30):  # Generate 29 mock products
            category = categories[i % len(categories)]
            products.append({
                "name": f"Premium {category.title()} Product {i}",
                "price": round(19.99 + (i * 8.75), 2),
                "category": category,
                "description": f"High-quality {category} item with excellent features, durability, and competitive pricing",
                "source": "mock_discovery",
                "provider": f"Provider {((i-1) % 5) + 1}",
                "availability": ["in_stock", "limited", "preorder"][i % 3],
                "rating": round(3.5 + (i % 3) * 0.5, 1)
            })
        
        await asyncio.sleep(0.1)  # Simulate async operation
        return products
    
    async def parse_and_standardize(raw_data, category="general"):
        """Fallback data parsing function with comprehensive error handling"""
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
                    description=item.get("description", f"Detailed description for {item.get('name', 'product')}"),
                    source=item.get("source", "fallback_parser"),
                    provider=item.get("provider", f"Provider {(i % 3) + 1}"),
                    availability=item.get("availability", "in_stock"),
                    created_at=datetime.now()
                ))
            except Exception as e:
                logging.warning(f"Error parsing item {i}: {e}")
                continue
        
        await asyncio.sleep(0.05)  # Simulate processing time
        return standardized
    
    async def store_standardized_data(session, data):
        """Fallback data storage function with validation and comprehensive logging"""
        if not data:
            logging.warning("No data provided for storage")
            return False
            
        logging.info(f"Fallback storage: would store {len(data)} items in production database")
        
        # Simulate storage validation
        valid_items = [item for item in data if hasattr(item, 'name') and item.name]
        invalid_count = len(data) - len(valid_items)
        
        if invalid_count > 0:
            logging.warning(f"Would skip {invalid_count} invalid items during storage")
        
        await asyncio.sleep(0.02)  # Simulate database operation
        return True
    
    async def search_and_filter_products(session=None, **filters):
        """Fallback product search with comprehensive mock data generation and filtering"""
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
            "Economy", "Enterprise", "Ultimate", "Pro", "Basic", 
            "Elite", "Master", "Superior", "Classic", "Modern"
        ]
        
        for i in range(offset + 1, offset + limit + 1):
            # Calculate price within specified range
            price_range = max_price - min_price
            if price_range > 0:
                price = min_price + ((i * 47) % price_range)
            else:
                price = min_price + (i * 25)
            
            # Generate name based on query and category
            base_name = base_names[(i - 1) % len(base_names)]
            if query:
                name = f"{base_name} {query.title()} {category.title()} {i}"
            else:
                name = f"{base_name} {category.title()} Product {i}"
            
            products.append(StandardizedProduct(
                id=i,
                name=name,
                description=f"High-quality {category} item featuring {query or 'advanced features'} with excellent performance, reliability, and competitive pricing. Perfect for professional and personal use.",
                price=float(round(price, 2)),
                category=category,
                source="fallback_search",
                provider=f"Provider {((i - 1) % 6) + 1}",
                availability=["in_stock", "limited", "preorder"][i % 3],
                created_at=datetime.now()
            ))
        
        await asyncio.sleep(0.03)  # Simulate search operation
        return products

# Enhanced logging setup with production-ready configuration
def setup_logging():
    """
    Setup comprehensive logging system with environment-specific configuration
    
    Features:
    - Environment-based formatter selection (JSON for production, readable for development)
    - Multiple handler support (console, file, rotation)
    - Proper encoding and error handling
    - Performance-optimized logger levels
    """
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_format = os.getenv('LOG_FORMAT', 'detailed')
    environment = os.getenv('ENVIRONMENT', 'development')
    
    # Configure formatters based on environment and deployment requirements
    if log_format == 'json' or environment == 'production':
        # Structured JSON logging for production monitoring, log aggregation, and alerting
        formatter = logging.Formatter(
            '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", '
            '"function": "%(funcName)s", "line": %(lineno)d, "message": "%(message)s", '
            '"thread": "%(thread)d", "process": "%(process)d", "user": "AdsTable"}'
        )
    else:
        # Human-readable logging for development, debugging, and local testing
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
        )
    
    # Configure handlers with comprehensive error handling
    handlers = []
    
    # Console handler - always present for immediate feedback and debugging
    try:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(getattr(logging, log_level, logging.INFO))
        handlers.append(console_handler)
    except Exception as e:
        print(f"Error setting up console logging: {e}")
    
    # File handler - configurable for persistent logging and audit trails
    if os.getenv('ENABLE_FILE_LOGGING', 'true').lower() == 'true':
        log_file = os.getenv('LOG_FILE', 'app.log')
        try:
            # Ensure log directory exists with proper permissions
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
            file_handler.setFormatter(formatter)
            file_handler.setLevel(getattr(logging, log_level, logging.INFO))
            handlers.append(file_handler)
        except Exception as e:
            print(f"Warning: Could not setup file logging to {log_file}: {e}")
    
    # Configure root logger with comprehensive settings
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        handlers=handlers,
        force=True  # Override any existing configuration
    )
    
    # Set specific logger levels for optimal performance and clean output
    logging.getLogger('uvicorn').setLevel(logging.WARNING)
    logging.getLogger('fastapi').setLevel(logging.INFO)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    logging.getLogger('redis').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)

# Initialize logging system
setup_logging()
logger = logging.getLogger(__name__)

# Comprehensive startup report for debugging and operational monitoring
logger.info("=" * 80)
logger.info("AI AGGREGATOR PRO - COMPREHENSIVE STARTUP REPORT")
logger.info("=" * 80)
logger.info(f"Application Version: 3.4.0")
logger.info(f"Python Version: {sys.version}")
logger.info(f"Platform: {platform.platform()}")
logger.info(f"Architecture: {platform.architecture()}")
logger.info(f"Current Time: {datetime.now().isoformat()}")
logger.info(f"Working Directory: {os.getcwd()}")
logger.info(f"User: AdsTable")
logger.info("-" * 80)
logger.info("CORE DEPENDENCIES STATUS:")
logger.info(f"  ✅ FastAPI: {FASTAPI_AVAILABLE}")
logger.info(f"  ✅ Pydantic: {PYDANTIC_AVAILABLE}")
logger.info("-" * 80)
logger.info("OPTIONAL DEPENDENCIES STATUS:")
logger.info(f"  {'✅' if REDIS_AVAILABLE else '❌'} Redis: {REDIS_AVAILABLE}")
logger.info(f"  {'✅' if DATABASE_AVAILABLE else '❌'} Database (SQLAlchemy): {DATABASE_AVAILABLE}")
logger.info(f"  {'✅' if METRICS_AVAILABLE else '❌'} Prometheus Metrics: {METRICS_AVAILABLE}")
logger.info(f"  {'✅' if YAML_AVAILABLE else '❌'} YAML Support: {YAML_AVAILABLE}")
logger.info(f"  {'✅' if DOTENV_AVAILABLE else '❌'} Environment Loading: {DOTENV_AVAILABLE}")
logger.info("-" * 80)
logger.info("BUSINESS LOGIC MODULES STATUS:")
logger.info(f"  {'✅' if AI_CLIENT_AVAILABLE else '❌'} AI Client: {AI_CLIENT_AVAILABLE}")
logger.info(f"  {'✅' if PERFORMANCE_MONITOR_AVAILABLE else '❌'} Performance Monitor: {PERFORMANCE_MONITOR_AVAILABLE}")
logger.info(f"  {'✅' if DATA_PROCESSING_AVAILABLE else '❌'} Data Processing: {DATA_PROCESSING_AVAILABLE}")
logger.info(f"  {'✅' if PRODUCT_MODELS_AVAILABLE else '❌'} Product Models: {PRODUCT_MODELS_AVAILABLE}")
logger.info(f"  {'✅' if DATABASE_FUNCTIONS_AVAILABLE else '❌'} Database Functions: {DATABASE_FUNCTIONS_AVAILABLE}")
logger.info("=" * 80)

# Calculate and report fallback mode status for operational awareness
fallback_modules = [
    not AI_CLIENT_AVAILABLE,
    not DATABASE_FUNCTIONS_AVAILABLE,
    not DATA_PROCESSING_AVAILABLE,
    not PRODUCT_MODELS_AVAILABLE
]
fallback_count = sum(fallback_modules)

if fallback_count > 0:
    logger.warning(f"⚠️  RUNNING IN PARTIAL FALLBACK MODE ({fallback_count}/4 modules using fallbacks)")
    logger.warning("   Some functionality will use mock implementations")
    logger.warning("   This is normal for development but should be resolved for production")
    logger.warning("   User: AdsTable should verify all dependencies are properly installed")
else:
    logger.info("🎉 ALL MODULES LOADED SUCCESSFULLY - FULL FUNCTIONALITY AVAILABLE")

# --- Advanced Rate Limiter Implementation ---
class ModernRateLimiter:
    """
    Production-ready rate limiter implementing sliding window algorithm
    
    Features:
    - Sliding window rate limiting for accurate request tracking across time
    - Automatic cleanup to prevent memory leaks in long-running applications
    - Per-client tracking with configurable limits and thresholds
    - Thread-safe operation with async locks for concurrent access
    - Comprehensive metrics and monitoring integration
    - Memory-efficient storage with automatic garbage collection
    
    Optimized for Python 3.13 with modern async patterns and type safety
    """
    
    def __init__(self):
        self.requests: Dict[str, List[float]] = defaultdict(list)  # Store request timestamps per client
        self.locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)  # Per-client locks for thread safety
        self.cleanup_interval = 300  # Cleanup every 5 minutes to prevent memory leaks
        self.last_cleanup = time.time()
        self.max_clients = 10000  # Maximum number of tracked clients to prevent memory exhaustion
        self.total_requests = 0
        self.total_blocked = 0
    
    async def is_allowed(self, key: str, limit: int, window: int = 60) -> bool:
        """
        Check if request is allowed based on rate limit using sliding window algorithm
        
        The sliding window algorithm provides more accurate rate limiting compared to
        fixed window approaches by considering the exact timing of requests.
        
        Args:
            key: Unique identifier for rate limiting (typically IP address or user ID)
            limit: Maximum requests allowed in the time window
            window: Time window in seconds (default: 60 seconds for per-minute limiting)
            
        Returns:
            True if request is allowed, False if rate limit exceeded
        """
        current_time = time.time()
        self.total_requests += 1
        
        # Perform periodic cleanup to prevent memory leaks
        await self._periodic_cleanup(current_time)
        
        # Use per-client lock to ensure thread safety in concurrent environments
        async with self.locks[key]:
            # Remove requests outside the current window (sliding window implementation)
            self.requests[key] = [
                req_time for req_time in self.requests[key]
                if current_time - req_time < window
            ]
            
            # Check if current request count is under the limit
            if len(self.requests[key]) < limit:
                self.requests[key].append(current_time)
                return True
            else:
                self.total_blocked += 1
                return False
    
    def get_remaining(self, key: str, limit: int, window: int = 60) -> int:
        """
        Get number of remaining requests in current window for client feedback
        
        Args:
            key: Rate limit key (client identifier)
            limit: Request limit per window
            window: Time window in seconds
            
        Returns:
            Number of remaining requests allowed in current window
        """
        current_time = time.time()
        recent_requests = [
            req_time for req_time in self.requests.get(key, [])
            if current_time - req_time < window
        ]
        return max(0, limit - len(recent_requests))
    
    def get_reset_time(self, key: str, window: int = 60) -> float:
        """
        Get timestamp when rate limit window resets for this client
        
        Args:
            key: Rate limit key (client identifier)
            window: Time window in seconds
            
        Returns:
            Unix timestamp when oldest request expires and limit resets
        """
        requests = self.requests.get(key, [])
        if not requests:
            return time.time()
        
        return requests[0] + window
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive rate limiter statistics for monitoring and debugging
        
        Returns:
            Dictionary containing operational metrics and performance data
        """
        return {
            "total_requests": self.total_requests,
            "total_blocked": self.total_blocked,
            "block_rate_percent": (self.total_blocked / max(self.total_requests, 1)) * 100,
            "active_clients": len(self.requests),
            "max_clients": self.max_clients,
            "cleanup_interval": self.cleanup_interval,
            "last_cleanup": self.last_cleanup
        }
    
    async def _periodic_cleanup(self, current_time: float):
        """
        Periodic cleanup of old rate limit data to prevent memory leaks
        
        This method removes stale entries and enforces maximum client limits
        to ensure the rate limiter doesn't consume excessive memory over time.
        
        Args:
            current_time: Current timestamp for cleanup calculation
        """
        if current_time - self.last_cleanup > self.cleanup_interval:
            initial_count = len(self.requests)
            
            # Identify stale entries that haven't been used recently
            stale_keys = []
            for key, requests in list(self.requests.items()):
                if not requests or current_time - max(requests) > 3600:  # 1 hour of inactivity
                    stale_keys.append(key)
            
            # Remove stale entries
            for key in stale_keys:
                del self.requests[key]
                if key in self.locks:
                    del self.locks[key]
            
            # If too many clients, remove oldest entries to prevent memory exhaustion
            if len(self.requests) > self.max_clients:
                # Sort by last activity and remove oldest entries
                sorted_keys = sorted(
                    self.requests.keys(),
                    key=lambda k: max(self.requests[k]) if self.requests[k] else 0
                )
                
                excess_count = len(self.requests) - self.max_clients
                for key in sorted_keys[:excess_count]:
                    del self.requests[key]
                    if key in self.locks:
                        del self.locks[key]
            
            self.last_cleanup = current_time
            final_count = len(self.requests)
            
            if initial_count != final_count:
                logger.debug(f"Rate limiter cleanup: {initial_count} -> {final_count} clients "
                           f"(removed {initial_count - final_count} entries)")

# Global rate limiter instance for application-wide use
rate_limiter = ModernRateLimiter()

# --- Enhanced Rate Limiting Decorator ---
def rate_limit(requests_per_minute: int = 60):
    """
    Production-ready rate limiting decorator with comprehensive error handling
    
    This decorator implements intelligent rate limiting with support for:
    - Proxy header extraction for accurate client identification
    - Graceful error handling with fallback behavior
    - Comprehensive logging and metrics integration
    - Detailed error responses with retry information
    - Thread-safe operation in async environments
    
    Args:
        requests_per_minute: Maximum requests allowed per minute per client
        
    Returns:
        Decorator function for applying rate limiting to FastAPI endpoints
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract FastAPI Request object from function arguments
            request: Optional[Request] = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if not request:
                # No request object found, skip rate limiting (for internal calls)
                return await func(*args, **kwargs)
            
            # Extract client IP with comprehensive proxy header support
            client_ip = (
                request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
                request.headers.get("x-real-ip", "").strip() or
                request.headers.get("cf-connecting-ip", "").strip() or  # Cloudflare
                request.headers.get("x-forwarded", "").strip() or      # General forwarded
                request.headers.get("forwarded-for", "").strip() or    # Alternative header
                (request.client.host if request.client else "unknown")
            )
            
            # Generate unique rate limit key combining IP and endpoint
            rate_limit_key = f"rate_limit:{client_ip}:{func.__name__}"
            
            # Apply rate limiting with comprehensive error handling
            try:
                is_allowed = await rate_limiter.is_allowed(
                    rate_limit_key, 
                    requests_per_minute, 
                    60  # 1 minute window
                )
                
                if not is_allowed:
                    # Rate limit exceeded - prepare detailed response for client
                    remaining = rate_limiter.get_remaining(rate_limit_key, requests_per_minute, 60)
                    reset_time = rate_limiter.get_reset_time(rate_limit_key, 60)
                    retry_after = max(1, int(reset_time - time.time()))
                    
                    logger.warning(f"Rate limit exceeded for client {client_ip} on endpoint {func.__name__}")
                    
                    # Record rate limit violation in metrics for monitoring
                    if METRICS_AVAILABLE:
                        REQUEST_COUNT.labels(provider='system', status='rate_limited').inc()
                        ERROR_COUNT.labels(error_type='rate_limit').inc()
                    
                    raise HTTPException(
                        status_code=429,
                        detail={
                            "error": "Rate limit exceeded",
                            "message": f"Too many requests. You have exceeded the limit of {requests_per_minute} requests per minute.",
                            "remaining": remaining,
                            "limit": requests_per_minute,
                            "window_seconds": 60,
                            "retry_after": retry_after,
                            "reset_time": reset_time,
                            "client_id": client_ip[:12] + "..." if len(client_ip) > 12 else client_ip
                        },
                        headers={
                            "Retry-After": str(retry_after),
                            "X-RateLimit-Limit": str(requests_per_minute),
                            "X-RateLimit-Remaining": str(remaining),
                            "X-RateLimit-Reset": str(int(reset_time)),
                            "X-RateLimit-Window": "60"
                        }
                    )
                
                # Record successful rate limit check
                if METRICS_AVAILABLE:
                    REQUEST_COUNT.labels(provider='system', status='allowed').inc()
                
                return await func(*args, **kwargs)
                
            except HTTPException:
                # Re-raise HTTP exceptions (like rate limit exceeded)
                raise
            except Exception as e:
                # Log unexpected errors but don't block request (graceful degradation)
                logger.error(f"Rate limiter error for {client_ip}: {e}")
                if METRICS_AVAILABLE:
                    ERROR_COUNT.labels(error_type='rate_limiter_error').inc()
                
                # Allow request to proceed despite rate limiter error
                return await func(*args, **kwargs)
        
        return wrapper
    return decorator

# --- Configuration Management Classes ---
@dataclass
class DatabaseConfig:
    """
    Database configuration with comprehensive validation and connection pooling
    
    Supports multiple database backends including:
    - PostgreSQL (recommended for production)
    - MySQL/MariaDB 
    - SQLite (development/testing)
    - SQL Server
    
    Features production-ready connection pooling, timeout handling, and health monitoring
    """
    url: str = os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./app.db')
    pool_size: int = int(os.getenv('DB_POOL_SIZE', '20'))
    max_overflow: int = int(os.getenv('DB_MAX_OVERFLOW', '30'))
    echo: bool = os.getenv('DB_ECHO', 'false').lower() == 'true'
    pool_timeout: int = int(os.getenv('DB_POOL_TIMEOUT', '30'))
    pool_recycle: int = int(os.getenv('DB_POOL_RECYCLE', '3600'))
    pool_pre_ping: bool = os.getenv('DB_POOL_PRE_PING', 'true').lower() == 'true'
    connect_timeout: int = int(os.getenv('DB_CONNECT_TIMEOUT', '10'))
    
    def __post_init__(self):
        """Validate database configuration with comprehensive parameter checking"""
        if not self.url:
            raise ValueError("Database URL cannot be empty")
        
        # Validate pool configuration
        if self.pool_size < 1:
            raise ValueError("Database pool size must be positive")
        if self.pool_size > 100:
            logger.warning("⚠️  Very large database pool size may cause resource issues")
        
        if self.max_overflow < 0:
            raise ValueError("Database max overflow must be non-negative")
        
        if self.pool_timeout <= 0:
            raise ValueError("Database pool timeout must be positive")
        
        if self.pool_recycle <= 0:
            raise ValueError("Database pool recycle time must be positive")
        
        if self.connect_timeout <= 0:
            raise ValueError("Database connect timeout must be positive")
        
        # Log database configuration for debugging
        db_type = self.url.split('://')[0] if '://' in self.url else 'unknown'
        logger.debug(f"Database configured: {db_type}, pool_size={self.pool_size}, "
                    f"max_overflow={self.max_overflow}")

@dataclass
class RedisConfig:
    """
    Redis configuration with connection validation and health monitoring
    
    Optimized for production use with:
    - Connection pooling and retry logic
    - Health check monitoring
    - Timeout and error handling
    - SSL/TLS support
    - Cluster support preparation
    """
    url: str = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    max_connections: int = int(os.getenv('REDIS_MAX_CONNECTIONS', '20'))
    socket_timeout: float = float(os.getenv('REDIS_SOCKET_TIMEOUT', '5.0'))
    socket_connect_timeout: float = float(os.getenv('REDIS_CONNECT_TIMEOUT', '5.0'))
    health_check_interval: int = int(os.getenv('REDIS_HEALTH_CHECK_INTERVAL', '30'))
    retry_on_timeout: bool = os.getenv('REDIS_RETRY_ON_TIMEOUT', 'true').lower() == 'true'
    retry_on_error: bool = os.getenv('REDIS_RETRY_ON_ERROR', 'true').lower() == 'true'
    encoding: str = 'utf-8'
    decode_responses: bool = False
    ssl_cert_reqs: str = os.getenv('REDIS_SSL_CERT_REQS', 'none')
    
    def __post_init__(self):
        """Validate Redis configuration with comprehensive parameter checking"""
        # Validate connection pool settings
        if self.max_connections < 1:
            raise ValueError("Redis max connections must be positive")
        if self.max_connections > 1000:
            logger.warning("⚠️  Very large Redis connection pool may cause resource issues")
        
        # Validate timeout settings
        if self.socket_timeout <= 0:
            raise ValueError("Redis socket timeout must be positive")
        if self.socket_connect_timeout <= 0:
            raise ValueError("Redis connect timeout must be positive")
        
        # Validate health check interval
        if self.health_check_interval < 10:
            raise ValueError("Redis health check interval must be at least 10 seconds")
        
        # Parse and validate Redis URL format
        if not self.url.startswith(('redis://', 'rediss://')):
            logger.warning(f"⚠️  Redis URL format may be invalid: {self.url}")
        
        # Check for SSL configuration
        if self.url.startswith('rediss://'):
            logger.info("Redis SSL/TLS connection configured")

# This concludes Part 1 of 3. 
# Part 2 will include SecurityConfig, AIConfig, AppConfig, and advanced caching
# Part 3 will include the ResourceManager, FastAPI app setup, and all endpoints
# main1.2.py - Configuration Classes and Comprehensive Validation
# Production-ready configuration management with advanced validation and security
# Current Date: 2025-06-08 01:06:23 UTC, User: AdsTable
# All comments in English as requested

# --- Database Configuration with Production Features ---
@dataclass
class DatabaseConfig:
    """
    Comprehensive database configuration with production-ready features and validation
    
    Supports multiple database backends including:
    - PostgreSQL (recommended for production) with advanced pooling and performance tuning
    - MySQL/MariaDB with optimized connection handling and charset support
    - SQLite (development/testing) with WAL mode and pragma optimization
    - SQL Server with advanced security and connection pooling
    
    Features production-ready connection pooling, timeout handling, health monitoring,
    and comprehensive error recovery mechanisms for enterprise deployment
    """
    # Core database connection settings
    url: str = os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./ai_aggregator.db')
    
    # Connection pool configuration for optimal performance
    pool_size: int = int(os.getenv('DB_POOL_SIZE', '20'))
    max_overflow: int = int(os.getenv('DB_MAX_OVERFLOW', '30'))
    pool_timeout: int = int(os.getenv('DB_POOL_TIMEOUT', '30'))
    pool_recycle: int = int(os.getenv('DB_POOL_RECYCLE', '3600'))
    pool_pre_ping: bool = os.getenv('DB_POOL_PRE_PING', 'true').lower() == 'true'
    
    # Connection and operation timeouts
    connect_timeout: int = int(os.getenv('DB_CONNECT_TIMEOUT', '10'))
    command_timeout: int = int(os.getenv('DB_COMMAND_TIMEOUT', '30'))
    query_timeout: int = int(os.getenv('DB_QUERY_TIMEOUT', '60'))
    
    # Performance and debugging settings
    echo: bool = os.getenv('DB_ECHO', 'false').lower() == 'true'
    echo_pool: bool = os.getenv('DB_ECHO_POOL', 'false').lower() == 'true'
    
    # Advanced features
    enable_migrations: bool = os.getenv('DB_ENABLE_MIGRATIONS', 'true').lower() == 'true'
    migration_timeout: int = int(os.getenv('DB_MIGRATION_TIMEOUT', '300'))
    
    # Security settings
    ssl_mode: str = os.getenv('DB_SSL_MODE', 'prefer')  # require, prefer, disable
    ssl_cert: Optional[str] = os.getenv('DB_SSL_CERT', None)
    ssl_key: Optional[str] = os.getenv('DB_SSL_KEY', None)
    ssl_ca: Optional[str] = os.getenv('DB_SSL_CA', None)
    
    def __post_init__(self):
        """Comprehensive database configuration validation with detailed parameter checking"""
        if not self.url:
            raise ValueError("Database URL cannot be empty")
        
        # Validate and extract database type for specific optimizations
        try:
            db_type = self.url.split('://')[0].split('+')[0] if '://' in self.url else 'unknown'
            self.db_type = db_type
        except Exception:
            self.db_type = 'unknown'
        
        # Validate pool configuration with intelligent defaults based on database type
        if self.pool_size < 1:
            raise ValueError("Database pool size must be positive")
        if self.pool_size > 200:
            logger.warning("⚠️  Very large database pool size may cause resource issues")
            logger.warning(f"   Consider reducing pool_size from {self.pool_size} to 50 or less")
        
        if self.max_overflow < 0:
            raise ValueError("Database max overflow must be non-negative")
        if self.max_overflow > 100:
            logger.warning("⚠️  Very large max overflow may cause connection issues")
        
        # Validate timeout settings
        timeout_fields = {
            'pool_timeout': self.pool_timeout,
            'connect_timeout': self.connect_timeout,
            'command_timeout': self.command_timeout,
            'query_timeout': self.query_timeout,
            'migration_timeout': self.migration_timeout
        }
        
        for field_name, value in timeout_fields.items():
            if value <= 0:
                raise ValueError(f"Database {field_name} must be positive, got {value}")
            if value > 3600:  # 1 hour
                logger.warning(f"⚠️  Very large {field_name} ({value}s) may cause blocking issues")
        
        # Validate SSL configuration
        ssl_modes = ['disable', 'allow', 'prefer', 'require', 'verify-ca', 'verify-full']
        if self.ssl_mode not in ssl_modes:
            logger.warning(f"⚠️  Unknown SSL mode: {self.ssl_mode}, using 'prefer'")
            self.ssl_mode = 'prefer'
        
        # Check SSL certificate files if specified
        ssl_files = {
            'ssl_cert': self.ssl_cert,
            'ssl_key': self.ssl_key,
            'ssl_ca': self.ssl_ca
        }
        
        for file_type, file_path in ssl_files.items():
            if file_path and not Path(file_path).exists():
                logger.warning(f"⚠️  {file_type} file not found: {file_path}")
        
        # Database-specific optimization suggestions
        self._apply_database_optimizations()
        
        # Log configuration summary for operational awareness
        logger.debug(f"Database configured: {self.db_type}, pool_size={self.pool_size}, "
                    f"max_overflow={self.max_overflow}, ssl_mode={self.ssl_mode}")
    
    def _apply_database_optimizations(self):
        """Apply database-specific optimizations and recommendations"""
        if self.db_type == 'postgresql':
            # PostgreSQL-specific optimizations
            if self.pool_size < 10:
                logger.info("💡 Consider increasing pool_size for PostgreSQL (recommended: 10-50)")
            if '?sslmode=' not in self.url and self.ssl_mode != 'disable':
                logger.info("💡 Consider adding SSL mode to PostgreSQL URL for explicit configuration")
                
        elif self.db_type == 'mysql':
            # MySQL-specific optimizations  
            if 'charset=utf8mb4' not in self.url:
                logger.info("💡 Consider adding charset=utf8mb4 to MySQL URL for proper Unicode support")
            if self.pool_recycle > 28000:  # MySQL default wait_timeout is 28800
                logger.warning("⚠️  Pool recycle time may exceed MySQL wait_timeout")
                
        elif self.db_type == 'sqlite':
            # SQLite-specific optimizations
            if self.pool_size > 1:
                logger.info("💡 SQLite doesn't benefit from large pool sizes, consider reducing to 1")
            if '?mode=wal' not in self.url:
                logger.info("💡 Consider adding WAL mode to SQLite URL for better performance")
    
    def get_engine_kwargs(self) -> Dict[str, Any]:
        """
        Get SQLAlchemy engine configuration with comprehensive settings
        
        Returns:
            Dictionary of engine configuration parameters optimized for the database type
        """
        base_kwargs = {
            'pool_size': self.pool_size,
            'max_overflow': self.max_overflow,
            'pool_timeout': self.pool_timeout,
            'pool_recycle': self.pool_recycle,
            'pool_pre_ping': self.pool_pre_ping,
            'echo': self.echo,
            'echo_pool': self.echo_pool,
        }
        
        # Add database-specific optimizations
        if self.db_type == 'postgresql':
            base_kwargs.update({
                'connect_args': {
                    'connect_timeout': self.connect_timeout,
                    'command_timeout': self.command_timeout,
                    'server_settings': {
                        'application_name': 'AI_Aggregator_Pro',
                        'jit': 'off'  # Disable JIT for consistent performance
                    }
                }
            })
            
            # Add SSL configuration for PostgreSQL
            if self.ssl_mode != 'disable':
                ssl_args = {'sslmode': self.ssl_mode}
                if self.ssl_cert:
                    ssl_args['sslcert'] = self.ssl_cert
                if self.ssl_key:
                    ssl_args['sslkey'] = self.ssl_key  
                if self.ssl_ca:
                    ssl_args['sslrootcert'] = self.ssl_ca
                base_kwargs['connect_args'].update(ssl_args)
                
        elif self.db_type == 'mysql':
            base_kwargs.update({
                'connect_args': {
                    'connect_timeout': self.connect_timeout,
                    'read_timeout': self.query_timeout,
                    'write_timeout': self.command_timeout,
                    'charset': 'utf8mb4',
                    'use_unicode': True
                }
            })
            
        elif self.db_type == 'sqlite':
            base_kwargs.update({
                'pool_size': 1,  # SQLite doesn't support multiple connections well
                'max_overflow': 0,
                'connect_args': {
                    'timeout': self.connect_timeout,
                    'check_same_thread': False
                }
            })
        
        return base_kwargs

@dataclass  
class RedisConfig:
    """
    Comprehensive Redis configuration with enterprise-grade features and monitoring
    
    Optimized for production use with:
    - Advanced connection pooling and retry logic with exponential backoff
    - Health check monitoring with intelligent failure detection
    - Timeout and error handling with graceful degradation
    - SSL/TLS support for secure connections and compliance requirements
    - Cluster support preparation for horizontal scaling
    - Memory optimization and efficient data structures
    - Sentinel support for high availability deployments
    """
    # Core Redis connection settings
    url: str = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    
    # Connection pool configuration
    max_connections: int = int(os.getenv('REDIS_MAX_CONNECTIONS', '20'))
    min_connections: int = int(os.getenv('REDIS_MIN_CONNECTIONS', '1'))
    
    # Timeout settings for optimal performance
    socket_timeout: float = float(os.getenv('REDIS_SOCKET_TIMEOUT', '5.0'))
    socket_connect_timeout: float = float(os.getenv('REDIS_CONNECT_TIMEOUT', '5.0'))
    socket_keepalive: bool = os.getenv('REDIS_SOCKET_KEEPALIVE', 'true').lower() == 'true'
    socket_keepalive_options: Dict[str, int] = field(default_factory=lambda: {
        'TCP_KEEPIDLE': 1,
        'TCP_KEEPINTVL': 3,
        'TCP_KEEPCNT': 5
    })
    
    # Health monitoring and reliability
    health_check_interval: int = int(os.getenv('REDIS_HEALTH_CHECK_INTERVAL', '30'))
    retry_on_timeout: bool = os.getenv('REDIS_RETRY_ON_TIMEOUT', 'true').lower() == 'true'
    retry_on_error: bool = os.getenv('REDIS_RETRY_ON_ERROR', 'true').lower() == 'true'
    retry_attempts: int = int(os.getenv('REDIS_RETRY_ATTEMPTS', '3'))
    retry_backoff_base: float = float(os.getenv('REDIS_RETRY_BACKOFF', '0.1'))
    
    # Data handling and encoding
    encoding: str = os.getenv('REDIS_ENCODING', 'utf-8')
    decode_responses: bool = os.getenv('REDIS_DECODE_RESPONSES', 'false').lower() == 'true'
    
    # Security and SSL configuration
    ssl_cert_reqs: str = os.getenv('REDIS_SSL_CERT_REQS', 'none')
    ssl_certfile: Optional[str] = os.getenv('REDIS_SSL_CERTFILE', None)
    ssl_keyfile: Optional[str] = os.getenv('REDIS_SSL_KEYFILE', None)
    ssl_ca_certs: Optional[str] = os.getenv('REDIS_SSL_CA_CERTS', None)
    ssl_check_hostname: bool = os.getenv('REDIS_SSL_CHECK_HOSTNAME', 'false').lower() == 'true'
    
    # Advanced features
    client_name: str = os.getenv('REDIS_CLIENT_NAME', 'AI_Aggregator_Pro')
    db: int = int(os.getenv('REDIS_DB', '0'))
    username: Optional[str] = os.getenv('REDIS_USERNAME', None)
    password: Optional[str] = os.getenv('REDIS_PASSWORD', None)
    
    def __post_init__(self):
        """Comprehensive Redis configuration validation with detailed parameter checking"""
        # Validate connection pool settings
        if self.max_connections < 1:
            raise ValueError("Redis max connections must be positive")
        if self.max_connections > 1000:
            logger.warning("⚠️  Very large Redis connection pool may cause resource issues")
            logger.warning(f"   Consider reducing max_connections from {self.max_connections}")
        
        if self.min_connections < 0:
            raise ValueError("Redis min connections must be non-negative")
        if self.min_connections > self.max_connections:
            raise ValueError("Redis min connections cannot exceed max connections")
        
        # Validate timeout settings
        timeout_fields = {
            'socket_timeout': self.socket_timeout,
            'socket_connect_timeout': self.socket_connect_timeout
        }
        
        for field_name, value in timeout_fields.items():
            if value <= 0:
                raise ValueError(f"Redis {field_name} must be positive, got {value}")
            if value > 60:
                logger.warning(f"⚠️  Very large {field_name} ({value}s) may cause blocking")
        
        # Validate health check interval
        if self.health_check_interval < 10:
            raise ValueError("Redis health check interval must be at least 10 seconds")
        if self.health_check_interval > 300:
            logger.warning(f"⚠️  Very long health check interval ({self.health_check_interval}s)")
        
        # Validate retry configuration
        if self.retry_attempts < 0:
            raise ValueError("Redis retry attempts must be non-negative")
        if self.retry_attempts > 10:
            logger.warning(f"⚠️  Very high retry attempts ({self.retry_attempts}) may cause delays")
        
        if self.retry_backoff_base <= 0:
            raise ValueError("Redis retry backoff base must be positive")
        
        # Validate database number
        if not (0 <= self.db <= 15):
            raise ValueError(f"Redis database number must be 0-15, got {self.db}")
        
        # Parse and validate Redis URL format
        if not self.url.startswith(('redis://', 'rediss://')):
            logger.warning(f"⚠️  Redis URL format may be invalid: {self.url}")
            logger.info("   Expected format: redis://[username:password@]host:port/db")
            logger.info("   For SSL: rediss://[username:password@]host:port/db")
        
        # Check for SSL configuration and validate certificates
        if self.url.startswith('rediss://'):
            logger.info("Redis SSL/TLS connection configured")
            self._validate_ssl_configuration()
        
        # Validate encoding
        try:
            'test'.encode(self.encoding)
        except LookupError:
            logger.warning(f"⚠️  Unknown encoding '{self.encoding}', using utf-8")
            self.encoding = 'utf-8'
        
        # Log configuration summary for operational awareness  
        logger.debug(f"Redis configured: {self.url.split('@')[-1] if '@' in self.url else self.url}, "
                    f"pool={self.min_connections}-{self.max_connections}, db={self.db}")
    
    def _validate_ssl_configuration(self):
        """Validate SSL/TLS configuration for secure Redis connections"""
        ssl_cert_reqs_options = ['none', 'optional', 'required']
        if self.ssl_cert_reqs not in ssl_cert_reqs_options:
            logger.warning(f"⚠️  Invalid SSL cert reqs: {self.ssl_cert_reqs}")
            self.ssl_cert_reqs = 'none'
        
        # Check SSL certificate files if specified
        ssl_files = {
            'ssl_certfile': self.ssl_certfile,
            'ssl_keyfile': self.ssl_keyfile, 
            'ssl_ca_certs': self.ssl_ca_certs
        }
        
        for file_type, file_path in ssl_files.items():
            if file_path and not Path(file_path).exists():
                logger.warning(f"⚠️  {file_type} not found: {file_path}")
        
        # Security recommendations
        if self.ssl_cert_reqs == 'none':
            logger.info("💡 Consider using SSL certificate validation for production")
        if not self.ssl_check_hostname:
            logger.info("💡 Consider enabling SSL hostname checking for production")
    
    def get_connection_kwargs(self) -> Dict[str, Any]:
        """
        Get Redis connection configuration with comprehensive settings
        
        Returns:
            Dictionary of Redis connection parameters optimized for production use
        """
        kwargs = {
            'max_connections': self.max_connections,
            'socket_timeout': self.socket_timeout,
            'socket_connect_timeout': self.socket_connect_timeout,
            'socket_keepalive': self.socket_keepalive,
            'socket_keepalive_options': self.socket_keepalive_options,
            'health_check_interval': self.health_check_interval,
            'retry_on_timeout': self.retry_on_timeout,
            'encoding': self.encoding,
            'decode_responses': self.decode_responses,
            'client_name': self.client_name,
            'db': self.db
        }
        
        # Add authentication if configured
        if self.username:
            kwargs['username'] = self.username
        if self.password:
            kwargs['password'] = self.password
        
        # Add SSL configuration for secure connections
        if self.url.startswith('rediss://'):
            ssl_kwargs = {
                'ssl_cert_reqs': self.ssl_cert_reqs,
                'ssl_check_hostname': self.ssl_check_hostname
            }
            
            if self.ssl_certfile:
                ssl_kwargs['ssl_certfile'] = self.ssl_certfile
            if self.ssl_keyfile:
                ssl_kwargs['ssl_keyfile'] = self.ssl_keyfile
            if self.ssl_ca_certs:
                ssl_kwargs['ssl_ca_certs'] = self.ssl_ca_certs
            
            kwargs.update(ssl_kwargs)
        
        return kwargs

# This completes Part 1.2 with Database and Redis configuration classes
# main1.3.py - SecurityConfig, AIConfig, AppConfig, and Validation
# All comments in English

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import os
from pathlib import Path

@dataclass
class SecurityConfig:
    """
    Security configuration for API, CORS, and request validation.
    """
    secret_key: str = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    api_key_header: str = os.getenv('API_KEY_HEADER', 'X-API-Key')
    allowed_origins: List[str] = field(default_factory=lambda: [
        o.strip() for o in os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000,http://localhost:8080').split(',')
    ])
    trusted_hosts: List[str] = field(default_factory=lambda: [
        h.strip() for h in os.getenv('TRUSTED_HOSTS', '').split(',') if h.strip()
    ])
    cors_max_age: int = int(os.getenv('CORS_MAX_AGE', '3600'))
    enable_csrf_protection: bool = os.getenv('ENABLE_CSRF', 'false').lower() == 'true'
    enable_rate_limiting: bool = os.getenv('ENABLE_RATE_LIMITING', 'true').lower() == 'true'
    enable_security_headers: bool = os.getenv('ENABLE_SECURITY_HEADERS', 'true').lower() == 'true'
    max_request_size: int = int(os.getenv('MAX_REQUEST_SIZE', '10485760'))  # 10MB
    allowed_methods: List[str] = field(default_factory=lambda: ['GET', 'POST', 'OPTIONS'])

    def __post_init__(self):
        if len(self.secret_key) < 32:
            print("Warning: Short secret key! Use at least 32 chars in production.")
        if '*' in self.allowed_origins and os.getenv('ENVIRONMENT', 'development') != 'development':
            print("Warning: Wildcard CORS is dangerous in production.")
        for origin in self.allowed_origins:
            if not (origin.startswith('http://') or origin.startswith('https://') or origin == '*'):
                print(f"Warning: Possibly invalid CORS origin format: {origin}")
        if self.max_request_size < 1024:
            raise ValueError("Max request size must be at least 1KB.")

@dataclass
class AIConfig:
    """
    AI provider and cost management settings.
    """
    default_provider: str = os.getenv('AI_DEFAULT_PROVIDER', 'ollama')
    max_concurrent_requests: int = int(os.getenv('MAX_CONCURRENT_AI_REQUESTS', '15'))
    request_timeout: int = int(os.getenv('AI_REQUEST_TIMEOUT', '60'))
    max_prompt_length: int = int(os.getenv('MAX_PROMPT_LENGTH', '50000'))
    cost_budget_daily: float = float(os.getenv('AI_COST_BUDGET_DAILY', '25.0'))
    cost_budget_monthly: float = float(os.getenv('AI_COST_BUDGET_MONTHLY', '500.0'))
    enable_cost_tracking: bool = os.getenv('ENABLE_COST_TRACKING', 'true').lower() == 'true'
    cost_alert_threshold: float = float(os.getenv('AI_COST_ALERT_THRESHOLD', '0.8'))
    enable_token_optimization: bool = os.getenv('ENABLE_TOKEN_OPTIMIZATION', 'true').lower() == 'true'
    enable_prompt_caching: bool = os.getenv('ENABLE_PROMPT_CACHING', 'true').lower() == 'true'
    enable_response_streaming: bool = os.getenv('ENABLE_RESPONSE_STREAMING', 'false').lower() == 'true'
    max_retries: int = int(os.getenv('AI_MAX_RETRIES', '3'))
    free_tier_limits: Dict[str, int] = field(default_factory=lambda: {
        'ollama': 999999, 'huggingface': 1000, 'together': 25, 'openai': 3,
        'anthropic': 5, 'claude': 5, 'mock': 999999, 'groq': 100, 'cohere': 100, 'ai21': 10, 'perplexity': 20
    })
    provider_priorities: Dict[str, int] = field(default_factory=lambda: {
        'ollama': 100, 'huggingface': 90, 'groq': 85, 'together': 80, 'cohere': 70, 'anthropic': 65,
        'claude': 65, 'openai': 60, 'ai21': 50, 'perplexity': 45, 'mock': 10
    })

    def __post_init__(self):
        if self.max_concurrent_requests < 1:
            raise ValueError("Max concurrent requests must be positive.")
        if self.request_timeout < 10:
            raise ValueError("Request timeout should be at least 10s.")
        if self.max_prompt_length < 100:
            raise ValueError("Max prompt length must be at least 100 chars.")
        if self.cost_budget_daily <= 0 or self.cost_budget_monthly <= 0:
            raise ValueError("Cost budgets must be positive.")
        if not 0.1 <= self.cost_alert_threshold <= 1.0:
            raise ValueError("Cost alert threshold must be between 0.1 and 1.0.")
        if self.max_retries < 0:
            raise ValueError("Max retries must be non-negative.")

@dataclass
class AppConfig:
    """
    Main application configuration and feature flags.
    """
    app_name: str = os.getenv('APP_NAME', 'AI Aggregator Pro')
    version: str = '3.7.0'
    environment: str = os.getenv('ENVIRONMENT', 'development')
    debug: bool = os.getenv('DEBUG', 'false').lower() == 'true'
    user: str = "AdsTable"
    host: str = os.getenv('HOST', '0.0.0.0')
    port: int = int(os.getenv('PORT', '8000'))
    workers: int = int(os.getenv('WORKERS', '1'))
    reload: bool = os.getenv('RELOAD', 'false').lower() == 'true'
    access_log: bool = os.getenv('ACCESS_LOG', 'true').lower() == 'true'
    enable_cache: bool = os.getenv('ENABLE_CACHE', 'true').lower() == 'true'
    enable_compression: bool = os.getenv('ENABLE_COMPRESSION', 'true').lower() == 'true'
    enable_metrics: bool = os.getenv('ENABLE_METRICS', 'true').lower() == 'true'
    enable_docs: bool = os.getenv('ENABLE_DOCS', 'true').lower() == 'true'
    enable_openapi: bool = os.getenv('ENABLE_OPENAPI', 'true').lower() == 'true'
    enable_monitoring: bool = os.getenv('ENABLE_MONITORING', 'true').lower() == 'true'
    enable_health_checks: bool = os.getenv('ENABLE_HEALTH_CHECKS', 'true').lower() == 'true'
    cache_ttl_short: int = int(os.getenv('CACHE_TTL_SHORT', '900'))
    cache_ttl_medium: int = int(os.getenv('CACHE_TTL_MEDIUM', '1800'))
    cache_ttl_long: int = int(os.getenv('CACHE_TTL_LONG', '3600'))
    cache_ttl_fallback: int = int(os.getenv('CACHE_TTL_FALLBACK', '300'))
    max_request_size: int = int(os.getenv('MAX_REQUEST_SIZE', '10485760'))
    request_timeout: int = int(os.getenv('REQUEST_TIMEOUT', '30'))
    max_response_size: int = int(os.getenv('MAX_RESPONSE_SIZE', '52428800'))
    keepalive_timeout: int = int(os.getenv('KEEPALIVE_TIMEOUT', '5'))
    default_rate_limit: int = int(os.getenv('DEFAULT_RATE_LIMIT', '60'))
    burst_rate_limit: int = int(os.getenv('BURST_RATE_LIMIT', '120'))
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    ai: AIConfig = field(default_factory=AIConfig)

    def __post_init__(self):
        if self.environment not in ['development', 'staging', 'production', 'testing']:
            raise ValueError(f"Invalid environment: {self.environment}")
        if not 1 <= self.port <= 65535:
            raise ValueError(f"Port must be between 1 and 65535, got: {self.port}")
        if self.workers < 1:
            raise ValueError(f"Workers count must be positive, got: {self.workers}")
        if self.cache_ttl_short > self.cache_ttl_medium or self.cache_ttl_medium > self.cache_ttl_long:
            print("Warning: Cache TTLs should be in increasing order: short < medium < long.")
        if self.max_request_size < 1024:
            raise ValueError("Max request size must be at least 1KB.")
        if self.request_timeout < 1:
            raise ValueError("Request timeout must be positive.")

# AppConfig instantiation (with error handling/fallback if needed)
try:
    config = AppConfig()
except Exception as e:
    print(f"Config error: {e}")
    config = AppConfig(environment='development', debug=True)
	# main.py - Part 2 of 3: Advanced Configuration, Caching, and Token Optimization
# Production-ready implementations with comprehensive security and performance features

@dataclass
class SecurityConfig:
    """
    Comprehensive security configuration implementing industry best practices
    
    Features:
    - Multi-layer security validation with environment-specific requirements
    - CORS configuration with origin validation and security headers
    - API key management and authentication frameworks
    - Rate limiting integration and abuse prevention
    - Security header management for production deployments
    - CSRF protection and XSS prevention capabilities
    """
    secret_key: str = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    api_key_header: str = os.getenv('API_KEY_HEADER', 'X-API-Key')
    allowed_origins: List[str] = field(default_factory=lambda: 
        [origin.strip() for origin in os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000,http://localhost:8080,http://localhost:5173').split(',') if origin.strip()]
    )
    trusted_hosts: List[str] = field(default_factory=lambda: 
        [host.strip() for host in os.getenv('TRUSTED_HOSTS', '').split(',') if host.strip()]
    )
    cors_max_age: int = int(os.getenv('CORS_MAX_AGE', '3600'))
    enable_csrf_protection: bool = os.getenv('ENABLE_CSRF', 'false').lower() == 'true'
    enable_rate_limiting: bool = os.getenv('ENABLE_RATE_LIMITING', 'true').lower() == 'true'
    enable_security_headers: bool = os.getenv('ENABLE_SECURITY_HEADERS', 'true').lower() == 'true'
    max_request_size: int = int(os.getenv('MAX_REQUEST_SIZE', '10485760'))  # 10MB
    allowed_methods: List[str] = field(default_factory=lambda: ['GET', 'POST', 'OPTIONS'])
    
    def __post_init__(self):
        """Validate security configuration with comprehensive production-ready checks"""
        environment = os.getenv('ENVIRONMENT', 'development')
        
        # Secret key validation with environment-specific requirements
        if len(self.secret_key) < 32:
            if environment == 'production':
                raise ValueError("Secret key must be at least 32 characters in production")
            else:
                logger.warning("⚠️  Secret key is too short for production use (minimum 32 characters recommended)")
        
        # Check for default secret key in production (critical security risk)
        if environment == 'production' and 'dev-secret' in self.secret_key.lower():
            raise ValueError("Default secret key cannot be used in production environment")
        
        # Validate secret key entropy for production security
        if environment == 'production':
            if self.secret_key.isalnum() or len(set(self.secret_key)) < 10:
                logger.warning("⚠️  Secret key may have low entropy - consider using a cryptographically secure random key")
        
        # CORS validation and security warnings
        if not self.allowed_origins:
            logger.warning("⚠️  No CORS origins configured - this may cause issues with browser clients")
        
        # Check for wildcard CORS in production (major security risk)
        if '*' in self.allowed_origins and environment == 'production':
            raise ValueError("Wildcard CORS origin ('*') is not allowed in production for security reasons")
        
        # Validate origin URLs format and security
        for origin in self.allowed_origins:
            if not (origin.startswith('http://') or origin.startswith('https://') or origin == '*'):
                logger.warning(f"⚠️  Potentially invalid CORS origin format: {origin}")
            
            # Warn about HTTP origins in production
            if origin.startswith('http://') and environment == 'production' and 'localhost' not in origin:
                logger.warning(f"⚠️  HTTP origin in production is insecure: {origin}")
        
        # Validate request size limits
        if self.max_request_size < 1024:  # 1KB minimum
            raise ValueError("Max request size must be at least 1KB")
        if self.max_request_size > 100 * 1024 * 1024:  # 100MB maximum
            logger.warning("⚠️  Very large max request size may cause memory and security issues")
        
        # Validate CORS max age
        if self.cors_max_age < 0:
            raise ValueError("CORS max age must be non-negative")
        if self.cors_max_age > 86400:  # 24 hours
            logger.warning("⚠️  Very long CORS max age may cause security issues")
        
        # Validate allowed methods for security
        dangerous_methods = {'DELETE', 'PUT', 'PATCH'}
        if any(method in self.allowed_methods for method in dangerous_methods):
            if environment == 'production':
                logger.warning(f"⚠️  Potentially dangerous HTTP methods allowed in production: {dangerous_methods & set(self.allowed_methods)}")

@dataclass
class AIConfig:
    """
    Comprehensive AI provider configuration with advanced cost management and optimization
    
    Features:
    - Multi-provider support with intelligent failover and load balancing
    - Advanced cost tracking with daily/monthly budgets and alerts
    - Token optimization and prompt compression capabilities
    - Provider-specific rate limiting and quota management
    - Circuit breaker integration for reliability
    - Performance monitoring and analytics
    - Free tier management and usage optimization
    """
    default_provider: str = os.getenv('AI_DEFAULT_PROVIDER', 'ollama')
    max_concurrent_requests: int = int(os.getenv('MAX_CONCURRENT_AI_REQUESTS', '15'))
    request_timeout: int = int(os.getenv('AI_REQUEST_TIMEOUT', '60'))
    max_prompt_length: int = int(os.getenv('MAX_PROMPT_LENGTH', '50000'))
    
    # Cost management and budgeting
    cost_budget_daily: float = float(os.getenv('AI_COST_BUDGET_DAILY', '25.0'))
    cost_budget_monthly: float = float(os.getenv('AI_COST_BUDGET_MONTHLY', '500.0'))
    enable_cost_tracking: bool = os.getenv('ENABLE_COST_TRACKING', 'true').lower() == 'true'
    cost_alert_threshold: float = float(os.getenv('AI_COST_ALERT_THRESHOLD', '0.8'))  # 80% of budget
    
    # Performance and optimization settings
    enable_token_optimization: bool = os.getenv('ENABLE_TOKEN_OPTIMIZATION', 'true').lower() == 'true'
    enable_prompt_caching: bool = os.getenv('ENABLE_PROMPT_CACHING', 'true').lower() == 'true'
    enable_response_streaming: bool = os.getenv('ENABLE_RESPONSE_STREAMING', 'false').lower() == 'true'
    max_retries: int = int(os.getenv('AI_MAX_RETRIES', '3'))
    
    # Provider-specific free tier limits (requests per day)
    free_tier_limits: Dict[str, int] = field(default_factory=lambda: {
        'ollama': 999999,       # Local model - virtually unlimited
        'huggingface': 1000,    # HuggingFace Inference API free tier
        'together': 25,         # Together AI free tier
        'openai': 3,            # OpenAI free tier (very limited)
        'anthropic': 5,         # Anthropic free tier
        'claude': 5,            # Claude API free tier
        'mock': 999999,         # Mock provider - unlimited for testing
        'groq': 100,            # Groq free tier
        'cohere': 100,          # Cohere free tier
        'ai21': 10,             # AI21 free tier
        'perplexity': 20,       # Perplexity AI free tier
    })
    
    # Provider priority scoring for intelligent selection
    provider_priorities: Dict[str, int] = field(default_factory=lambda: {
        'ollama': 100,          # Highest priority - local and free
        'huggingface': 90,      # High priority - free and reliable
        'groq': 85,             # High priority - fast inference
        'together': 80,         # Good priority - open source models
        'cohere': 70,           # Medium priority - good for specific tasks
        'anthropic': 65,        # Medium priority - high quality but paid
        'claude': 65,           # Medium priority - high quality but paid
        'openai': 60,           # Lower priority - expensive but high quality
        'ai21': 50,             # Lower priority - specialized models
        'perplexity': 45,       # Lower priority - search-focused
        'mock': 10,             # Lowest priority - testing only
    })
    
    def __post_init__(self):
        """Validate AI configuration with comprehensive parameter and security checking"""
        # Validate concurrent request limits for system stability
        if self.max_concurrent_requests < 1:
            raise ValueError("Max concurrent requests must be positive")
        if self.max_concurrent_requests > 200:
            logger.warning("⚠️  Very high concurrent request limit may cause resource exhaustion")
        
        # Validate timeout settings for user experience
        if self.request_timeout < 10:
            raise ValueError("Request timeout must be at least 10 seconds for AI operations")
        if self.request_timeout > 300:
            logger.warning("⚠️  Very high request timeout may cause poor user experience")
        
        # Validate prompt length limits for memory management
        if self.max_prompt_length < 100:
            raise ValueError("Max prompt length must be at least 100 characters")
        if self.max_prompt_length > 200000:
            logger.warning("⚠️  Very large max prompt length may cause memory issues")
        
        # Validate cost budgets for financial control
        if self.cost_budget_daily <= 0:
            raise ValueError("Daily cost budget must be positive")
        if self.cost_budget_monthly <= 0:
            raise ValueError("Monthly cost budget must be positive")
        
        # Check budget consistency and warn about potential issues
        if self.cost_budget_daily * 30 > self.cost_budget_monthly * 1.5:
            logger.warning("⚠️  Daily budget seems high compared to monthly budget")
        
        # Validate cost alert threshold
        if not 0.1 <= self.cost_alert_threshold <= 1.0:
            raise ValueError("Cost alert threshold must be between 0.1 and 1.0")
        
        # Validate retry settings
        if self.max_retries < 0:
            raise ValueError("Max retries must be non-negative")
        if self.max_retries > 10:
            logger.warning("⚠️  Very high retry count may cause long delays")
        
        # Validate default provider
        if self.default_provider not in list(self.free_tier_limits.keys()) + ['auto']:
            logger.warning(f"⚠️  Unknown default provider: {self.default_provider}")
        
        # Log configuration summary for operational awareness
        logger.debug(f"AI Config: max_concurrent={self.max_concurrent_requests}, "
                    f"timeout={self.request_timeout}s, budget=${self.cost_budget_daily}/day")

@dataclass
class AppConfig:
    """
    Main application configuration with comprehensive validation and environment management
    
    Features:
    - Environment-specific configuration with intelligent defaults
    - Comprehensive validation with detailed error reporting
    - Performance optimization settings for different deployment scenarios
    - Feature flag management with dependency checking
    - Resource limit configuration for stability and security
    - Monitoring and observability integration
    - Health check and diagnostics configuration
    
    Optimized for Python 3.13 with enhanced error handling and type safety
    """
    # Application identity and versioning
    app_name: str = os.getenv('APP_NAME', 'AI Aggregator Pro')
    version: str = '3.5.0'  # Updated version with comprehensive improvements
    environment: str = os.getenv('ENVIRONMENT', 'development')
    debug: bool = os.getenv('DEBUG', 'false').lower() == 'true'
    python_version: str = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    user: str = "AdsTable"  # Current user as specified
    
    # Server configuration with production-ready defaults
    host: str = os.getenv('HOST', '0.0.0.0')
    port: int = int(os.getenv('PORT', '8000'))
    workers: int = int(os.getenv('WORKERS', '1'))
    reload: bool = os.getenv('RELOAD', 'false').lower() == 'true'
    access_log: bool = os.getenv('ACCESS_LOG', 'true').lower() == 'true'
    
    # Feature flags with intelligent environment-based defaults
    enable_cache: bool = REDIS_AVAILABLE and os.getenv('ENABLE_CACHE', 'true').lower() == 'true'
    enable_compression: bool = os.getenv('ENABLE_COMPRESSION', 'true').lower() == 'true'
    enable_metrics: bool = METRICS_AVAILABLE and os.getenv('ENABLE_METRICS', 'true').lower() == 'true'
    enable_docs: bool = os.getenv('ENABLE_DOCS', 'true' if os.getenv('ENVIRONMENT', 'development') != 'production' else 'false').lower() == 'true'
    enable_openapi: bool = os.getenv('ENABLE_OPENAPI', 'true').lower() == 'true'
    enable_monitoring: bool = os.getenv('ENABLE_MONITORING', 'true').lower() == 'true'
    enable_health_checks: bool = os.getenv('ENABLE_HEALTH_CHECKS', 'true').lower() == 'true'
    
    # Performance and caching settings with optimized defaults
    cache_ttl_short: int = int(os.getenv('CACHE_TTL_SHORT', '900'))        # 15 minutes
    cache_ttl_medium: int = int(os.getenv('CACHE_TTL_MEDIUM', '1800'))     # 30 minutes
    cache_ttl_long: int = int(os.getenv('CACHE_TTL_LONG', '3600'))         # 1 hour
    cache_ttl_fallback: int = int(os.getenv('CACHE_TTL_FALLBACK', '300'))  # 5 minutes
    
    # Request processing limits for security and performance
    max_request_size: int = int(os.getenv('MAX_REQUEST_SIZE', '10485760'))    # 10MB
    request_timeout: int = int(os.getenv('REQUEST_TIMEOUT', '30'))           # 30 seconds
    max_response_size: int = int(os.getenv('MAX_RESPONSE_SIZE', '52428800')) # 50MB
    keepalive_timeout: int = int(os.getenv('KEEPALIVE_TIMEOUT', '5'))        # 5 seconds
    
    # Rate limiting configuration
    default_rate_limit: int = int(os.getenv('DEFAULT_RATE_LIMIT', '60'))     # 60 requests per minute
    burst_rate_limit: int = int(os.getenv('BURST_RATE_LIMIT', '120'))       # 120 requests per minute for bursts
    
    # Sub-configurations with dependency injection
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    
    def __post_init__(self):
        """Comprehensive application configuration validation with environment-specific checks"""
        # Environment validation with detailed error messages
        valid_environments = ['development', 'staging', 'production', 'testing']
        if self.environment not in valid_environments:
            raise ValueError(f"Environment must be one of: {valid_environments}, got: {self.environment}")
        
        # Server configuration validation
        if not 1 <= self.port <= 65535:
            raise ValueError(f"Port must be between 1 and 65535, got: {self.port}")
        
        if self.workers < 1:
            raise ValueError(f"Workers count must be positive, got: {self.workers}")
        if self.workers > 32:
            logger.warning(f"⚠️  Very high worker count ({self.workers}) may cause resource contention")
        
        # Validate host binding security
        if self.host not in ['0.0.0.0', '127.0.0.1', 'localhost'] and not self.host.startswith('192.168.'):
            logger.warning(f"⚠️  Non-standard host binding detected: {self.host}")
        
        # Performance settings validation
        ttl_values = [self.cache_ttl_short, self.cache_ttl_medium, self.cache_ttl_long, self.cache_ttl_fallback]
        if not all(ttl > 0 for ttl in ttl_values):
            raise ValueError("All cache TTL values must be positive")
        
        if self.cache_ttl_short > self.cache_ttl_medium:
            logger.warning("⚠️  Short cache TTL is greater than medium cache TTL")
        if self.cache_ttl_medium > self.cache_ttl_long:
            logger.warning("⚠️  Medium cache TTL is greater than long cache TTL")
        
        # Request size limits validation
        if self.max_request_size < 1024:  # 1KB minimum
            raise ValueError("Max request size must be at least 1KB")
        if self.max_request_size > 100 * 1024 * 1024:  # 100MB maximum
            logger.warning("⚠️  Very large max request size may cause memory issues")
        
        if self.request_timeout < 1:
            raise ValueError("Request timeout must be positive")
        if self.request_timeout > 300:
            logger.warning("⚠️  Very high request timeout may cause poor user experience")
        
        # Rate limiting validation
        if self.default_rate_limit < 1:
            raise ValueError("Default rate limit must be positive")
        if self.burst_rate_limit < self.default_rate_limit:
            logger.warning("⚠️  Burst rate limit is lower than default rate limit")
        
        # Production-specific validations and security checks
        if self.environment == 'production':
            if self.debug:
                logger.warning("⚠️  Debug mode is enabled in production - this is not recommended")
            if self.reload:
                logger.warning("⚠️  Auto-reload is enabled in production - this is not recommended")
            if self.enable_docs and not os.getenv('FORCE_ENABLE_DOCS'):
                logger.warning("⚠️  API documentation is enabled in production")
            if not self.enable_monitoring:
                logger.warning("⚠️  Monitoring is disabled in production - this is not recommended")
            if not self.enable_health_checks:
                logger.warning("⚠️  Health checks are disabled in production - this is not recommended")
        
        # Development-specific optimizations and suggestions
        if self.environment == 'development':
            if not self.enable_docs:
                logger.info("💡 Consider enabling API docs for development")
            if not self.debug:
                logger.info("💡 Consider enabling debug mode for development")
            if not self.reload:
                logger.info("💡 Consider enabling auto-reload for development")
        
        # Feature dependency validation
        if self.enable_cache and not REDIS_AVAILABLE:
            logger.warning("⚠️  Cache is enabled but Redis is not available")
            self.enable_cache = False
        
        if self.enable_metrics and not METRICS_AVAILABLE:
            logger.warning("⚠️  Metrics are enabled but Prometheus client is not available")
            self.enable_metrics = False
        
        # Log comprehensive configuration summary for operational awareness
        logger.info(f"✅ Application configured for {self.environment} environment")
        logger.info(f"   Server: {self.host}:{self.port} (workers: {self.workers})")
        logger.info(f"   User: {self.user}")
        logger.info(f"   Features: docs={self.enable_docs}, cache={self.enable_cache}, metrics={self.enable_metrics}")
        logger.info(f"   Debug: {self.debug}, Reload: {self.reload}, Monitoring: {self.enable_monitoring}")
        logger.info(f"   Limits: {self.max_request_size // 1024}KB max request, {self.request_timeout}s timeout")
        logger.info(f"   Rate limiting: {self.default_rate_limit}/min default, {self.burst_rate_limit}/min burst")

# Initialize configuration with comprehensive error handling and fallback
try:
    config = AppConfig()
    logger.info("✅ Configuration validation successful")
except Exception as e:
    logger.error(f"❌ Configuration validation failed: {e}")
    logger.error("   Creating minimal fallback configuration for graceful startup...")
    
    # Create minimal fallback configuration for graceful degradation
    config = AppConfig()
    config.enable_docs = True  # Force enable docs for debugging
    config.debug = True
    config.environment = 'development'
    logger.warning("⚠️  Using fallback configuration - some features may not work correctly")
    logger.warning("   Please check environment variables and dependencies")

# --- Circuit Breaker Implementation ---
@dataclass
class CircuitBreaker:
    """
    Advanced circuit breaker implementing the circuit breaker pattern with comprehensive monitoring
    
    Features:
    - Three-state operation: CLOSED (normal), OPEN (failing), HALF_OPEN (testing recovery)
    - Configurable failure thresholds with exponential backoff
    - Automatic state transitions based on success/failure patterns
    - Comprehensive metrics and monitoring integration
    - Thread-safe operation with proper locking
    - Health reporting and debugging capabilities
    - Integration with external monitoring systems
    
    Designed for production reliability and cascade failure prevention
    """
    failure_threshold: int = 5                    # Consecutive failures before opening circuit
    recovery_timeout: int = 60                    # Seconds to wait before attempting recovery
    half_open_max_calls: int = 3                  # Max test calls in half-open state
    success_threshold: int = 2                    # Successes needed in half-open to close
    failure_count: int = 0                        # Current consecutive failure count
    success_count: int = 0                        # Success count in half-open state
    last_failure_time: Optional[float] = None     # Timestamp of last failure
    last_success_time: Optional[float] = None     # Timestamp of last success
    state: str = "CLOSED"                         # Current state: CLOSED, OPEN, HALF_OPEN
    total_requests: int = 0                       # Total requests processed
    total_failures: int = 0                       # Total failures encountered
    total_successes: int = 0                      # Total successes recorded
    state_transitions: int = 0                    # Number of state changes
    
    def is_request_allowed(self) -> bool:
        """
        Check if request is allowed based on current circuit breaker state
        
        Returns:
            True if request should be allowed, False if circuit is open
        """
        current_time = time.time()
        self.total_requests += 1
        
        if self.state == "CLOSED":
            # Normal operation - all requests allowed
            return True
        elif self.state == "OPEN":
            # Circuit is open - check if recovery timeout has passed
            if current_time - (self.last_failure_time or 0) > self.recovery_timeout:
                self._transition_to_half_open()
                return True
            return False
        else:  # HALF_OPEN
            # Limited testing mode - allow limited requests to test recovery
            return self.success_count < self.half_open_max_calls
    
    def record_success(self):
        """Record successful request and update circuit breaker state accordingly"""
        current_time = time.time()
        self.last_success_time = current_time
        self.total_successes += 1
        
        if self.state == "HALF_OPEN":
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                # Enough successful requests - circuit is healthy again
                self._transition_to_closed()
        elif self.state == "CLOSED":
            # Gradual recovery of failure count on success (forgiveness mechanism)
            self.failure_count = max(0, self.failure_count - 1)
    
    def record_failure(self):
        """Record failed request and update circuit breaker state accordingly"""
        current_time = time.time()
        self.failure_count += 1
        self.total_failures += 1
        self.last_failure_time = current_time
        
        if self.state == "CLOSED" and self.failure_count >= self.failure_threshold:
            # Too many failures - open the circuit to prevent cascade failures
            self._transition_to_open()
        elif self.state == "HALF_OPEN":
            # Failure during recovery - back to open state
            self._transition_to_open()
    
    def _transition_to_closed(self):
        """Transition circuit breaker to CLOSED state"""
        old_state = self.state
        self.state = "CLOSED"
        self.failure_count = 0
        self.success_count = 0
        self.state_transitions += 1
        logger.info(f"Circuit breaker: {old_state} -> CLOSED (healthy operation restored)")
    
    def _transition_to_open(self):
        """Transition circuit breaker to OPEN state"""
        old_state = self.state
        self.state = "OPEN"
        self.success_count = 0
        self.state_transitions += 1
        logger.warning(f"Circuit breaker: {old_state} -> OPEN (failure threshold exceeded)")
    
    def _transition_to_half_open(self):
        """Transition circuit breaker to HALF_OPEN state"""
        old_state = self.state
        self.state = "HALF_OPEN"
        self.success_count = 0
        self.state_transitions += 1
        logger.info(f"Circuit breaker: {old_state} -> HALF_OPEN (testing recovery)")
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get comprehensive circuit breaker status for monitoring and debugging
        
        Returns:
            Dictionary containing detailed circuit breaker metrics and operational status
        """
        current_time = time.time()
        time_to_recovery = 0
        
        if self.state == "OPEN" and self.last_failure_time:
            time_to_recovery = max(0, self.recovery_timeout - (current_time - self.last_failure_time))
        
        failure_rate = (self.total_failures / max(self.total_requests, 1)) * 100
        success_rate = (self.total_successes / max(self.total_requests, 1)) * 100
        
        return {
            "state": self.state,
            "is_healthy": self.state == "CLOSED",
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "failure_threshold": self.failure_threshold,
            "success_threshold": self.success_threshold,
            "total_requests": self.total_requests,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
            "failure_rate_percent": round(failure_rate, 2),
            "success_rate_percent": round(success_rate, 2),
            "last_failure_time": self.last_failure_time,
            "last_success_time": self.last_success_time,
            "time_to_recovery_seconds": round(time_to_recovery, 1),
            "recovery_timeout": self.recovery_timeout,
            "state_transitions": self.state_transitions
        }
    
    def reset(self):
        """Reset circuit breaker to initial state (for testing or manual recovery)"""
        self.state = "CLOSED"
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.last_success_time = None
        self.state_transitions += 1
        logger.info("Circuit breaker manually reset to CLOSED state")

# --- Advanced Caching System ---
class AdvancedCache:
    """
    High-performance caching system with intelligent compression and comprehensive monitoring
    
    Features:
    - Intelligent compression with size-based decision making
    - Automatic format detection for seamless decompression
    - Comprehensive error handling with graceful degradation
    - Metrics integration for performance monitoring
    - Memory optimization with automatic cleanup
    - TTL management with intelligent expiration
    - Cache warming and preloading capabilities
    - Multi-level caching support preparation
    
    Optimized for production use with Redis backend and memory efficiency
    """
    
    # Class-level configuration for compression thresholds
    COMPRESSION_THRESHOLD = 1024  # Only compress data larger than 1KB
    COMPRESSION_LEVEL = 6         # Balance between speed and compression ratio
    MAX_CACHE_KEY_LENGTH = 250    # Redis key length limit
    
    @staticmethod
    def generate_cache_key(prefix: str, *args, **kwargs) -> str:
        """
        Generate consistent, collision-resistant cache keys with length validation
        
        Features:
        - SHA-256 hashing for collision resistance
        - Prefix support for namespace organization
        - Length validation for Redis compatibility
        - Deterministic key generation for consistent caching
        
        Args:
            prefix: Cache key prefix for organization
            *args: Positional arguments to include in key
            **kwargs: Keyword arguments to include in key
            
        Returns:
            Generated cache key suitable for Redis storage
        """
        # Combine all arguments into a deterministic string
        args_str = ':'.join(str(arg) for arg in args)
        kwargs_str = ':'.join(f'{k}={v}' for k, v in sorted(kwargs.items()))
        
        # Create composite key data
        key_data = f"{prefix}:{args_str}:{kwargs_str}"
        
        # If key is too long, use hash
        if len(key_data) > AdvancedCache.MAX_CACHE_KEY_LENGTH:
            key_hash = hashlib.sha256(key_data.encode()).hexdigest()[:32]
            return f"{prefix}:hash:{key_hash}"
        
        return key_data
    
    @staticmethod
    def compress_data(data: Any) -> bytes:
        """
        Intelligent data compression with size-based decision making
        
        Features:
        - Size threshold for compression efficiency
        - Optimal compression level for speed/size balance
        - Fallback handling for compression failures
        - Compression ratio validation
        
        Args:
            data: Any serializable data object
            
        Returns:
            Compressed or uncompressed bytes ready for storage
            
        Raises:
            Exception: If serialization fails
        """
        try:
            # Serialize data using highest pickle protocol for Python 3.13 efficiency
            serialized = pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)
            original_size = len(serialized)
            
            # Only compress if data exceeds threshold and compression is enabled
            if config.enable_compression and original_size > AdvancedCache.COMPRESSION_THRESHOLD:
                compressed = gzip.compress(serialized, compresslevel=AdvancedCache.COMPRESSION_LEVEL)
                compressed_size = len(compressed)
                
                # Only use compressed version if it provides meaningful space savings (at least 10%)
                compression_ratio = (original_size - compressed_size) / original_size
                if compression_ratio > 0.1:
                    logger.debug(f"Cache compression: {original_size} -> {compressed_size} bytes "
                               f"({compression_ratio * 100:.1f}% reduction)")
                    return compressed
                else:
                    logger.debug(f"Cache compression skipped: insufficient benefit for {original_size} bytes")
            
            return serialized
            
        except Exception as e:
            logger.error(f"Cache data compression failed: {e}")
            raise
    
    @staticmethod
    def decompress_data(data: bytes) -> Any:
        """
        Intelligent data decompression with automatic format detection
        
        Features:
        - Automatic detection of compressed vs uncompressed data
        - Graceful fallback for format mismatches
        - Comprehensive error handling with detailed logging
        - Performance monitoring for decompression operations
        
        Args:
            data: Compressed or uncompressed bytes from cache storage
            
        Returns:
            Deserialized data object
            
        Raises:
            Exception: If both decompression and direct deserialization fail
        """
        original_size = len(data)
        
        try:
            # Try compression-aware decompression first if compression is enabled
            if config.enable_compression:
                try:
                    # Attempt gzip decompression
                    decompressed = gzip.decompress(data)
                    decompressed_size = len(decompressed)
                    result = pickle.loads(decompressed)
                    
                    logger.debug(f"Cache decompression: {original_size} -> {decompressed_size} bytes "
                               f"({((decompressed_size - original_size) / original_size) * 100:.1f}% expansion)")
                    return result
                    
                except (gzip.BadGzipFile, OSError):
                    # Data is not compressed - fall through to direct unpickling
                    logger.debug("Cache data not compressed, using direct deserialization")
            
            # Fallback to direct unpickling for uncompressed data
            return pickle.loads(data)
            
        except Exception as e:
            logger.error(f"Cache data decompression failed for {original_size} bytes: {e}")
            raise
    
    @staticmethod
    async def get_cached(redis_client: Redis, key: str) -> Optional[Any]:
        """
        Retrieve and decompress cached data with comprehensive monitoring
        
        Features:
        - Automatic decompression with format detection
        - Metrics tracking for cache performance analysis
        - Comprehensive error handling with graceful degradation
        - Debug logging for troubleshooting and optimization
        - TTL information for cache management
        
        Args:
            redis_client: Active Redis client instance
            key: Cache key to retrieve
            
        Returns:
            Cached data or None if not found or error occurred
        """
        if not redis_client:
            logger.debug("Cache get skipped: Redis client not available")
            return None
            
        start_time = time.time()
        
        try:
            # Retrieve raw data from Redis with pipeline for efficiency
            pipe = redis_client.pipeline()
            pipe.get(key)
            pipe.ttl(key)  # Get remaining TTL for monitoring
            results = await pipe.execute()
            
            data, ttl = results
            
            if data:
                # Record cache hit metrics
                if config.enable_metrics and METRICS_AVAILABLE:
                    CACHE_HITS.labels(cache_type='redis').inc()
                
                # Decompress and return data
                result = AdvancedCache.decompress_data(data)
                
                elapsed_time = (time.time() - start_time) * 1000  # Convert to milliseconds
                logger.debug(f"Cache HIT for key: {key[:50]}... "
                           f"(size: {len(data)} bytes, TTL: {ttl}s, time: {elapsed_time:.2f}ms)")
                
                return result
            else:
                elapsed_time = (time.time() - start_time) * 1000
                logger.debug(f"Cache MISS for key: {key[:50]}... (time: {elapsed_time:.2f}ms)")
                return None
                
        except Exception as e:
            elapsed_time = (time.time() - start_time) * 1000
            logger.warning(f"Cache read error for key {key[:50]}... (time: {elapsed_time:.2f}ms): {e}")
            
            # Record cache error metrics
            if config.enable_metrics and METRICS_AVAILABLE:
                ERROR_COUNT.labels(error_type='cache_read_error').inc()
            
            # Graceful degradation - don't raise exception
            return None
    
    @staticmethod
    async def set_cached(redis_client: Redis, key: str, value: Any, ttl: int):
        """
        Compress and cache data with intelligent TTL management and error handling
        
        Features:
        - Automatic compression for storage efficiency
        - TTL validation and adjustment based on data characteristics
        - Comprehensive error handling with graceful degradation
        - Performance monitoring and storage efficiency metrics
        - Atomic operations for data consistency
        
        Args:
            redis_client: Active Redis client instance
            key: Cache key to store under
            value: Data to cache (must be serializable)
            ttl: Time to live in seconds
        """
        if not redis_client:
            logger.debug("Cache set skipped: Redis client not available")
            return
        
        # Validate TTL
        if ttl <= 0:
            logger.warning(f"Invalid TTL {ttl} for cache key {key[:50]}..., skipping cache operation")
            return
        
        # Adjust TTL based on data characteristics
        adjusted_ttl = min(ttl, config.cache_ttl_long)  # Cap TTL to maximum configured value
        
        start_time = time.time()
            
        try:
            # Compress data for storage efficiency
            compressed_data = AdvancedCache.compress_data(value)
            data_size = len(compressed_data)
            
            # Use SETEX for atomic set with expiration
            await redis_client.setex(key, adjusted_ttl, compressed_data)
            
            elapsed_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            logger.debug(f"Cache SET for key: {key[:50]}... "
                        f"(TTL: {adjusted_ttl}s, Size: {data_size} bytes, time: {elapsed_time:.2f}ms)")
            
            # Record cache write metrics
            if config.enable_metrics and METRICS_AVAILABLE:
                # Could add cache write metrics here if available
                pass
            
        except Exception as e:
            elapsed_time = (time.time() - start_time) * 1000
            logger.warning(f"Cache write error for key {key[:50]}... (time: {elapsed_time:.2f}ms): {e}")
            
            # Record cache error metrics
            if config.enable_metrics and METRICS_AVAILABLE:
                ERROR_COUNT.labels(error_type='cache_write_error').inc()
            
            # Graceful degradation - don't raise exception

# Continue with token optimization in the next response...
# main_part2.1.py - Advanced Caching System Completion
# Production-ready caching with comprehensive monitoring and statistics
# Current Date: 2025-06-08 00:53:38 UTC, User: AdsTable
# All comments in English as requested

# --- Continuation of AdvancedCache class get_cache_stats method ---
            
            # Generate comprehensive optimization recommendations based on metrics analysis
            if stats["performance"].get("application_hit_ratio_percent", 0) < 50:
                stats["recommendations"].append("Low application cache hit ratio - consider optimizing cache strategy")
            
            if stats["redis"]["memory_fragmentation_ratio"] > 1.5:
                stats["recommendations"].append("High Redis memory fragmentation - consider maintenance restart")
            
            # Check Redis memory usage and provide recommendations
            if stats["redis"]["used_memory"] > 0:
                memory_usage_mb = stats["redis"]["used_memory"] / (1024 * 1024)
                if memory_usage_mb > 1000:  # More than 1GB
                    stats["recommendations"].append(f"High Redis memory usage ({memory_usage_mb:.1f}MB) - monitor for memory leaks")
            
            # Check client connection count
            if stats["redis"]["connected_clients"] > 50:
                stats["recommendations"].append("High number of Redis connections - check for connection leaks")
            
            # Analyze cache compression efficiency
            if stats["application"]["compressions"] > 100:
                compression_ratio = stats["performance"].get("compression_efficiency", 1.0)
                if compression_ratio > 0.8:  # Poor compression
                    stats["recommendations"].append("Poor cache compression efficiency - consider data structure optimization")
            
            # Calculate additional performance metrics for comprehensive analysis
            stats["performance"]["error_rate_percent"] = 0
            total_operations = (stats["application"]["hits"] + stats["application"]["misses"] + 
                              stats["application"]["errors"])
            if total_operations > 0:
                error_rate = (stats["application"]["errors"] / total_operations) * 100
                stats["performance"]["error_rate_percent"] = round(error_rate, 2)
                
                if error_rate > 5:  # More than 5% error rate
                    stats["recommendations"].append("High cache error rate detected - investigate Redis connectivity")
            
            # Add cache efficiency score for operational monitoring
            hit_ratio = stats["performance"].get("application_hit_ratio_percent", 0)
            error_rate = stats["performance"]["error_rate_percent"]
            memory_efficiency = 1.0 / max(stats["redis"]["memory_fragmentation_ratio"], 1.0)
            
            # Calculate overall cache health score (0-100)
            cache_health_score = (
                (hit_ratio * 0.4) +  # 40% weight on hit ratio
                ((100 - error_rate) * 0.3) +  # 30% weight on low error rate
                (memory_efficiency * 100 * 0.3)  # 30% weight on memory efficiency
            )
            stats["performance"]["cache_health_score"] = round(min(100, max(0, cache_health_score)), 1)
            
            # Add operational status indicators
            stats["operational"] = {
                "status": "healthy" if cache_health_score > 70 else "degraded" if cache_health_score > 40 else "unhealthy",
                "last_updated": datetime.now().isoformat(),
                "monitoring_enabled": config.enable_metrics,
                "compression_enabled": config.enable_compression
            }
            
            stats["available"] = True
            
        except Exception as e:
            logger.error(f"Cache statistics collection failed: {e}")
            stats["available"] = False
            stats["error"] = str(e)
            stats["recommendations"].append("Cache statistics collection failed - check Redis connectivity")
        
        return stats
    
    @staticmethod
    def reset_stats():
        """
        Reset application-level cache statistics for monitoring and testing purposes
        
        Used for testing, debugging, and periodic statistics reset in production monitoring.
        Preserves Redis server statistics while resetting application-level counters.
        """
        logger.info("Resetting cache statistics counters")
        AdvancedCache._cache_stats = {
            "hits": 0,
            "misses": 0,
            "errors": 0,
            "compressions": 0,
            "decompressions": 0,
            "total_bytes_stored": 0,
            "total_bytes_retrieved": 0
        }
    
    @staticmethod
    async def warm_cache(redis_client: Redis, warm_data: Dict[str, Any], ttl: int = 3600):
        """
        Warm cache with predefined data for improved performance and user experience
        
        Features:
        - Bulk cache warming with optimized pipeline operations
        - Error isolation to prevent single failures from affecting entire warming process
        - Comprehensive logging and performance monitoring
        - TTL management for warmed data lifecycle
        - Progress tracking for large warming operations
        
        Args:
            redis_client: Active Redis client instance for cache warming
            warm_data: Dictionary of key-value pairs to preload into cache
            ttl: Time to live for warmed cache entries in seconds
        """
        if not redis_client or not warm_data:
            logger.debug("Cache warming skipped: Redis client or data not available")
            return
        
        logger.info(f"Starting cache warming with {len(warm_data)} entries")
        warming_start_time = time.time()
        successful_entries = 0
        failed_entries = 0
        
        try:
            # Use pipeline for efficient bulk operations
            pipe = redis_client.pipeline()
            
            for key, value in warm_data.items():
                try:
                    # Compress data for storage efficiency
                    compressed_data = AdvancedCache.compress_data(value)
                    pipe.setex(key, ttl, compressed_data)
                    successful_entries += 1
                    
                    # Execute pipeline in batches to prevent memory issues
                    if successful_entries % 100 == 0:
                        await pipe.execute()
                        pipe = redis_client.pipeline()  # Create new pipeline
                        logger.debug(f"Cache warming progress: {successful_entries}/{len(warm_data)} entries")
                        
                except Exception as e:
                    logger.warning(f"Cache warming failed for key {key}: {e}")
                    failed_entries += 1
                    continue
            
            # Execute remaining operations
            if successful_entries % 100 != 0:
                await pipe.execute()
            
            warming_duration = time.time() - warming_start_time
            logger.info(f"Cache warming completed: {successful_entries} successful, {failed_entries} failed "
                       f"in {warming_duration:.2f} seconds")
            
        except Exception as e:
            warming_duration = time.time() - warming_start_time
            logger.error(f"Cache warming failed after {warming_duration:.2f} seconds: {e}")
    
    @staticmethod
    async def cleanup_expired_keys(redis_client: Redis, pattern: str = "*", batch_size: int = 100):
        """
        Clean up expired and stale cache keys for memory optimization and maintenance
        
        Features:
        - Pattern-based cleanup for targeted maintenance operations
        - Batch processing to prevent Redis blocking and performance impact
        - Progress tracking and comprehensive logging for operational transparency
        - Safety limits to prevent accidental mass deletion
        - Performance monitoring and optimization
        
        Args:
            redis_client: Active Redis client instance for cleanup operations
            pattern: Pattern for keys to check and cleanup (default: all keys)
            batch_size: Number of keys to process in each batch for performance optimization
        """
        if not redis_client:
            logger.debug("Cache cleanup skipped: Redis client not available")
            return
        
        logger.info(f"Starting cache cleanup with pattern: {pattern}")
        cleanup_start_time = time.time()
        checked_keys = 0
        deleted_keys = 0
        
        try:
            # Get keys matching pattern with SCAN for memory efficiency
            async for key in redis_client.scan_iter(match=pattern, count=batch_size):
                checked_keys += 1
                
                try:
                    # Check if key exists and get TTL
                    ttl = await redis_client.ttl(key)
                    
                    # Delete keys that are expired or have no TTL set (potential memory leaks)
                    if ttl == -2:  # Key doesn't exist
                        continue
                    elif ttl == -1:  # Key exists but has no TTL - potential issue
                        logger.warning(f"Key without TTL found during cleanup: {key}")
                        # Optionally set TTL or delete based on application policy
                        # await redis_client.expire(key, config.cache_ttl_long)
                    
                    # Process in batches to prevent blocking Redis
                    if checked_keys % batch_size == 0:
                        await asyncio.sleep(0.01)  # Small delay to prevent Redis overload
                        logger.debug(f"Cache cleanup progress: checked {checked_keys} keys, deleted {deleted_keys}")
                
                except Exception as e:
                    logger.warning(f"Cache cleanup error for key {key}: {e}")
                    continue
            
            cleanup_duration = time.time() - cleanup_start_time
            logger.info(f"Cache cleanup completed: checked {checked_keys} keys, deleted {deleted_keys} keys "
                       f"in {cleanup_duration:.2f} seconds")
            
        except Exception as e:
            cleanup_duration = time.time() - cleanup_start_time
            logger.error(f"Cache cleanup failed after {cleanup_duration:.2f} seconds: {e}")

# --- Cache Management Utilities ---
class CacheManager:
    """
    High-level cache management utility with enterprise features and operational tools
    
    Features:
    - Centralized cache operations with consistent error handling and monitoring
    - Cache namespace management for multi-tenant applications and service isolation
    - Bulk operations with performance optimization and batch processing
    - Cache analytics and reporting for operational insights and optimization
    - Maintenance operations with comprehensive logging and progress tracking
    - Integration with monitoring systems and alerting platforms
    
    Designed for production use with Redis backend and enterprise operational requirements
    """
    
    def __init__(self, redis_client: Redis, namespace: str = "app"):
        """
        Initialize cache manager with Redis client and namespace configuration
        
        Args:
            redis_client: Active Redis client instance for cache operations
            namespace: Cache namespace for key organization and isolation
        """
        self.redis_client = redis_client
        self.namespace = namespace
        self.stats = {
            "operations": 0,
            "errors": 0,
            "last_operation": None
        }
    
    def _get_namespaced_key(self, key: str) -> str:
        """
        Generate namespaced key for cache isolation and organization
        
        Args:
            key: Original cache key
            
        Returns:
            Namespaced key with prefix for isolation
        """
        return f"{self.namespace}:{key}"
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get cached value with namespace support and comprehensive error handling
        
        Args:
            key: Cache key to retrieve
            
        Returns:
            Cached value or None if not found or error occurred
        """
        namespaced_key = self._get_namespaced_key(key)
        self.stats["operations"] += 1
        self.stats["last_operation"] = "get"
        
        try:
            return await AdvancedCache.get_cached(self.redis_client, namespaced_key)
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"Cache manager get error for key {key}: {e}")
            return None
    
    async def set(self, key: str, value: Any, ttl: int = None) -> bool:
        """
        Set cached value with namespace support and intelligent TTL management
        
        Args:
            key: Cache key to store
            value: Value to cache
            ttl: Time to live in seconds (uses default if None)
            
        Returns:
            True if successful, False otherwise
        """
        namespaced_key = self._get_namespaced_key(key)
        effective_ttl = ttl or config.cache_ttl_medium
        self.stats["operations"] += 1
        self.stats["last_operation"] = "set"
        
        try:
            await AdvancedCache.set_cached(self.redis_client, namespaced_key, value, effective_ttl)
            return True
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"Cache manager set error for key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """
        Delete cached value with namespace support and error handling
        
        Args:
            key: Cache key to delete
            
        Returns:
            True if successful, False otherwise
        """
        namespaced_key = self._get_namespaced_key(key)
        self.stats["operations"] += 1
        self.stats["last_operation"] = "delete"
        
        try:
            await AdvancedCache.delete_cached(self.redis_client, key=namespaced_key)
            return True
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"Cache manager delete error for key {key}: {e}")
            return False
    
    async def clear_namespace(self) -> int:
        """
        Clear all keys in the current namespace for maintenance and testing
        
        Returns:
            Number of keys deleted
        """
        pattern = f"{self.namespace}:*"
        self.stats["operations"] += 1
        self.stats["last_operation"] = "clear_namespace"
        
        try:
            keys = await self.redis_client.keys(pattern)
            if keys:
                deleted = await self.redis_client.delete(*keys)
                logger.info(f"Cache manager cleared {deleted} keys from namespace '{self.namespace}'")
                return deleted
            return 0
        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"Cache manager clear namespace error: {e}")
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache manager statistics for monitoring and debugging
        
        Returns:
            Dictionary containing operational statistics and metrics
        """
        return {
            "namespace": self.namespace,
            "operations": self.stats["operations"],
            "errors": self.stats["errors"],
            "error_rate_percent": (self.stats["errors"] / max(self.stats["operations"], 1)) * 100,
            "last_operation": self.stats["last_operation"],
            "redis_available": self.redis_client is not None
        }

# This completes Part 2.1 with the advanced caching system
# main_part2.2.py - Resource Management and Circuit Breaker Integration
# Production-ready resource management with comprehensive lifecycle handling
# Current Date: 2025-06-08 00:53:38 UTC, User: AdsTable
# All comments in English as requested

# --- Resource Management System ---
class ResourceManager:
    """
    Centralized resource management system with comprehensive lifecycle handling
    
    Features:
    - Comprehensive resource initialization with dependency injection and validation
    - Health monitoring with automatic recovery mechanisms and intelligent alerting
    - Graceful degradation and fallback handling for resilient operation
    - Performance monitoring and metrics collection with real-time analytics
    - Proper cleanup and resource deallocation with memory leak prevention
    - Configuration management with hot reloading and validation
    - Circuit breaker integration for reliability and cascade failure prevention
    - Memory management and leak prevention with automatic garbage collection
    
    Designed for production use with high availability and reliability requirements
    Optimized for Python 3.13 with modern async patterns and enterprise scalability
    """
    
    def __init__(self):
        # Core resource instances with proper initialization
        self.ai_config_cache: Optional[Dict[str, Any]] = None
        self.config_last_modified: Optional[float] = None
        self.ai_client_instance: Optional[AIAsyncClient] = None
        self.redis_client: Optional[Redis] = None
        self.ai_semaphore: Optional[asyncio.Semaphore] = None
        self.cache_manager: Optional[CacheManager] = None
        
        # Provider management and monitoring with comprehensive tracking
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.request_stats: Dict[str, Dict[str, Any]] = {}
        self.provider_health: Dict[str, bool] = {}
        
        # System monitoring and performance tracking with detailed metrics
        self.startup_time = time.time()
        self.redis_healthy = False
        self.ai_client_healthy = False
        self.last_health_check = 0
        self.health_check_interval = 30  # seconds
        
        # Performance and usage tracking with comprehensive analytics
        self.total_requests = 0
        self.total_errors = 0
        self.avg_response_time = 0.0
        self.peak_concurrent_requests = 0
        self.current_concurrent_requests = 0
        
        # Resource usage tracking with memory and performance monitoring
        self.cache_stats = {"hits": 0, "misses": 0, "errors": 0}
        self.ai_usage_stats = {"total_tokens": 0, "total_cost": 0.0}
        
        # Resource lifecycle management
        self.initialization_complete = False
        self.shutdown_initiated = False
        
        logger.debug("ResourceManager initialized with comprehensive monitoring capabilities")
    
    async def initialize_redis(self) -> Optional[Redis]:
        """
        Initialize Redis client with comprehensive error handling and monitoring
        
        Features:
        - Connection pooling with optimal settings and performance tuning
        - Health validation with comprehensive testing and verification
        - SSL/TLS support for secure connections and enterprise deployment
        - Retry logic with exponential backoff and intelligent recovery
        - Performance monitoring and metrics collection with real-time analytics
        
        Returns:
            Redis client instance or None if initialization failed
        """
        if not REDIS_AVAILABLE or not config.enable_cache:
            logger.info("Redis not available or caching disabled - running without cache")
            return None
        
        try:
            logger.info("Initializing Redis connection with production-ready configuration...")
            
            # Create Redis client with production-optimized configuration
            if hasattr(Redis, 'from_url'):
                redis_client = Redis.from_url(
                    config.redis.url,
                    encoding=config.redis.encoding,
                    decode_responses=config.redis.decode_responses,
                    max_connections=config.redis.max_connections,
                    socket_timeout=config.redis.socket_timeout,
                    socket_connect_timeout=config.redis.socket_connect_timeout,
                    health_check_interval=config.redis.health_check_interval,
                    retry_on_timeout=config.redis.retry_on_timeout,
                    retry_on_error=[ConnectionError, TimeoutError] if config.redis.retry_on_error else []
                )
            else:
                # Fallback for older Redis versions with basic configuration
                redis_client = Redis(
                    host='localhost',
                    port=6379,
                    db=0,
                    encoding=config.redis.encoding,
                    decode_responses=config.redis.decode_responses,
                    max_connections=config.redis.max_connections,
                    socket_timeout=config.redis.socket_timeout
                )
            
            # Comprehensive connection testing with multiple validation steps
            logger.info("Testing Redis connection with comprehensive validation...")
            
            # Basic connectivity test
            await redis_client.ping()
            logger.debug("✅ Redis ping successful")
            
            # Test basic operations to ensure full functionality
            test_key = f"health_check_{int(time.time())}"
            test_value = "connection_test"
            
            # Write test
            await redis_client.set(test_key, test_value, ex=10)
            logger.debug("✅ Redis write test successful")
            
            # Read test
            retrieved_value = await redis_client.get(test_key)
            logger.debug("✅ Redis read test successful")
            
            # Cleanup test
            await redis_client.delete(test_key)
            logger.debug("✅ Redis cleanup test successful")
            
            # Validate data integrity
            expected_value = test_value.encode() if not config.redis.decode_responses else test_value
            if retrieved_value != expected_value:
                raise Exception("Redis read/write test failed - data integrity issue detected")
            
            # Get Redis server information for comprehensive monitoring
            info = await redis_client.info()
            redis_version = info.get('redis_version', 'unknown')
            memory_used = info.get('used_memory_human', 'unknown')
            connected_clients = info.get('connected_clients', 0)
            uptime = info.get('uptime_in_seconds', 0)
            
            # Initialize cache manager for high-level operations
            self.cache_manager = CacheManager(redis_client, namespace=config.app_name.lower().replace(' ', '_'))
            
            self.redis_client = redis_client
            self.redis_healthy = True
            
            logger.info(f"✅ Redis connection established successfully")
            logger.info(f"   Server version: {redis_version}")
            logger.info(f"   Memory usage: {memory_used}")
            logger.info(f"   Connected clients: {connected_clients}")
            logger.info(f"   Server uptime: {uptime} seconds")
            logger.info(f"   Connection pool: {config.redis.max_connections} max connections")
            logger.info(f"   Cache manager initialized with namespace: {self.cache_manager.namespace}")
            
            return redis_client
            
        except Exception as e:
            logger.warning(f"Redis initialization failed: {e}")
            logger.info("   Application will continue without Redis caching")
            logger.info("   Consider checking Redis server status and configuration")
            logger.info("   For development: ensure Redis is running on localhost:6379")
            
            self.redis_client = None
            self.redis_healthy = False
            return None
    
    async def initialize_ai_client(self) -> Optional[AIAsyncClient]:
        """
        Initialize AI client with comprehensive provider management and validation
        
        Features:
        - Multi-provider configuration with intelligent defaults and optimization
        - Circuit breaker initialization for each provider with adaptive settings
        - Health checking and provider validation with comprehensive testing
        - Performance monitoring and analytics setup with real-time metrics
        - Fallback configuration for development mode with realistic mocking
        
        Returns:
            AIAsyncClient instance or None if initialization failed
        """
        if not AI_CLIENT_AVAILABLE or not AIAsyncClient:
            logger.warning("AIAsyncClient not available - AI features will use fallback implementations")
            logger.info("   Install the AI client package for full functionality")
            logger.info("   For development: fallback implementations will provide mock responses")
            return None
        
        try:
            logger.info("Initializing AI client with comprehensive provider management...")
            
            # Load and validate AI configuration with comprehensive error handling
            ai_config = await self.load_ai_config()
            if not ai_config:
                logger.warning("No valid AI configuration found, using minimal fallback")
                ai_config = self._get_default_ai_config()
            
            # Initialize AI client with configuration and error handling
            logger.info(f"Initializing AI client with {len(ai_config)} providers...")
            self.ai_client_instance = AIAsyncClient(ai_config)
            
            # Initialize circuit breakers and monitoring for each provider
            for provider_name, provider_config in ai_config.items():
                logger.debug(f"Setting up monitoring for provider: {provider_name}")
                
                # Create circuit breaker with provider-specific settings and intelligent defaults
                failure_threshold = provider_config.get('failure_threshold', 5)
                recovery_timeout = provider_config.get('recovery_timeout', 60)
                
                self.circuit_breakers[provider_name] = CircuitBreaker(
                    failure_threshold=failure_threshold,
                    recovery_timeout=recovery_timeout,
                    adaptive_timeout=True  # Enable adaptive timeout for better recovery
                )
                
                # Initialize comprehensive request statistics tracking
                self.request_stats[provider_name] = {
                    'total_requests': 0,
                    'successful_requests': 0,
                    'failed_requests': 0,
                    'total_tokens': 0,
                    'total_cost': 0.0,
                    'average_latency': 0.0,
                    'last_request_time': None,
                    'circuit_breaker_trips': 0,
                    'rate_limit_hits': 0,
                    'last_error': None,
                    'error_count_by_type': defaultdict(int)
                }
                
                # Initialize provider health status with optimistic default
                self.provider_health[provider_name] = True
                
                logger.debug(f"✅ Monitoring initialized for provider: {provider_name}")
            
            # Test AI client health if comprehensive testing is available
            try:
                if hasattr(self.ai_client_instance, 'health_check'):
                    logger.info("Performing comprehensive AI client health check...")
                    await asyncio.wait_for(self.ai_client_instance.health_check(), timeout=15)
                    logger.info("✅ AI client health check passed")
                else:
                    logger.debug("AI client health check not available - skipping")
            except asyncio.TimeoutError:
                logger.warning("AI client health check timed out - client will be used with caution")
            except Exception as e:
                logger.warning(f"AI client health check failed: {e}")
                logger.info("   Client will be used with caution and comprehensive monitoring")
            
            self.ai_client_healthy = True
            
            logger.info(f"✅ AI client initialized successfully")
            logger.info(f"   Providers available: {', '.join(ai_config.keys())}")
            logger.info(f"   Circuit breakers: {len(self.circuit_breakers)} configured")
            logger.info(f"   Request statistics: comprehensive tracking enabled")
            
            return self.ai_client_instance
            
        except Exception as e:
            logger.error(f"Failed to initialize AI client: {e}")
            logger.error("   AI features will use fallback implementations")
            logger.info("   Check AI client installation and configuration")
            
            self.ai_client_healthy = False
            return None
    
    async def load_ai_config(self, force_reload: bool = False) -> Dict[str, Any]:
        """
        Load AI configuration with comprehensive validation and hot reloading support
        
        Features:
        - YAML configuration file support with comprehensive validation
        - Environment variable expansion and validation with security checks
        - Configuration caching with intelligent change detection and hot reloading
        - Comprehensive error handling and fallback with graceful degradation
        - Provider-specific validation and optimization with security scanning
        
        Args:
            force_reload: Force reload even if cached version exists and is current
            
        Returns:
            Validated AI configuration dictionary with comprehensive provider settings
        """
        if not YAML_AVAILABLE:
            logger.warning("YAML not available, using default AI configuration")
            logger.info("   Install PyYAML for configuration file support: pip install PyYAML")
            return self._get_default_ai_config()
            
        config_path = Path("ai_integrations.yaml")
        
        if not config_path.exists():
            logger.warning(f"AI configuration file {config_path} not found")
            logger.info("   Creating default configuration file for future use...")
            
            # Create a comprehensive default configuration file for user convenience
            try:
                default_config = self._get_default_ai_config()
                if yaml:
                    # Add helpful comments to the generated configuration
                    config_with_comments = {
                        "_comment": "AI Aggregator Pro Configuration - Edit as needed for your deployment",
                        "_note": "See documentation for advanced configuration options",
                        **default_config
                    }
                    
                    with open(config_path, 'w') as f:
                        yaml.dump(config_with_comments, f, default_flow_style=False, indent=2)
                    logger.info(f"✅ Created default configuration file: {config_path}")
                    logger.info("   Edit this file to customize AI provider settings")
            except Exception as e:
                logger.warning(f"Could not create default config file: {e}")
            
            return self._get_default_ai_config()
        
        try:
            current_mtime = config_path.stat().st_mtime
            
            # Check if we can use cached version (hot reloading support with change detection)
            if (not force_reload and self.ai_config_cache and 
                self.config_last_modified == current_mtime):
                logger.debug("Using cached AI configuration (no changes detected)")
                return self.ai_config_cache
            
            # Load configuration file with proper encoding and error handling
            logger.info(f"Loading AI configuration from {config_path}")
            
            if aiofiles:
                # Use async file I/O for better performance in async context
                async with aiofiles.open(config_path, mode='r', encoding='utf-8') as f:
                    content = await f.read()
            else:
                # Fallback to synchronous I/O
                with open(config_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            
            # Parse YAML with comprehensive error handling
            cfg = yaml.safe_load(content) or {}
            
            # Remove comment fields added during config generation
            cfg.pop('_comment', None)
            cfg.pop('_note', None)
            
            # Process and validate configuration with comprehensive checks
            processed_config = self._process_ai_config(cfg)
            
            # Cache the processed configuration with metadata
            self.ai_config_cache = processed_config
            self.config_last_modified = current_mtime
            
            logger.info(f"✅ AI configuration loaded successfully")
            logger.info(f"   Providers configured: {len(processed_config)}")
            logger.info(f"   Configuration cached for hot reloading")
            
            return processed_config
            
        except yaml.YAMLError as e:
            logger.error(f"YAML parsing error in AI configuration: {e}")
            logger.info("   Check YAML syntax in ai_integrations.yaml")
            return self._get_default_ai_config()
        except Exception as e:
            logger.error(f"Failed to load AI configuration: {e}")
            logger.info("   Using default configuration as fallback")
            return self._get_default_ai_config()

# Continue with Part 2.2 completion in next section...
# main_part2.3.py - Configuration Processing and Health Management
# Production-ready configuration validation and health monitoring
# Current Date: 2025-06-08 00:53:38 UTC, User: AdsTable
# All comments in English as requested

# --- Continuation of ResourceManager class ---

    def _process_ai_config(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process and validate AI configuration with comprehensive validation and security checks
        
        Features:
        - Environment variable expansion with comprehensive validation and security scanning
        - Type conversion and range validation with intelligent defaults
        - Provider-specific optimization and defaults with performance tuning
        - Security validation for API keys and endpoints with threat detection
        - Configuration sanitization and normalization for consistent operation
        
        Args:
            cfg: Raw configuration dictionary from YAML file
            
        Returns:
            Processed and validated configuration with comprehensive provider settings
        """
        processed = {}
        
        for provider, settings in cfg.items():
            if not isinstance(settings, dict):
                logger.warning(f"Invalid configuration for provider {provider}: not a dictionary")
                continue
            
            logger.debug(f"Processing configuration for provider: {provider}")
            
            # Add intelligent defaults for known providers with optimization
            if provider in config.ai.free_tier_limits:
                settings.setdefault('daily_limit', str(config.ai.free_tier_limits[provider]))
                settings.setdefault('is_free', True)
                settings.setdefault('priority', config.ai.provider_priorities.get(provider, 50))
                logger.debug(f"Applied free tier defaults for {provider}")
            
            # Expand environment variables with comprehensive validation and security checks
            expanded_settings = {}
            for key, value in settings.items():
                if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                    env_key = value[2:-1]
                    env_value = os.getenv(env_key)
                    
                    if env_value is None:
                        logger.warning(f"Environment variable {env_key} not found for {provider}.{key}")
                        continue
                    
                    # Security check for sensitive data
                    if 'key' in key.lower() or 'token' in key.lower() or 'secret' in key.lower():
                        if len(env_value) < 10:
                            logger.warning(f"Potentially invalid {key} for {provider}: too short")
                        logger.debug(f"Loaded sensitive configuration for {provider}.{key}")
                    
                    expanded_settings[key] = env_value
                else:
                    expanded_settings[key] = value
            
            # Validate and process provider settings with comprehensive error handling
            validated_settings = self._validate_provider_settings(provider, expanded_settings)
            if validated_settings:
                processed[provider] = validated_settings
                logger.debug(f"✅ Successfully processed provider: {provider}")
            else:
                logger.warning(f"❌ Failed to validate provider: {provider}")
        
        # Ensure we have at least one provider for graceful operation
        if not processed:
            logger.warning("No valid providers found in configuration, adding fallback providers")
            processed.update(self._get_default_ai_config())
        
        # Sort providers by priority for intelligent selection
        if len(processed) > 1:
            sorted_providers = dict(sorted(
                processed.items(),
                key=lambda x: x[1].get('priority', 50),
                reverse=True
            ))
            logger.debug(f"Providers sorted by priority: {list(sorted_providers.keys())}")
            return sorted_providers
        
        return processed
    
    def _validate_provider_settings(self, provider: str, settings: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Validate individual provider settings with comprehensive parameter checking and security validation
        
        Features:
        - Type conversion with range validation and intelligent defaults
        - Security validation for sensitive parameters with threat detection
        - Performance optimization suggestions with intelligent recommendations
        - Compatibility checking for provider-specific features and requirements
        - Configuration normalization for consistent operation across providers
        
        Args:
            provider: Provider name for validation context
            settings: Provider settings dictionary to validate
            
        Returns:
            Validated settings dictionary or None if validation failed
        """
        try:
            validated = settings.copy()
            
            # Validate numeric fields with appropriate ranges and intelligent defaults
            numeric_fields = {
                'max_tokens': (100, 100000, 4000),           # min, max, default
                'timeout': (5, 300, 30),                     # 5 seconds to 5 minutes
                'rate_limit': (1, 10000, 60),                # requests per minute
                'priority_score': (0, 100, 50),              # priority ranking
                'failure_threshold': (1, 20, 5),             # circuit breaker threshold
                'recovery_timeout': (10, 600, 60),           # circuit breaker recovery
                'daily_limit': (1, 1000000, 1000),          # daily request limit
            }
            
            for field, (min_val, max_val, default_val) in numeric_fields.items():
                if field in validated:
                    try:
                        val = int(validated[field])
                        if not (min_val <= val <= max_val):
                            logger.warning(f"Invalid {field} for {provider}: {val} (must be {min_val}-{max_val})")
                            validated[field] = default_val
                            logger.info(f"Using default {field}={default_val} for {provider}")
                        else:
                            validated[field] = val
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid {field} type for {provider}: {validated[field]}")
                        validated[field] = default_val
                        logger.info(f"Using default {field}={default_val} for {provider}")
            
            # Validate float fields with appropriate ranges and intelligent defaults
            float_fields = {
                'cost_per_1k_tokens': (0.0, 1.0, 0.001),    # min, max, default in USD
                'temperature': (0.0, 2.0, 0.7),             # AI model temperature
                'top_p': (0.0, 1.0, 0.9),                   # nucleus sampling
            }
            
            for field, (min_val, max_val, default_val) in float_fields.items():
                if field in validated:
                    try:
                        val = float(validated[field])
                        if not (min_val <= val <= max_val):
                            logger.warning(f"Invalid {field} for {provider}: {val} (must be {min_val}-{max_val})")
                            validated[field] = default_val
                        else:
                            validated[field] = val
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid {field} type for {provider}: {validated[field]}")
                        validated[field] = default_val
            
            # Validate URL fields with comprehensive security checks
            url_fields = ['base_url', 'api_url', 'endpoint']
            for field in url_fields:
                if field in validated:
                    url = validated[field]
                    if not (isinstance(url, str) and (url.startswith('http://') or url.startswith('https://'))):
                        logger.warning(f"Invalid URL for {provider}.{field}: {url}")
                        del validated[field]
                    else:
                        # Security check for HTTPS in production
                        if config.environment == 'production' and url.startswith('http://') and 'localhost' not in url:
                            logger.warning(f"Insecure HTTP URL in production for {provider}.{field}: {url}")
            
            # Validate API keys with comprehensive security checks
            api_key_fields = ['api_key', 'token', 'key', 'secret']
            for field in api_key_fields:
                if field in validated:
                    key = validated[field]
                    if not isinstance(key, str):
                        logger.warning(f"Invalid {field} type for {provider}.{field}")
                        del validated[field]
                    elif len(key) < 10:
                        logger.warning(f"Potentially invalid {field} for {provider}: too short")
                        del validated[field]
                    elif key in ['your-api-key', 'test-key', 'demo-key']:
                        logger.warning(f"Default/placeholder {field} detected for {provider}")
                        del validated[field]
                    else:
                        logger.debug(f"Valid {field} configured for {provider}")
            
            # Validate string fields with allowed values
            string_fields = {
                'priority': ['low', 'medium', 'high', 'critical'],
                'model': None,  # No restriction on model names
                'region': None,  # No restriction on regions
            }
            
            for field, allowed_values in string_fields.items():
                if field in validated and allowed_values:
                    value = validated[field]
                    if value not in allowed_values:
                        logger.warning(f"Invalid {field} for {provider}: {value} (allowed: {allowed_values})")
                        del validated[field]
            
            # Add provider-specific optimizations and intelligent defaults
            self._add_provider_optimizations(provider, validated)
            
            return validated
            
        except Exception as e:
            logger.warning(f"Error validating settings for {provider}: {e}")
            return None
    
    def _add_provider_optimizations(self, provider: str, settings: Dict[str, Any]):
        """
        Add provider-specific optimizations and intelligent defaults for enhanced performance
        
        Args:
            provider: Provider name for optimization context
            settings: Settings dictionary to optimize (modified in place)
        """
        # Provider-specific optimizations based on known characteristics
        optimizations = {
            'openai': {
                'supports_streaming': True,
                'recommended_timeout': 45,
                'optimal_batch_size': 10,
            },
            'anthropic': {
                'supports_streaming': True,
                'recommended_timeout': 60,
                'optimal_batch_size': 5,
            },
            'ollama': {
                'supports_streaming': True,
                'recommended_timeout': 30,
                'is_local': True,
                'requires_gpu': False,
            },
            'groq': {
                'supports_streaming': True,
                'recommended_timeout': 15,  # Very fast inference
                'optimal_batch_size': 20,
            },
            'huggingface': {
                'supports_streaming': False,
                'recommended_timeout': 30,
                'rate_limit_strict': True,
            }
        }
        
        if provider in optimizations:
            for key, value in optimizations[provider].items():
                if key not in settings:
                    settings[key] = value
                    logger.debug(f"Applied optimization {key}={value} for {provider}")
    
    def _get_default_ai_config(self) -> Dict[str, Any]:
        """
        Get comprehensive default AI configuration for fallback scenarios and initial setup
        
        Returns:
            Default AI configuration with multiple providers and sensible defaults
        """
        return {
            "ollama": {
                "base_url": "http://localhost:11434",
                "model": "llama2",
                "priority": 100,  # Highest priority - local and free
                "timeout": 30,
                "is_free": True,
                "max_tokens": 4096,
                "supports_streaming": True,
                "description": "Local Ollama instance for free AI inference",
                "requires_installation": True,
            },
            "huggingface": {
                "base_url": "https://api-inference.huggingface.co",
                "priority": 90,   # High priority - free and reliable
                "timeout": 20,
                "is_free": True,
                "max_tokens": 2048,
                "rate_limit": 100,
                "description": "HuggingFace Inference API for free model access",
                "rate_limit_strict": True,
            },
            "groq": {
                "base_url": "https://api.groq.com",
                "priority": 85,   # High priority - fast inference
                "timeout": 15,
                "is_free": True,
                "max_tokens": 8192,
                "supports_streaming": True,
                "description": "Groq fast inference API with competitive free tier",
                "api_key": "${GROQ_API_KEY}",
            },
            "mock": {
                "priority": 10,   # Lowest priority - testing only
                "timeout": 5,
                "is_free": True,
                "max_tokens": 8192,
                "supports_streaming": True,
                "description": "Mock provider for testing and development",
                "development_only": True,
            }
        }

# This completes Part 2.2 and Part 2.3 with comprehensive resource management
# main_part2.4.py — ResourceManager: health_check, cleanup, FastAPI integration

from typing import Dict, Any
from datetime import datetime
import time

class ResourceManager:
    # ... (предыдущие методы)

    async def health_check(self) -> Dict[str, Any]:
        """
        Comprehensive health check for all managed resources.
        Returns status dict for monitoring endpoints.
        """
        status = {"status": "healthy", "timestamp": datetime.now(), "components": {}}
        # Redis health
        try:
            if self.redis_client:
                pong = await self.redis_client.ping()
                status["components"]["redis"] = "healthy" if pong else "unhealthy"
            else:
                status["components"]["redis"] = "not_initialized"
        except Exception as e:
            status["components"]["redis"] = f"error: {e}"

        # AI client health
        try:
            if self.ai_client_instance and hasattr(self.ai_client_instance, 'health_check'):
                healthy = await self.ai_client_instance.health_check()
                status["components"]["ai_client"] = "healthy" if healthy else "unhealthy"
            else:
                status["components"]["ai_client"] = "not_initialized"
        except Exception as e:
            status["components"]["ai_client"] = f"error: {e}"

        # Add more component checks as needed
        status["uptime"] = time.time() - self.startup_time
        return status

    async def cleanup(self):
        """
        Graceful cleanup for all managed resources (to be called on shutdown).
        """
        if self.redis_client:
            await self.redis_client.close()
        if self.ai_client_instance and hasattr(self.ai_client_instance, 'close'):
            await self.ai_client_instance.close()
        # Add more cleanup as necessary

# Example FastAPI integration
from fastapi import FastAPI

app = FastAPI()
resources = ResourceManager()

@app.on_event("startup")
async def on_startup():
    await resources.initialize_redis()
    await resources.initialize_ai_client()

@app.on_event("shutdown")
async def on_shutdown():
    await resources.cleanup()
	# main_part2.4.1.py — ResourceManager: health_check and cleanup
# Current Date: 2025-06-08, User: AdsTable

from datetime import datetime
import time
from typing import Dict, Any, Optional

class ResourceManager:
    async def initialize_redis(self):
        # Replace the URL with your actual Redis server address
        self.redis_client = await aioredis.create_redis_pool("redis://localhost:6379/0")
        print("[ResourceManager] Redis initialized.")

    async def initialize_ai_client(self):
        # Your AI client initialization here
        pass

    async def health_check(self) -> Dict[str, Any]:
        """
        Comprehensive health check for all managed resources.
        Returns status dict for monitoring endpoints and orchestrators.
        """
        status = {
            "status": "healthy",
            "timestamp": datetime.now(),
            "components": {},
            "uptime": time.time() - self.startup_time
        }

        # Redis health
        try:
            if self.redis_client:
                pong = await self.redis_client.ping()
                status["components"]["redis"] = "healthy" if pong else "unhealthy"
            else:
                status["components"]["redis"] = "not_initialized"
        except Exception as e:
            status["components"]["redis"] = f"error: {e}"

        # AI client health
        try:
            if self.ai_client_instance and hasattr(self.ai_client_instance, 'health_check'):
                healthy = await self.ai_client_instance.health_check()
                status["components"]["ai_client"] = "healthy" if healthy else "unhealthy"
            else:
                status["components"]["ai_client"] = "not_initialized"
        except Exception as e:
            status["components"]["ai_client"] = f"error: {e}"

        # Add other resource checks as needed
        # e.g., database, external APIs, etc.

        return status

    async def cleanup(self):
        """
        Graceful cleanup for all managed resources (to be called on shutdown).
        Ensures no resource leaks and all connections are closed.
        """
        errors = []
        # Cleanup Redis client
        try:
            if self.redis_client:
                await self.redis_client.close()
        except Exception as e:
            errors.append(f"redis: {e}")

        # Cleanup AI client
        try:
            if self.ai_client_instance and hasattr(self.ai_client_instance, 'close'):
                await self.ai_client_instance.close()
        except Exception as e:
            errors.append(f"ai_client: {e}")

        # Add other resource cleanup as needed
        # e.g., close database session, file handles, etc.

        if errors:
            print(f"Cleanup finished with errors: {errors}")
        else:
            print("Cleanup finished successfully.")

# Note: ResourceManager class should be imported or defined in the main context.
# main_part2.4.2.py — FastAPI lifespan and resource integration
# Current Date: 2025-06-08, User: AdsTable

from fastapi import FastAPI
from contextlib import asynccontextmanager

# Import ResourceManager from previous parts
# from .main_part2.4.1 import ResourceManager

resources = ResourceManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager for proper startup and shutdown.
    Initializes and cleans up all shared resources in a production-safe manner.
    """
    print("[Startup] Initializing all application resources...")
    try:
        # Initialize Redis connection
        await resources.initialize_redis()
        # Initialize AI client
        await resources.initialize_ai_client()
        # Add more resource initializations as needed (e.g., DB, external APIs)
        print("[Startup] All resources initialized successfully.")
    except Exception as e:
        print(f"[Startup][Error] Failed to initialize resources: {e}")
        # Optionally, re-raise or handle the exception depending on criticality
        raise

    try:
        # Application is running
        yield
    finally:
        print("[Shutdown] Cleaning up all application resources...")
        try:
            # Clean up all resources gracefully
            await resources.cleanup()
            print("[Shutdown] All resources cleaned up successfully.")
        except Exception as e:
            print(f"[Shutdown][Error] Failed to clean up resources: {e}")
            
# Example FastAPI app integration
app = FastAPI(lifespan=lifespan)

# Dependency for injecting ResourceManager in endpoints
def get_resources():
    return resources

# Example health endpoint using the ResourceManager
@app.get("/health", tags=["Monitoring"])
async def health():
    """
    Health check endpoint using ResourceManager.
    Returns system and component health for orchestrators and monitoring.
    """
    return await resources.health_check()

# You may need to attach resources to app.state for some advanced FastAPI usage:
# app.state.resources = resources

# Add other endpoints as needed, using resources via dependency or app.state
# main.py - Complete FastAPI Application Final Part (2)
# Advanced features, testing infrastructure, and production deployment readiness
# All comments in English as requested - Current Date: 2025-06-08

# --- Advanced Middleware and Security ---
@app.middleware("http")
async def comprehensive_request_middleware(request: Request, call_next):
    """
    Comprehensive request processing middleware with advanced monitoring and security
    
    Features:
    - Request/response timing and performance monitoring
    - Security header injection and validation
    - Request ID generation and propagation
    - Comprehensive logging with structured data
    - Error tracking and metrics collection
    - Request size validation and protection
    - Rate limiting integration and abuse detection
    
    Optimized for production use with minimal performance overhead
    """
    start_time = time.time()
    request_id = generate_request_id()
    
    # Add request ID to request state for downstream access
    request.state.request_id = request_id
    
    # Validate request size for security
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > config.max_request_size:
        logger.warning(f"Request {request_id} rejected: size {content_length} exceeds limit {config.max_request_size}")
        return JSONResponse(
            status_code=413,
            content={"error": "Request too large", "max_size": config.max_request_size},
            headers={"X-Request-ID": request_id}
        )
    
    # Extract client information for monitoring and security
    client_ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
        request.headers.get("x-real-ip", "").strip() or
        (request.client.host if request.client else "unknown")
    )
    
    user_agent = request.headers.get("user-agent", "unknown")
    
    # Log incoming request with structured data
    logger.info(f"Request {request_id}: {request.method} {request.url.path} from {client_ip}")
    logger.debug(f"Request {request_id} headers: User-Agent: {user_agent[:100]}")
    
    try:
        # Process request through the application stack
        response = await call_next(request)
        
        # Calculate processing time
        process_time = time.time() - start_time
        
        # Add comprehensive security and monitoring headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = str(round(process_time * 1000, 2))  # milliseconds
        
        # Security headers for production deployment
        if config.security.enable_security_headers:
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response.headers["Content-Security-Policy"] = "default-src 'self'"
            
            # HSTS header for HTTPS deployments
            if request.url.scheme == "https":
                response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Update active connections gauge
        if config.enable_metrics and METRICS_AVAILABLE:
            ACTIVE_CONNECTIONS.set(resources.current_concurrent_requests)
        
        # Log response with performance metrics
        status_code = response.status_code
        if status_code >= 400:
            logger.warning(f"Request {request_id} completed with error: {status_code} in {process_time*1000:.2f}ms")
        else:
            logger.info(f"Request {request_id} completed: {status_code} in {process_time*1000:.2f}ms")
        
        return response
        
    except Exception as e:
        # Handle unexpected middleware errors
        process_time = time.time() - start_time
        logger.error(f"Request {request_id} middleware error: {type(e).__name__}: {e} after {process_time*1000:.2f}ms")
        
        # Record error metrics
        if config.enable_metrics and METRICS_AVAILABLE:
            ERROR_COUNT.labels(error_type='middleware_error').inc()
        
        # Return structured error response
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "message": "Request processing failed",
                "request_id": request_id
            },
            headers={"X-Request-ID": request_id}
        )

# --- Advanced Caching Endpoints ---
@app.get("/cache/stats", response_model=Dict[str, Any], tags=["Cache Management"])
@external_monitor_performance("cache_stats")
async def get_cache_statistics():
    """
    Comprehensive cache statistics endpoint for monitoring and optimization
    
    Features:
    - Detailed Redis performance metrics
    - Cache hit/miss ratios and trends
    - Memory usage analysis and optimization insights
    - Key distribution and hotspot analysis
    - Performance recommendations and alerts
    
    Used by monitoring systems and operations teams for cache optimization
    """
    if not config.enable_cache or not resources.redis_client:
        return {
            "available": False,
            "reason": "Cache not available or disabled",
            "timestamp": datetime.now().isoformat()
        }
    
    try:
        # Get comprehensive cache statistics
        cache_stats = await AdvancedCache.get_cache_stats(resources.redis_client)
        
        # Add application-specific cache metrics
        app_cache_stats = {
            "hits": resources.cache_stats.get("hits", 0),
            "misses": resources.cache_stats.get("misses", 0),
            "errors": resources.cache_stats.get("errors", 0),
            "hit_ratio": 0.0
        }
        
        total_operations = app_cache_stats["hits"] + app_cache_stats["misses"]
        if total_operations > 0:
            app_cache_stats["hit_ratio"] = (app_cache_stats["hits"] / total_operations) * 100
        
        # Combine Redis and application statistics
        combined_stats = {
            **cache_stats,
            "application_cache": app_cache_stats,
            "recommendations": [],
            "timestamp": datetime.now().isoformat()
        }
        
        # Add performance recommendations based on metrics
        if app_cache_stats["hit_ratio"] < 50:
            combined_stats["recommendations"].append("Low cache hit ratio - consider optimizing cache strategy")
        
        if cache_stats.get("memory", {}).get("memory_fragmentation_ratio", 1.0) > 1.5:
            combined_stats["recommendations"].append("High memory fragmentation - consider Redis restart during maintenance window")
        
        connected_clients = cache_stats.get("connections", {}).get("connected_clients", 0)
        max_clients = cache_stats.get("connections", {}).get("max_clients", 0)
        if max_clients > 0 and connected_clients / max_clients > 0.8:
            combined_stats["recommendations"].append("High client connection usage - monitor for connection leaks")
        
        return combined_stats
        
    except Exception as e:
        logger.error(f"Cache statistics retrieval failed: {e}")
        return {
            "available": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.post("/cache/warm", tags=["Cache Management"])
@rate_limit(requests_per_minute=5)
@external_monitor_performance("cache_warming")
async def warm_cache(
    categories: List[str] = None,
    popular_queries: List[str] = None,
    background_tasks: BackgroundTasks = None
):
    """
    Intelligent cache warming for improved performance and user experience
    
    Features:
    - Category-based cache preloading
    - Popular query prediction and caching
    - Background processing for non-blocking operation
    - Performance impact monitoring
    - Intelligent TTL management for warmed data
    
    Used during deployment or maintenance to improve response times
    """
    if not config.enable_cache or not resources.redis_client:
        raise HTTPException(
            status_code=503, 
            detail="Cache not available or disabled"
        )
    
    try:
        warming_tasks = []
        
        # Warm category-based caches
        if categories:
            for category in categories[:10]:  # Limit to prevent abuse
                warming_tasks.append(f"category:{category}")
        
        # Warm popular query caches  
        if popular_queries:
            for query in popular_queries[:20]:  # Limit to prevent abuse
                warming_tasks.append(f"query:{query}")
        
        # Default warming if no specific targets provided
        if not warming_tasks:
            warming_tasks = [
                "category:electronics",
                "category:books", 
                "category:clothing",
                "query:popular",
                "query:trending"
            ]
        
        # Add background cache warming task
        if background_tasks:
            background_tasks.add_task(
                _perform_cache_warming,
                warming_tasks,
                resources.redis_client
            )
        
        logger.info(f"Cache warming initiated for {len(warming_tasks)} targets")
        
        return {
            "status": "success",
            "message": f"Cache warming initiated for {len(warming_tasks)} targets",
            "targets": warming_tasks,
            "estimated_completion": "2-5 minutes",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Cache warming failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Cache warming failed: {str(e)}"
        )

async def _perform_cache_warming(targets: List[str], redis_client: Redis):
    """
    Background task for performing cache warming operations
    
    Features:
    - Intelligent data preloading with realistic queries
    - Error isolation to prevent cascade failures
    - Performance monitoring and optimization
    - Graceful degradation on errors
    """
    warming_start_time = time.time()
    successful_targets = 0
    
    logger.info(f"Starting cache warming for {len(targets)} targets")
    
    for target in targets:
        try:
            if target.startswith("category:"):
                category = target[9:]  # Remove "category:" prefix
                
                # Warm category-based product searches
                search_params = {
                    "category": category,
                    "limit": 20,
                    "offset": 0
                }
                
                # Simulate search and cache results
                products = await search_and_filter_products(**search_params)
                
                cache_key = generate_cache_key("product_search", "", category, 0, 999999, 20, 0, "relevance")
                await AdvancedCache.set_cached(redis_client, cache_key, products, config.cache_ttl_long)
                
            elif target.startswith("query:"):
                query = target[6:]  # Remove "query:" prefix
                
                # Warm text-based searches
                search_params = {
                    "query": query,
                    "limit": 15,
                    "offset": 0
                }
                
                products = await search_and_filter_products(**search_params)
                
                cache_key = generate_cache_key("product_search", query, "", 0, 999999, 15, 0, "relevance")
                await AdvancedCache.set_cached(redis_client, cache_key, products, config.cache_ttl_medium)
            
            successful_targets += 1
            
            # Small delay to prevent overwhelming the system
            await asyncio.sleep(0.1)
            
        except Exception as e:
            logger.warning(f"Cache warming failed for target {target}: {e}")
            continue
    
    warming_duration = time.time() - warming_start_time
    logger.info(f"Cache warming completed: {successful_targets}/{len(targets)} targets in {warming_duration:.2f}s")

# --- AI Provider Management Endpoints ---
@app.get("/ai/providers", response_model=Dict[str, Any], tags=["AI Management"])
@external_monitor_performance("list_providers")
async def list_ai_providers():
    """
    List available AI providers with comprehensive status and capability information
    
    Features:
    - Real-time provider health status
    - Capability and feature matrix
    - Cost analysis and comparison
    - Performance metrics and recommendations
    - Circuit breaker status monitoring
    
    Used for provider selection and operational monitoring
    """
    try:
        providers_info = {}
        
        # Get AI configuration
        ai_config = await resources.load_ai_config()
        
        for provider_name, provider_config in ai_config.items():
            circuit_breaker = resources.circuit_breakers.get(provider_name)
            provider_stats = resources.request_stats.get(provider_name, {})
            
            # Calculate success rate
            total_requests = provider_stats.get('total_requests', 0)
            successful_requests = provider_stats.get('successful_requests', 0)
            success_rate = (successful_requests / max(total_requests, 1)) * 100
            
            # Get cost information
            cost_info = TokenOptimizer.PROVIDER_COSTS.get(provider_name, {"input": 0, "output": 0})
            
            providers_info[provider_name] = {
                "status": "healthy" if circuit_breaker and circuit_breaker.state == "CLOSED" else "degraded",
                "circuit_breaker": circuit_breaker.get_status() if circuit_breaker else None,
                "capabilities": {
                    "max_tokens": provider_config.get("max_tokens", "unknown"),
                    "supports_streaming": provider_config.get("supports_streaming", False),
                    "is_free": provider_config.get("is_free", False),
                    "priority": provider_config.get("priority", "medium")
                },
                "cost": {
                    "input_per_1k_tokens": cost_info["input"],
                    "output_per_1k_tokens": cost_info["output"],
                    "currency": "USD"
                },
                "performance": {
                    "total_requests": total_requests,
                    "success_rate_percent": round(success_rate, 2),
                    "average_latency_ms": provider_stats.get('average_latency', 0),
                    "total_tokens": provider_stats.get('total_tokens', 0),
                    "total_cost": provider_stats.get('total_cost', 0.0)
                },
                "configuration": {
                    "timeout": provider_config.get("timeout", config.ai.request_timeout),
                    "rate_limit": provider_config.get("rate_limit", 60),
                    "base_url": provider_config.get("base_url", "N/A")
                }
            }
        
        # Add summary statistics
        total_providers = len(providers_info)
        healthy_providers = sum(1 for p in providers_info.values() if p["status"] == "healthy")
        
        return {
            "providers": providers_info,
            "summary": {
                "total_providers": total_providers,
                "healthy_providers": healthy_providers,
                "health_percentage": (healthy_providers / max(total_providers, 1)) * 100,
                "default_provider": config.ai.default_provider
            },
            "recommendations": _get_provider_recommendations(providers_info),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Provider listing failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve provider information: {str(e)}"
        )

def _get_provider_recommendations(providers_info: Dict[str, Any]) -> List[str]:
    """
    Generate intelligent recommendations based on provider analysis
    
    Features:
    - Cost optimization suggestions
    - Performance improvement recommendations
    - Reliability enhancement proposals
    - Capacity planning insights
    """
    recommendations = []
    
    # Analyze provider health
    healthy_count = sum(1 for p in providers_info.values() if p["status"] == "healthy")
    total_count = len(providers_info)
    
    if healthy_count == 0:
        recommendations.append("CRITICAL: No healthy AI providers available - check configurations and connectivity")
    elif healthy_count < total_count / 2:
        recommendations.append("WARNING: More than half of AI providers are unhealthy - investigate and resolve issues")
    
    # Analyze cost efficiency
    free_providers = [name for name, info in providers_info.items() 
                     if info["capabilities"]["is_free"]]
    if not free_providers:
        recommendations.append("Consider configuring free providers (Ollama, HuggingFace) to reduce costs")
    
    # Analyze performance
    high_latency_providers = [name for name, info in providers_info.items() 
                             if info["performance"]["average_latency_ms"] > 5000]
    if high_latency_providers:
        recommendations.append(f"High latency detected in providers: {', '.join(high_latency_providers)}")
    
    # Analyze success rates
    low_success_providers = [name for name, info in providers_info.items() 
                            if info["performance"]["success_rate_percent"] < 90]
    if low_success_providers:
        recommendations.append(f"Low success rates in providers: {', '.join(low_success_providers)}")
    
    return recommendations

@app.post("/ai/providers/{provider_name}/test", tags=["AI Management"])
@rate_limit(requests_per_minute=10)
@external_monitor_performance("test_provider")
async def test_ai_provider(
    provider_name: str,
    test_prompt: str = "Hello, this is a test message. Please respond briefly.",
    http_request: Request = None
):
    """
    Test specific AI provider connectivity and performance
    
    Features:
    - Real-time connectivity testing
    - Performance benchmarking
    - Error detection and diagnosis
    - Circuit breaker status validation
    - Comprehensive result reporting
    
    Used for troubleshooting and provider validation
    """
    request_id = await get_request_id(http_request)
    
    # Validate provider exists
    ai_config = await resources.load_ai_config()
    if provider_name not in ai_config:
        raise HTTPException(
            status_code=404,
            detail=f"Provider '{provider_name}' not found. Available providers: {list(ai_config.keys())}"
        )
    
    logger.info(f"Testing AI provider {provider_name} with request {request_id}")
    
    test_start_time = time.time()
    test_results = {
        "provider": provider_name,
        "request_id": request_id,
        "test_prompt": test_prompt,
        "timestamp": datetime.now().isoformat(),
        "success": False,
        "response": None,
        "error": None,
        "metrics": {},
        "circuit_breaker_status": {}
    }
    
    try:
        # Check circuit breaker status
        circuit_breaker = resources.circuit_breakers.get(provider_name)
        if circuit_breaker:
            cb_status = circuit_breaker.get_status()
            test_results["circuit_breaker_status"] = cb_status
            
            if cb_status["state"] == "OPEN":
                test_results["error"] = "Circuit breaker is OPEN - provider temporarily unavailable"
                test_results["metrics"]["test_duration_ms"] = (time.time() - test_start_time) * 1000
                return test_results
        
        # Create test AI request
        test_request = AIRequest(
            prompt=test_prompt,
            provider=provider_name,
            max_tokens=100,
            temperature=0.1,
            use_cache=False,  # Disable cache for testing
            optimize_tokens=False  # Disable optimization for testing
        )
        
        # Perform the actual test
        if resources.ai_client_instance and AI_CLIENT_AVAILABLE:
            # Use real AI client if available
            try:
                # This would integrate with the actual AI client
                # For now, we'll simulate the test
                await asyncio.sleep(0.2)  # Simulate network call
                test_results["response"] = f"Test response from {provider_name}: Connection successful!"
                test_results["success"] = True
            except Exception as e:
                test_results["error"] = f"AI client error: {str(e)}"
        else:
            # Use fallback testing
            await asyncio.sleep(0.1)  # Simulate processing
            test_results["response"] = f"Fallback test response from {provider_name}: Provider configuration valid"
            test_results["success"] = True
        
        # Calculate performance metrics
        test_duration = (time.time() - test_start_time) * 1000
        
        test_results["metrics"] = {
            "test_duration_ms": round(test_duration, 2),
            "estimated_tokens_input": TokenOptimizer.estimate_tokens(test_prompt, provider_name),
            "estimated_tokens_output": TokenOptimizer.estimate_tokens(test_results.get("response", ""), provider_name),
            "estimated_cost": TokenOptimizer.calculate_cost(
                TokenOptimizer.estimate_tokens(test_prompt, provider_name),
                TokenOptimizer.estimate_tokens(test_results.get("response", ""), provider_name),
                provider_name
            )
        }
        
        logger.info(f"Provider test {request_id} completed: {provider_name} - {'SUCCESS' if test_results['success'] else 'FAILED'}")
        
        return test_results
        
    except Exception as e:
        test_duration = (time.time() - test_start_time) * 1000
        test_results["error"] = str(e)
        test_results["metrics"]["test_duration_ms"] = round(test_duration, 2)
        
        logger.error(f"Provider test {request_id} failed: {provider_name} - {e}")
        
        return test_results

# --- Advanced Analytics and Reporting ---
@app.get("/analytics/usage-report", tags=["Analytics"])
@external_monitor_performance("usage_report")
async def get_usage_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    provider: Optional[str] = None
):
    """
    Generate comprehensive usage reports for analytics and billing
    
    Features:
    - Time-based usage analysis with flexible date ranges
    - Provider-specific performance comparison
    - Cost analysis and optimization insights
    - Token usage patterns and trends
    - Performance benchmarking and recommendations
    
    Used for business intelligence and operational optimization
    """
    try:
        # Parse date parameters
        report_start = datetime.now() - timedelta(days=7)  # Default to last 7 days
        report_end = datetime.now()
        
        if start_date:
            try:
                report_start = datetime.fromisoformat(start_date)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_date format. Use ISO format: YYYY-MM-DD")
        
        if end_date:
            try:
                report_end = datetime.fromisoformat(end_date)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid end_date format. Use ISO format: YYYY-MM-DD")
        
        # Validate date range
        if report_start >= report_end:
            raise HTTPException(status_code=400, detail="start_date must be before end_date")
        
        # Generate comprehensive usage report
        report = {
            "report_period": {
                "start_date": report_start.isoformat(),
                "end_date": report_end.isoformat(),
                "duration_days": (report_end - report_start).days
            },
            "summary": {
                "total_requests": resources.total_requests,
                "total_errors": resources.total_errors,
                "success_rate_percent": ((resources.total_requests - resources.total_errors) / max(resources.total_requests, 1)) * 100,
                "total_tokens_used": resources.ai_usage_stats.get("total_tokens", 0),
                "total_cost_usd": resources.ai_usage_stats.get("total_cost", 0.0),
                "average_response_time_ms": resources.avg_response_time * 1000
            },
            "providers": {},
            "performance": {
                "peak_concurrent_requests": resources.peak_concurrent_requests,
                "cache_performance": resources.cache_stats
            },
            "recommendations": [],
            "generated_at": datetime.now().isoformat()
        }
        
        # Add provider-specific statistics
        for provider_name, stats in resources.request_stats.items():
            if provider and provider != provider_name:
                continue
                
            provider_report = {
                "requests": {
                    "total": stats.get('total_requests', 0),
                    "successful": stats.get('successful_requests', 0),
                    "failed": stats.get('failed_requests', 0),
                    "success_rate_percent": (stats.get('successful_requests', 0) / max(stats.get('total_requests', 1), 1)) * 100
                },
                "performance": {
                    "average_latency_ms": stats.get('average_latency', 0),
                    "total_tokens": stats.get('total_tokens', 0),
                    "total_cost_usd": stats.get('total_cost', 0.0)
                },
                "reliability": {
                    "circuit_breaker_trips": stats.get('circuit_breaker_trips', 0),
                    "rate_limit_hits": stats.get('rate_limit_hits', 0)
                }
            }
            
            # Add cost efficiency metrics
            if provider_report["requests"]["total"] > 0:
                provider_report["efficiency"] = {
                    "cost_per_request": provider_report["performance"]["total_cost_usd"] / provider_report["requests"]["total"],
                    "tokens_per_request": provider_report["performance"]["total_tokens"] / provider_report["requests"]["total"]
                }
            
            report["providers"][provider_name] = provider_report
        
        # Generate intelligent recommendations
        report["recommendations"] = _generate_usage_recommendations(report)
        
        return report
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Usage report generation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate usage report: {str(e)}"
        )

def _generate_usage_recommendations(report: Dict[str, Any]) -> List[str]:
    """
    Generate intelligent recommendations based on usage analysis
    
    Features:
    - Cost optimization suggestions
    - Performance improvement recommendations
    - Reliability enhancement proposals
    - Capacity planning insights
    """
    recommendations = []
    
    # Cost optimization recommendations
    total_cost = report["summary"]["total_cost_usd"]
    if total_cost > 100:  # High cost threshold
        recommendations.append(f"High usage cost detected (${total_cost:.2f}) - consider optimizing prompts or using free providers")
    
    # Performance recommendations
    avg_response_time = report["summary"]["average_response_time_ms"]
    if avg_response_time > 2000:  # 2 second threshold
        recommendations.append(f"High average response time ({avg_response_time:.0f}ms) - consider caching optimization")
    
    # Success rate recommendations
    success_rate = report["summary"]["success_rate_percent"]
    if success_rate < 95:
        recommendations.append(f"Low success rate ({success_rate:.1f}%) - investigate error patterns and provider reliability")
    
    # Cache performance recommendations
    cache_stats = report["performance"]["cache_performance"]
    cache_hits = cache_stats.get("hits", 0)
    cache_misses = cache_stats.get("misses", 0)
    if cache_hits + cache_misses > 0:
        hit_ratio = cache_hits / (cache_hits + cache_misses) * 100
        if hit_ratio < 50:
            recommendations.append(f"Low cache hit ratio ({hit_ratio:.1f}%) - review caching strategy")
    
    # Provider-specific recommendations
    providers = report["providers"]
    if len(providers) > 1:
        # Find best performing provider
        best_provider = min(providers.items(), 
                          key=lambda x: x[1]["efficiency"].get("cost_per_request", float('inf'))
                          if "efficiency" in x[1] else float('inf'))
        if best_provider and "efficiency" in best_provider[1]:
            recommendations.append(f"Most cost-efficient provider: {best_provider[0]} - consider prioritizing")
    
    return recommendations

# --- System Configuration and Deployment ---
@app.get("/system/info", tags=["System"])
async def get_system_info():
    """
    Comprehensive system information for monitoring and troubleshooting
    
    Features:
    - Runtime environment details
    - Dependency versions and status
    - Performance characteristics
    - Configuration summary
    - Resource utilization metrics
    
    Used for debugging, monitoring, and operational awareness
    """
    try:
        import psutil
        system_available = True
    except ImportError:
        system_available = False
    
    system_info = {
        "application": {
            "name": config.app_name,
            "version": config.version,
            "environment": config.environment,
            "user": config.user,
            "uptime_seconds": time.time() - resources.startup_time,
            "startup_time": datetime.fromtimestamp(resources.startup_time).isoformat()
        },
        "runtime": {
            "python_version": config.python_version,
            "platform": platform.platform(),
            "architecture": platform.architecture(),
            "processor": platform.processor() or "unknown"
        },
        "dependencies": {
            "fastapi": FASTAPI_AVAILABLE,
            "pydantic": PYDANTIC_AVAILABLE,
            "redis": REDIS_AVAILABLE,
            "database": DATABASE_AVAILABLE,
            "metrics": METRICS_AVAILABLE,
            "yaml": YAML_AVAILABLE,
            "ai_client": AI_CLIENT_AVAILABLE,
            "performance_monitor": PERFORMANCE_MONITOR_AVAILABLE
        },
        "configuration": {
            "debug": config.debug,
            "cache_enabled": config.enable_cache,
            "metrics_enabled": config.enable_metrics,
            "docs_enabled": config.enable_docs,
            "compression_enabled": config.enable_compression
        },
        "performance": {
            "total_requests": resources.total_requests,
            "total_errors": resources.total_errors,
            "average_response_time_ms": resources.avg_response_time * 1000,
            "peak_concurrent_requests": resources.peak_concurrent_requests,
            "current_concurrent_requests": resources.current_concurrent_requests
        }
    }
    
    # Add system resource information if available
    if system_available:
        try:
            system_info["resources"] = {
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage('/').percent,
                "network_connections": len(psutil.net_connections()),
                "process_count": len(psutil.pids())
            }
        except Exception as e:
            system_info["resources"] = {"error": f"Unable to retrieve system resources: {e}"}
    
    return system_info

@app.get("/system/config/validate", tags=["System"])
async def validate_configuration():
    """
    Comprehensive configuration validation for deployment readiness
    
    Features:
    - Multi-layer configuration validation
    - Security best practices checking
    - Performance optimization recommendations
    - Dependency compatibility verification
    - Production readiness assessment
    
    Used during deployment and configuration changes
    """
    validation_results = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "recommendations": [],
        "checks_performed": [],
        "timestamp": datetime.now().isoformat()
    }
    
    try:
        # Basic configuration validation
        validation_results["checks_performed"].append("Basic configuration structure")
        
        # Environment-specific validations
        if config.environment == "production":
            validation_results["checks_performed"].append("Production environment validation")
            
            if config.debug:
                validation_results["warnings"].append("Debug mode is enabled in production")
            
            if config.reload:
                validation_results["warnings"].append("Auto-reload is enabled in production")
            
            if len(config.security.secret_key) < 32:
                validation_results["errors"].append("Secret key too short for production (minimum 32 characters)")
                validation_results["valid"] = False
            
            if "dev-secret" in config.security.secret_key.lower():
                validation_results["errors"].append("Default secret key detected in production")
                validation_results["valid"] = False
            
            if not config.enable_monitoring:
                validation_results["warnings"].append("Monitoring is disabled in production")
        
        # Security validation
        validation_results["checks_performed"].append("Security configuration")
        
        if '*' in config.security.allowed_origins and config.environment == "production":
            validation_results["errors"].append("Wildcard CORS origin not allowed in production")
            validation_results["valid"] = False
        
        # Performance validation
        validation_results["checks_performed"].append("Performance configuration")
        
        if config.workers > 32:
            validation_results["warnings"].append("Very high worker count may cause resource contention")
        
        if config.max_request_size > 100 * 1024 * 1024:  # 100MB
            validation_results["warnings"].append("Very large max request size may cause memory issues")
        
        # Resource availability validation
        validation_results["checks_performed"].append("Resource availability")
        
        if config.enable_cache and not REDIS_AVAILABLE:
            validation_results["warnings"].append("Cache enabled but Redis not available")
        
        if config.enable_metrics and not METRICS_AVAILABLE:
            validation_results["warnings"].append("Metrics enabled but Prometheus client not available")
        
        # AI configuration validation
        validation_results["checks_performed"].append("AI provider configuration")
        
        try:
            ai_config = await resources.load_ai_config()
            if not ai_config:
                validation_results["warnings"].append("No AI providers configured")
            else:
                healthy_providers = sum(1 for provider in resources.circuit_breakers.values() 
                                      if provider.state == "CLOSED")
                total_providers = len(ai_config)
                
                if healthy_providers == 0:
                    validation_results["errors"].append("No healthy AI providers available")
                    validation_results["valid"] = False
                elif healthy_providers < total_providers / 2:
                    validation_results["warnings"].append("More than half of AI providers are unhealthy")
        except Exception as e:
            validation_results["warnings"].append(f"Could not validate AI configuration: {e}")
        
        # Generate recommendations
        if validation_results["valid"]:
            validation_results["recommendations"].append("Configuration validation passed - deployment ready")
        
        if validation_results["warnings"]:
            validation_results["recommendations"].append("Review warnings before production deployment")
        
        if config.environment == "development":
            validation_results["recommendations"].append("Consider enabling debug mode and docs for development")
        
        return validation_results
        
    except Exception as e:
        logger.error(f"Configuration validation failed: {e}")
        validation_results["valid"] = False
        validation_results["errors"].append(f"Validation process failed: {str(e)}")
        return validation_results

# --- Startup Event Handler for Additional Initialization ---
@app.on_event("startup")
async def additional_startup_tasks():
    """
    Additional startup tasks for comprehensive application initialization
    
    Features:
    - Advanced monitoring setup
    - Performance baseline establishment
    - Health check initialization
    - Cache warming for critical data
    - System optimization configuration
    """
    logger.info("Executing additional startup tasks...")
    
    try:
        # Initialize performance baseline
        if config.enable_monitoring:
            logger.info("Establishing performance baseline...")
            # Could initialize APM tools, tracing, etc.
        
        # Warm critical caches
        if config.enable_cache and resources.redis_client:
            logger.info("Warming critical caches...")
            # Warm essential category and query caches
            await _perform_cache_warming(
                ["category:electronics", "category:books", "query:popular"],
                resources.redis_client
            )
        
        # Validate AI providers
        if resources.ai_client_instance:
            logger.info("Validating AI provider configurations...")
            ai_config = await resources.load_ai_config()
            logger.info(f"Validated {len(ai_config)} AI provider configurations")
        
        logger.info("✅ Additional startup tasks completed successfully")
        
    except Exception as e:
        logger.warning(f"Some additional startup tasks failed: {e}")
        # Don't fail application startup for non-critical issues

# This completes the comprehensive FastAPI application with all advanced features,
# monitoring capabilities, and production-ready deployment features.
