# main.py - Next-gen AI Aggregator Service: Cost-optimized, High-performance, Production-ready
from __future__ import annotations
import logging
import json
import os
import time
import asyncio
import gzip
import pickle
from contextlib import asynccontextmanager
from packaging.version import Version 
from functools import lru_cache, wraps
from typing import Any, Dict, List, Optional, Union, AsyncGenerator, Callable
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import hashlib
import yaml
import aiofiles
from redis.asyncio import Redis
#import aioredis
from dotenv import load_dotenv

# FastAPI and middleware imports
from fastapi import (
    FastAPI, HTTPException, Query, Body, Depends, Request, 
    BackgroundTasks, status
)
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, ConfigDict, field_validator, computed_field
from fastapi.requests import Request

# Database and async imports
from sqlalchemy.ext.asyncio import AsyncSession

# Rate limiting and monitoring
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# Prometheus metrics (free monitoring solution)
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
    logger.warning("Prometheus metrics not available, install prometheus_client for monitoring")

# Import business logic modules
from services.ai_async_client import AIAsyncClient
from product_schema import Product, ApiResponse
from models import StandardizedProduct
from database import create_db_and_tables, get_session
from data_discoverer import discover_and_extract_data
from data_parser import parse_and_standardize
from data_storage import store_standardized_data
from data_search import search_and_filter_products

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

load_dotenv()

# --- Enhanced Configuration with Environment Optimization ---
@dataclass
class AppConfig:
    """Centralized configuration with validation and optimization"""
    config_reload_interval: int = int(os.getenv('CONFIG_RELOAD_INTERVAL', '300'))
    max_concurrent_ai_requests: int = int(os.getenv('MAX_CONCURRENT_AI_REQUESTS', '15'))
    redis_url: str = os.getenv('REDIS_URL', 'redis://localhost:6379')
    ai_request_timeout: int = int(os.getenv('AI_REQUEST_TIMEOUT', '45'))
    enable_cache: bool = os.getenv('ENABLE_CACHE', 'true').lower() == 'true'
    enable_compression: bool = os.getenv('ENABLE_COMPRESSION', 'true').lower() == 'true'
    enable_metrics: bool = METRICS_AVAILABLE and os.getenv('ENABLE_METRICS', 'true').lower() == 'true'
    cache_ttl_short: int = int(os.getenv('CACHE_TTL_SHORT', '900'))  # 15 minutes
    cache_ttl_long: int = int(os.getenv('CACHE_TTL_LONG', '3600'))   # 1 hour
    max_prompt_length: int = int(os.getenv('MAX_PROMPT_LENGTH', '32000'))
    free_tier_limits: Dict[str, int] = field(default_factory=lambda: {
        'openai': 3,      # Free tier daily limit
        'huggingface': 1000,  # Higher free tier
        'together': 25,   # Good free tier
        'ollama': 999999, # Unlimited local
    })

config = AppConfig()

# --- Global Resource Management ---
class ResourceManager:
    """Centralized resource management with proper cleanup"""
    def __init__(self):
        self.ai_config_cache: Optional[Dict[str, Any]] = None
        self.ai_client_instance: Optional[AIAsyncClient] = None
        self.redis_client: Optional[Redis] = None
        self.config_last_modified: Optional[float] = None
        self.ai_semaphore: Optional[asyncio.Semaphore] = None
        self.circuit_breakers: Dict[str, 'CircuitBreaker'] = {}
        
    async def cleanup(self):
        """Cleanup all resources"""
        if self.ai_client_instance:
            await self.ai_client_instance.aclose()
        if self.redis_client:
            await self.redis_client.close()

resources = ResourceManager()

# --- Circuit Breaker Pattern for AI Provider Resilience ---
@dataclass
class CircuitBreaker:
    """Circuit breaker for AI provider failure handling"""
    failure_threshold: int = 5
    recovery_timeout: int = 60
    failure_count: int = 0
    last_failure_time: Optional[float] = None
    state: str = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def is_request_allowed(self) -> bool:
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
        self.failure_count = 0
        self.state = "CLOSED"
    
    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"

# --- Advanced Caching with Compression ---
class AdvancedCache:
    """High-performance cache with compression and smart TTL"""
    
    @staticmethod
    def compress_data(data: Any) -> bytes:
        """Compress data using gzip for storage efficiency"""
        if not config.enable_compression:
            return pickle.dumps(data)
        return gzip.compress(pickle.dumps(data))
    
    @staticmethod
    def decompress_data(data: bytes) -> Any:
        """Decompress data"""
        if not config.enable_compression:
            return pickle.loads(data)
        return pickle.loads(gzip.decompress(data))
    
    @staticmethod
    async def get_cached(redis_client: Redis, key: str) -> Optional[Any]:
        """Get and decompress cached data"""
        try:
            data = await redis_client.get(key)
            if data:
                if config.enable_metrics:
                    CACHE_HITS.labels(cache_type='redis').inc()
                return AdvancedCache.decompress_data(data)
        except Exception as e:
            logger.warning(f"Cache read error: {e}")
        return None
    
    @staticmethod
    async def set_cached(redis_client: Redis, key: str, value: Any, ttl: int):
        """Compress and cache data"""
        try:
            compressed_data = AdvancedCache.compress_data(value)
            await redis_client.setex(key, ttl, compressed_data)
        except Exception as e:
            logger.warning(f"Cache write error: {e}")

# --- Token Optimization Utilities ---
class TokenOptimizer:
    """Advanced token counting and optimization"""
    
    @staticmethod
    def estimate_tokens(text: str, provider: str = "openai") -> int:
        """Estimate token count for different providers"""
        # Rough estimation: 1 token ≈ 4 characters for most models
        base_estimate = len(text) // 4
        
        # Provider-specific adjustments
        multipliers = {
            "openai": 1.0,
            "moonshot": 1.0,
            "together": 0.9,  # Slightly more efficient
            "huggingface": 0.8,
            "ollama": 0.7,    # Local, more efficient
        }
        
        return int(base_estimate * multipliers.get(provider, 1.0))
    
    @staticmethod
    def optimize_prompt(prompt: str, max_tokens: int = 4000) -> str:
        """Optimize prompt to reduce token usage"""
        estimated_tokens = TokenOptimizer.estimate_tokens(prompt)
        
        if estimated_tokens <= max_tokens:
            return prompt
        
        # Simple optimization: truncate from middle, keep beginning and end
        reduction_ratio = max_tokens / estimated_tokens
        keep_length = int(len(prompt) * reduction_ratio)
        
        if keep_length < 200:  # Minimum viable prompt
            return prompt[:200] + "..."
        
        # Keep first 60% and last 40%
        first_part = prompt[:int(keep_length * 0.6)]
        last_part = prompt[-int(keep_length * 0.4):]
        
        return f"{first_part}...[optimized]...{last_part}"

# --- Provider-specific streaming parsers (Enhanced) ---
STREAMING_PARSERS = {
    'openai': lambda chunk: _parse_openai_chunk(chunk),
    'moonshot': lambda chunk: _parse_openai_chunk(chunk),
    'together': lambda chunk: _parse_together_chunk(chunk),
    'huggingface': lambda chunk: _parse_huggingface_chunk(chunk),
    'ollama': lambda chunk: _parse_ollama_chunk(chunk),
    'minimax': lambda chunk: _parse_minimax_chunk(chunk),
    'claude': lambda chunk: _parse_claude_chunk(chunk),
}

def _parse_openai_chunk(chunk: str) -> Optional[str]:
    """Enhanced OpenAI/Moonshot parser with error recovery"""
    try:
        if chunk.startswith('data: '):
            chunk = chunk[6:]
        if chunk.strip() in ['[DONE]', '']:
            return None
        data = json.loads(chunk)
        return data.get('choices', [{}])[0].get('delta', {}).get('content', '')
    except (json.JSONDecodeError, KeyError, IndexError):
        return None

def _parse_together_chunk(chunk: str) -> Optional[str]:
    try:
        data = json.loads(chunk)
        return data.get('choices', [{}])[0].get('text', '')
    except (json.JSONDecodeError, KeyError, IndexError):
        return None

def _parse_huggingface_chunk(chunk: str) -> Optional[str]:
    try:
        data = json.loads(chunk)
        return data.get('token', {}).get('text', '')
    except (json.JSONDecodeError, KeyError, IndexError):
        return None

def _parse_ollama_chunk(chunk: str) -> Optional[str]:
    try:
        data = json.loads(chunk)
        return data.get('response', '')
    except (json.JSONDecodeError, KeyError, IndexError):
        return None

def _parse_minimax_chunk(chunk: str) -> Optional[str]:
    try:
        data = json.loads(chunk)
        return data.get('choices', [{}])[0].get('delta', '')
    except (json.JSONDecodeError, KeyError, IndexError):
        return None

def _parse_claude_chunk(chunk: str) -> Optional[str]:
    """New parser for Claude/Anthropic"""
    try:
        data = json.loads(chunk)
        return data.get('completion', '')
    except (json.JSONDecodeError, KeyError, IndexError):
        return None

# --- Enhanced Resource Getters ---
async def get_redis_client() -> Optional[Redis]:
    """Get Redis client with connection pooling"""
    if resources.redis_client is None:
        try:
            resources.redis_client = aioredis.from_url(
                config.redis_url,
                encoding="utf-8",
                decode_responses=False,  # Handle binary data for compression
                max_connections=20
            )
            await resources.redis_client.ping()
            logger.info("Redis connection established with compression support")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}, proceeding without cache")
            resources.redis_client = None
    return resources.redis_client

@lru_cache(maxsize=1)
def get_config_path() -> Path:
    return Path("ai_integrations.yaml")

async def load_ai_config(force_reload: bool = False) -> Dict[str, Any]:
    """Load AI configuration with enhanced validation"""
    config_path = get_config_path()
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file {config_path} not found")

    current_mtime = config_path.stat().st_mtime
    if (not force_reload and resources.ai_config_cache and 
        resources.config_last_modified == current_mtime):
        return resources.ai_config_cache

    try:
        async with aiofiles.open(config_path, mode='r', encoding='utf-8') as f:
            content = await f.read()
        cfg = yaml.safe_load(content)

        # Enhanced environment variable substitution
        for provider, settings in cfg.items():
            if not isinstance(settings, dict):
                continue
            
            # Add default free tier settings
            if provider in config.free_tier_limits:
                settings.setdefault('daily_limit', config.free_tier_limits[provider])
                settings.setdefault('priority', 'high' if provider == 'ollama' else 'medium')
            
            for key, value in settings.items():
                if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                    env_key = value[2:-1]
                    env_value = os.getenv(env_key)
                    if env_value is None:
                        logger.warning(f"Environment variable {env_key} not found for {provider}.{key}")
                        continue
                    cfg[provider][key] = env_value

        resources.ai_config_cache = cfg
        resources.config_last_modified = current_mtime
        logger.info(f"AI configuration loaded with {len(cfg)} providers")
        return cfg

    except (yaml.YAMLError, ValueError) as e:
        logger.error(f"Failed to load AI configuration: {e}")
        raise RuntimeError(f"Configuration error: {e}")

def get_ai_semaphore() -> asyncio.Semaphore:
    """Get AI request semaphore"""
    if resources.ai_semaphore is None:
        resources.ai_semaphore = asyncio.Semaphore(config.max_concurrent_ai_requests)
    return resources.ai_semaphore

async def get_ai_client() -> AIAsyncClient:
    """Get AI client with circuit breaker initialization"""
    ai_config = await load_ai_config()
    if resources.ai_client_instance is None:
        resources.ai_client_instance = AIAsyncClient(ai_config)
        
        # Initialize circuit breakers for each provider
        for provider in ai_config.keys():
            resources.circuit_breakers[provider] = CircuitBreaker()
        
        logger.info(f"AI client initialized with {len(ai_config)} providers")
    return resources.ai_client_instance

def generate_cache_key(prefix: str, *args, **kwargs) -> str:
    """Generate optimized cache key"""
    key_data = f"{prefix}:{':'.join(map(str, args))}:{':'.join(f'{k}={v}' for k, v in sorted(kwargs.items()))}"
    return hashlib.sha256(key_data.encode()).hexdigest()[:32]  # Shorter keys

# --- Performance Monitoring Decorator ---
def monitor_performance(func_name: str):
    """Decorator for performance monitoring"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                if config.enable_metrics:
                    REQUEST_DURATION.observe(time.time() - start_time)
                return result
            except Exception as e:
                if config.enable_metrics:
                    REQUEST_COUNT.labels(provider=kwargs.get('provider', 'unknown'), status='error').inc()
                raise
        return wrapper
    return decorator

# --- Enhanced Pydantic Models ---
class AIRequest(BaseModel):
    """Enhanced AI request with optimization features"""
    prompt: str
    provider: str = "ollama"  # Default to free local option
    max_tokens: Optional[int] = None
    temperature: float = 0.7
    use_cache: bool = True
    optimize_tokens: bool = True
    priority: str = "medium"  # low, medium, high
    
    model_config = ConfigDict(frozen=True)

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Prompt cannot be empty")
        if len(v) > config.max_prompt_length:
            raise ValueError(f"Prompt too long (max {config.max_prompt_length} characters)")
        return v.strip()

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        allowed = frozenset([
            "openai", "moonshot", "together", "huggingface", 
            "ollama", "claude", "minimax", "local"
        ])
        if v not in allowed:
            raise ValueError(f"Provider must be one of: {list(allowed)}")
        return v

    @computed_field
    @property
    def estimated_cost(self) -> float:
        """Estimate request cost"""
        token_count = TokenOptimizer.estimate_tokens(self.prompt, self.provider)
        # Cost per 1K tokens (USD)
        costs = {
            "openai": 0.03,
            "claude": 0.015,
            "together": 0.008,
            "moonshot": 0.012,
            "huggingface": 0.0,  # Free tier
            "ollama": 0.0,      # Local
        }
        return (token_count / 1000) * costs.get(self.provider, 0.01)

class IngestionRequest(BaseModel):
    """Enhanced ingestion request"""
    source_identifier: str
    category: str
    use_cache: bool = True
    priority: str = "medium"
    compression_level: int = 6  # gzip compression level
    
    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        allowed = frozenset([
            "electricity_plan", "mobile_plan", "internet_plan", 
            "broadband_plan", "energy_plan", "telecom_plan"
        ])
        if v not in allowed:
            raise ValueError(f"Category must be one of: {list(allowed)}")
        return v

class HealthResponse(BaseModel):
    """Comprehensive health response"""
    status: str
    version: str
    timestamp: datetime
    ai_client_ready: bool
    ai_providers_status: Dict[str, str]
    redis_available: bool
    database_connected: bool
    uptime_seconds: float
    cache_hit_rate: float = 0.0
    total_requests: int = 0
    active_connections: int = 0
    
    model_config = ConfigDict(frozen=True)

# --- Application Lifecycle ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Enhanced lifecycle management"""
    start_time = time.time()
    app.state.start_time = start_time
    logger.info("🚀 Starting AI Aggregator Service Pro v3.0.0")

    try:
        # Initialize database
        await create_db_and_tables()
        logger.info("✅ Database initialized")

        # Initialize Redis cache
        if config.enable_cache:
            await get_redis_client()
            logger.info("✅ Cache system ready")

        # Pre-warm AI client
        await get_ai_client()
        logger.info("✅ AI client initialized")

        logger.info("🎉 All services ready!")
        yield

    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
        raise
    finally:
        logger.info("🔄 Shutting down services...")
        await resources.cleanup()
        logger.info("✅ Cleanup completed")

# --- FastAPI Application ---
app = FastAPI(
    title="AI Aggregator Service Pro",
    description="Next-generation AI service with cost optimization and performance focus",
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/docs" if os.getenv('ENVIRONMENT') != 'production' else None,
    redoc_url="/redoc" if os.getenv('ENVIRONMENT') != 'production' else None
)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Middleware stack
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

if config.enable_compression:
    app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv('ALLOWED_ORIGINS', 
                           'http://localhost:3000,http://localhost:8080').split(','),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    max_age=3600,
)

if os.getenv('TRUSTED_HOSTS'):
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=os.getenv('TRUSTED_HOSTS').split(',')
    )

# --- Smart Provider Selection ---
async def select_optimal_provider(request: AIRequest, available_providers: List[str]) -> str:
    """Select optimal provider based on cost, availability, and performance"""
    
    # Filter by circuit breaker status
    healthy_providers = []
    for provider in available_providers:
        if provider in resources.circuit_breakers:
            if resources.circuit_breakers[provider].is_request_allowed():
                healthy_providers.append(provider)
        else:
            healthy_providers.append(provider)
    
    if not healthy_providers:
        raise HTTPException(status_code=503, detail="No healthy AI providers available")
    
    # Priority scoring
    scores = {}
    for provider in healthy_providers:
        score = 0
        
        # Cost optimization (higher score for cheaper/free options)
        if provider in ['ollama', 'huggingface']:
            score += 100  # Free options get highest priority
        elif provider in ['together', 'moonshot']:
            score += 50   # Lower cost options
        else:
            score += 10   # Paid options
        
        # Performance factor
        performance_scores = {
            'ollama': 80,     # Fast local
            'together': 70,   # Good API speed
            'openai': 60,     # Reliable but slower
            'claude': 65,     # Good balance
        }
        score += performance_scores.get(provider, 40)
        
        # Request priority adjustment
        if request.priority == "high" and provider in ['openai', 'claude']:
            score += 30
        elif request.priority == "low" and provider in ['ollama', 'huggingface']:
            score += 40
        
        scores[provider] = score
    
    # Return highest scoring provider
    optimal_provider = max(scores, key=scores.get)
    logger.info(f"Selected provider {optimal_provider} with score {scores[optimal_provider]}")
    return optimal_provider

# --- AI Endpoints ---
@app.post("/ai/ask")
@limiter.limit("50/minute")
@monitor_performance("ai_ask")
async def ai_ask(
    request: Request,
    ai_request: AIRequest,
    background_tasks: BackgroundTasks,
    stream: bool = Query(False, description="Enable streaming response")
):
    """Ultra-optimized AI query with smart provider selection"""
    
    # Optimize prompt if requested
    optimized_prompt = ai_request.prompt
    if ai_request.optimize_tokens:
        optimized_prompt = TokenOptimizer.optimize_prompt(ai_request.prompt)
    
    # Generate cache key
    cache_key = None
    if config.enable_cache and ai_request.use_cache:
        cache_key = generate_cache_key(
            "ai_ask_v2", optimized_prompt, ai_request.provider, 
            ai_request.temperature, ai_request.max_tokens
        )
    
    # Check cache first
    redis_client = await get_redis_client()
    if redis_client and cache_key:
        cached_result = await AdvancedCache.get_cached(redis_client, cache_key)
        if cached_result:
            logger.info("💾 Cache hit for AI request")
            cached_result['cached'] = True
            return cached_result

    # Get AI client and available providers
    ai_client = await get_ai_client()
    ai_config = await load_ai_config()
    
    # Smart provider selection
    if ai_request.provider == "auto":
        selected_provider = await select_optimal_provider(
            ai_request, list(ai_config.keys())
        )
    else:
        selected_provider = ai_request.provider
    
    # Check circuit breaker
    circuit_breaker = resources.circuit_breakers.get(selected_provider)
    if circuit_breaker and not circuit_breaker.is_request_allowed():
        raise HTTPException(
            status_code=503, 
            detail=f"Provider {selected_provider} temporarily unavailable"
        )

    semaphore = get_ai_semaphore()
    async with semaphore:
        try:
            if stream:
                parser = STREAMING_PARSERS.get(selected_provider, STREAMING_PARSERS['openai'])
                
                async def generate_optimized_stream() -> AsyncGenerator[str, None]:
                    buffer = ""
                    token_count = 0
                    
                    async for chunk in ai_client.stream(
                        optimized_prompt,
                        provider=selected_provider,
                        max_tokens=ai_request.max_tokens,
                        temperature=ai_request.temperature
                    ):
                        content = parser(chunk)
                        if content:
                            buffer += content
                            token_count += len(content.split())
                            yield content
                    
                    # Record metrics
                    if config.enable_metrics:
                        TOKEN_USAGE.labels(provider=selected_provider).inc(token_count)
                        REQUEST_COUNT.labels(provider=selected_provider, status='success').inc()
                    
                    # Cache complete response
                    if cache_key and buffer:
                        background_tasks.add_task(
                            _cache_ai_response, cache_key, {
                                "provider": selected_provider,
                                "prompt": optimized_prompt,
                                "answer": buffer,
                                "streamed": True,
                                "tokens_used": token_count,
                                "cached": False
                            }
                        )
                
                return StreamingResponse(
                    generate_optimized_stream(),
                    media_type="text/plain",
                    headers={
                        "Cache-Control": "no-cache",
                        "X-Provider": selected_provider,
                        "X-Optimized": str(ai_request.optimize_tokens)
                    }
                )

            # Non-streaming response
            answer = await asyncio.wait_for(
                ai_client.ask(
                    optimized_prompt,
                    provider=selected_provider,
                    max_tokens=ai_request.max_tokens,
                    temperature=ai_request.temperature
                ),
                timeout=config.ai_request_timeout
            )

            # Record success
            if circuit_breaker:
                circuit_breaker.record_success()
            
            token_count = TokenOptimizer.estimate_tokens(answer, selected_provider)
            
            response = {
                "provider": selected_provider,
                "prompt": optimized_prompt,
                "answer": answer,
                "cached": False,
                "tokens_used": token_count,
                "estimated_cost": ai_request.estimated_cost,
                "optimized": ai_request.optimize_tokens
            }

            # Record metrics
            if config.enable_metrics:
                TOKEN_USAGE.labels(provider=selected_provider).inc(token_count)
                REQUEST_COUNT.labels(provider=selected_provider, status='success').inc()

            # Cache response
            if cache_key:
                ttl = config.cache_ttl_short if token_count < 1000 else config.cache_ttl_long
                background_tasks.add_task(
                    _cache_ai_response, cache_key, response, ttl
                )

            return response

        except asyncio.TimeoutError:
            if circuit_breaker:
                circuit_breaker.record_failure()
            logger.error(f"AI request timeout for provider {selected_provider}")
            raise HTTPException(status_code=408, detail="AI request timeout")
        except Exception as e:
            if circuit_breaker:
                circuit_breaker.record_failure()
            logger.error(f"AI service error: {e}")
            raise HTTPException(status_code=500, detail=f"AI service error: {str(e)}")

async def _cache_ai_response(cache_key: str, response: Dict[str, Any], ttl: int = None):
    """Background task to cache AI responses with compression"""
    redis_client = await get_redis_client()
    if redis_client:
        try:
            cache_ttl = ttl or config.cache_ttl_short
            await AdvancedCache.set_cached(redis_client, cache_key, response, cache_ttl)
        except Exception as e:
            logger.warning(f"Cache write error: {e}")

# --- Batch Processing with Smart Queuing ---
@app.post("/ai/batch")
@limiter.limit("5/minute")
async def ai_batch(
    request: Request,
    prompts: List[str] = Body(..., min_items=1, max_items=50),
    provider: str = Query("auto", description="AI Provider (auto for smart selection)"),
    concurrency: int = Query(3, ge=1, le=8, description="Concurrent requests"),
    priority: str = Query("medium", description="Batch priority")
):
    """Smart batch processing with cost optimization"""
    
    if not prompts:
        raise HTTPException(status_code=422, detail="Prompts list cannot be empty")

    ai_client = await get_ai_client()
    ai_config = await load_ai_config()
    
    # Determine optimal provider for batch
    if provider == "auto":
        # For batch processing, prefer free/local options
        free_providers = [p for p in ai_config.keys() if p in ['ollama', 'huggingface']]
        selected_provider = free_providers[0] if free_providers else list(ai_config.keys())[0]
    else:
        selected_provider = provider

    batch_semaphore = asyncio.Semaphore(min(concurrency, config.max_concurrent_ai_requests))

    async def process_single_prompt(idx: int, prompt: str) -> Dict[str, Any]:
        async with batch_semaphore:
            try:
                # Optimize prompt for batch processing
                optimized_prompt = TokenOptimizer.optimize_prompt(prompt, max_tokens=2000)
                
                result = await asyncio.wait_for(
                    ai_client.ask(optimized_prompt, provider=selected_provider),
                    timeout=config.ai_request_timeout
                )
                return {
                    "index": idx,
                    "prompt": prompt[:100] + "..." if len(prompt) > 100 else prompt,
                    "answer": result,
                    "status": "success",
                    "tokens_used": TokenOptimizer.estimate_tokens(result, selected_provider)
                }
            except Exception as e:
                logger.error(f"Batch item {idx} error: {e}")
                return {
                    "index": idx,
                    "prompt": prompt[:100] + "..." if len(prompt) > 100 else prompt,
                    "error": str(e),
                    "status": "error"
                }

    try:
        # Process with progress tracking
        start_time = time.time()
        results = await asyncio.gather(
            *[process_single_prompt(i, prompt) for i, prompt in enumerate(prompts)],
            return_exceptions=True
        )
        
        processing_time = time.time() - start_time
        successful = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
        failed = len(results) - successful
        total_tokens = sum(r.get("tokens_used", 0) for r in results if isinstance(r, dict))

        return {
            "provider": selected_provider,
            "batch_size": len(prompts),
            "successful": successful,
            "failed": failed,
            "processing_time_seconds": round(processing_time, 2),
            "total_tokens_used": total_tokens,
            "average_tokens_per_request": round(total_tokens / len(prompts), 2) if prompts else 0,
            "results": results
        }

    except Exception as e:
        logger.error(f"Batch processing error: {e}")
        raise HTTPException(status_code=500, detail=f"Batch processing error: {str(e)}")

# --- Enhanced Health Check ---
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Comprehensive health check with performance metrics"""
    app_start_time = getattr(app.state, 'start_time', time.time())
    uptime = time.time() - app_start_time

    # Test AI providers with circuit breaker status
    ai_providers_status = {}
    try:
        ai_client = await get_ai_client()
        ai_config = await load_ai_config()
        
        for provider in ai_config.keys():
            circuit_breaker = resources.circuit_breakers.get(provider)
            
            if circuit_breaker and circuit_breaker.state == "OPEN":
                ai_providers_status[provider] = f"circuit_open (failures: {circuit_breaker.failure_count})"
                continue
                
            try:
                await asyncio.wait_for(
                    ai_client.ask("test", provider=provider, max_tokens=1),
                    timeout=3
                )
                ai_providers_status[provider] = "healthy"
                if circuit_breaker:
                    circuit_breaker.record_success()
            except Exception as e:
                error_msg = str(e)[:50]
                ai_providers_status[provider] = f"error: {error_msg}"
                if circuit_breaker:
                    circuit_breaker.record_failure()
                    
    except Exception as e:
        logger.error(f"Health check AI error: {e}")
        ai_providers_status = {"error": str(e)}

    # Test Redis and get cache stats
    redis_available = False
    cache_hit_rate = 0.0
    
    if config.enable_cache:
        try:
            redis_client = await get_redis_client()
            if redis_client:
                await redis_client.ping()
                redis_available = True
                
                # Calculate cache hit rate
                info = await redis_client.info()
                hits = info.get('keyspace_hits', 0)
                misses = info.get('keyspace_misses', 0)
                if hits + misses > 0:
                    cache_hit_rate = hits / (hits + misses)
        except Exception:
            pass

    return HealthResponse(
        status="healthy",
        version="3.0.0",
        timestamp=datetime.now(),
        ai_client_ready=resources.ai_client_instance is not None,
        ai_providers_status=ai_providers_status,
        redis_available=redis_available,
        database_connected=True,
        uptime_seconds=uptime,
        cache_hit_rate=cache_hit_rate,
        total_requests=0,  # Would be populated from metrics
        active_connections=0
    )

# --- Metrics Endpoint ---
if config.enable_metrics:
    @app.get("/metrics")
    async def metrics():
        """Prometheus metrics endpoint"""
        return Response(generate_latest(), media_type="text/plain")

# --- Admin Endpoints ---
@app.post("/admin/reload-config")
@limiter.limit("3/hour")
async def reload_config(request: Request):
    """Hot reload configuration with validation"""
    try:
        await load_ai_config(force_reload=True)
        
        # Recreate AI client
        if resources.ai_client_instance:
            await resources.ai_client_instance.aclose()
            resources.ai_client_instance = None
        
        await get_ai_client()
        logger.info("🔄 Configuration reloaded successfully")
        return {"status": "success", "message": "Configuration reloaded"}
    except Exception as e:
        logger.error(f"Config reload error: {e}")
        raise HTTPException(status_code=500, detail=f"Config reload failed: {str(e)}")

@app.get("/admin/cost-optimization")
@limiter.limit("10/hour")
async def get_cost_optimization_stats(request: Request):
    """Get detailed cost optimization statistics"""
    redis_client = await get_redis_client()
    
    stats = {
        "cache_enabled": config.enable_cache,
        "compression_enabled": config.enable_compression,
        "cache_available": redis_client is not None,
        "max_concurrent_requests": config.max_concurrent_ai_requests,
        "request_timeout": config.ai_request_timeout,
        "free_tier_providers": list(config.free_tier_limits.keys()),
        "optimization_features": [
            "Smart provider selection",
            "Token optimization",
            "Response compression",
            "Intelligent caching",
            "Circuit breaker protection"
        ]
    }

    if redis_client:
        try:
            info = await redis_client.info()
            stats.update({
                "redis_memory_used": info.get('used_memory_human', 'N/A'),
                "redis_keyspace_hits": info.get('keyspace_hits', 0),
                "redis_keyspace_misses": info.get('keyspace_misses', 0),
                "cache_compression_ratio": "~60-80%"  # Typical gzip compression
            })
        except Exception as e:
            logger.warning(f"Error getting cache stats: {e}")

    return stats

# --- Enhanced Ingestion ---
@app.post("/ingest_data")
@limiter.limit("15/hour")
async def ingest_provider_data(
    request: Request,
    ingestion_request: IngestionRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session)
):
    """Cost-optimized data ingestion with smart caching"""
    
    cache_key = None
    if config.enable_cache and ingestion_request.use_cache:
        cache_key = generate_cache_key(
            "ingestion_v2",
            ingestion_request.source_identifier,
            ingestion_request.category,
            ingestion_request.compression_level
        )

    # Check cache first
    redis_client = await get_redis_client()
    if redis_client and cache_key:
        cached_result = await AdvancedCache.get_cached(redis_client, cache_key)
        if cached_result:
            logger.info("💾 Cache hit for data ingestion")
            cached_result['cached'] = True
            return cached_result

    logger.info(f"🔄 Starting optimized ingestion: {ingestion_request.source_identifier}")

    try:
        # AI-powered extraction with cost control
        raw_data = discover_and_extract_data(
            source_identifier=ingestion_request.source_identifier,
            category=ingestion_request.category,
            use_cache=ingestion_request.use_cache
        )

        if not raw_data:
            result = {
                "message": "No data extracted from source",
                "products_stored": 0,
                "source": ingestion_request.source_identifier,
                "cost_optimized": True,
                "compression_used": config.enable_compression
            }
        else:
            standardized_data = parse_and_standardize(raw_data, category=ingestion_request.category)
            
            if not standardized_data:
                result = {
                    "message": "No standardized data generated",
                    "products_stored": 0,
                    "source": ingestion_request.source_identifier,
                    "cost_optimized": True
                }
            else:
                await store_standardized_data(session=session, data=standardized_data)
                result = {
                    "message": f"Successfully ingested {len(standardized_data)} products",
                    "products_stored": len(standardized_data),
                    "source": ingestion_request.source_identifier,
                    "cost_optimized": True,
                    "cached": False,
                    "compression_level": ingestion_request.compression_level
                }

        # Cache with smart TTL
        if cache_key:
            cache_ttl = config.cache_ttl_long if result["products_stored"] > 0 else config.cache_ttl_short
            background_tasks.add_task(
                _cache_ingestion_result, cache_key, result, cache_ttl
            )

        return result

    except Exception as e:
        logger.error(f"Ingestion error: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

async def _cache_ingestion_result(cache_key: str, result: Dict[str, Any], ttl: int):
    """Cache ingestion results with compression"""
    redis_client = await get_redis_client()
    if redis_client:
        try:
            await AdvancedCache.set_cached(redis_client, cache_key, result, ttl)
        except Exception as e:
            logger.warning(f"Cache write error: {e}")

# --- Root Endpoint ---
@app.get("/")
async def root():
    """Service information with feature overview"""
    return {
        "service": "AI Aggregator Service Pro",
        "version": "3.0.0",
        "status": "🚀 Ready",
        "features": [
            "🎯 Smart provider selection",
            "💰 Cost optimization", 
            "⚡ High-performance caching",
            "🔄 Circuit breaker protection",
            "📊 Performance monitoring",
            "🗜️ Response compression",
            "🔧 Hot configuration reload"
        ],
        "free_providers": list(config.free_tier_limits.keys()),
        "docs": "/docs" if os.getenv('ENVIRONMENT') != 'production' else "disabled",
        "health": "/health",
        "metrics": "/metrics" if config.enable_metrics else "disabled"
    }

# --- Application Entry Point ---
if __name__ == "__main__":
    import uvicorn
    
    uvicorn_config = {
        "app": app,
        "host": "0.0.0.0",
        "port": int(os.getenv('PORT', '8000')),
        "workers": 1,  # Single worker for async app
        "loop": "uvloop",
        "http": "httptools",
        "access_log": os.getenv('ENVIRONMENT') != 'production',
        "reload": os.getenv('ENVIRONMENT') == 'development'
    }
    
    logger.info("🚀 Starting AI Aggregator Service Pro with optimized configuration")
    uvicorn.run(**uvicorn_config)