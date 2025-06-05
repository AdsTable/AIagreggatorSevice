# main.py - Unified, high-performance, cost-optimized AI Aggregator Service

from __future__ import annotations
import json
import logging
import os
import time
import asyncio
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any, Dict, List, Optional, Union, AsyncGenerator
from pathlib import Path
from datetime import datetime
import hashlib
import yaml
import aiofiles
import aioredis
from dotenv import load_dotenv
from fastapi import (
    FastAPI, HTTPException, Query, Body, Depends, Request, BackgroundTasks
)
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, ConfigDict, field_validator, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# Import AI services and business logic
from services.ai_async_client import AIAsyncClient
from product_schema import Product, ApiResponse
from models import StandardizedProduct
from database import create_db_and_tables, get_session
from data_discoverer import discover_and_extract_data
from data_parser import parse_and_standardize
from data_storage import store_standardized_data
from data_search import search_and_filter_products

# Structured logging config
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('app.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

load_dotenv()  # Load env vars at startup

# --- Constants for performance and control ---
CONFIG_RELOAD_INTERVAL = int(os.getenv('CONFIG_RELOAD_INTERVAL', '300'))
MAX_CONCURRENT_AI_REQUESTS = int(os.getenv('MAX_CONCURRENT_AI_REQUESTS', '10'))
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
AI_REQUEST_TIMEOUT = int(os.getenv('AI_REQUEST_TIMEOUT', '30'))
ENABLE_CACHE = os.getenv('ENABLE_CACHE', 'true').lower() == 'true'

# --- Global resource handles (singleton pattern) ---
_ai_config_cache: Optional[Dict[str, Any]] = None
_ai_client_instance: Optional[AIAsyncClient] = None
_redis_client: Optional[aioredis.Redis] = None
_config_last_modified: Optional[float] = None
_ai_semaphore: Optional[asyncio.Semaphore] = None

# --- Provider-specific streaming chunk parsers ---
STREAMING_PARSERS = {
    'openai': lambda chunk: _parse_openai_chunk(chunk),
    'moonshot': lambda chunk: _parse_openai_chunk(chunk),
    'together': lambda chunk: _parse_together_chunk(chunk),
    'huggingface': lambda chunk: _parse_huggingface_chunk(chunk),
    'ollama': lambda chunk: _parse_ollama_chunk(chunk),
    'minimax': lambda chunk: _parse_minimax_chunk(chunk)
}

def _parse_openai_chunk(chunk: str) -> Optional[str]:
    """Parse OpenAI/Moonshot streaming format chunk."""
    try:
        if chunk.startswith('data: '):
            chunk = chunk[6:]
        if chunk.strip() == '[DONE]':
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

# --- Redis and AI client lifecycle ---
async def get_redis_client() -> Optional[aioredis.Redis]:
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = aioredis.from_url(
                REDIS_URL, encoding="utf-8", decode_responses=True
            )
            await _redis_client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}, proceeding without cache")
            _redis_client = None
    return _redis_client

@lru_cache(maxsize=1)
def get_config_path() -> Path:
    return Path("ai_integrations.yaml")

async def load_ai_config(force_reload: bool = False) -> Dict[str, Any]:
    """Load and cache AI configuration with optional reload."""
    global _ai_config_cache, _config_last_modified
    config_path = get_config_path()
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file {config_path} not found")
    current_mtime = config_path.stat().st_mtime
    if not force_reload and _ai_config_cache and _config_last_modified == current_mtime:
        return _ai_config_cache
    try:
        async with aiofiles.open(config_path, mode='r', encoding='utf-8') as f:
            content = await f.read()
        cfg = yaml.safe_load(content)
        for provider, settings in cfg.items():
            if not isinstance(settings, dict):
                continue
            for key, value in settings.items():
                if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                    env_key = value[2:-1]
                    env_value = os.getenv(env_key)
                    if env_value is None:
                        logger.warning(f"Environment variable {env_key} not found for {provider}.{key}")
                        continue
                    cfg[provider][key] = env_value
        _ai_config_cache = cfg
        _config_last_modified = current_mtime
        logger.info(f"AI configuration loaded from {config_path}")
        return cfg
    except (yaml.YAMLError, ValueError) as e:
        logger.error(f"Failed to load AI configuration: {e}")
        raise RuntimeError(f"Configuration error: {e}")

def get_ai_semaphore() -> asyncio.Semaphore:
    global _ai_semaphore
    if _ai_semaphore is None:
        _ai_semaphore = asyncio.Semaphore(MAX_CONCURRENT_AI_REQUESTS)
    return _ai_semaphore

async def get_ai_client() -> AIAsyncClient:
    global _ai_client_instance
    config = await load_ai_config()
    if _ai_client_instance is None:
        _ai_client_instance = AIAsyncClient(config)
        logger.info("AI client initialized")
    return _ai_client_instance

def generate_cache_key(prefix: str, *args, **kwargs) -> str:
    key_data = f"{prefix}:{':'.join(map(str, args))}:{':'.join(f'{k}={v}' for k, v in sorted(kwargs.items()))}"
    return hashlib.md5(key_data.encode()).hexdigest()

# --- Parsing utilities ---
def safe_numeric_parse(value: Optional[str], parse_type: type, field_name: str) -> Optional[Union[int, float]]:
    if not value or not value.strip():
        return None
    try:
        if parse_type == int:
            return int(float(value))
        return float(value)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid {parse_type.__name__} format for {field_name}: '{value}'"
        )

def safe_float_parse(value: Optional[str]) -> Optional[float]:
    return safe_numeric_parse(value, float, "number")

def safe_int_parse(value: Optional[str]) -> Optional[int]:
    return safe_numeric_parse(value, int, "integer")

# --- Pydantic models ---
class IngestionRequest(BaseModel):
    source_identifier: str
    category: str
    use_cache: bool = True
    model_config = ConfigDict(
        str_strip_whitespace=True, validate_assignment=True, frozen=True
    )
    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        allowed = frozenset(["electricity_plan", "mobile_plan", "internet_plan", "broadband_plan"])
        if v not in allowed:
            raise ValueError(f"Category must be one of: {list(allowed)}")
        return v
    @field_validator("source_identifier")
    @classmethod
    def validate_source_identifier(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("source_identifier cannot be empty")
        return v.strip()

class AIRequest(BaseModel):
    prompt: str
    provider: str = "openai"
    max_tokens: Optional[int] = None
    temperature: float = 0.7
    use_cache: bool = True
    model_config = ConfigDict(frozen=True)
    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Prompt cannot be empty")
        if len(v) > 50000:
            raise ValueError("Prompt too long (max 50000 characters)")
        return v.strip()
    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        allowed = frozenset(["openai", "moonshot", "together", "huggingface", "ollama", "tibber", "wenxin", "minimax"])
        if v not in allowed:
            raise ValueError(f"Provider must be one of: {list(allowed)}")
        return v

class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime
    ai_client_ready: bool
    ai_providers_status: Dict[str, str]
    redis_available: bool
    database_connected: bool
    uptime_seconds: float
    model_config = ConfigDict(frozen=True)

# --- Lifecycle management ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    start_time = time.time()
    app.state.start_time = start_time
    logger.info("Application startup: Initializing services...")
    try:
        await create_db_and_tables()
        if ENABLE_CACHE:
            await get_redis_client()
        await get_ai_client()
        logger.info("Application initialized successfully")
        yield
    except Exception as e:
        logger.error(f"Application startup failed: {e}")
        raise
    finally:
        logger.info("Application shutdown: Cleaning up resources...")
        global _ai_client_instance
        if _ai_client_instance:
            await _ai_client_instance.aclose()
            _ai_client_instance = None
        global _redis_client
        if _redis_client:
            await _redis_client.close()
            _redis_client = None
        logger.info("Application shutdown completed")

# --- FastAPI app initialization ---
app = FastAPI(
    title="AI Aggregator Service Pro",
    description="Production-ready AI-powered data aggregation service with cost optimization",
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/docs" if os.getenv('ENVIRONMENT') != 'production' else None,
    redoc_url="/redoc" if os.getenv('ENVIRONMENT') != 'production' else None
)
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv('ALLOWED_ORIGINS', 'http://localhost:3000,http://localhost:8080').split(','),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
if os.getenv('TRUSTED_HOSTS'):
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=os.getenv('TRUSTED_HOSTS').split(',')
    )

# --- AI endpoints ---
@app.post("/ai/ask")
@limiter.limit("30/minute")
async def ai_ask(
    request: Request,
    ai_request: AIRequest,
    background_tasks: BackgroundTasks,
    stream: bool = Query(False, description="Enable streaming response")
):
    cache_key = None
    if ENABLE_CACHE and ai_request.use_cache:
        cache_key = generate_cache_key("ai_ask", ai_request.prompt, ai_request.provider)
    redis_client = await get_redis_client()
    if redis_client:
        try:
            cached_result = await redis_client.get(cache_key)
            if cached_result:
                logger.info(f"Cache hit for AI request")
                return json.loads(cached_result)
        except Exception as e:
            logger.warning(f"Cache read error: {e}")
    ai_client = await get_ai_client()
    semaphore = get_ai_semaphore()
    async with semaphore:
        try:
            if stream:
                parser = STREAMING_PARSERS.get(ai_request.provider, STREAMING_PARSERS['openai'])
                async def generate_optimized_stream() -> AsyncGenerator[str, None]:
                    buffer = ""
                    async for chunk in ai_client.stream(
                        ai_request.prompt,
                        provider=ai_request.provider,
                        max_tokens=ai_request.max_tokens,
                        temperature=ai_request.temperature
                    ):
                        content = parser(chunk)
                        if content:
                            buffer += content
                            yield content
                    if ENABLE_CACHE and ai_request.use_cache and cache_key and buffer:
                        background_tasks.add_task(_cache_ai_response, cache_key, {
                            "provider": ai_request.provider,
                            "prompt": ai_request.prompt,
                            "answer": buffer,
                            "streamed": True
                        })
                return StreamingResponse(
                    generate_optimized_stream(),
                    media_type="text/plain",
                    headers={
                        "Cache-Control": "no-cache",
                        "X-Provider": ai_request.provider
                    }
                )
            answer = await asyncio.wait_for(
                ai_client.ask(
                    ai_request.prompt,
                    provider=ai_request.provider,
                    max_tokens=ai_request.max_tokens,
                    temperature=ai_request.temperature
                ),
                timeout=AI_REQUEST_TIMEOUT
            )
            response = {
                "provider": ai_request.provider,
                "prompt": ai_request.prompt,
                "answer": answer,
                "cached": False,
                "tokens_used": len(answer.split()) if answer else 0
            }
            if ENABLE_CACHE and ai_request.use_cache and cache_key:
                background_tasks.add_task(_cache_ai_response, cache_key, response)
            return response
        except asyncio.TimeoutError:
            logger.error(f"AI request timeout for provider {ai_request.provider}")
            raise HTTPException(status_code=408, detail="AI request timeout")
        except Exception as e:
            logger.error(f"AI service error: {e}")
            raise HTTPException(status_code=500, detail=f"AI service error: {str(e)}")

async def _cache_ai_response(cache_key: str, response: Dict[str, Any]):
    redis_client = await get_redis_client()
    if redis_client:
        try:
            await redis_client.setex(
                cache_key, 3600, json.dumps(response, default=str)
            )
        except Exception as e:
            logger.warning(f"Cache write error: {e}")

@app.post("/ai/batch")
@limiter.limit("10/minute")
async def ai_batch(
    request: Request,
    prompts: List[str] = Body(..., min_items=1, max_items=20),
    provider: str = Query("openai", description="AI Provider for batch processing"),
    concurrency: int = Query(5, ge=1, le=10, description="Concurrent requests limit")
):
    if not prompts:
        raise HTTPException(status_code=422, detail="Prompts list cannot be empty")
    ai_client = await get_ai_client()
    batch_semaphore = asyncio.Semaphore(min(concurrency, MAX_CONCURRENT_AI_REQUESTS))
    async def process_single_prompt(prompt: str) -> Dict[str, Any]:
        async with batch_semaphore:
            try:
                result = await asyncio.wait_for(
                    ai_client.ask(prompt, provider=provider),
                    timeout=AI_REQUEST_TIMEOUT
                )
                return {"prompt": prompt, "answer": result, "status": "success"}
            except Exception as e:
                logger.error(f"Batch item error: {e}")
                return {"prompt": prompt, "error": str(e), "status": "error"}
    try:
        results = await asyncio.gather(
            *[process_single_prompt(prompt) for prompt in prompts],
            return_exceptions=False
        )
        successful = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
        failed = len(results) - successful
        return {
            "provider": provider,
            "batch_size": len(prompts),
            "successful": successful,
            "failed": failed,
            "results": results
        }
    except Exception as e:
        logger.error(f"Batch processing error: {e}")
        raise HTTPException(status_code=500, detail=f"Batch processing error: {str(e)}")

# --- Health check ---
@app.get("/health", response_model=HealthResponse)
async def health_check():
    app_start_time = getattr(app.state, 'start_time', time.time())
    uptime = time.time() - app_start_time
    ai_providers_status = {}
    try:
        ai_client = await get_ai_client()
        config = await load_ai_config()
        for provider in config.keys():
            try:
                await asyncio.wait_for(
                    ai_client.ask("ping", provider=provider, max_tokens=1),
                    timeout=5
                )
                ai_providers_status[provider] = "healthy"
            except Exception as e:
                ai_providers_status[provider] = f"error: {str(e)[:50]}"
    except Exception as e:
        logger.error(f"Health check AI error: {e}")
        ai_providers_status = {"error": str(e)}
    redis_available = False
    if ENABLE_CACHE:
        try:
            redis_client = await get_redis_client()
            if redis_client:
                await redis_client.ping()
                redis_available = True
        except Exception:
            pass
    return HealthResponse(
        status="healthy",
        version="3.0.0",
        timestamp=datetime.now(),
        ai_client_ready=_ai_client_instance is not None,
        ai_providers_status=ai_providers_status,
        redis_available=redis_available,
        database_connected=True,
        uptime_seconds=uptime
    )

# --- Config reload for hot updates ---
@app.post("/admin/reload-config")
@limiter.limit("5/hour")
async def reload_config(request: Request):
    try:
        await load_ai_config(force_reload=True)
        global _ai_client_instance
        if _ai_client_instance:
            await _ai_client_instance.aclose()
            _ai_client_instance = None
        await get_ai_client()
        logger.info("Configuration reloaded successfully")
        return {"status": "success", "message": "Configuration reloaded"}
    except Exception as e:
        logger.error(f"Config reload error: {e}")
        raise HTTPException(status_code=500, detail=f"Config reload failed: {str(e)}")

# --- Ingestion endpoint with caching ---
@app.post("/ingest_data")
@limiter.limit("20/hour")
async def ingest_provider_data(
    request: Request,
    ingestion_request: IngestionRequest,
    session: AsyncSession = Depends(get_session),
    background_tasks: BackgroundTasks
):
    cache_key = None
    if ENABLE_CACHE and ingestion_request.use_cache:
        cache_key = generate_cache_key(
            "ingestion", ingestion_request.source_identifier, ingestion_request.category
        )
    redis_client = await get_redis_client()
    if redis_client:
        try:
            cached_result = await redis_client.get(cache_key)
            if cached_result:
                logger.info("Cache hit for data ingestion")
                return json.loads(cached_result)
        except Exception as e:
            logger.warning(f"Cache read error: {e}")
    logger.info(f"Starting cost-optimized ingestion: {ingestion_request.source_identifier}")
    try:
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
                "cost_optimized": True
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
                    "cached": False
                }
        if ENABLE_CACHE and ingestion_request.use_cache and cache_key:
            background_tasks.add_task(_cache_ingestion_result, cache_key, result)
        return result
    except Exception as e:
        logger.error(f"Ingestion error: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

async def _cache_ingestion_result(cache_key: str, result: Dict[str, Any]):
    redis_client = await get_redis_client()
    if redis_client:
        try:
            await redis_client.setex(
                cache_key, 1800, json.dumps(result, default=str)
            )
        except Exception as e:
            logger.warning(f"Cache write error: {e}")

# --- Cost stats endpoint ---
@app.get("/admin/cost-stats")
@limiter.limit("10/hour")
async def get_cost_stats(request: Request):
    redis_client = await get_redis_client()
    stats = {
        "cache_enabled": ENABLE_CACHE,
        "cache_available": redis_client is not None,
        "max_concurrent_requests": MAX_CONCURRENT_AI_REQUESTS,
        "request_timeout": AI_REQUEST_TIMEOUT,
        "total_ai_requests": 0,
        "cached_responses": 0,
        "cache_hit_rate": 0.0
    }
    if redis_client:
        try:
            info = await redis_client.info()
            stats.update({
                "redis_memory_used": info.get('used_memory_human', 'N/A'),
                "redis_keyspace_hits": info.get('keyspace_hits', 0),
                "redis_keyspace_misses": info.get('keyspace_misses', 0)
            })
            hits = info.get('keyspace_hits', 0)
            misses = info.get('keyspace_misses', 0)
            if hits + misses > 0:
                stats["cache_hit_rate"] = hits / (hits + misses)
        except Exception as e:
            logger.warning(f"Error getting cache stats: {e}")
    return stats

# --- Root endpoint ---
@app.get("/")
async def root():
    return {
        "service": "AI Aggregator Service Pro",
        "version": "3.0.0",
        "features": [
            "Cost optimization",
            "Smart caching",
            "Rate limiting",
            "Provider failover",
            "Hot config reload"
        ],
        "docs": "/docs" if os.getenv('ENVIRONMENT') != 'production' else "disabled",
        "health": "/health"
    }

# --- Application entry point ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv('PORT', '8000')),
        workers=int(os.getenv('WORKERS', '1')),
        loop="uvloop",
        http="httptools",
        access_log=os.getenv('ENVIRONMENT') != 'production',
        reload=os.getenv('ENVIRONMENT') == 'development'
    )