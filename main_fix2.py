# main.py - AI Aggregator Pro: Ultimate Production Version with Custom Providers
# Full infrastructure for custom AI providers, hot-reload, monitoring, and extensibility

from __future__ import annotations
import os
import sys
import time
import asyncio
import gzip
import pickle
import hashlib
import platform
import logging
import json
import importlib
import inspect
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable, Union, Type
from collections import defaultdict
from enum import Enum
from contextlib import asynccontextmanager
from functools import wraps
from abc import ABC, abstractmethod

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
except ImportError:
    pass

try:
    from fastapi import (
        FastAPI, HTTPException, Query, Request, BackgroundTasks, Response, Body
    )
    from fastapi.responses import JSONResponse, StreamingResponse
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.middleware.trustedhost import TrustedHostMiddleware
    from fastapi.middleware.gzip import GZipMiddleware
except ImportError:
    raise ImportError("FastAPI is required. Install with: pip install fastapi uvicorn")

try:
    from pydantic import BaseModel, ConfigDict, field_validator, computed_field
except ImportError:
    raise ImportError("Pydantic v2 is required. Install with: pip install 'pydantic>=2.0'")

# Redis and Prometheus (optionally available)
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

try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest
    METRICS_AVAILABLE = True
    REQUEST_COUNT = Counter('ai_requests_total', 'Total AI requests processed', ['provider', 'status'])
    REQUEST_DURATION = Histogram('ai_request_duration_seconds', 'AI request processing duration')
    CACHE_HITS = Counter('cache_hits_total', 'Cache hit operations', ['cache_type'])
    ACTIVE_CONNECTIONS = Gauge('active_connections', 'Currently active connections')
    TOKEN_USAGE = Counter('tokens_used_total', 'Total tokens consumed', ['provider'])
    ERROR_COUNT = Counter('errors_total', 'Total errors encountered', ['error_type'])
    CUSTOM_PROVIDER_REQUESTS = Counter('custom_provider_requests_total', 'Requests to custom providers', ['provider', 'status'])
    CUSTOM_PROVIDER_DURATION = Histogram('custom_provider_duration_seconds', 'Custom provider response time', ['provider'])
except ImportError:
    METRICS_AVAILABLE = False

# --- Logging Setup ---
def setup_logging():
    """Initialize logging system with production-ready configuration."""
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    
    handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(getattr(logging, log_level, logging.INFO))
    handlers.append(console_handler)
    
    # File handler (optional)
    if os.getenv('ENABLE_FILE_LOGGING', 'true').lower() == 'true':
        log_file = os.getenv('LOG_FILE', 'app.log')
        try:
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)
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
        force=True
    )
    
    # Reduce noise from external libraries
    logging.getLogger('uvicorn').setLevel(logging.WARNING)
    logging.getLogger('fastapi').setLevel(logging.INFO)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    logging.getLogger('redis').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)

# Initialize logging FIRST
setup_logging()
logger = logging.getLogger(__name__)

# --- Core Infrastructure Components (FIXED: Define before use) ---

class CircuitBreaker:
    """
    Enterprise-grade circuit breaker implementation for AI provider fault tolerance.
    Provides automatic failure detection, recovery, and comprehensive monitoring.
    """
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60,
                 half_open_max_calls: int = 3, success_threshold: int = 2):
        """
        Initialize circuit breaker with configurable thresholds.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds before attempting recovery
            half_open_max_calls: Max calls allowed in half-open state
            success_threshold: Successes needed in half-open to close circuit
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.success_threshold = success_threshold
        
        # State tracking
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.half_open_calls = 0
        
        # Statistics
        self.total_calls = 0
        self.total_failures = 0
        self.total_successes = 0
        self.state_transitions = []
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
    
    async def call(self, func: Callable, *args, **kwargs):
        """
        Execute function through circuit breaker protection.
        
        Args:
            func: Async function to execute
            *args, **kwargs: Function arguments
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerOpenError: When circuit is open
            Exception: Original function exceptions
        """
        async with self._lock:
            self.total_calls += 1
            
            # Check if circuit should be opened
            if self.state == "CLOSED" and self.failure_count >= self.failure_threshold:
                self._transition_to_open()
            
            # Check if circuit can transition to half-open
            elif self.state == "OPEN" and self._should_attempt_reset():
                self._transition_to_half_open()
            
            # Reject calls when circuit is open
            if self.state == "OPEN":
                raise CircuitBreakerOpenError(f"Circuit breaker is OPEN (failures: {self.failure_count})")
            
            # Limit calls in half-open state
            if self.state == "HALF_OPEN" and self.half_open_calls >= self.half_open_max_calls:
                raise CircuitBreakerOpenError("Circuit breaker HALF_OPEN call limit exceeded")
        
        # Execute the function
        try:
            if self.state == "HALF_OPEN":
                async with self._lock:
                    self.half_open_calls += 1
            
            start_time = time.time()
            result = await func(*args, **kwargs)
            execution_time = time.time() - start_time
            
            # Record success
            await self._record_success(execution_time)
            return result
            
        except Exception as e:
            # Record failure
            await self._record_failure(e)
            raise
    
    async def _record_success(self, execution_time: float):
        """Record successful execution and update state."""
        async with self._lock:
            self.total_successes += 1
            self.failure_count = 0  # Reset failure count on success
            
            if self.state == "HALF_OPEN":
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    self._transition_to_closed()
    
    async def _record_failure(self, exception: Exception):
        """Record failed execution and update state."""
        async with self._lock:
            self.total_failures += 1
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.state == "HALF_OPEN":
                self._transition_to_open()
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self.last_failure_time is None:
            return False
        return time.time() - self.last_failure_time >= self.recovery_timeout
    
    def _transition_to_open(self):
        """Transition circuit breaker to OPEN state."""
        self.state = "OPEN"
        self.half_open_calls = 0
        self.success_count = 0
        self._record_state_transition("OPEN")
        logger.warning(f"🔴 Circuit breaker opened (failures: {self.failure_count})")
    
    def _transition_to_half_open(self):
        """Transition circuit breaker to HALF_OPEN state."""
        self.state = "HALF_OPEN"
        self.half_open_calls = 0
        self.success_count = 0
        self._record_state_transition("HALF_OPEN")
        logger.info(f"🟡 Circuit breaker half-open (attempting recovery)")
    
    def _transition_to_closed(self):
        """Transition circuit breaker to CLOSED state."""
        self.state = "CLOSED"
        self.failure_count = 0
        self.half_open_calls = 0
        self.success_count = 0
        self._record_state_transition("CLOSED")
        logger.info(f"🟢 Circuit breaker closed (recovery successful)")
    
    def _record_state_transition(self, new_state: str):
        """Record state transition for monitoring."""
        transition = {
            "timestamp": datetime.now().isoformat(),
            "from_state": getattr(self, '_previous_state', 'UNKNOWN'),
            "to_state": new_state,
            "failure_count": self.failure_count,
            "total_calls": self.total_calls
        }
        self.state_transitions.append(transition)
        self._previous_state = new_state
        
        # Limit transition history
        if len(self.state_transitions) > 100:
            self.state_transitions = self.state_transitions[-100:]
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive circuit breaker status."""
        success_rate = (self.total_successes / max(self.total_calls, 1)) * 100
        
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "half_open_calls": self.half_open_calls,
            "configuration": {
                "failure_threshold": self.failure_threshold,
                "recovery_timeout": self.recovery_timeout,
                "half_open_max_calls": self.half_open_max_calls,
                "success_threshold": self.success_threshold
            },
            "statistics": {
                "total_calls": self.total_calls,
                "total_successes": self.total_successes,
                "total_failures": self.total_failures,
                "success_rate_percent": round(success_rate, 2),
                "last_failure_time": self.last_failure_time,
                "state_transitions": len(self.state_transitions)
            }
        }
    
    async def reset(self):
        """Manually reset circuit breaker to CLOSED state."""
        async with self._lock:
            self._transition_to_closed()
            logger.info("🔄 Circuit breaker manually reset")

class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit breaker is open."""
    pass

class ModernRateLimiter:-same
    """
    Advanced rate limiter with sliding window, burst handling, and intelligent throttling.
    Supports both memory-based and Redis-backed implementations.
    """
    
    def __init__(self, use_redis: bool = True):
        self.use_redis = use_redis and REDIS_AVAILABLE
        self.requests = defaultdict(list)  # Memory-based fallback
        self.burst_allowance = defaultdict(int)
        self.last_reset = defaultdict(float)
        self._lock = asyncio.Lock()
    
    async def is_allowed(self, key: str, limit: int, window: int, 
                        burst_multiplier: float = 1.5) -> bool:
        """
        Check if request is allowed under rate limiting rules.
        
        Args:
            key: Unique identifier for rate limiting (IP, user ID, etc.)
            limit: Number of requests allowed per window
            window: Time window in seconds
            burst_multiplier: Multiplier for burst allowance
            
        Returns:
            bool: True if request is allowed, False otherwise
        """
        if self.use_redis:
            return await self._is_allowed_redis(key, limit, window, burst_multiplier)
        else:
            return await self._is_allowed_memory(key, limit, window, burst_multiplier)
    
    async def _is_allowed_redis(self, key: str, limit: int, window: int, 
                               burst_multiplier: float) -> bool:
        """Redis-based rate limiting implementation."""
        # Implementation would use Redis sliding window
        # For now, fallback to memory-based
        return await self._is_allowed_memory(key, limit, window, burst_multiplier)
    
    async def _is_allowed_memory(self, key: str, limit: int, window: int, 
                                burst_multiplier: float) -> bool:
        """Memory-based rate limiting with sliding window."""
        async with self._lock:
            current_time = time.time()
            
            # Clean old requests outside the window
            self.requests[key] = [
                req_time for req_time in self.requests[key]
                if current_time - req_time < window
            ]
            
            # Calculate current request count
            current_requests = len(self.requests[key])
            burst_limit = int(limit * burst_multiplier)
            
            # Check if under normal limit
            if current_requests < limit:
                self.requests[key].append(current_time)
                return True
            
            # Check burst allowance
            elif current_requests < burst_limit:
                # Allow burst but consume from future allowance
                burst_used = current_requests - limit + 1
                if self.burst_allowance[key] >= burst_used:
                    self.burst_allowance[key] -= burst_used
                    self.requests[key].append(current_time)
                    return True
            
            # Request denied
            return False
    
    def get_remaining(self, key: str, limit: int, window: int) -> int:
        """Get remaining requests allowed for the key."""
        current_time = time.time()
        recent_requests = [
            req_time for req_time in self.requests[key]
            if current_time - req_time < window
        ]
        return max(0, limit - len(recent_requests))
    
    def get_stats(self) -> Dict[str, Any]:
        """Get rate limiter statistics."""
        current_time = time.time()
        active_keys = [
            key for key, requests in self.requests.items()
            if any(current_time - req_time < 3600 for req_time in requests)  # Active in last hour
        ]
        
        return {
            "implementation": "redis" if self.use_redis else "memory",
            "active_clients": len(active_keys),
            "total_tracked_requests": sum(len(reqs) for reqs in self.requests.values()),
            "burst_allowances_used": sum(self.burst_allowance.values())
        }

class AdvancedCache:
    """
    Advanced caching system with compression, TTL management, and intelligent eviction.
    Supports both Redis and memory-based implementations with automatic fallback.
    """
    
    @staticmethod
    async def get_cached(redis_client, key: str, default=None):
        """Get cached value with automatic decompression and deserialization."""
        if not redis_client:
            return default
        
        try:
            cached_data = await redis_client.get(key)
            if cached_data is None:
                return default
            
            # Handle compressed data
            if isinstance(cached_data, bytes) and cached_data.startswith(b'\x1f\x8b'):
                try:
                    cached_data = gzip.decompress(cached_data)
                except:
                    pass  # Not compressed or corrupted
            
            # Deserialize
            if isinstance(cached_data, bytes):
                try:
                    return pickle.loads(cached_data)
                except:
                    try:
                        return json.loads(cached_data.decode('utf-8'))
                    except:
                        return cached_data.decode('utf-8')
            
            return cached_data
            
        except Exception as e:
            logger.warning(f"Cache get error for key {key}: {e}")
            return default
    
    @staticmethod
    async def set_cached(redis_client, key: str, value, ttl: int = 3600, 
                        compress: bool = True) -> bool:
        """Set cached value with optional compression and TTL."""
        if not redis_client:
            return False
        
        try:
            # Serialize the value
            if isinstance(value, (dict, list)):
                serialized = json.dumps(value, ensure_ascii=False).encode('utf-8')
            elif isinstance(value, str):
                serialized = value.encode('utf-8')
            else:
                serialized = pickle.dumps(value)
            
            # Compress if beneficial
            if compress and len(serialized) > 1024:  # Only compress larger data
                compressed = gzip.compress(serialized, compresslevel=6)
                if len(compressed) < len(serialized) * 0.9:  # 10% saving minimum
                    serialized = compressed
            
            # Store with TTL
            await redis_client.setex(key, ttl, serialized)
            
            # Update metrics
            if METRICS_AVAILABLE:
                CACHE_HITS.labels(cache_type='set').inc()
            
            return True
            
        except Exception as e:
            logger.warning(f"Cache set error for key {key}: {e}")
            return False
    
    @staticmethod
    async def delete_cached(redis_client, key: str) -> bool:
        """Delete cached value."""
        if not redis_client:
            return False
        
        try:
            result = await redis_client.delete(key)
            return result > 0
        except Exception as e:
            logger.warning(f"Cache delete error for key {key}: {e}")
            return False
    
    @staticmethod
    async def cleanup_expired_keys(redis_client, pattern: str = "*", 
                                  batch_size: int = 1000) -> int:
        """Clean up expired keys in batches."""
        if not redis_client:
            return 0
        
        try:
            deleted_count = 0
            cursor = 0
            
            while True:
                cursor, keys = await redis_client.scan(
                    cursor=cursor, match=pattern, count=batch_size
                )
                
                if keys:
                    # Check TTL and delete expired keys
                    for key in keys:
                        ttl = await redis_client.ttl(key)
                        if ttl == -1:  # No expiration set, skip
                            continue
                        elif ttl == -2:  # Key doesn't exist
                            deleted_count += 1
                    
                if cursor == 0:
                    break
            
            return deleted_count
            
        except Exception as e:
            logger.warning(f"Cache cleanup error: {e}")
            return 0
    
    @staticmethod
    def get_stats() -> Dict[str, Any]:
        """Get caching statistics."""
        # Placeholder for cache statistics
        # In a real implementation, this would collect actual Redis stats
        return {
            "hit_rate_percent": 85.0,  # Would be calculated from actual metrics
            "total_operations": 1000,
            "compression_ratio_percent": 65.0,
            "average_ttl_seconds": 1800,
            "memory_usage_mb": 128.0
        }

class TokenOptimizer:
    """
    Intelligent token optimization and cost calculation system.
    Provides provider-specific token estimation and cost optimization strategies.
    """
    
    # Provider-specific token pricing (per 1k tokens)
    TOKEN_PRICES = {
        'openai': {'input': 0.0015, 'output': 0.002},
        'anthropic': {'input': 0.008, 'output': 0.024},
        'claude': {'input': 0.008, 'output': 0.024},
        'together': {'input': 0.0002, 'output': 0.0002},
        'groq': {'input': 0.00027, 'output': 0.00027},
        'cohere': {'input': 0.0015, 'output': 0.002},
        'ai21': {'input': 0.0025, 'output': 0.0025},
        'perplexity': {'input': 0.0005, 'output': 0.0005},
        'huggingface': {'input': 0.0001, 'output': 0.0001},
        'ollama': {'input': 0.0, 'output': 0.0},
        'local': {'input': 0.0, 'output': 0.0},
        'mock': {'input': 0.0, 'output': 0.0},
        'custom': {'input': 0.0001, 'output': 0.0001}  # Default for custom providers
    }
    
    # Provider quality scores (0-100)
    PROVIDER_QUALITY_SCORES = {
        'openai': 95,
        'anthropic': 92,
        'claude': 92,
        'groq': 85,
        'together': 80,
        'cohere': 78,
        'ai21': 75,
        'perplexity': 70,
        'huggingface': 65,
        'ollama': 70,
        'local': 60,
        'mock': 10,
        'custom': 50  # Default for custom providers
    }
    
    @staticmethod
    def estimate_tokens(text: str, provider: str = 'openai') -> int:
        """
        Estimate token count for given text and provider.
        
        Args:
            text: Input text to analyze
            provider: Provider name for provider-specific estimation
            
        Returns:
            int: Estimated token count
        """
        if not text:
            return 0
        
        # Basic estimation: ~4 characters per token for English text
        # This varies by provider and language, but gives reasonable approximation
        base_tokens = len(text) / 4
        
        # Provider-specific adjustments
        provider_multipliers = {
            'openai': 1.0,
            'anthropic': 0.95,
            'claude': 0.95,
            'together': 1.1,
            'groq': 1.05,
            'cohere': 1.0,
            'ai21': 1.0,
            'perplexity': 1.0,
            'huggingface': 1.2,
            'ollama': 1.1,
            'local': 1.1,
            'mock': 1.0,
            'custom': 1.0
        }
        
        multiplier = provider_multipliers.get(provider, 1.0)
        estimated_tokens = int(base_tokens * multiplier)
        
        # Add some tokens for special formatting, JSON structure, etc.
        overhead_tokens = min(50, max(5, len(text) // 1000))
        
        return estimated_tokens + overhead_tokens
    
    @staticmethod
    def calculate_cost(input_tokens: int, output_tokens: int, provider: str) -> float:
        """
        Calculate cost for given token usage and provider.
        
        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            provider: Provider name
            
        Returns:
            float: Estimated cost in USD
        """
        pricing = TokenOptimizer.TOKEN_PRICES.get(provider, {'input': 0.001, 'output': 0.001})
        
        input_cost = (input_tokens / 1000) * pricing['input']
        output_cost = (output_tokens / 1000) * pricing['output']
        
        return round(input_cost + output_cost, 6)
    
    @staticmethod
    def recommend_provider(prompt: str, budget: float = 0.01, 
                          preference: str = "balanced") -> Dict[str, Any]:
        """
        Recommend optimal provider based on prompt characteristics and constraints.
        
        Args:
            prompt: Input prompt to analyze
            budget: Maximum budget for the request
            preference: Optimization preference ('cost', 'quality', 'speed', 'balanced')
            
        Returns:
            Dict with provider recommendation and analysis
        """
        prompt_tokens = TokenOptimizer.estimate_tokens(prompt)
        estimated_output_tokens = min(1000, max(100, prompt_tokens // 2))  # Estimate output
        
        recommendations = []
        
        for provider, pricing in TokenOptimizer.TOKEN_PRICES.items():
            cost = TokenOptimizer.calculate_cost(prompt_tokens, estimated_output_tokens, provider)
            quality = TokenOptimizer.PROVIDER_QUALITY_SCORES.get(provider, 50)
            
            # Skip if over budget
            if cost > budget:
                continue
            
            # Calculate optimization score based on preference
            if preference == "cost":
                score = (budget - cost) / budget * 100  # Higher score for lower cost
            elif preference == "quality":
                score = quality
            elif preference == "speed":
                # Speed ranking (subjective, based on typical performance)
                speed_scores = {
                    'groq': 95, 'together': 90, 'ollama': 85, 'local': 80,
                    'openai': 75, 'cohere': 70, 'anthropic': 65, 'claude': 65,
                    'ai21': 60, 'perplexity': 60, 'huggingface': 50, 'mock': 100,
                    'custom': 60
                }
                score = speed_scores.get(provider, 50)
            else:  # balanced
                cost_score = (budget - cost) / budget * 100
                quality_score = quality
                speed_scores = {
                    'groq': 95, 'together': 90, 'ollama': 85, 'local': 80,
                    'openai': 75, 'cohere': 70, 'anthropic': 65, 'claude': 65,
                    'ai21': 60, 'perplexity': 60, 'huggingface': 50, 'mock': 100,
                    'custom': 60
                }
                speed_score = speed_scores.get(provider, 50)
                score = (cost_score * 0.3 + quality_score * 0.4 + speed_score * 0.3)
            
            recommendations.append({
                'provider': provider,
                'estimated_cost': cost,
                'quality_score': quality,
                'optimization_score': round(score, 2),
                'within_budget': True
            })
        
        # Sort by optimization score
        recommendations.sort(key=lambda x: x['optimization_score'], reverse=True)
        
        return {
            'recommended_provider': recommendations[0]['provider'] if recommendations else 'mock',
            'prompt_analysis': {
                'estimated_input_tokens': prompt_tokens,
                'estimated_output_tokens': estimated_output_tokens,
                'complexity': 'high' if prompt_tokens > 1000 else 'medium' if prompt_tokens > 300 else 'low'
            },
            'budget_analysis': {
                'budget': budget,
                'providers_within_budget': len(recommendations),
                'cheapest_option': min(recommendations, key=lambda x: x['estimated_cost']) if recommendations else None
            },
            'all_recommendations': recommendations[:5]  # Top 5 recommendations
        }

# --- Configuration Classes ---

@dataclass
class DatabaseConfig:
    """Extended database configuration with full validation and production settings."""
    url: str = os.getenv('DATABASE_URL', 'sqlite+aiosqlite:///./ai_aggregator.db')
    pool_size: int = int(os.getenv('DB_POOL_SIZE', '20'))
    max_overflow: int = int(os.getenv('DB_MAX_OVERFLOW', '30'))
    pool_timeout: int = int(os.getenv('DB_POOL_TIMEOUT', '30'))
    pool_recycle: int = int(os.getenv('DB_POOL_RECYCLE', '3600'))
    pool_pre_ping: bool = os.getenv('DB_POOL_PRE_PING', 'true').lower() == 'true'
    connect_timeout: int = int(os.getenv('DB_CONNECT_TIMEOUT', '10'))
    command_timeout: int = int(os.getenv('DB_COMMAND_TIMEOUT', '30'))
    query_timeout: int = int(os.getenv('DB_QUERY_TIMEOUT', '60'))
    echo: bool = os.getenv('DB_ECHO', 'false').lower() == 'true'
    echo_pool: bool = os.getenv('DB_ECHO_POOL', 'false').lower() == 'true'
    enable_migrations: bool = os.getenv('DB_ENABLE_MIGRATIONS', 'true').lower() == 'true'
    migration_timeout: int = int(os.getenv('DB_MIGRATION_TIMEOUT', '300'))
    ssl_mode: str = os.getenv('DB_SSL_MODE', 'prefer')
    ssl_cert: Optional[str] = os.getenv('DB_SSL_CERT', None)
    ssl_key: Optional[str] = os.getenv('DB_SSL_KEY', None)
    ssl_ca: Optional[str] = os.getenv('DB_SSL_CA', None)

    def __post_init__(self):
        """Validate database configuration parameters."""
        if not self.url:
            raise ValueError("Database URL cannot be empty")
        if self.pool_size < 1:
            raise ValueError("Database pool size must be positive")
        if self.max_overflow < 0:
            raise ValueError("Database max overflow must be non-negative")
        if self.pool_timeout <= 0:
            raise ValueError("Database pool timeout must be positive")
        if self.pool_recycle <= 0:
            raise ValueError("Database pool recycle must be positive")
        if self.connect_timeout <= 0:
            raise ValueError("Database connect timeout must be positive")
        if self.command_timeout <= 0:
            raise ValueError("Database command timeout must be positive")
        if self.query_timeout <= 0:
            raise ValueError("Database query timeout must be positive")
        if self.migration_timeout < 60:
            raise ValueError("Migration timeout is too low (minimum 60s)")

        valid_ssl_modes = ['disable', 'allow', 'prefer', 'require', 'verify-ca', 'verify-full']
        if self.ssl_mode not in valid_ssl_modes:
            logger.warning(f"Unknown SSL mode: {self.ssl_mode}, using 'prefer'")
            self.ssl_mode = 'prefer'

        # Additional production checks
        if self.pool_size > 100:
            logger.warning("Very high pool size detected - consider scaling horizontally instead")
        if self.pool_timeout > 60:
            logger.warning("High pool timeout may impact user experience")

@dataclass
class RedisConfig:
    """Extended Redis configuration with comprehensive connection settings."""
    url: str = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    max_connections: int = int(os.getenv('REDIS_MAX_CONNECTIONS', '20'))
    min_connections: int = int(os.getenv('REDIS_MIN_CONNECTIONS', '1'))
    socket_timeout: float = float(os.getenv('REDIS_SOCKET_TIMEOUT', '5.0'))
    socket_connect_timeout: float = float(os.getenv('REDIS_CONNECT_TIMEOUT', '5.0'))
    socket_keepalive: bool = os.getenv('REDIS_SOCKET_KEEPALIVE', 'true').lower() == 'true'
    socket_keepalive_options: Dict[str, int] = field(default_factory=lambda: {
        'TCP_KEEPIDLE': 1,
        'TCP_KEEPINTVL': 3,
        'TCP_KEEPCNT': 5
    })
    health_check_interval: int = int(os.getenv('REDIS_HEALTH_CHECK_INTERVAL', '30'))
    retry_on_timeout: bool = os.getenv('REDIS_RETRY_ON_TIMEOUT', 'true').lower() == 'true'
    retry_on_error: bool = os.getenv('REDIS_RETRY_ON_ERROR', 'true').lower() == 'true'
    retry_attempts: int = int(os.getenv('REDIS_RETRY_ATTEMPTS', '3'))
    retry_backoff_base: float = float(os.getenv('REDIS_RETRY_BACKOFF', '0.1'))
    encoding: str = os.getenv('REDIS_ENCODING', 'utf-8')
    decode_responses: bool = os.getenv('REDIS_DECODE_RESPONSES', 'false').lower() == 'true'
    ssl_cert_reqs: str = os.getenv('REDIS_SSL_CERT_REQS', 'none')
    ssl_certfile: Optional[str] = os.getenv('REDIS_SSL_CERTFILE', None)
    ssl_keyfile: Optional[str] = os.getenv('REDIS_SSL_KEYFILE', None)
    ssl_ca_certs: Optional[str] = os.getenv('REDIS_SSL_CA_CERTS', None)
    ssl_check_hostname: bool = os.getenv('REDIS_SSL_CHECK_HOSTNAME', 'false').lower() == 'true'
    client_name: str = os.getenv('REDIS_CLIENT_NAME', 'AI_Aggregator_Pro')
    db: int = int(os.getenv('REDIS_DB', '0'))
    username: Optional[str] = os.getenv('REDIS_USERNAME', None)
    password: Optional[str] = os.getenv('REDIS_PASSWORD', None)

    def __post_init__(self):
        """Validate Redis configuration parameters."""
        if self.max_connections < 1:
            raise ValueError("Redis max connections must be positive")
        if self.min_connections < 0:
            raise ValueError("Redis min connections must be non-negative")
        if self.min_connections > self.max_connections:
            raise ValueError("Redis min connections cannot exceed max connections")
        if self.socket_timeout <= 0:
            raise ValueError("Redis socket timeout must be positive")
        if self.socket_connect_timeout <= 0:
            raise ValueError("Redis connect timeout must be positive")
        if self.health_check_interval < 10:
            raise ValueError("Redis health check interval must be at least 10 seconds")
        if self.retry_attempts < 0:
            raise ValueError("Redis retry attempts must be non-negative")
        if not (0 <= self.db <= 15):
            raise ValueError(f"Redis database number must be 0-15, got {self.db}")
        if not self.url.startswith(('redis://', 'rediss://')):
            logger.warning(f"Redis URL format may be invalid: {self.url}")

@dataclass
class SecurityConfig:
    """Enhanced security configuration with comprehensive protection settings."""
    secret_key: str = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    api_key_header: str = os.getenv('API_KEY_HEADER', 'X-API-Key')
    allowed_origins: List[str] = field(default_factory=lambda: [
        origin.strip() for origin in os.getenv(
            'ALLOWED_ORIGINS', 
            'http://localhost:3000,http://localhost:8080,http://localhost:5173'
        ).split(',') if origin.strip()
    ])
    trusted_hosts: List[str] = field(default_factory=lambda: [
        host.strip() for host in os.getenv('TRUSTED_HOSTS', '').split(',') 
        if host.strip()
    ])
    cors_max_age: int = int(os.getenv('CORS_MAX_AGE', '3600'))
    enable_csrf_protection: bool = os.getenv('ENABLE_CSRF', 'false').lower() == 'true'
    enable_rate_limiting: bool = os.getenv('ENABLE_RATE_LIMITING', 'true').lower() == 'true'
    enable_security_headers: bool = os.getenv('ENABLE_SECURITY_HEADERS', 'true').lower() == 'true'
    max_request_size: int = int(os.getenv('MAX_REQUEST_SIZE', '10485760'))  # 10MB
    allowed_methods: List[str] = field(default_factory=lambda: ['GET', 'POST', 'OPTIONS'])
    custom_provider_security: bool = os.getenv('CUSTOM_PROVIDER_SECURITY', 'true').lower() == 'true'
    provider_execution_timeout: int = int(os.getenv('PROVIDER_EXECUTION_TIMEOUT', '30'))
    max_custom_providers: int = int(os.getenv('MAX_CUSTOM_PROVIDERS', '10'))

    def __post_init__(self):
        """Validate security configuration and issue warnings for insecure settings."""
        if len(self.secret_key) < 32:
            logger.warning("🔒 Secret key is too short for production use! Minimum 32 characters recommended.")
        if self.secret_key == 'dev-secret-key-change-in-production':
            logger.warning("🔒 Using default secret key! Change SECRET_KEY environment variable for production.")
        if '*' in self.allowed_origins and os.getenv('ENVIRONMENT', 'development') != 'development':
            logger.warning("🔒 Wildcard CORS origins detected in non-development environment - security risk!")
        if not self.enable_rate_limiting:
            logger.warning("🔒 Rate limiting is disabled - may be vulnerable to abuse!")
        if self.max_request_size > 50 * 1024 * 1024:  # 50MB
            logger.warning("🔒 Very large max request size configured - potential DoS risk!")

@dataclass
class AIConfig:
    """AI provider configuration with cost management and optimization settings."""
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

    # Enhanced free tier limits with more providers
    free_tier_limits: Dict[str, int] = field(default_factory=lambda: {
        'ollama': 999999,
        'huggingface': 1000,
        'together': 25,
        'openai': 3,
        'anthropic': 5,
        'claude': 5,
        'mock': 999999,
        'groq': 100,
        'cohere': 100,
        'ai21': 10,
        'perplexity': 20,
        'local': 999999,
        'custom': 50  # Default limit for custom providers
    })

    # Provider priority scoring for intelligent selection
    provider_priorities: Dict[str, int] = field(default_factory=lambda: {
        'ollama': 100,
        'huggingface': 90,
        'groq': 85,
        'together': 80,
        'cohere': 70,
        'anthropic': 65,
        'claude': 65,
        'openai': 60,
        'ai21': 50,
        'perplexity': 45,
        'local': 95,
        'mock': 10,
        'custom': 30  # Lower priority for custom providers by default
    })

    def __post_init__(self):
        """Validate AI configuration parameters."""
        if self.max_concurrent_requests < 1:
            raise ValueError("Max concurrent requests must be positive")
        if self.request_timeout < 10:
            raise ValueError("Request timeout should be at least 10 seconds")
        if self.max_prompt_length < 100:
            raise ValueError("Max prompt length must be at least 100 characters")
        if not (0.0 <= self.cost_alert_threshold <= 1.0):
            raise ValueError("Cost alert threshold must be between 0.0 and 1.0")
        if self.max_retries < 0:
            raise ValueError("Max retries must be non-negative")

        # Validate provider priorities
        for provider, priority in self.provider_priorities.items():
            if not (0 <= priority <= 100):
                logger.warning(f"Provider {provider} has invalid priority {priority}, should be 0-100")

@dataclass
class AppConfig:
    """Main application configuration with comprehensive feature flags and settings."""
    app_name: str = os.getenv('APP_NAME', 'AI Aggregator Pro')
    version: str = '4.1.0'  # Updated version
    environment: str = os.getenv('ENVIRONMENT', 'development')
    debug: bool = os.getenv('DEBUG', 'false').lower() == 'true'
    user: str = "AdsTable"
    host: str = os.getenv('HOST', '0.0.0.0')
    port: int = int(os.getenv('PORT', '8000'))
    workers: int = int(os.getenv('WORKERS', '1'))
    reload: bool = os.getenv('RELOAD', 'false').lower() == 'true'
    access_log: bool = os.getenv('ACCESS_LOG', 'true').lower() == 'true'

    # Feature flags with intelligent defaults
    enable_cache: bool = REDIS_AVAILABLE and os.getenv('ENABLE_CACHE', 'true').lower() == 'true'
    enable_compression: bool = os.getenv('ENABLE_COMPRESSION', 'true').lower() == 'true'
    enable_metrics: bool = METRICS_AVAILABLE and os.getenv('ENABLE_METRICS', 'true').lower() == 'true'
    enable_docs: bool = os.getenv('ENABLE_DOCS', 'true' if os.getenv('ENVIRONMENT', 'development') != 'production' else 'false').lower() == 'true'
    enable_openapi: bool = os.getenv('ENABLE_OPENAPI', 'true').lower() == 'true'
    enable_monitoring: bool = os.getenv('ENABLE_MONITORING', 'true').lower() == 'true'
    enable_health_checks: bool = os.getenv('ENABLE_HEALTH_CHECKS', 'true').lower() == 'true'
    enable_custom_providers: bool = os.getenv('ENABLE_CUSTOM_PROVIDERS', 'true').lower() == 'true'
    enable_hot_reload: bool = os.getenv('ENABLE_HOT_RELOAD', 'true').lower() == 'true'

    # Performance and caching settings
    cache_ttl_short: int = int(os.getenv('CACHE_TTL_SHORT', '900'))        # 15 minutes
    cache_ttl_medium: int = int(os.getenv('CACHE_TTL_MEDIUM', '1800'))     # 30 minutes
    cache_ttl_long: int = int(os.getenv('CACHE_TTL_LONG', '3600'))         # 1 hour
    cache_ttl_fallback: int = int(os.getenv('CACHE_TTL_FALLBACK', '300'))  # 5 minutes

    # Request processing limits
    max_request_size: int = int(os.getenv('MAX_REQUEST_SIZE', '10485760'))    # 10MB
    request_timeout: int = int(os.getenv('REQUEST_TIMEOUT', '30'))           # 30 seconds
    max_response_size: int = int(os.getenv('MAX_RESPONSE_SIZE', '52428800')) # 50MB
    keepalive_timeout: int = int(os.getenv('KEEPALIVE_TIMEOUT', '5'))        # 5 seconds

    # Rate limiting configuration
    default_rate_limit: int = int(os.getenv('DEFAULT_RATE_LIMIT', '60'))     # 60 requests per minute
    burst_rate_limit: int = int(os.getenv('BURST_RATE_LIMIT', '120'))       # 120 requests per minute for bursts
    admin_rate_limit: int = int(os.getenv('ADMIN_RATE_LIMIT', '10'))        # 10 admin operations per minute

    # Sub-configurations
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    ai: AIConfig = field(default_factory=AIConfig)

    def __post_init__(self):
        """Validate application configuration and environment settings."""
        valid_environments = ['development', 'staging', 'production', 'testing']
        if self.environment not in valid_environments:
            raise ValueError(f"Invalid environment: {self.environment}. Must be one of: {valid_environments}")
        if not 1 <= self.port <= 65535:
            raise ValueError(f"Port must be between 1 and 65535, got: {self.port}")
        if self.workers < 1:
            raise ValueError("Number of workers must be positive")

        # Environment-specific warnings
        if self.environment == 'production':
            if self.debug:
                logger.warning("🔒 Debug mode enabled in production - security risk!")
            if self.reload:
                logger.warning("🔒 Auto-reload enabled in production - performance impact!")
            if self.enable_docs:
                logger.warning("🔒 API documentation exposed in production - consider disabling")

        # Performance warnings
        if self.cache_ttl_short > self.cache_ttl_medium:
            logger.warning("⚡ Short TTL is longer than medium TTL - check cache configuration")
        if self.cache_ttl_medium > self.cache_ttl_long:
            logger.warning("⚡ Medium TTL is longer than long TTL - check cache configuration")

# Initialize configuration
try:
    config = AppConfig()
    logger.info(f"✅ Configuration loaded successfully for environment: {config.environment}")
except Exception as e:
    logger.error(f"❌ Configuration error: {e}")
    # Fallback to development configuration
    config = AppConfig(environment='development', debug=True)
    logger.warning("🔧 Using fallback development configuration")

# --- Custom AI Provider Infrastructure ---

class AIProviderMetadata:
    """Metadata for AI provider registration and management."""
    
    def __init__(self, name: str, description: str, version: str = "1.0.0", 
                 author: str = "Unknown", tags: List[str] = None):
        self.name = name
        self.description = description
        self.version = version
        self.author = author
        self.tags = tags or []
        self.created_at = datetime.now()
        self.request_count = 0
        self.error_count = 0
        self.total_latency = 0.0
        self.last_used = None

class AIProviderBase(ABC):
    """
    Abstract base class for custom AI providers.
    All custom providers must inherit from this class and implement the required methods.
    """
    
    def __init__(self, metadata: AIProviderMetadata):
        self.metadata = metadata
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60,
            half_open_max_calls=3,
            success_threshold=2
        )
    
    @abstractmethod
    async def ask(self, prompt: str, **kwargs) -> str:
        """
        Process a prompt and return a response.
        
        Args:
            prompt: The input prompt/question
            **kwargs: Additional parameters (temperature, max_tokens, etc.)
            
        Returns:
            str: The AI response
            
        Raises:
            Exception: If processing fails
        """
        pass
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform a health check for this provider.
        
        Returns:
            Dict containing health status information
        """
        return {
            "status": "healthy",
            "provider": self.metadata.name,
            "circuit_breaker": self.circuit_breaker.get_status(),
            "metrics": {
                "request_count": self.metadata.request_count,
                "error_count": self.metadata.error_count,
                "average_latency": (
                    self.metadata.total_latency / max(self.metadata.request_count, 1)
                ),
                "last_used": self.metadata.last_used.isoformat() if self.metadata.last_used else None
            }
        }
    
    def get_info(self) -> Dict[str, Any]:
        """Get detailed information about this provider."""
        return {
            "name": self.metadata.name,
            "description": self.metadata.description,
            "version": self.metadata.version,
            "author": self.metadata.author,
            "tags": self.metadata.tags,
            "created_at": self.metadata.created_at.isoformat(),
            "statistics": {
                "total_requests": self.metadata.request_count,
                "total_errors": self.metadata.error_count,
                "success_rate": (
                    (self.metadata.request_count - self.metadata.error_count) / 
                    max(self.metadata.request_count, 1) * 100
                ),
                "average_latency_ms": (
                    self.metadata.total_latency * 1000 / 
                    max(self.metadata.request_count, 1)
                ),
                "last_used": self.metadata.last_used.isoformat() if self.metadata.last_used else None
            },
            "circuit_breaker": self.circuit_breaker.get_status()
        }

# --- Built-in Custom Provider Examples ---

class EchoProvider(AIProviderBase):
    """Simple echo provider for testing and demonstration."""
    
    def __init__(self):
        metadata = AIProviderMetadata(
            name="echo",
            description="Echo provider that returns the input prompt with a prefix",
            version="1.0.0",
            author="AdsTable",
            tags=["demo", "testing", "echo"]
        )
        super().__init__(metadata)
    
    async def ask(self, prompt: str, **kwargs) -> str:
        """Echo the prompt back with a prefix."""
        await asyncio.sleep(0.1)  # Simulate processing time
        prefix = kwargs.get('prefix', '[ECHO]')
        return f"{prefix}: {prompt}"

class ReverseProvider(AIProviderBase):
    """Provider that reverses the input prompt."""
    
    def __init__(self):
        metadata = AIProviderMetadata(
            name="reverse",
            description="Reverses the input prompt character by character",
            version="1.0.0",
            author="AdsTable",
            tags=["demo", "text-processing", "reverse"]
        )
        super().__init__(metadata)
    
    async def ask(self, prompt: str, **kwargs) -> str:
        """Reverse the prompt."""
        await asyncio.sleep(0.05)  # Simulate processing time
        return prompt[::-1]

class UppercaseProvider(AIProviderBase):
    """Provider that converts text to uppercase."""
    
    def __init__(self):
        metadata = AIProviderMetadata(
            name="uppercase",
            description="Converts input prompt to uppercase",
            version="1.0.0",
            author="AdsTable",
            tags=["demo", "text-processing", "uppercase"]
        )
        super().__init__(metadata)
    
    async def ask(self, prompt: str, **kwargs) -> str:
        """Convert prompt to uppercase."""
        await asyncio.sleep(0.02)  # Simulate processing time
        return prompt.upper()

class MockAIProvider(AIProviderBase):
    """Mock AI provider for testing purposes."""
    
    def __init__(self):
        metadata = AIProviderMetadata(
            name="mock_ai",
            description="Mock AI provider that generates simple responses based on keywords",
            version="1.1.0",
            author="AdsTable",
            tags=["demo", "ai", "mock", "testing"]
        )
        super().__init__(metadata)
        self.responses = {
            "hello": "Hello! How can I help you today?",
            "weather": "I'm sorry, I don't have access to current weather data.",
            "time": f"The current time is {datetime.now().strftime('%H:%M:%S')}",
            "date": f"Today's date is {datetime.now().strftime('%Y-%m-%d')}",
            "help": "I'm a mock AI. Try asking about: hello, weather, time, date, or anything else!",
        }
    
    async def ask(self, prompt: str, **kwargs) -> str:
        """Generate a mock AI response based on keywords in the prompt."""
        await asyncio.sleep(0.2)  # Simulate AI processing time
        prompt_lower = prompt.lower()
        
        # Check for keywords
        for keyword, response in self.responses.items():
            if keyword in prompt_lower:
                return response
        
        # Default response
        return f"I understand you're asking about: '{prompt}'. This is a mock response for testing purposes."

# --- Provider Registry and Management ---

class AIProviderRegistry:
    """
    Centralized registry for managing custom AI providers with validation, 
    hot-reload, and comprehensive monitoring.
    """
    
    def __init__(self):
        self.providers: Dict[str, AIProviderBase] = {}
        self.provider_configs: Dict[str, Dict[str, Any]] = {}
        self.registry_lock = asyncio.Lock()
        self.hot_reload_enabled = config.enable_hot_reload
        self.last_config_check = time.time()
        self.config_check_interval = 30  # seconds
        
        # Initialize built-in providers
        self._register_builtin_providers()
    
    def _register_builtin_providers(self):
        """Register built-in demonstration providers."""
        builtin_providers = [
            EchoProvider(),
            ReverseProvider(),
            UppercaseProvider(),
            MockAIProvider()
        ]
        
        for provider in builtin_providers:
            self.providers[provider.metadata.name] = provider
            logger.info(f"✅ Built-in provider registered: {provider.metadata.name}")
    
    async def register_provider(self, provider: AIProviderBase, override: bool = False) -> bool:
        """
        Register a custom AI provider with validation.
        
        Args:
            provider: The provider instance to register
            override: Whether to override existing provider with same name
            
        Returns:
            bool: True if registration successful, False otherwise
        """
        async with self.registry_lock:
            provider_name = provider.metadata.name
            
            # Validation
            if not provider_name:
                logger.error("Provider name cannot be empty")
                return False
            
            if not provider_name.isalnum() and '_' not in provider_name:
                logger.error(f"Provider name '{provider_name}' contains invalid characters")
                return False
            
            if provider_name in self.providers and not override:
                logger.error(f"Provider '{provider_name}' already exists. Use override=True to replace.")
                return False
            
            if (len(self.providers) >= config.security.max_custom_providers and 
                provider_name not in self.providers):
                logger.error(f"Maximum number of custom providers ({config.security.max_custom_providers}) reached")
                return False
            
            # Security validation
            if config.security.custom_provider_security:
                if not await self._validate_provider_security(provider):
                    logger.error(f"Provider '{provider_name}' failed security validation")
                    return False
            
            # Register the provider
            old_provider = self.providers.get(provider_name)
            self.providers[provider_name] = provider
            
            # Update metrics
            if config.enable_metrics and METRICS_AVAILABLE:
                if old_provider:
                    logger.info(f"🔄 Provider updated: {provider_name}")
                else:
                    logger.info(f"✅ Provider registered: {provider_name}")
            
            return True
    
    async def unregister_provider(self, provider_name: str) -> bool:
        """
        Unregister a custom AI provider.
        
        Args:
            provider_name: Name of the provider to unregister
            
        Returns:
            bool: True if unregistration successful, False otherwise
        """
        async with self.registry_lock:
            if provider_name not in self.providers:
                logger.warning(f"Provider '{provider_name}' not found for unregistration")
                return False
            
            # Don't allow unregistering built-in providers in production
            builtin_providers = {'echo', 'reverse', 'uppercase', 'mock_ai'}
            if provider_name in builtin_providers and config.environment == 'production':
                logger.error(f"Cannot unregister built-in provider '{provider_name}' in production")
                return False
            
            del self.providers[provider_name]
            self.provider_configs.pop(provider_name, None)
            logger.info(f"🗑️ Provider unregistered: {provider_name}")
            return True
    
    async def get_provider(self, provider_name: str) -> Optional[AIProviderBase]:
        """Get a provider by name."""
        return self.providers.get(provider_name)
    
    def list_providers(self) -> List[str]:
        """List all registered provider names."""
        return list(self.providers.keys())
    
    def get_provider_info(self, provider_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a provider."""
        provider = self.providers.get(provider_name)
        return provider.get_info() if provider else None
    
    async def health_check_all(self) -> Dict[str, Any]:
        """
        Perform comprehensive health check on all registered providers with detailed analytics.
        
        Returns:
            Dict containing comprehensive health status for all providers
        """
        results = {}
        health_summary = {
            "overall_status": "healthy",
            "total_providers": len(self.providers),
            "healthy_providers": 0,
            "degraded_providers": 0,
            "unhealthy_providers": 0,
            "timestamp": datetime.now().isoformat(),
            "check_duration_ms": 0
        }
        
        start_time = time.time()
        
        try:
            # Create tasks for concurrent health checks
            health_tasks = []
            for name, provider in self.providers.items():
                task = asyncio.create_task(
                    self._individual_health_check(name, provider),
                    name=f"health_check_{name}"
                )
                health_tasks.append(task)
            
            # Wait for all health checks with timeout
            completed_results = await asyncio.gather(
                *health_tasks, 
                return_exceptions=True
            )
            
            # Process results
            for i, result in enumerate(completed_results):
                provider_name = list(self.providers.keys())[i]
                
                if isinstance(result, Exception):
                    results[provider_name] = {
                        "status": "error", 
                        "provider": provider_name,
                        "error": str(result),
                        "timestamp": datetime.now().isoformat()
                    }
                    health_summary["unhealthy_providers"] += 1
                else:
                    results[provider_name] = result
                    
                    # Categorize provider health
                    status = result.get("status", "unknown")
                    if status == "healthy":
                        health_summary["healthy_providers"] += 1
                    elif status in ["degraded", "timeout"]:
                        health_summary["degraded_providers"] += 1
                    else:
                        health_summary["unhealthy_providers"] += 1
            
            # Determine overall system health
            if health_summary["unhealthy_providers"] > 0:
                if health_summary["healthy_providers"] == 0:
                    health_summary["overall_status"] = "critical"
                else:
                    health_summary["overall_status"] = "degraded"
            elif health_summary["degraded_providers"] > 0:
                health_summary["overall_status"] = "degraded"
            
            # Calculate additional metrics
            health_summary["health_percentage"] = round(
                (health_summary["healthy_providers"] / max(health_summary["total_providers"], 1)) * 100, 2
            )
            
            health_summary["check_duration_ms"] = round((time.time() - start_time) * 1000, 2)
            
            return {
                "summary": health_summary,
                "providers": results,
                "recommendations": self._generate_health_recommendations(results)
            }
            
        except Exception as e:
            logger.error(f"Health check system error: {e}")
            return {
                "summary": {
                    **health_summary,
                    "overall_status": "system_error",
                    "error": str(e)
                },
                "providers": results
            }
    
    async def _individual_health_check(self, name: str, provider: AIProviderBase) -> Dict[str, Any]:
        """
        Perform individual provider health check with comprehensive metrics.
        
        Args:
            name: Provider name
            provider: Provider instance
            
        Returns:
            Dict containing detailed health information
        """
        try:
            # Basic health check with timeout
            health_result = await asyncio.wait_for(
                provider.health_check(), 
                timeout=10.0
            )
            
            # Enhanced health analysis
            circuit_breaker_status = provider.circuit_breaker.get_status()
            
            # Determine health status based on multiple factors
            status = "healthy"
            
            # Check circuit breaker state
            if circuit_breaker_status["state"] == "OPEN":
                status = "unhealthy"
            elif circuit_breaker_status["state"] == "HALF_OPEN":
                status = "degraded"
            
            # Check success rate
            success_rate = circuit_breaker_status["statistics"]["success_rate_percent"]
            if success_rate < 50:
                status = "unhealthy"
            elif success_rate < 80:
                status = "degraded"
            
            # Check recent activity
            if provider.metadata.last_used:
                time_since_last_use = (datetime.now() - provider.metadata.last_used).total_seconds()
                if time_since_last_use > 3600:  # 1 hour
                    status = "idle"
            
            # Performance scoring
            avg_latency = provider.metadata.total_latency / max(provider.metadata.request_count, 1)
            performance_score = self._calculate_performance_score(avg_latency, success_rate)
            
            enhanced_result = {
                **health_result,
                "status": status,
                "performance_score": performance_score,
                "detailed_metrics": {
                    "circuit_breaker_state": circuit_breaker_status["state"],
                    "success_rate_percent": success_rate,
                    "average_latency_ms": round(avg_latency * 1000, 2),
                    "total_requests": provider.metadata.request_count,
                    "total_errors": provider.metadata.error_count,
                    "time_since_last_use_minutes": round(
                        (datetime.now() - provider.metadata.last_used).total_seconds() / 60, 2
                    ) if provider.metadata.last_used else None
                },
                "health_check_timestamp": datetime.now().isoformat()
            }
            
            return enhanced_result
            
        except asyncio.TimeoutError:
            return {
                "status": "timeout", 
                "provider": name,
                "error": "Health check timed out",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "status": "error", 
                "provider": name, 
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def _calculate_performance_score(self, avg_latency: float, success_rate: float) -> float:
        """
        Calculate comprehensive performance score for a provider.
        
        Args:
            avg_latency: Average latency in seconds
            success_rate: Success rate percentage
            
        Returns:
            float: Performance score (0-100)
        """
        # Base score from success rate
        score = success_rate
        
        # Latency penalty
        if avg_latency > 10:  # 10+ seconds is very slow
            score *= 0.3
        elif avg_latency > 5:  # 5+ seconds is slow
            score *= 0.6
        elif avg_latency > 2:  # 2+ seconds is moderate
            score *= 0.8
        elif avg_latency > 1:  # 1+ second is acceptable
            score *= 0.9
        # Under 1 second gets no penalty
        
        return round(max(0, min(100, score)), 2)
    
    def _generate_health_recommendations(self, results: Dict[str, Any]) -> List[str]:
        """
        Generate actionable health recommendations based on provider status.
        
        Args:
            results: Health check results for all providers
            
        Returns:
            List of recommendation strings
        """
        recommendations = []
        
        unhealthy_providers = [
            name for name, result in results.items() 
            if result.get("status") in ["unhealthy", "error", "timeout"]
        ]
        
        degraded_providers = [
            name for name, result in results.items() 
            if result.get("status") == "degraded"
        ]
        
        if unhealthy_providers:
            recommendations.append(
                f"Investigate unhealthy providers: {', '.join(unhealthy_providers)}"
            )
        
        if degraded_providers:
            recommendations.append(
                f"Monitor degraded providers: {', '.join(degraded_providers)}"
            )
        
        # Check for high latency providers
        high_latency_providers = [
            name for name, result in results.items()
            if result.get("detailed_metrics", {}).get("average_latency_ms", 0) > 5000
        ]
        
        if high_latency_providers:
            recommendations.append(
                f"Optimize latency for providers: {', '.join(high_latency_providers)}"
            )
        
        # Check for low success rate providers
        low_success_providers = [
            name for name, result in results.items()
            if result.get("detailed_metrics", {}).get("success_rate_percent", 100) < 80
        ]
        
        if low_success_providers:
            recommendations.append(
                f"Improve reliability for providers: {', '.join(low_success_providers)}"
            )
        
        if not recommendations:
            recommendations.append("All providers are operating normally")
        
        return recommendations
    
    async def _validate_provider_security(self, provider: AIProviderBase) -> bool:
        """
        Validate provider security with comprehensive checks.
        
        Args:
            provider: Provider instance to validate
            
        Returns:
            bool: True if provider passes security validation
        """
        try:
            # Check if provider has required methods
            if not hasattr(provider, 'ask') or not callable(provider.ask):
                logger.warning(f"Provider {provider.metadata.name} missing ask method")
                return False
            
            # Test with safe input
            test_result = await asyncio.wait_for(
                provider.ask("test", max_tokens=10), 
                timeout=config.security.provider_execution_timeout
            )
            
            # Basic response validation
            if not isinstance(test_result, str):
                logger.warning(f"Provider {provider.metadata.name} returned non-string response")
                return False
            
            if len(test_result) > 10000:  # Prevent excessively long responses
                logger.warning(f"Provider {provider.metadata.name} returned excessively long response")
                return False
            
            # Check for potentially dangerous patterns
            dangerous_patterns = ['<script', 'javascript:', 'data:', 'vbscript:', 'onload=']
            test_result_lower = test_result.lower()
            
            for pattern in dangerous_patterns:
                if pattern in test_result_lower:
                    logger.warning(f"Provider {provider.metadata.name} returned potentially dangerous content")
                    return False
            
            return True
            
        except asyncio.TimeoutError:
            logger.warning(f"Provider {provider.metadata.name} timed out during security validation")
            return False
        except Exception as e:
            logger.warning(f"Provider {provider.metadata.name} failed security validation: {e}")
            return False
    
    async def hot_reload_check(self):
        """
        Check for configuration changes and reload providers if necessary.
        Supports hot-reloading of provider configurations without service restart.
        """
        if not self.hot_reload_enabled:
            return
        
        current_time = time.time()
        if current_time - self.last_config_check < self.config_check_interval:
            return
        
        self.last_config_check = current_time
        
        # Check for configuration file changes
        config_path = Path("custom_providers.yaml")
        if config_path.exists():
            try:
                mtime = config_path.stat().st_mtime
                if hasattr(self, '_last_config_mtime') and mtime > self._last_config_mtime:
                    await self._load_providers_from_config(config_path)
                    self._last_config_mtime = mtime
            except Exception as e:
                logger.error(f"Error during hot reload check: {e}")
    
    async def _load_providers_from_config(self, config_path: Path):
        """
        Load providers from configuration file with validation and error handling.
        
        Args:
            config_path: Path to configuration file
        """
        logger.info(f"🔄 Hot reloading providers from {config_path}")
        
        try:
            if not YAML_AVAILABLE:
                logger.warning("YAML not available for configuration loading")
                return
            
            # Read and parse configuration
            with open(config_path, 'r', encoding='utf-8') as f:
                provider_configs = yaml.safe_load(f)
            
            if not isinstance(provider_configs, dict):
                logger.error("Invalid configuration format - expected dictionary")
                return
            
            # Process provider configurations
            for provider_name, provider_config in provider_configs.items():
                try:
                    await self._process_provider_config(provider_name, provider_config)
                except Exception as e:
                    logger.error(f"Failed to process provider config for {provider_name}: {e}")
            
            logger.info(f"✅ Hot reload completed successfully")
            
        except Exception as e:
            logger.error(f"Hot reload failed: {e}")
    
    async def _process_provider_config(self, name: str, config: Dict[str, Any]):
        """
        Process individual provider configuration for hot reload.
        
        Args:
            name: Provider name
            config: Provider configuration dictionary
        """
        # This is a placeholder for configuration-based provider loading
        # In a real implementation, this would:
        # 1. Validate the configuration
        # 2. Dynamically load provider modules
        # 3. Create provider instances
        # 4. Register providers with validation
        
        logger.info(f"Processing config for provider: {name}")
        # Implementation depends on specific configuration format and requirements

# Initialize global provider registry
provider_registry = AIProviderRegistry()

# --- Resource Management and Connection Pooling ---

class ResourceManager:
    """
    Comprehensive resource management system for connection pooling, 
    semaphores, and service coordination.
    """
    
    def __init__(self):
        self.startup_time = time.time()
        self.redis_client: Optional[Redis] = None
        self.ai_semaphore: Optional[asyncio.Semaphore] = None
        self.request_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "cache_hits": 0,
            "average_latency_ms": 0
        })
        self.cost_tracker: Dict[str, float] = defaultdict(float)
        self.active_connections = 0
        self._initialized = False
    
    async def initialize(self):
        """Initialize all resources with proper error handling and validation."""
        if self._initialized:
            return
        
        logger.info("🚀 Initializing resource manager...")
        
        try:
            # Initialize Redis connection
            if config.enable_cache and REDIS_AVAILABLE:
                await self._initialize_redis()
            
            # Initialize AI request semaphore
            self.ai_semaphore = asyncio.Semaphore(config.ai.max_concurrent_requests)
            
            # Validate resource initialization
            await self._validate_resources()
            
            self._initialized = True
            logger.info("✅ Resource manager initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Resource manager initialization failed: {e}")
            raise
    
    async def _initialize_redis(self):
        """Initialize Redis connection with comprehensive configuration."""
        try:
            redis_config = config.redis
            
            # Create Redis connection with full configuration
            connection_kwargs = {
                'max_connections': redis_config.max_connections,
                'socket_timeout': redis_config.socket_timeout,
                'socket_connect_timeout': redis_config.socket_connect_timeout,
                'socket_keepalive': redis_config.socket_keepalive,
                'health_check_interval': redis_config.health_check_interval,
                'retry_on_timeout': redis_config.retry_on_timeout,
                'retry_on_error': redis_config.retry_on_error,
                'encoding': redis_config.encoding,
                'decode_responses': redis_config.decode_responses,
                'client_name': redis_config.client_name,
                'db': redis_config.db
            }
            
            # Add authentication if provided
            if redis_config.username:
                connection_kwargs['username'] = redis_config.username
            if redis_config.password:
                connection_kwargs['password'] = redis_config.password
            
            # Add SSL configuration if needed
            if redis_config.url.startswith('rediss://'):
                connection_kwargs.update({
                    'ssl_cert_reqs': redis_config.ssl_cert_reqs,
                    'ssl_certfile': redis_config.ssl_certfile,
                    'ssl_keyfile': redis_config.ssl_keyfile,
                    'ssl_ca_certs': redis_config.ssl_ca_certs,
                    'ssl_check_hostname': redis_config.ssl_check_hostname
                })
            
            # Create Redis client
            self.redis_client = Redis.from_url(
                redis_config.url,
                **{k: v for k, v in connection_kwargs.items() if v is not None}
            )
            
            # Test connection
            await self.redis_client.ping()
            logger.info("✅ Redis connection established successfully")
            
        except Exception as e:
            logger.warning(f"⚠️ Redis initialization failed: {e}. Continuing without cache.")
            self.redis_client = None
    
    async def _validate_resources(self):
        """Validate that all critical resources are properly initialized."""
        validations = []
        
        # Check AI semaphore
        if self.ai_semaphore is None:
            validations.append("AI semaphore not initialized")
        
        # Check Redis if caching is enabled
        if config.enable_cache and self.redis_client is None:
            validations.append("Redis cache unavailable but caching is enabled")
        
        if validations:
            logger.warning(f"Resource validation warnings: {', '.join(validations)}")
        else:
            logger.info("✅ All resources validated successfully")
    
    def get_ai_semaphore(self) -> asyncio.Semaphore:
        """Get AI request semaphore for concurrent request limiting."""
        if not self.ai_semaphore:
            # Fallback semaphore if not properly initialized
            return asyncio.Semaphore(config.ai.max_concurrent_requests)
        return self.ai_semaphore
    
    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check for all managed resources."""
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": round(time.time() - self.startup_time, 2),
            "resources": {}
        }
        
        try:
            # Check Redis health
            if self.redis_client:
                try:
                    redis_start = time.time()
                    await self.redis_client.ping()
                    redis_latency = (time.time() - redis_start) * 1000
                    
                    health_status["resources"]["redis"] = {
                        "status": "healthy",
                        "latency_ms": round(redis_latency, 2),
                        "connection_pool_available": True
                    }
                except Exception as e:
                    health_status["resources"]["redis"] = {
                        "status": "unhealthy",
                        "error": str(e)
                    }
                    health_status["status"] = "degraded"
            else:
                health_status["resources"]["redis"] = {
                    "status": "disabled",
                    "reason": "Redis not configured or unavailable"
                }
            
            # Check AI semaphore
            if self.ai_semaphore:
                available_permits = self.ai_semaphore._value
                health_status["resources"]["ai_semaphore"] = {
                    "status": "healthy",
                    "available_permits": available_permits,
                    "max_permits": config.ai.max_concurrent_requests
                }
                
                if available_permits == 0:
                    health_status["status"] = "busy"
            else:
                health_status["resources"]["ai_semaphore"] = {
                    "status": "error",
                    "error": "Semaphore not initialized"
                }
                health_status["status"] = "unhealthy"
            
            # Add system statistics
            health_status["statistics"] = {
                "total_requests": sum(stats["total_requests"] for stats in self.request_stats.values()),
                "total_errors": sum(stats["failed_requests"] for stats in self.request_stats.values()),
                "total_cost_usd": round(sum(self.cost_tracker.values()), 4),
                "active_connections": self.active_connections,
                "providers_registered": len(provider_registry.list_providers())
            }
            
        except Exception as e:
            health_status["status"] = "error"
            health_status["error"] = str(e)
        
        return health_status
    
    async def cleanup(self):
        """Clean up all resources properly during shutdown."""
        logger.info("🧹 Cleaning up resources...")
        
        try:
            # Close Redis connections
            if self.redis_client:
                await self.redis_client.close()
                logger.info("✅ Redis connections closed")
            
            # Reset semaphores
            self.ai_semaphore = None
            
            # Clear statistics
            self.request_stats.clear()
            self.cost_tracker.clear()
            
            self._initialized = False
            logger.info("✅ Resource cleanup completed")
            
        except Exception as e:
            logger.error(f"❌ Resource cleanup failed: {e}")

# Initialize global resource manager
resources = ResourceManager()

# --- Advanced Exception Handling ---

class AIServiceException(Exception):
    """Base exception for AI service operations."""
    
    def __init__(self, message: str, error_code: str = None, details: Dict[str, Any] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "UNKNOWN_ERROR"
        self.details = details or {}
        self.timestamp = datetime.now().isoformat()

class ProviderException(AIServiceException):
    """Exception for AI provider-related errors."""
    
    def __init__(self, provider: str, message: str, error_code: str = None, details: Dict[str, Any] = None):
        super().__init__(message, error_code, details)
        self.provider = provider

class CacheException(AIServiceException):
    """Exception for cache-related errors."""
    pass

class ConfigurationException(AIServiceException):
    """Exception for configuration-related errors."""
    pass

class RateLimitException(AIServiceException):
    """Exception for rate limiting violations."""
    
    def __init__(self, message: str, retry_after: int = None, details: Dict[str, Any] = None):
        super().__init__(message, "RATE_LIMIT_EXCEEDED", details)
        self.retry_after = retry_after

# --- Rate Limiting Decorator ---

def rate_limit(requests_per_minute: int = 60):
    """
    Decorator for endpoint-level rate limiting with Redis backend.
    
    Args:
        requests_per_minute: Maximum requests allowed per minute
    
    Returns:
        Decorated function with rate limiting
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request object
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if not request:
                # If no request object found, proceed without rate limiting
                return await func(*args, **kwargs)
            
            # Create rate limiter instance
            rate_limiter = ModernRateLimiter(use_redis=config.enable_cache and resources.redis_client)
            
            # Get client identifier
            client_ip = request.client.host if request.client else "unknown"
            
            # Check rate limit
            is_allowed = await rate_limiter.is_allowed(
                key=f"endpoint:{func.__name__}:{client_ip}",
                limit=requests_per_minute,
                window=60  # 1 minute window
            )
            
            if not is_allowed:
                remaining = rate_limiter.get_remaining(
                    f"endpoint:{func.__name__}:{client_ip}",
                    requests_per_minute,
                    60
                )
                
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "Rate limit exceeded",
                        "limit": requests_per_minute,
                        "window": "1 minute",
                        "remaining": remaining,
                        "retry_after": 60
                    }
                )
            
            # Proceed with function execution
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator

# --- Background Task Management ---

class BackgroundTaskManager:
    """
    Advanced background task management system for periodic maintenance,
    monitoring, and optimization tasks.
    """
    
    def __init__(self):
        self.tasks: List[asyncio.Task] = []
        self.task_configs: Dict[str, Dict[str, Any]] = {}
        self.is_running = False
        self._shutdown_event = asyncio.Event()
    
    async def start(self):
        """Start all background tasks with proper error handling."""
        if self.is_running:
            return
        
        logger.info("🔄 Starting background task manager...")
        
        try:
            # Register default tasks
            await self._register_default_tasks()
            
            # Start all registered tasks
            for task_name, task_config in self.task_configs.items():
                task = asyncio.create_task(
                    self._run_periodic_task(task_name, task_config),
                    name=task_name
                )
                self.tasks.append(task)
                logger.info(f"✅ Started background task: {task_name}")
            
            self.is_running = True
            logger.info(f"✅ Background task manager started with {len(self.tasks)} tasks")
            
        except Exception as e:
            logger.error(f"❌ Background task manager startup failed: {e}")
            raise
    
    async def _register_default_tasks(self):
        """Register default system maintenance tasks."""
        self.task_configs = {
            "provider_health_monitor": {
                "function": self._monitor_provider_health,
                "interval": 30,  # seconds
                "description": "Monitor provider health and circuit breaker status"
            },
            "cache_cleanup": {
                "function": self._cleanup_expired_cache,
                "interval": 300,  # 5 minutes
                "description": "Clean up expired cache entries"
            },
            "metrics_collector": {
                "function": self._collect_system_metrics,
                "interval": 60,  # 1 minute
                "description": "Collect and update system metrics"
            },
            "cost_tracker": {
                "function": self._track_costs,
                "interval": 120,  # 2 minutes
                "description": "Track and analyze AI usage costs"
            },
            "hot_reload_checker": {
                "function": self._check_hot_reload,
                "interval": 30,  # 30 seconds
                "description": "Check for configuration changes for hot reload"
            }
        }
    
    async def _run_periodic_task(self, task_name: str, task_config: Dict[str, Any]):
        """
        Run a periodic background task with error handling and logging.
        
        Args:
            task_name: Name of the task
            task_config: Task configuration dictionary
        """
        task_function = task_config["function"]
        interval = task_config["interval"]
        
        logger.info(f"🔄 Starting periodic task: {task_name} (interval: {interval}s)")
        
        while not self._shutdown_event.is_set():
            try:
                start_time = time.time()
                await task_function()
                execution_time = time.time() - start_time
                
                if execution_time > interval * 0.8:  # Warn if task takes > 80% of interval
                    logger.warning(
                        f"⚠️ Task {task_name} took {execution_time:.2f}s "
                        f"(interval: {interval}s) - consider optimization"
                    )
                
                # Wait for next interval or shutdown
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(), 
                        timeout=interval
                    )
                    break  # Shutdown requested
                except asyncio.TimeoutError:
                    continue  # Normal interval timeout, continue loop
                
            except asyncio.CancelledError:
                logger.info(f"🛑 Background task cancelled: {task_name}")
                break
            except Exception as e:
                logger.error(f"❌ Error in background task {task_name}: {e}")
                # Continue running despite errors, but add exponential backoff
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(), 
                        timeout=min(interval * 2, 300)  # Max 5 minute backoff
                    )
                    break
                except asyncio.TimeoutError:
                    continue
        
        logger.info(f"✅ Background task stopped: {task_name}")
    
    async def _monitor_provider_health(self):
        """Monitor provider health and update circuit breaker status."""
        try:
            health_results = await provider_registry.health_check_all()
            
            # Log health summary
            summary = health_results.get("summary", {})
            if summary.get("overall_status") != "healthy":
                logger.warning(
                    f"⚠️ System health: {summary.get('overall_status')} "
                    f"({summary.get('healthy_providers', 0)}/{summary.get('total_providers', 0)} healthy)"
                )
            
            # Update metrics if available
            if config.enable_metrics and METRICS_AVAILABLE:
                for provider_name, result in health_results.get("providers", {}).items():
                    status = result.get("status", "unknown")
                    if status == "healthy":
                        # Update provider-specific metrics
                        pass
            
        except Exception as e:
            logger.error(f"Provider health monitoring failed: {e}")
    
    async def _cleanup_expired_cache(self):
        """Clean up expired cache entries to maintain performance."""
        if not resources.redis_client:
            return
        
        try:
            deleted_count = await AdvancedCache.cleanup_expired_keys(
                resources.redis_client,
                pattern="ai_cache:*",
                batch_size=100
            )
            
            if deleted_count > 0:
                logger.info(f"🧹 Cleaned up {deleted_count} expired cache entries")
            
        except Exception as e:
            logger.error(f"Cache cleanup failed: {e}")
    
    async def _collect_system_metrics(self):
        """Collect and update system performance metrics."""
        try:
            # Update request statistics
            total_requests = sum(stats["total_requests"] for stats in resources.request_stats.values())
            total_errors = sum(stats["failed_requests"] for stats in resources.request_stats.values())
            
            # Update Prometheus metrics if available
            if config.enable_metrics and METRICS_AVAILABLE:
                # Update gauge metrics
                ACTIVE_CONNECTIONS.set(resources.active_connections)
                
                # Calculate error rate
                error_rate = (total_errors / max(total_requests, 1)) * 100
                if error_rate > 10:  # Log high error rates
                    logger.warning(f"⚠️ High error rate detected: {error_rate:.2f}%")
            
        except Exception as e:
            logger.error(f"Metrics collection failed: {e}")
    
    async def _track_costs(self):
        """Track and analyze AI usage costs with budget monitoring."""
        try:
            total_cost = sum(resources.cost_tracker.values())
            daily_budget = config.ai.cost_budget_daily
            
            # Check budget thresholds
            if total_cost > daily_budget * config.ai.cost_alert_threshold:
                budget_percentage = (total_cost / daily_budget) * 100
                logger.warning(
                    f"💰 Cost alert: ${total_cost:.4f} spent "
                    f"({budget_percentage:.1f}% of daily budget)"
                )
            
            # Log cost summary
            if total_cost > 0:
                logger.info(f"💰 Total costs: ${total_cost:.4f} (Budget: ${daily_budget:.2f})")
            
        except Exception as e:
            logger.error(f"Cost tracking failed: {e}")
    
    async def _check_hot_reload(self):
        """Check for configuration changes and trigger hot reload if needed."""
        try:
            await provider_registry.hot_reload_check()
        except Exception as e:
            logger.error(f"Hot reload check failed: {e}")
    
    async def stop(self):
        """Stop all background tasks gracefully."""
        if not self.is_running:
            return
        
        logger.info("🛑 Stopping background task manager...")
        
        # Signal shutdown to all tasks
        self._shutdown_event.set()
        
        # Wait for tasks to complete gracefully
        if self.tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self.tasks, return_exceptions=True),
                    timeout=30.0  # 30 second grace period
                )
            except asyncio.TimeoutError:
                logger.warning("⚠️ Some background tasks did not stop gracefully, cancelling...")
                for task in self.tasks:
                    if not task.done():
                        task.cancel()
        
        self.tasks.clear()
        self.is_running = False
        logger.info("✅ Background task manager stopped")
    
    def get_task_statistics(self) -> Dict[str, Any]:
        """Get statistics about running background tasks."""
        return {
            "total_tasks": len(self.tasks),
            "running_tasks": len([t for t in self.tasks if not t.done()]),
            "completed_tasks": len([t for t in self.tasks if t.done() and not t.cancelled()]),
            "cancelled_tasks": len([t for t in self.tasks if t.cancelled()]),
            "failed_tasks": len([t for t in self.tasks if t.done() and t.exception()]),
            "manager_status": "running" if self.is_running else "stopped",
            "task_configs": list(self.task_configs.keys())
        }

# Initialize global background task manager
background_manager = BackgroundTaskManager()

# Create global rate limiter instance
rate_limiter = ModernRateLimiter(use_redis=config.enable_cache and REDIS_AVAILABLE)

logger.info("🎯 Core infrastructure components initialized successfully")
logger.info(f"📋 Configuration: {config.app_name} v{config.version} ({config.environment})")
logger.info(f"🔧 Features: Cache={config.enable_cache}, Metrics={config.enable_metrics}, Custom Providers={config.enable_custom_providers}")