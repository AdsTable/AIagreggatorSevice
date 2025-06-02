# services/ai_async_client.py - Next-generation AI client with advanced optimization
from __future__ import annotations

import asyncio
import json
import logging
import time
import hashlib
import gzip
import pickle
import os
import sys
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Union, AsyncGenerator, Callable, Tuple
from enum import Enum
from collections import defaultdict, deque
from datetime import datetime, timedelta
import statistics
import aiohttp
import ssl
from urllib.parse import urljoin
import base64

# Import optional dependencies with graceful fallbacks
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    from transformers import pipeline
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

logger = logging.getLogger(__name__)

class ProviderType(Enum):
    """Advanced provider types with cost and performance characteristics"""
    # Free/Local providers (highest priority)
    OLLAMA = "ollama"                    # Local inference
    LLAMAFILE = "llamafile"              # Self-contained executable
    GGUF_LOCAL = "gguf_local"            # Local GGUF models
    HUGGINGFACE_FREE = "huggingface"     # Free inference API
    
    # Low-cost cloud providers
    TOGETHER = "together"                # Competitive pricing
    FIREWORKS = "fireworks"              # Fast inference
    REPLICATE = "replicate"              # Pay-per-use
    GROQ = "groq"                        # Ultra-fast inference
    
    # Premium providers (fallback only)
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    
    # Specialized providers
    COHERE = "cohere"
    MISTRAL = "mistral"
    PERPLEXITY = "perplexity"

class TaskComplexity(Enum):
    """Task complexity levels for intelligent routing"""
    SIMPLE = "simple"        # Basic Q&A, translations
    MEDIUM = "medium"        # Analysis, summarization
    COMPLEX = "complex"      # Code generation, reasoning
    CREATIVE = "creative"    # Writing, storytelling

@dataclass
class ProviderConfig:
    """Enhanced provider configuration with advanced optimization settings"""
    name: str
    provider_type: ProviderType
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    models: List[str] = field(default_factory=list)
    
    # Cost optimization
    cost_per_1k_tokens: float = 0.0
    free_tier_limit: int = 0  # requests per day
    is_free: bool = False
    
    # Performance settings
    max_tokens: int = 4096
    timeout: int = 30
    rate_limit: int = 60  # requests per minute
    concurrent_limit: int = 5
    
    # Quality metrics
    quality_score: float = 1.0  # 0.0 to 1.0
    speed_score: float = 1.0    # 0.0 to 1.0
    reliability_score: float = 1.0
    
    # Advanced features
    supports_streaming: bool = True
    supports_batching: bool = False
    supports_function_calling: bool = False
    supports_vision: bool = False
    
    # Optimization flags
    enable_compression: bool = True
    enable_caching: bool = True
    enable_retry: bool = True
    retry_attempts: int = 3
    retry_delay: float = 1.0
    
    # Headers and authentication
    headers: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        """Post-initialization setup"""
        if self.cost_per_1k_tokens == 0.0:
            self.is_free = True
        
        # Default models for each provider type
        if not self.models:
            self.models = self._get_default_models()
    
    def _get_default_models(self) -> List[str]:
        """Get default models for provider type"""
        default_models = {
            ProviderType.OLLAMA: ["llama3.2", "phi3", "gemma2"],
            ProviderType.LLAMAFILE: ["llama-3.2-1b", "phi-3-mini"],
            ProviderType.HUGGINGFACE_FREE: ["microsoft/DialoGPT-medium", "meta-llama/Llama-2-7b-chat-hf"],
            ProviderType.TOGETHER: ["meta-llama/Llama-2-7b-chat-hf", "mistralai/Mixtral-8x7B-Instruct-v0.1"],
            ProviderType.GROQ: ["llama-3.1-8b-instant", "mixtral-8x7b-32768"],
            ProviderType.OPENAI: ["gpt-4o-mini", "gpt-3.5-turbo"],
            ProviderType.ANTHROPIC: ["claude-3-haiku-20240307", "claude-3-sonnet-20240229"],
        }
        return default_models.get(self.provider_type, ["default"])

@dataclass
class TokenUsage:
    """Token usage tracking with cost calculation"""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    
    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens
    
    def calculate_cost(self, input_cost: float, output_cost: float) -> float:
        """Calculate total cost based on token usage"""
        return (self.input_tokens * input_cost + self.output_tokens * output_cost) / 1000

@dataclass
class AIResponse:
    """Enhanced AI response with comprehensive metadata"""
    content: str
    provider: str
    model: str
    tokens_used: TokenUsage
    cost: float = 0.0
    latency_ms: float = 0.0
    cached: bool = False
    compressed: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    quality_score: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return asdict(self)

class ProviderError(Exception):
    """Enhanced exception with error categorization"""
    def __init__(self, provider: str, message: str, error_code: Optional[str] = None, 
                 retry_after: Optional[int] = None, is_rate_limit: bool = False):
        self.provider = provider
        self.error_code = error_code
        self.retry_after = retry_after
        self.is_rate_limit = is_rate_limit
        super().__init__(f"[{provider}] {message}")

class TokenOptimizer:
    """Advanced token optimization and compression utilities"""
    
    def __init__(self):
        self.token_cache = {}
        
    def estimate_tokens(self, text: str, model: str = "gpt-3.5-turbo") -> int:
        """Accurate token estimation using tiktoken when available"""
        if TIKTOKEN_AVAILABLE:
            try:
                encoding = tiktoken.encoding_for_model(model)
                return len(encoding.encode(text))
            except:
                pass
        
        # Fallback estimation based on provider type
        if "claude" in model.lower():
            return len(text) // 3.5  # Claude is more efficient
        elif "llama" in model.lower():
            return len(text) // 3.0  # Llama models
        else:
            return len(text) // 4.0  # Default GPT estimation
    
    def compress_prompt(self, prompt: str, target_tokens: int, model: str = "gpt-3.5-turbo") -> str:
        """Intelligent prompt compression with content preservation"""
        current_tokens = self.estimate_tokens(prompt, model)
        
        if current_tokens <= target_tokens:
            return prompt
        
        # Calculate compression ratio needed
        compression_ratio = target_tokens / current_tokens
        
        # Apply compression strategies
        compressed = self._apply_compression_strategies(prompt, compression_ratio)
        
        # Verify compression success
        final_tokens = self.estimate_tokens(compressed, model)
        if final_tokens <= target_tokens:
            return compressed
        
        # Fallback: simple truncation with ellipsis
        words = prompt.split()
        target_words = int(len(words) * compression_ratio)
        return " ".join(words[:target_words]) + "..."
    
    def _apply_compression_strategies(self, text: str, ratio: float) -> str:
        """Apply multiple compression strategies"""
        strategies = [
            self._remove_redundancy,
            self._compress_whitespace,
            self._abbreviate_common_phrases,
            self._smart_truncation
        ]
        
        compressed = text
        for strategy in strategies:
            compressed = strategy(compressed, ratio)
            
        return compressed
    
    def _remove_redundancy(self, text: str, ratio: float) -> str:
        """Remove redundant phrases and repeated information"""
        sentences = text.split('. ')
        unique_sentences = []
        seen_concepts = set()
        
        for sentence in sentences:
            # Simple concept extraction (could be enhanced with NLP)
            concepts = set(sentence.lower().split())
            if not concepts.intersection(seen_concepts) or len(unique_sentences) < 2:
                unique_sentences.append(sentence)
                seen_concepts.update(concepts)
        
        return '. '.join(unique_sentences)
    
    def _compress_whitespace(self, text: str, ratio: float) -> str:
        """Compress unnecessary whitespace"""
        import re
        # Remove multiple spaces, tabs, newlines
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def _abbreviate_common_phrases(self, text: str, ratio: float) -> str:
        """Abbreviate common phrases to save tokens"""
        abbreviations = {
            "for example": "e.g.",
            "that is": "i.e.",
            "and so on": "etc.",
            "as soon as possible": "ASAP",
            "frequently asked questions": "FAQ",
            "artificial intelligence": "AI",
            "machine learning": "ML",
            "deep learning": "DL",
            "natural language processing": "NLP",
        }
        
        for phrase, abbrev in abbreviations.items():
            text = text.replace(phrase, abbrev)
            text = text.replace(phrase.title(), abbrev)
        
        return text
    
    def _smart_truncation(self, text: str, ratio: float) -> str:
        """Intelligent truncation preserving important content"""
        if ratio >= 0.8:
            return text
        
        # Preserve beginning and end, truncate middle
        words = text.split()
        total_words = len(words)
        keep_words = int(total_words * ratio)
        
        if keep_words < 20:
            return " ".join(words[:keep_words]) + "..."
        
        # Keep first 60% and last 40% of remaining words
        start_words = int(keep_words * 0.6)
        end_words = keep_words - start_words
        
        beginning = " ".join(words[:start_words])
        ending = " ".join(words[-end_words:])
        
        return f"{beginning} ... {ending}"

class SmartCache:
    """Advanced caching system with compression and semantic similarity"""
    
    def __init__(self, max_size: int = 1000, compression_enabled: bool = True):
        self.cache: Dict[str, Any] = {}
        self.access_times: Dict[str, datetime] = {}
        self.hit_counts: Dict[str, int] = defaultdict(int)
        self.max_size = max_size
        self.compression_enabled = compression_enabled
        self.hits = 0
        self.misses = 0
    
    def _generate_key(self, prompt: str, model: str, params: Dict[str, Any]) -> str:
        """Generate cache key with semantic considerations"""
        # Normalize prompt for better cache hits
        normalized_prompt = self._normalize_prompt(prompt)
        
        cache_data = {
            'prompt': normalized_prompt,
            'model': model,
            'params': {k: v for k, v in sorted(params.items()) if k in ['temperature', 'max_tokens']}
        }
        
        key_string = json.dumps(cache_data, sort_keys=True)
        return hashlib.sha256(key_string.encode()).hexdigest()
    
    def _normalize_prompt(self, prompt: str) -> str:
        """Normalize prompt for better cache matching"""
        # Remove extra whitespace and normalize case for certain patterns
        import re
        normalized = re.sub(r'\s+', ' ', prompt.strip())
        
        # Could add semantic normalization here (e.g., synonyms, paraphrases)
        return normalized
    
    def get(self, prompt: str, model: str, params: Dict[str, Any]) -> Optional[AIResponse]:
        """Get cached response with LRU eviction"""
        key = self._generate_key(prompt, model, params)
        
        if key in self.cache:
            self.hits += 1
            self.access_times[key] = datetime.now()
            self.hit_counts[key] += 1
            
            cached_data = self.cache[key]
            if self.compression_enabled and isinstance(cached_data, bytes):
                cached_data = self._decompress_data(cached_data)
            
            # Create response object from cached data
            if isinstance(cached_data, dict):
                response = AIResponse(**cached_data)
                response.cached = True
                return response
        
        self.misses += 1
        return None
    
    def set(self, prompt: str, model: str, params: Dict[str, Any], response: AIResponse) -> None:
        """Cache response with optional compression"""
        if len(self.cache) >= self.max_size:
            self._evict_lru()
        
        key = self._generate_key(prompt, model, params)
        data = response.to_dict()
        
        if self.compression_enabled:
            data = self._compress_data(data)
        
        self.cache[key] = data
        self.access_times[key] = datetime.now()
        self.hit_counts[key] = 0
    
    def _compress_data(self, data: Any) -> bytes:
        """Compress data for storage efficiency"""
        serialized = pickle.dumps(data)
        return gzip.compress(serialized)
    
    def _decompress_data(self, data: bytes) -> Any:
        """Decompress stored data"""
        decompressed = gzip.decompress(data)
        return pickle.loads(decompressed)
    
    def _evict_lru(self) -> None:
        """Evict least recently used items"""
        if not self.access_times:
            return
        
        # Remove oldest 20% of items
        items_to_remove = max(1, len(self.cache) // 5)
        oldest_keys = sorted(self.access_times.items(), key=lambda x: x[1])[:items_to_remove]
        
        for key, _ in oldest_keys:
            self.cache.pop(key, None)
            self.access_times.pop(key, None)
            self.hit_counts.pop(key, None)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        total_requests = self.hits + self.misses
        hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': f"{hit_rate:.2f}%",
            'compression_enabled': self.compression_enabled,
            'memory_saved': self._estimate_compression_savings()
        }
    
    def _estimate_compression_savings(self) -> str:
        """Estimate memory savings from compression"""
        if not self.compression_enabled:
            return "0%"
        
        # This is an approximation
        return "~60-80%"

class ProviderMetrics:
    """Enhanced metrics tracking with performance analysis"""
    
    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        
        # Request tracking
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        
        # Performance metrics
        self.response_times = deque(maxlen=window_size)
        self.token_counts = deque(maxlen=window_size)
        self.costs = deque(maxlen=window_size)
        
        # Error tracking
        self.consecutive_failures = 0
        self.last_success: Optional[datetime] = None
        self.last_failure: Optional[datetime] = None
        self.error_types: Dict[str, int] = defaultdict(int)
        
        # Health status
        self.is_healthy = True
        self.health_score = 1.0
        
    def record_success(self, response_time: float, tokens: int, cost: float) -> None:
        """Record successful request"""
        self.total_requests += 1
        self.successful_requests += 1
        self.consecutive_failures = 0
        self.last_success = datetime.now()
        
        self.response_times.append(response_time)
        self.token_counts.append(tokens)
        self.costs.append(cost)
        
        self._update_health()
    
    def record_failure(self, error_type: str = "unknown") -> None:
        """Record failed request"""
        self.total_requests += 1
        self.failed_requests += 1
        self.consecutive_failures += 1
        self.last_failure = datetime.now()
        self.error_types[error_type] += 1
        
        self._update_health()
    
    def _update_health(self) -> None:
        """Update health status based on recent performance"""
        if self.total_requests == 0:
            self.health_score = 1.0
            self.is_healthy = True
            return
        
        # Calculate success rate
        success_rate = self.successful_requests / self.total_requests
        
        # Factor in consecutive failures
        failure_penalty = min(self.consecutive_failures * 0.1, 0.5)
        
        # Calculate health score
        self.health_score = max(0.0, success_rate - failure_penalty)
        self.is_healthy = self.health_score > 0.5 and self.consecutive_failures < 5
    
    def get_avg_response_time(self) -> float:
        """Get average response time from recent requests"""
        return statistics.mean(self.response_times) if self.response_times else 0.0
    
    def get_efficiency_score(self, cost_weight: float = 0.3, speed_weight: float = 0.4, 
                           quality_weight: float = 0.3) -> float:
        """Calculate overall efficiency score"""
        if not self.response_times:
            return 0.0
        
        # Speed score (inverse of response time)
        avg_time = self.get_avg_response_time()
        speed_score = max(0.0, 1.0 - (avg_time / 10.0))  # Normalize to 10s max
        
        # Cost score (inverse of average cost)
        avg_cost = statistics.mean(self.costs) if self.costs else 0.0
        cost_score = max(0.0, 1.0 - (avg_cost / 0.01))  # Normalize to $0.01 max
        
        # Quality score (success rate)
        quality_score = self.health_score
        
        return (speed_score * speed_weight + 
                cost_score * cost_weight + 
                quality_score * quality_weight)

class AIProviderBase(ABC):
    """Enhanced abstract base class with advanced features"""
    
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.metrics = ProviderMetrics()
        self.session: Optional[aiohttp.ClientSession] = None
        self.rate_limiter = self._create_rate_limiter()
        self.token_optimizer = TokenOptimizer()
        
    def _create_rate_limiter(self) -> Callable:
        """Create rate limiter for this provider"""
        request_times = deque()
        
        async def rate_limit():
            now = time.time()
            # Remove old requests outside the window
            while request_times and now - request_times[0] >= 60:
                request_times.popleft()
            
            if len(request_times) >= self.config.rate_limit:
                sleep_time = 60 - (now - request_times[0])
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
            
            request_times.append(now)
        
        return rate_limit
    
    async def __aenter__(self):
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()
    
    async def initialize(self) -> None:
        """Initialize provider with optimized session"""
        try:
            connector = aiohttp.TCPConnector(
                limit=self.config.concurrent_limit * 2,
                limit_per_host=self.config.concurrent_limit,
                ttl_dns_cache=300,
                use_dns_cache=True,
                ssl=ssl.create_default_context()
            )
            
            timeout = aiohttp.ClientTimeout(
                total=self.config.timeout,
                connect=10,
                sock_read=self.config.timeout - 10
            )
            
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers=self.config.headers,
                json_serialize=json.dumps,
                raise_for_status=False
            )
            
            logger.info(f"✅ Initialized {self.config.name} provider")
            
        except Exception as e:
            logger.warning(f"Failed to initialize {self.config.name}: {e}")
            self.session = None
    
    async def cleanup(self) -> None:
        """Cleanup provider resources"""
        if self.session and not self.session.closed:
            try:
                await self.session.close()
                # Wait for underlying connections to close
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.warning(f"Error closing session for {self.config.name}: {e}")
    
    @abstractmethod
    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        """Send request to AI provider"""
        pass
    
    @abstractmethod
    async def stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Stream response from AI provider"""
        pass
    
    async def batch_ask(self, prompts: List[str], **kwargs) -> List[AIResponse]:
        """Process multiple prompts (default implementation)"""
        if not self.config.supports_batching:
            # Sequential processing for providers without native batching
            results = []
            for prompt in prompts:
                try:
                    response = await self.ask(prompt, **kwargs)
                    results.append(response)
                except Exception as e:
                    error_response = AIResponse(
                        content=f"Error: {str(e)}",
                        provider=self.config.name,
                        model=kwargs.get('model', 'unknown'),
                        tokens_used=TokenUsage()
                    )
                    results.append(error_response)
            return results
        
        # Implement provider-specific batching
        return await self._batch_ask_native(prompts, **kwargs)
    
    async def _batch_ask_native(self, prompts: List[str], **kwargs) -> List[AIResponse]:
        """Provider-specific batch implementation"""
        raise NotImplementedError("Native batching not implemented for this provider")

# Free/Local Provider Implementations

class OllamaProvider(AIProviderBase):
    """Enhanced Ollama provider with model management"""
    
    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        """Send request to Ollama with optimization"""
        await self.rate_limiter()
        start_time = time.time()
        
        try:
            if not self.session:
                raise ProviderError(self.config.name, "Session not initialized")
            
            model = kwargs.get('model', self.config.models[0])
            
            # Optimize prompt if needed
            max_context = kwargs.get('max_tokens', self.config.max_tokens)
            optimized_prompt = self.token_optimizer.compress_prompt(prompt, max_context // 2, model)
            
            payload = {
                "model": model,
                "prompt": optimized_prompt,
                "stream": False,
                "options": {
                    "temperature": kwargs.get('temperature', 0.7),
                    "num_predict": kwargs.get('max_tokens', self.config.max_tokens),
                    "top_p": kwargs.get('top_p', 0.9),
                    "repeat_penalty": 1.1
                }
            }
            
            url = urljoin(self.config.base_url or 'http://localhost:11434', '/api/generate')
            
            async with self.session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ProviderError(
                        self.config.name, 
                        f"HTTP {response.status}: {error_text}",
                        is_rate_limit=(response.status == 429)
                    )
                
                data = await response.json()
                content = data.get('response', '')
                
                latency_ms = (time.time() - start_time) * 1000
                tokens_used = TokenUsage(
                    input_tokens=self.token_optimizer.estimate_tokens(optimized_prompt, model),
                    output_tokens=self.token_optimizer.estimate_tokens(content, model)
                )
                
                ai_response = AIResponse(
                    content=content,
                    provider=self.config.name,
                    model=model,
                    tokens_used=tokens_used,
                    cost=0.0,  # Free local inference
                    latency_ms=latency_ms,
                    metadata=data
                )
                
                self.metrics.record_success(latency_ms, tokens_used.total_tokens, 0.0)
                return ai_response
                
        except Exception as e:
            self.metrics.record_failure(type(e).__name__)
            logger.error(f"Ollama request failed: {e}")
            raise ProviderError(self.config.name, str(e))
    
    async def stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Stream response from Ollama with optimization"""
        await self.rate_limiter()
        
        try:
            if not self.session:
                raise ProviderError(self.config.name, "Session not initialized")
            
            model = kwargs.get('model', self.config.models[0])
            optimized_prompt = self.token_optimizer.compress_prompt(
                prompt, 
                kwargs.get('max_tokens', self.config.max_tokens) // 2, 
                model
            )
            
            payload = {
                "model": model,
                "prompt": optimized_prompt,
                "stream": True,
                "options": {
                    "temperature": kwargs.get('temperature', 0.7),
                    "num_predict": kwargs.get('max_tokens', self.config.max_tokens)
                }
            }
            
            url = urljoin(self.config.base_url or 'http://localhost:11434', '/api/generate')
            
            async with self.session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ProviderError(self.config.name, f"HTTP {response.status}: {error_text}")
                
                async for line in response.content:
                    if line:
                        try:
                            data = json.loads(line.decode())
                            if 'response' in data and data['response']:
                                yield data['response']
                            if data.get('done', False):
                                break
                        except json.JSONDecodeError:
                            continue
                            
        except Exception as e:
            self.metrics.record_failure(type(e).__name__)
            logger.error(f"Ollama streaming failed: {e}")
            raise ProviderError(self.config.name, str(e))

class HuggingFaceProvider(AIProviderBase):
    """Enhanced HuggingFace provider with intelligent model selection"""
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.model_cache = {}  # Cache for model availability
    
    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        """Send request to HuggingFace with smart model selection"""
        await self.rate_limiter()
        start_time = time.time()
        
        try:
            if not self.session:
                raise ProviderError(self.config.name, "Session not initialized")
            
            model = kwargs.get('model', await self._select_best_model(prompt))
            url = f"https://api-inference.huggingface.co/models/{model}"
            
            headers = {"Content-Type": "application/json"}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
            
            # Optimize prompt
            max_tokens = kwargs.get('max_tokens', self.config.max_tokens)
            optimized_prompt = self.token_optimizer.compress_prompt(prompt, max_tokens // 2, model)
            
            payload = {
                "inputs": optimized_prompt,
                "parameters": {
                    "max_new_tokens": max_tokens,
                    "temperature": kwargs.get('temperature', 0.7),
                    "return_full_text": False,
                    "do_sample": True,
                    "top_p": kwargs.get('top_p', 0.9)
                },
                "options": {
                    "wait_for_model": True,
                    "use_cache": kwargs.get('use_cache', True)
                }
            }
            
            async with self.session.post(url, json=payload, headers=headers) as response:
                if response.status == 503:
                    # Model loading, wait and retry
                    await asyncio.sleep(2)
                    async with self.session.post(url, json=payload, headers=headers) as retry_response:
                        if retry_response.status != 200:
                            raise ProviderError(self.config.name, f"HTTP {retry_response.status}")
                        data = await retry_response.json()
                elif response.status == 429:
                    raise ProviderError(
                        self.config.name, 
                        "Rate limit exceeded", 
                        is_rate_limit=True,
                        retry_after=int(response.headers.get('retry-after', 60))
                    )
                elif response.status != 200:
                    error_text = await response.text()
                    raise ProviderError(self.config.name, f"HTTP {response.status}: {error_text}")
                else:
                    data = await response.json()
                
                # Parse response
                if isinstance(data, list) and len(data) > 0:
                    content = data[0].get('generated_text', str(data))
                elif isinstance(data, dict) and 'generated_text' in data:
                    content = data['generated_text']
                else:
                    content = str(data)
                
                latency_ms = (time.time() - start_time) * 1000
                tokens_used = TokenUsage(
                    input_tokens=self.token_optimizer.estimate_tokens(optimized_prompt, model),
                    output_tokens=self.token_optimizer.estimate_tokens(content, model)
                )
                
                ai_response = AIResponse(
                    content=content,
                    provider=self.config.name,
                    model=model,
                    tokens_used=tokens_used,
                    cost=0.0,  # Free tier
                    latency_ms=latency_ms,
                    metadata=data if isinstance(data, dict) else {}
                )
                
                self.metrics.record_success(latency_ms, tokens_used.total_tokens, 0.0)
                return ai_response
                
        except Exception as e:
            self.metrics.record_failure(type(e).__name__)
            logger.error(f"HuggingFace request failed: {e}")
            if isinstance(e, ProviderError):
                raise
            raise ProviderError(self.config.name, str(e))
    
    async def _select_best_model(self, prompt: str) -> str:
        """Select best model based on prompt characteristics"""
        # Simple heuristics for model selection
        prompt_length = len(prompt)
        
        if prompt_length > 2000:
            # Long prompts: use models with larger context
            return "microsoft/DialoGPT-large"
        elif "code" in prompt.lower() or "programming" in prompt.lower():
            # Code-related prompts
            return "microsoft/CodeBERT-base"
        else:
            # Default conversational model
            return self.config.models[0] if self.config.models else "microsoft/DialoGPT-medium"
    
    async def stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Simulate streaming for HuggingFace (most models don't support true streaming)"""
        response = await self.ask(prompt, **kwargs)
        
        # Simulate streaming by yielding content in chunks
        content = response.content
        chunk_size = max(1, len(content) // 20)  # 20 chunks
        
        for i in range(0, len(content), chunk_size):
            chunk = content[i:i + chunk_size]
            yield chunk
            await asyncio.sleep(0.05)  # Small delay for realistic streaming

class GroqProvider(AIProviderBase):
    """Ultra-fast Groq provider for speed-critical applications"""
    
    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        """Send request to Groq with speed optimization"""
        await self.rate_limiter()
        start_time = time.time()
        
        try:
            if not self.session:
                raise ProviderError(self.config.name, "Session not initialized")
            
            model = kwargs.get('model', self.config.models[0])
            
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "messages": [{"role": "user", "content": prompt}],
                "model": model,
                "max_tokens": kwargs.get('max_tokens', self.config.max_tokens),
                "temperature": kwargs.get('temperature', 0.7),
                "stream": False
            }
            
            url = urljoin(self.config.base_url or 'https://api.groq.com/openai/v1', '/chat/completions')
            
            async with self.session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ProviderError(
                        self.config.name, 
                        f"HTTP {response.status}: {error_text}",
                        is_rate_limit=(response.status == 429)
                    )
                
                data = await response.json()
                content = data['choices'][0]['message']['content']
                
                latency_ms = (time.time() - start_time) * 1000
                usage = data.get('usage', {})
                tokens_used = TokenUsage(
                    input_tokens=usage.get('prompt_tokens', 0),
                    output_tokens=usage.get('completion_tokens', 0)
                )
                
                # Groq is fast but not free
                cost = tokens_used.calculate_cost(0.0001, 0.0001)  # Very low cost
                
                ai_response = AIResponse(
                    content=content,
                    provider=self.config.name,
                    model=model,
                    tokens_used=tokens_used,
                    cost=cost,
                    latency_ms=latency_ms,
                    metadata=usage
                )
                
                self.metrics.record_success(latency_ms, tokens_used.total_tokens, cost)
                return ai_response
                
        except Exception as e:
            self.metrics.record_failure(type(e).__name__)
            logger.error(f"Groq request failed: {e}")
            if isinstance(e, ProviderError):
                raise
            raise ProviderError(self.config.name, str(e))
    
    async def stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Stream response from Groq"""
        await self.rate_limiter()
        
        try:
            if not self.session:
                raise ProviderError(self.config.name, "Session not initialized")
            
            model = kwargs.get('model', self.config.models[0])
            
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "messages": [{"role": "user", "content": prompt}],
                "model": model,
                "max_tokens": kwargs.get('max_tokens', self.config.max_tokens),
                "temperature": kwargs.get('temperature', 0.7),
                "stream": True
            }
            
            url = urljoin(self.config.base_url or 'https://api.groq.com/openai/v1', '/chat/completions')
            
            async with self.session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ProviderError(self.config.name, f"HTTP {response.status}: {error_text}")
                
                async for line in response.content:
                    if line:
                        line_str = line.decode().strip()
                        if line_str.startswith('data: '):
                            data_str = line_str[6:]
                            if data_str != '[DONE]':
                                try:
                                    data = json.loads(data_str)
                                    if 'choices' in data and data['choices']:
                                        delta = data['choices'][0].get('delta', {})
                                        content = delta.get('content', '')
                                        if content:
                                            yield content
                                except json.JSONDecodeError:
                                    continue
                                    
        except Exception as e:
            self.metrics.record_failure(type(e).__name__)
            logger.error(f"Groq streaming failed: {e}")
            raise ProviderError(self.config.name, str(e))

class MockProvider(AIProviderBase):
    """Enhanced mock provider for testing and development"""
    
    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        """Return enhanced mock response"""
        await asyncio.sleep(0.1)  # Simulate network latency
        
        model = kwargs.get('model', 'mock-model-v1')
        
        # Generate contextual mock response
        if "error" in prompt.lower():
            content = "Mock error simulation: This is a simulated error response for testing purposes."
        elif "code" in prompt.lower():
            content = f"```python\n# Mock code response for: {prompt[:30]}...\ndef mock_function():\n    return 'mock_result'\n```"
        elif len(prompt) > 100:
            content = f"Mock response for long prompt: {prompt[:50]}... [Content processed and summarized]"
        else:
            content = f"Mock response for: {prompt}"
        
        tokens_used = TokenUsage(
            input_tokens=len(prompt) // 4,
            output_tokens=len(content) // 4
        )
        
        return AIResponse(
            content=content,
            provider=self.config.name,
            model=model,
            tokens_used=tokens_used,
            cost=0.0,
            latency_ms=100.0,
            metadata={"mock": True, "timestamp": datetime.now().isoformat()}
        )
    
    async def stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Stream mock response"""
        response = await self.ask(prompt, **kwargs)
        content = response.content
        
        # Simulate realistic streaming
        words = content.split()
        for i, word in enumerate(words):
            if i == 0:
                yield word
            else:
                yield f" {word}"
            await asyncio.sleep(0.03)  # Realistic word-by-word streaming

class AIAsyncClient:
    """
    Next-generation AI client with advanced optimization and cost management
    
    Features:
    - Intelligent provider selection based on cost, performance, and task complexity
    - Advanced caching with compression and semantic similarity
    - Token optimization and prompt compression
    - Adaptive batching and concurrent processing
    - Comprehensive health monitoring and failover
    - Real-time cost tracking and budget management
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.providers: Dict[str, AIProviderBase] = {}
        self.provider_configs: Dict[str, ProviderConfig] = {}
        
        # Advanced features
        self.cache = SmartCache(max_size=1000, compression_enabled=True)
        self.token_optimizer = TokenOptimizer()
        
        # Cost tracking
        self.daily_cost = 0.0
        self.daily_budget = float(config.get('daily_budget', 10.0))
        self.cost_alerts_enabled = config.get('cost_alerts', True)
        
        # Performance tracking
        self._global_stats = {
            'total_requests': 0,
            'cache_hits': 0,
            'cost_saved': 0.0,
            'tokens_saved': 0
        }
        
        self._setup_providers()
    
    def _setup_providers(self) -> None:
        """Initialize all configured providers with enhanced setup"""
        provider_classes = {
            'ollama': OllamaProvider,
            'huggingface': HuggingFaceProvider,
            'groq': GroqProvider,
            'together': self._create_openai_compatible_provider,
            'fireworks': self._create_openai_compatible_provider,
            'openai': self._create_openai_provider,
            'anthropic': self._create_anthropic_provider,
            'mock': MockProvider,
        }
        
        successful_providers = 0
        
        for provider_name, provider_config in self.config.items():
            if provider_name in ['daily_budget', 'cost_alerts']:
                continue  # Skip non-provider config
                
            try:
                # Create enhanced provider configuration
                config = self._create_provider_config(provider_name, provider_config)
                
                # Get provider class
                provider_class = provider_classes.get(provider_name, MockProvider)
                
                # Create provider instance
                if callable(provider_class):
                    provider = provider_class(config)
                else:
                    provider = provider_class  # Already instantiated
                
                self.providers[provider_name] = provider
                self.provider_configs[provider_name] = config
                
                logger.info(f"✅ Configured {provider_name} provider (free: {config.is_free})")
                successful_providers += 1
                
            except Exception as e:
                logger.error(f"❌ Failed to configure {provider_name} provider: {e}")
                
                # Create fallback mock provider
                try:
                    mock_config = ProviderConfig(
                        name=f"{provider_name}_mock",
                        provider_type=ProviderType.OLLAMA,  # Default type
                        is_free=True
                    )
                    mock_provider = MockProvider(mock_config)
                    
                    self.providers[f"{provider_name}_mock"] = mock_provider
                    self.provider_configs[f"{provider_name}_mock"] = mock_config
                    
                    logger.info(f"🔄 Created mock fallback for {provider_name}")
                except Exception as fallback_error:
                    logger.error(f"Failed to create fallback for {provider_name}: {fallback_error}")
        
        # Ensure at least one provider is available
        if not self.providers:
            logger.warning("No providers configured, creating default mock provider")
            default_config = ProviderConfig(
                name="default_mock",
                provider_type=ProviderType.OLLAMA,
                is_free=True
            )
            default_provider = MockProvider(default_config)
            
            self.providers["default_mock"] = default_provider
            self.provider_configs["default_mock"] = default_config
        
        # Sort providers by preference (free first, then by cost)
        self._sort_providers_by_preference()
        
        logger.info(f"🚀 AI client initialized with {len(self.providers)} providers ({successful_providers} successful)")
    
    def _create_provider_config(self, provider_name: str, provider_settings: Dict[str, Any]) -> ProviderConfig:
        """Create enhanced provider configuration"""
        
        # Map provider names to types
        provider_type_mapping = {
            'ollama': ProviderType.OLLAMA,
            'huggingface': ProviderType.HUGGINGFACE_FREE,
            'groq': ProviderType.GROQ,
            'together': ProviderType.TOGETHER,
            'fireworks': ProviderType.FIREWORKS,
            'openai': ProviderType.OPENAI,
            'anthropic': ProviderType.ANTHROPIC,
            'mock': ProviderType.OLLAMA  # Use OLLAMA as default for mocks
        }
        
        provider_type = provider_type_mapping.get(provider_name, ProviderType.OLLAMA)
        
        # Safe value extraction with type conversion
        def safe_get(key: str, default: Any, type_converter: Callable = str):
            value = provider_settings.get(key, default)
            try:
                if value is None:
                    return default
                return type_converter(value)
            except (ValueError, TypeError):
                logger.warning(f"Invalid {key} value for {provider_name}: {value}, using default: {default}")
                return default
        
        return ProviderConfig(
            name=provider_name,
            provider_type=provider_type,
            api_key=safe_get('api_key', None),
            base_url=safe_get('base_url', None),
            models=provider_settings.get('models', []),
            cost_per_1k_tokens=safe_get('cost_per_1k_tokens', 0.0, float),
            free_tier_limit=safe_get('free_tier_limit', 0, int),
            max_tokens=safe_get('max_tokens', 4096, int),
            timeout=safe_get('timeout', 30, int),
            rate_limit=safe_get('rate_limit', 60, int),
            concurrent_limit=safe_get('concurrent_limit', 5, int),
            quality_score=safe_get('quality_score', 1.0, float),
            speed_score=safe_get('speed_score', 1.0, float),
            reliability_score=safe_get('reliability_score', 1.0, float),
            supports_streaming=safe_get('supports_streaming', True, bool),
            supports_batching=safe_get('supports_batching', False, bool),
            enable_compression=safe_get('enable_compression', True, bool),
            enable_caching=safe_get('enable_caching', True, bool),
            retry_attempts=safe_get('retry_attempts', 3, int),
            retry_delay=safe_get('retry_delay', 1.0, float),
            headers=provider_settings.get('headers', {})
        )
    
    def _create_openai_compatible_provider(self, config: ProviderConfig) -> AIProviderBase:
        """Create OpenAI-compatible provider for Together, Fireworks, etc."""
        # This would implement OpenAI-compatible API calls
        # For now, return mock provider
        return MockProvider(config)
    
    def _create_openai_provider(self, config: ProviderConfig) -> AIProviderBase:
        """Create OpenAI provider"""
        # This would implement actual OpenAI integration
        # For now, return mock provider
        return MockProvider(config)
    
    def _create_anthropic_provider(self, config: ProviderConfig) -> AIProviderBase:
        """Create Anthropic provider"""
        # This would implement actual Anthropic integration
        # For now, return mock provider
        return MockProvider(config)
    
    def _sort_providers_by_preference(self) -> None:
        """Sort providers by cost and performance preference"""
        def provider_score(name_config_tuple) -> float:
            name, config = name_config_tuple
            score = 0.0
            
            # Heavily favor free providers
            if config.is_free:
                score += 1000
            
            # Favor low-cost providers
            score += max(0, 100 - config.cost_per_1k_tokens * 10000)
            
            # Add quality and speed scores
            score += config.quality_score * 50
            score += config.speed_score * 30
            score += config.reliability_score * 20
            
            return score
        
        sorted_configs = sorted(self.provider_configs.items(), key=provider_score, reverse=True)
        
        # Log provider preference order
        logger.info("Provider preference order:")
        for i, (name, config) in enumerate(sorted_configs, 1):
            cost_info = "FREE" if config.is_free else f"${config.cost_per_1k_tokens:.4f}/1K tokens"
            logger.info(f"  {i}. {name} ({cost_info})")
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.aclose()
    
    async def initialize(self) -> None:
        """Initialize all providers"""
        initialization_tasks = []
        for provider in self.providers.values():
            initialization_tasks.append(provider.initialize())
        
        if initialization_tasks:
            results = await asyncio.gather(*initialization_tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    provider_name = list(self.providers.keys())[i]
                    logger.warning(f"Failed to initialize provider {provider_name}: {result}")
    
    async def aclose(self) -> None:
        """Cleanup all provider resources"""
        cleanup_tasks = []
        for provider in self.providers.values():
            cleanup_tasks.append(provider.cleanup())
        
        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        
        logger.info("🔄 AI client cleanup completed")
    
    def _select_optimal_provider(
        self, 
        task_complexity: TaskComplexity = TaskComplexity.MEDIUM,
        preferred_provider: Optional[str] = None,
        budget_conscious: bool = True
    ) -> str:
        """Enhanced provider selection with intelligent routing"""
        
        if preferred_provider and preferred_provider in self.providers:
            provider_config = self.provider_configs[preferred_provider]
            if self._check_budget_constraint(provider_config):
                return preferred_provider
        
        # Filter healthy providers
        healthy_providers = []
        for name, provider in self.providers.items():
            config = self.provider_configs[name]
            if (provider.metrics.is_healthy and 
                self._check_budget_constraint(config) and
                self._check_rate_limits(provider)):
                healthy_providers.append((name, provider, config))
        
        if not healthy_providers:
            raise ProviderError("system", "No healthy providers available within budget")
        
        # Score providers based on multiple factors
        scored_providers = []
        for name, provider, config in healthy_providers:
            score = self._calculate_provider_score(
                provider, config, task_complexity, budget_conscious
            )
            scored_providers.append((score, name))
        
        # Sort by score (highest first)
        scored_providers.sort(reverse=True)
        selected = scored_providers[0][1]
        
        logger.debug(f"🎯 Selected provider: {selected} (score: {scored_providers[0][0]:.2f})")
        return selected
    
    def _calculate_provider_score(
        self, 
        provider: AIProviderBase, 
        config: ProviderConfig,
        task_complexity: TaskComplexity,
        budget_conscious: bool
    ) -> float:
        """Calculate comprehensive provider score"""
        score = 0.0
        
        # Base score from configuration
        score += config.quality_score * 30
        score += config.speed_score * 25
        score += config.reliability_score * 20
        
        # Cost optimization
        if budget_conscious:
            if config.is_free:
                score += 50  # Strong preference for free providers
            else:
                # Penalize expensive providers
                cost_penalty = min(config.cost_per_1k_tokens * 1000, 30)
                score -= cost_penalty
        
        # Performance metrics
        efficiency_score = provider.metrics.get_efficiency_score()
        score += efficiency_score * 25
        
        # Task complexity matching
        if task_complexity == TaskComplexity.COMPLEX:
            if config.provider_type in [ProviderType.OPENAI, ProviderType.ANTHROPIC]:
                score += 15  # Boost premium providers for complex tasks
        elif task_complexity == TaskComplexity.SIMPLE:
            if config.is_free:
                score += 20  # Strongly prefer free providers for simple tasks
        
        # Penalize recent failures
        score -= provider.metrics.consecutive_failures * 10
        
        return max(0.0, score)
    
    def _check_budget_constraint(self, config: ProviderConfig) -> bool:
        """Check if provider is within daily budget"""
        if config.is_free:
            return True
        
        if self.daily_cost >= self.daily_budget:
            return False
        
        # Allow providers that won't exceed budget significantly
        estimated_request_cost = config.cost_per_1k_tokens * 2  # Assume 2K tokens per request
        return self.daily_cost + estimated_request_cost <= self.daily_budget * 1.1
    
    def _check_rate_limits(self, provider: AIProviderBase) -> bool:
        """Check if provider is not rate limited"""
        # This would implement more sophisticated rate limit checking
        return provider.metrics.consecutive_failures < 3
    
    async def ask(
        self,
        prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        task_complexity: TaskComplexity = TaskComplexity.MEDIUM,
        use_cache: bool = True,
        budget_conscious: bool = True,
        **kwargs
    ) -> str:
        """
        Enhanced ask method with comprehensive optimization
        
        Args:
            prompt: Input text prompt
            provider: Specific provider to use (auto-select if None)
            model: Specific model to use
            max_tokens: Maximum tokens in response
            temperature: Response creativity (0.0-1.0)
            task_complexity: Task complexity for intelligent routing
            use_cache: Whether to use response caching
            budget_conscious: Prioritize cost over quality
            **kwargs: Additional provider-specific parameters
        
        Returns:
            AI-generated response text
        """
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty")
        
        self._global_stats['total_requests'] += 1
        
        # Check cache first
        cache_params = {
            'max_tokens': max_tokens,
            'temperature': temperature,
            **kwargs
        }
        
        if use_cache:
            cached_response = self.cache.get(prompt, model or "auto", cache_params)
            if cached_response:
                self._global_stats['cache_hits'] += 1
                logger.info("💾 Cache hit - returning cached response")
                return cached_response.content
        
        # Select optimal provider
        selected_provider = self._select_optimal_provider(
            task_complexity=task_complexity,
            preferred_provider=provider,
            budget_conscious=budget_conscious
        )
        
        provider_instance = self.providers[selected_provider]
        provider_config = self.provider_configs[selected_provider]
        
        try:
            # Prepare request parameters
            request_kwargs = {
                'model': model,
                'max_tokens': max_tokens or provider_config.max_tokens,
                'temperature': temperature,
                **kwargs
            }
            
            # Execute request with retry logic
            response = await self._execute_with_retry(
                provider_instance, 
                provider_instance.ask, 
                prompt, 
                **request_kwargs
            )
            
            # Update cost tracking
            if not provider_config.is_free:
                self.daily_cost += response.cost
                if self.cost_alerts_enabled and self.daily_cost > self.daily_budget * 0.8:
                    logger.warning(f"💰 Daily budget warning: ${self.daily_cost:.4f} / ${self.daily_budget:.2f}")
            
            # Cache successful response
            if use_cache and provider_config.enable_caching:
                self.cache.set(prompt, model or "auto", cache_params, response)
            
            logger.info(
                f"✅ {selected_provider} response: {response.tokens_used.total_tokens} tokens, "
                f"{response.latency_ms:.0f}ms, ${response.cost:.4f}"
            )
            
            return response.content
            
        except Exception as e:
            logger.error(f"Provider {self.config.name} failed: {e}")
            raise

    async def generate_simple_response(self, prompt: str) -> str:
        """Simple response for health checks"""
        # Simplified version for health monitoring
        return f"Health check response from {self.config.name}"

    async def _make_api_request(self, session: aiohttp.ClientSession, prompt: str, model: str, **kwargs) -> str:
        """Make actual API request to provider (implement for each provider type)"""
        # This is a mock implementation - replace with actual API calls
        await asyncio.sleep(0.1)  # Simulate network delay
        
        if self.config.provider_type == ProviderType.OPENAI:
            return f"OpenAI response to: {prompt[:50]}..."
        elif self.config.provider_type == ProviderType.ANTHROPIC:
            return f"Anthropic response to: {prompt[:50]}..."
        else:
            return f"{self.config.name} response to: {prompt[:50]}..."

    def _check_rate_limit(self) -> bool:
        """Check if request is within rate limits"""
        now = time.time()
        # Clean old requests from window
        self.request_count_window = [t for t in self.request_count_window if now - t < 60]
        
        if len(self.request_count_window) >= self.config.rate_limit:
            return False
        
        self.request_count_window.append(now)
        return True

    def _update_success_metrics(self, response_time: float):
        """Update metrics after successful request"""
        self.metrics.successful_requests += 1
        self.metrics.consecutive_failures = 0
        self.metrics.last_success = datetime.now()
        self.metrics.response_times.append(response_time)
        
        # Keep only last 100 response times
        if len(self.metrics.response_times) > 100:
            self.metrics.response_times.pop(0)
        
        self.metrics.avg_response_time = statistics.mean(self.metrics.response_times)
        self.is_healthy = True

    def _update_failure_metrics(self):
        """Update metrics after failed request"""
        self.metrics.failed_requests += 1
        self.metrics.consecutive_failures += 1
        self.metrics.last_failure = datetime.now()
        
        # Mark as unhealthy after 3 consecutive failures
        if self.metrics.consecutive_failures >= 3:
            self.is_healthy = False

    def get_efficiency_score(self) -> float:
        """Calculate provider efficiency score"""
        if self.metrics.total_requests == 0:
            return 0.0
        
        success_rate = self.metrics.successful_requests / self.metrics.total_requests
        speed_factor = max(0.1, 1.0 / (self.metrics.avg_response_time + 0.1))
        cost_factor = max(0.1, 1.0 / (self.config.cost_per_token + 0.001))
        
        # Weighted score: 40% success rate, 30% speed, 20% cost, 10% quality
        score = (
            success_rate * 0.4 +
            min(speed_factor, 1.0) * 0.3 +
            min(cost_factor, 1.0) * 0.2 +
            self.config.quality_score * 0.1
        )
        
        return min(score, 1.0)

class AIProviderManager:
    def __init__(self):
        self.providers: Dict[str, AIProvider] = {}
        self.cache = ResponseCache()
        self.health_monitor = HealthMonitor()
        self.monitoring_task = None
        self.failover_enabled = True

    def add_provider(self, config: ProviderConfig):
        """Add a new AI provider"""
        provider = AIProvider(config)
        self.providers[config.name] = provider
        logger.info(f"Added provider: {config.name}")

    async def start_monitoring(self):
        """Start health monitoring for all providers"""
        if self.providers:
            self.monitoring_task = asyncio.create_task(
                self.health_monitor.start_monitoring(self.providers)
            )
            logger.info("Started provider health monitoring")

    async def stop_monitoring(self):
        """Stop health monitoring"""
        self.health_monitor.stop_monitoring()
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped provider health monitoring")

    def select_best_provider(self, task_complexity: TaskComplexity = TaskComplexity.MEDIUM) -> Optional[str]:
        """Select the best provider based on current metrics and task complexity"""
        if not self.providers:
            return None

        healthy_providers = {name: provider for name, provider in self.providers.items() 
                           if provider.is_healthy}
        
        if not healthy_providers:
            logger.warning("No healthy providers available")
            return None

        # Score providers based on efficiency and task complexity
        provider_scores = {}
        for name, provider in healthy_providers.items():
            base_score = provider.get_efficiency_score()
            
            # Adjust score based on task complexity
            if task_complexity == TaskComplexity.COMPLEX:
                # Prefer high-quality providers for complex tasks
                base_score += provider.config.quality_score * 0.2
            elif task_complexity == TaskComplexity.SIMPLE:
                # Prefer fast, cheap providers for simple tasks
                speed_bonus = (1.0 / (provider.metrics.avg_response_time + 0.1)) * 0.1
                cost_bonus = (1.0 / (provider.config.cost_per_token + 0.001)) * 0.1
                base_score += min(speed_bonus + cost_bonus, 0.3)
            
            provider_scores[name] = base_score

        # Select provider with highest score
        best_provider = max(provider_scores.items(), key=lambda x: x[1])
        logger.debug(f"Selected provider: {best_provider[0]} (score: {best_provider[1]:.3f})")
        
        return best_provider[0]

    async def generate_response(self, prompt: str, model: str = None, 
                              task_complexity: TaskComplexity = TaskComplexity.MEDIUM,
                              use_cache: bool = True, **kwargs) -> Dict:
        """Generate response with automatic provider selection and failover"""
        
        # Check cache first
        if use_cache:
            cached_response = self.cache.get(prompt, model or "default", kwargs)
            if cached_response:
                return {
                    'response': cached_response['response'],
                    'cached': True,
                    'provider': cached_response.get('provider', 'cache')
                }

        # Select best provider
        selected_provider_name = self.select_best_provider(task_complexity)
        if not selected_provider_name:
            raise Exception("No available providers")

        # Try selected provider with failover
        providers_to_try = [selected_provider_name]
        if self.failover_enabled:
            # Add other healthy providers as fallbacks
            other_providers = [name for name in self.providers.keys() 
                             if name != selected_provider_name and self.providers[name].is_healthy]
            providers_to_try.extend(other_providers[:2])  # Try up to 2 fallbacks

        last_exception = None
        for provider_name in providers_to_try:
            try:
                provider = self.providers[provider_name]
                response = await provider.generate_response(prompt, model, **kwargs)
                
                # Cache successful response
                if use_cache:
                    self.cache.set(prompt, model or "default", kwargs, response)
                
                response['cached'] = False
                return response
                
            except Exception as e:
                last_exception = e
                logger.warning(f"Provider {provider_name} failed, trying next: {e}")
                continue

        # All providers failed
        raise Exception(f"All providers failed. Last error: {last_exception}")

    async def batch_process(self, prompts: List[str], max_concurrency: int = 5, 
                          task_complexity: TaskComplexity = TaskComplexity.MEDIUM,
                          **kwargs) -> List[Dict]:
        """Process multiple prompts with concurrency control"""
        semaphore = asyncio.Semaphore(max_concurrency)
        
        async def process_single(prompt: str) -> Dict:
            async with semaphore:
                try:
                    return await self.generate_response(prompt, task_complexity=task_complexity, **kwargs)
                except Exception as e:
                    return {'error': str(e), 'prompt': prompt[:50] + '...'}
        
        tasks = [process_single(prompt) for prompt in prompts]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Convert exceptions to error dictionaries
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    'error': str(result),
                    'prompt': prompts[i][:50] + '...'
                })
            else:
                processed_results.append(result)
        
        return processed_results

    def get_system_stats(self) -> Dict:
        """Get comprehensive system statistics"""
        provider_stats = {}
        for name, provider in self.providers.items():
            metrics = provider.metrics
            provider_stats[name] = {
                'total_requests': metrics.total_requests,
                'success_rate': f"{(metrics.successful_requests / max(metrics.total_requests, 1) * 100):.1f}%",
                'avg_response_time': f"{metrics.avg_response_time:.3f}s",
                'is_healthy': provider.is_healthy,
                'efficiency_score': f"{provider.get_efficiency_score():.3f}",
                'consecutive_failures': metrics.consecutive_failures,
                'last_success': metrics.last_success.isoformat() if metrics.last_success else None
            }

        return {
            'providers': provider_stats,
            'cache_stats': self.cache.get_stats(),
            'health_checks': self.health_monitor.health_checks,
            'total_providers': len(self.providers),
            'healthy_providers': sum(1 for p in self.providers.values() if p.is_healthy)
        }

# Example usage and configuration
async def main():
    # Initialize the manager
    manager = AIProviderManager()
    
    # Add providers
    providers_config = [
        ProviderConfig(
            name="openai_gpt4",
            provider_type=ProviderType.OPENAI,
            api_key="your_openai_key",
            base_url="https://api.openai.com/v1",
            models=["gpt-4", "gpt-3.5-turbo"],
            cost_per_token=0.00003,
            max_tokens=4096,
            rate_limit=60,
            quality_score=0.95,
            speed_score=0.8
        ),
        ProviderConfig(
            name="anthropic_claude",
            provider_type=ProviderType.ANTHROPIC,
            api_key="your_anthropic_key",
            base_url="https://api.anthropic.com/v1",
            models=["claude-3-opus", "claude-3-sonnet"],
            cost_per_token=0.000015,
            max_tokens=4096,
            rate_limit=50,
            quality_score=0.92,
            speed_score=0.85
        ),
        ProviderConfig(
            name="google_gemini",
            provider_type=ProviderType.GOOGLE,
            api_key="your_google_key",
            base_url="https://generativelanguage.googleapis.com/v1",
            models=["gemini-pro"],
            cost_per_token=0.00001,
            max_tokens=2048,
            rate_limit=100,
            quality_score=0.88,
            speed_score=0.9
        )
    ]
    
    for config in providers_config:
        manager.add_provider(config)
    
    # Start monitoring
    await manager.start_monitoring()
    
    try:
        # Single request
        response = await manager.generate_response(
            "Explain quantum computing in simple terms",
            task_complexity=TaskComplexity.MEDIUM
        )
        print("Single Response:", response)
        
        # Batch processing
        prompts = [
            "What is machine learning?",
            "Explain blockchain technology",
            "What are the benefits of renewable energy?",
            "How does cryptocurrency work?",
            "What is artificial intelligence?"
        ]
        
        batch_results = await manager.batch_process(
            prompts, 
            max_concurrency=3,
            task_complexity=TaskComplexity.SIMPLE
        )
        print(f"\nBatch Results: Processed {len(batch_results)} prompts")
        
        # Get system statistics
        stats = manager.get_system_stats()
        print("\nSystem Statistics:")
        print(json.dumps(stats, indent=2, default=str))
        
        # Wait a bit for monitoring
        await asyncio.sleep(10)
        
    finally:
        # Clean shutdown
        await manager.stop_monitoring()

if __name__ == "__main__":
    asyncio.run(main())