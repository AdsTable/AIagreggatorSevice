# services/ai_async_client.py
"""
AI Async Client - Production-ready implementation with English comments
Optimized for performance, cost-effectiveness, and maintainability
Combined from # ai_async_client__complex_async-3.py and ai_async_client__complex_async-4.py
"""
from __future__ import annotations
import asyncio
import json
import logging
import time
import hashlib
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union, AsyncGenerator
from enum import Enum
from collections import defaultdict, deque
from datetime import datetime
import aiohttp
import ssl
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

# Global response cache for cost optimization
_response_cache: Dict[str, tuple[str, float]] = {}
CACHE_TTL = 3600  # 1 hour cache TTL

class ProviderType(Enum):
    """Supported AI providers ordered by cost-effectiveness"""
    OLLAMA = "ollama"              # Free local inference
    HUGGINGFACE = "huggingface"    # Free tier available
    GROQ = "groq"                  # Fast and affordable
    OPENAI = "openai"              # Premium provider
    YANDEXGPT = "yandexgpt"        # Regional provider
    MOCK = "mock"                  # Testing/fallback

class TaskComplexity(Enum):
    """Task complexity levels for intelligent routing"""
    SIMPLE = "simple"        # Basic Q&A, translations
    MEDIUM = "medium"        # Analysis, summarization
    COMPLEX = "complex"      # Code generation, reasoning

@dataclass
class ProviderConfig:
    """Enhanced provider configuration with cost optimization"""
    name: str
    provider_type: ProviderType
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    max_tokens: int = 4096
    timeout: int = 30
    cost_per_1k_tokens: float = 0.0
    priority: int = 50
    is_free: bool = False
    rate_limit: int = 60  # requests per minute
    retry_attempts: int = 3
    retry_delay: float = 1.0
    headers: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        """Auto-configure based on cost"""
        if self.cost_per_1k_tokens <= 0.001:
            self.is_free = True
            self.priority += 30

@dataclass
class TokenUsage:
    """Token usage tracking with cost calculation"""
    input_tokens: int = 0
    output_tokens: int = 0
    
    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

@dataclass
class AIResponse:
    """AI response with comprehensive metadata"""
    content: str
    provider: str
    model: str
    tokens_used: TokenUsage
    cost: float = 0.0
    latency_ms: float = 0.0
    cached: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

class ProviderError(Exception):
    """Enhanced exception with error categorization"""
    def __init__(self, provider: str, message: str, error_code: Optional[str] = None, 
                 is_rate_limit: bool = False):
        self.provider = provider
        self.error_code = error_code
        self.is_rate_limit = is_rate_limit
        super().__init__(f"[{provider}] {message}")

class ProviderMetrics:
    """Performance metrics tracking for providers"""
    
    def __init__(self):
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.consecutive_failures = 0
        self.last_success: Optional[datetime] = None
        self.last_failure: Optional[datetime] = None
        self.response_times = deque(maxlen=100)
        self.is_healthy = True
        
    def record_success(self, response_time: float):
        """Record successful request"""
        self.total_requests += 1
        self.successful_requests += 1
        self.consecutive_failures = 0
        self.last_success = datetime.now()
        self.response_times.append(response_time)
        self.is_healthy = True
        
    def record_failure(self):
        """Record failed request"""
        self.total_requests += 1
        self.failed_requests += 1
        self.consecutive_failures += 1
        self.last_failure = datetime.now()
        
        # Mark unhealthy after 3 consecutive failures
        if self.consecutive_failures >= 3:
            self.is_healthy = False
    
    def get_success_rate(self) -> float:
        """Calculate success rate"""
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests
    
    def get_avg_response_time(self) -> float:
        """Get average response time"""
        if not self.response_times:
            return 0.0
        return sum(self.response_times) / len(self.response_times)

class AIProviderBase(ABC):
    """Base class for AI providers with common functionality"""
    
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.metrics = ProviderMetrics()
        self.session: Optional[aiohttp.ClientSession] = None
        self._last_request_time = 0.0
        
    async def initialize(self) -> None:
        """Initialize HTTP session with optimized settings"""
        try:
            connector = aiohttp.TCPConnector(
                limit=20,
                limit_per_host=10,
                ttl_dns_cache=300,
                ssl=ssl.create_default_context()
            )
            
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers=self.config.headers
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
                await asyncio.sleep(0.1)  # Allow cleanup
            except Exception as e:
                logger.warning(f"Error closing session for {self.config.name}: {e}")
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count (4 chars per token approximation)"""
        return max(1, len(text) // 4)
    
    def _calculate_cost(self, tokens: int) -> float:
        """Calculate cost based on token usage"""
        return (tokens / 1000) * self.config.cost_per_1k_tokens
    
    def _get_cache_key(self, prompt: str, **kwargs) -> str:
        """Generate cache key for request"""
        cache_data = {
            'prompt': prompt,
            'model': kwargs.get('model', self.config.model),
            'provider': self.config.name
        }
        cache_str = json.dumps(cache_data, sort_keys=True)
        return hashlib.md5(cache_str.encode()).hexdigest()
    
    def _get_cached_response(self, cache_key: str) -> Optional[str]:
        """Get response from cache if valid"""
        if cache_key in _response_cache:
            response, timestamp = _response_cache[cache_key]
            if time.time() - timestamp < CACHE_TTL:
                return response
            else:
                del _response_cache[cache_key]
        return None
    
    def _cache_response(self, cache_key: str, response: str):
        """Cache response with TTL"""
        _response_cache[cache_key] = (response, time.time())
        
        # Simple cache size management
        if len(_response_cache) > 1000:
            oldest_keys = sorted(_response_cache.items(), key=lambda x: x[1][1])[:200]
            for key, _ in oldest_keys:
                del _response_cache[key]
    
    async def _apply_rate_limit(self):
        """Apply rate limiting between requests"""
        now = time.time()
        time_since_last = now - self._last_request_time
        min_interval = 60.0 / self.config.rate_limit
        
        if time_since_last < min_interval:
            sleep_time = min_interval - time_since_last
            await asyncio.sleep(sleep_time)
        
        self._last_request_time = time.time()
    
    @abstractmethod
    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        """Send request to AI provider"""
        pass
    
    async def stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Default streaming implementation (simulate)"""
        response = await self.ask(prompt, **kwargs)
        content = response.content
        
        # Simulate streaming by yielding words
        words = content.split()
        for i, word in enumerate(words):
            if i == 0:
                yield word
            else:
                yield f" {word}"
            await asyncio.sleep(0.03)

class OllamaProvider(AIProviderBase):
    """Ollama local provider - completely free"""
    
    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        """Send request to Ollama with optimization"""
        if not self.metrics.is_healthy:
            raise ProviderError(self.config.name, "Provider marked as unhealthy")
        
        # Check cache first
        cache_key = self._get_cache_key(prompt, **kwargs)
        cached_response = self._get_cached_response(cache_key)
        if cached_response:
            logger.debug(f"Cache hit for {self.config.name}")
            return AIResponse(
                content=cached_response,
                provider=self.config.name,
                model=kwargs.get('model', self.config.model or 'llama3.2'),
                tokens_used=TokenUsage(output_tokens=self._estimate_tokens(cached_response)),
                cost=0.0,
                latency_ms=1.0,
                cached=True
            )
        
        await self._apply_rate_limit()
        start_time = time.time()
        
        try:
            if not self.session:
                raise ProviderError(self.config.name, "Session not initialized")
            
            model = kwargs.get('model', self.config.model or 'llama3.2:1b')
            
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": kwargs.get('temperature', 0.7),
                    "num_predict": kwargs.get('max_tokens', self.config.max_tokens),
                }
            }
            
            url = urljoin(self.config.base_url or 'http://localhost:11434', '/api/generate')
            
            async with self.session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.metrics.record_failure()
                    raise ProviderError(
                        self.config.name, 
                        f"HTTP {response.status}: {error_text}",
                        is_rate_limit=(response.status == 429)
                    )
                
                data = await response.json()
                content = data.get('response', '').strip()
                
                if not content:
                    self.metrics.record_failure()
                    raise ProviderError(self.config.name, "Empty response received")
                
                latency_ms = (time.time() - start_time) * 1000
                tokens_used = TokenUsage(
                    input_tokens=self._estimate_tokens(prompt),
                    output_tokens=self._estimate_tokens(content)
                )
                
                # Cache successful response
                self._cache_response(cache_key, content)
                self.metrics.record_success(latency_ms)
                
                return AIResponse(
                    content=content,
                    provider=self.config.name,
                    model=model,
                    tokens_used=tokens_used,
                    cost=0.0,  # Free
                    latency_ms=latency_ms,
                    metadata=data
                )
                
        except Exception as e:
            self.metrics.record_failure()
            logger.error(f"Ollama request failed: {e}")
            if isinstance(e, ProviderError):
                raise
            raise ProviderError(self.config.name, str(e))

class HuggingFaceProvider(AIProviderBase):
    """HuggingFace provider with free tier support"""
    
    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        """Send request to HuggingFace with smart model selection"""
        if not self.metrics.is_healthy:
            raise ProviderError(self.config.name, "Provider marked as unhealthy")
        
        # Check cache first
        cache_key = self._get_cache_key(prompt, **kwargs)
        cached_response = self._get_cached_response(cache_key)
        if cached_response:
            return AIResponse(
                content=cached_response,
                provider=self.config.name,
                model=kwargs.get('model', 'microsoft/DialoGPT-medium'),
                tokens_used=TokenUsage(output_tokens=self._estimate_tokens(cached_response)),
                cost=0.0,
                latency_ms=1.0,
                cached=True
            )
        
        await self._apply_rate_limit()
        start_time = time.time()
        
        try:
            if not self.session:
                raise ProviderError(self.config.name, "Session not initialized")
            
            model = kwargs.get('model', self.config.model or 'microsoft/DialoGPT-medium')
            url = f"https://api-inference.huggingface.co/models/{model}"
            
            headers = {"Content-Type": "application/json"}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
            
            payload = {
                "inputs": prompt,
                "parameters": {
                    "max_new_tokens": kwargs.get('max_tokens', min(512, self.config.max_tokens)),
                    "temperature": kwargs.get('temperature', 0.7),
                    "return_full_text": False,
                    "do_sample": True
                },
                "options": {
                    "wait_for_model": True,
                    "use_cache": True
                }
            }
            
            async with self.session.post(url, json=payload, headers=headers) as response:
                # Handle model loading
                if response.status == 503:
                    await asyncio.sleep(3)
                    async with self.session.post(url, json=payload, headers=headers) as retry_response:
                        response = retry_response
                
                if response.status == 429:
                    self.metrics.record_failure()
                    raise ProviderError(
                        self.config.name, 
                        "Rate limit exceeded", 
                        is_rate_limit=True
                    )
                
                if response.status != 200:
                    error_text = await response.text()
                    self.metrics.record_failure()
                    raise ProviderError(self.config.name, f"HTTP {response.status}: {error_text}")
                
                data = await response.json()
                
                # Parse response format variations
                if isinstance(data, list) and data:
                    content = data[0].get('generated_text', str(data))
                elif isinstance(data, dict):
                    content = data.get('generated_text', str(data))
                else:
                    content = str(data)
                
                content = content.strip()
                if not content:
                    self.metrics.record_failure()
                    raise ProviderError(self.config.name, "Empty response received")
                
                latency_ms = (time.time() - start_time) * 1000
                tokens_used = TokenUsage(
                    input_tokens=self._estimate_tokens(prompt),
                    output_tokens=self._estimate_tokens(content)
                )
                
                # Cache successful response
                self._cache_response(cache_key, content)
                self.metrics.record_success(latency_ms)
                
                return AIResponse(
                    content=content,
                    provider=self.config.name,
                    model=model,
                    tokens_used=tokens_used,
                    cost=0.0,  # Free tier
                    latency_ms=latency_ms,
                    metadata=data if isinstance(data, dict) else {}
                )
                
        except Exception as e:
            self.metrics.record_failure()
            logger.error(f"HuggingFace request failed: {e}")
            if isinstance(e, ProviderError):
                raise
            raise ProviderError(self.config.name, str(e))

class GroqProvider(AIProviderBase):
    """Groq provider - fast and affordable"""
    
    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        """Send request to Groq with speed optimization"""
        if not self.metrics.is_healthy:
            raise ProviderError(self.config.name, "Provider marked as unhealthy")
        
        # Check cache
        cache_key = self._get_cache_key(prompt, **kwargs)
        cached_response = self._get_cached_response(cache_key)
        if cached_response:
            return AIResponse(
                content=cached_response,
                provider=self.config.name,
                model=kwargs.get('model', 'llama3-8b-8192'),
                tokens_used=TokenUsage(output_tokens=self._estimate_tokens(cached_response)),
                cost=0.0,
                latency_ms=1.0,
                cached=True
            )
        
        await self._apply_rate_limit()
        start_time = time.time()
        
        try:
            if not self.session:
                raise ProviderError(self.config.name, "Session not initialized")
            
            model = kwargs.get('model', self.config.model or 'llama3-8b-8192')
            
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
                    self.metrics.record_failure()
                    raise ProviderError(
                        self.config.name, 
                        f"HTTP {response.status}: {error_text}",
                        is_rate_limit=(response.status == 429)
                    )
                
                data = await response.json()
                content = data['choices'][0]['message']['content'].strip()
                
                latency_ms = (time.time() - start_time) * 1000
                usage = data.get('usage', {})
                tokens_used = TokenUsage(
                    input_tokens=usage.get('prompt_tokens', self._estimate_tokens(prompt)),
                    output_tokens=usage.get('completion_tokens', self._estimate_tokens(content))
                )
                
                cost = self._calculate_cost(tokens_used.total_tokens)
                
                # Cache successful response
                self._cache_response(cache_key, content)
                self.metrics.record_success(latency_ms)
                
                return AIResponse(
                    content=content,
                    provider=self.config.name,
                    model=model,
                    tokens_used=tokens_used,
                    cost=cost,
                    latency_ms=latency_ms,
                    metadata=usage
                )
                
        except Exception as e:
            self.metrics.record_failure()
            logger.error(f"Groq request failed: {e}")
            if isinstance(e, ProviderError):
                raise
            raise ProviderError(self.config.name, str(e))

class OpenAIProvider(AIProviderBase):
    """OpenAI provider implementation"""
    
    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        """Send request to OpenAI"""
        if not self.metrics.is_healthy:
            raise ProviderError(self.config.name, "Provider marked as unhealthy")
        
        # Check cache
        cache_key = self._get_cache_key(prompt, **kwargs)
        cached_response = self._get_cached_response(cache_key)
        if cached_response:
            return AIResponse(
                content=cached_response,
                provider=self.config.name,
                model=kwargs.get('model', 'gpt-3.5-turbo'),
                tokens_used=TokenUsage(output_tokens=self._estimate_tokens(cached_response)),
                cost=0.0,
                latency_ms=1.0,
                cached=True
            )
        
        await self._apply_rate_limit()
        start_time = time.time()
        
        try:
            if not self.session:
                raise ProviderError(self.config.name, "Session not initialized")
            
            model = kwargs.get('model', self.config.model or 'gpt-3.5-turbo')
            
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": kwargs.get('max_tokens', self.config.max_tokens),
                "temperature": kwargs.get('temperature', 0.7)
            }
            
            url = f"{self.config.base_url or 'https://api.openai.com/v1'}/chat/completions"
            
            async with self.session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.metrics.record_failure()
                    raise ProviderError(
                        self.config.name, 
                        f"HTTP {response.status}: {error_text}",
                        is_rate_limit=(response.status == 429)
                    )
                
                data = await response.json()
                content = data['choices'][0]['message']['content'].strip()
                
                latency_ms = (time.time() - start_time) * 1000
                usage = data.get('usage', {})
                tokens_used = TokenUsage(
                    input_tokens=usage.get('prompt_tokens', self._estimate_tokens(prompt)),
                    output_tokens=usage.get('completion_tokens', self._estimate_tokens(content))
                )
                
                cost = self._calculate_cost(tokens_used.total_tokens)
                
                # Cache successful response
                self._cache_response(cache_key, content)
                self.metrics.record_success(latency_ms)
                
                return AIResponse(
                    content=content,
                    provider=self.config.name,
                    model=model,
                    tokens_used=tokens_used,
                    cost=cost,
                    latency_ms=latency_ms,
                    metadata=usage
                )
                
        except Exception as e:
            self.metrics.record_failure()
            logger.error(f"OpenAI request failed: {e}")
            if isinstance(e, ProviderError):
                raise
            raise ProviderError(self.config.name, str(e))

class YandexGPTProvider(AIProviderBase):
    """YandexGPT provider implementation"""
    
    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        """Send request to YandexGPT"""
        if not self.metrics.is_healthy:
            raise ProviderError(self.config.name, "Provider marked as unhealthy")
        
        # Check cache
        cache_key = self._get_cache_key(prompt, **kwargs)
        cached_response = self._get_cached_response(cache_key)
        if cached_response:
            return AIResponse(
                content=cached_response,
                provider=self.config.name,
                model=self.config.model or 'yandexgpt-lite',
                tokens_used=TokenUsage(output_tokens=self._estimate_tokens(cached_response)),
                cost=0.0,
                latency_ms=1.0,
                cached=True
            )
        
        await self._apply_rate_limit()
        start_time = time.time()
        
        try:
            if not self.session:
                raise ProviderError(self.config.name, "Session not initialized")
            
            headers = {
                "Authorization": f"Api-Key {self.config.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "modelUri": kwargs.get('model', self.config.model),
                "completionOptions": {"stream": False},
                "messages": [{"role": "user", "text": prompt}]
            }
            
            url = self.config.base_url
            
            async with self.session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.metrics.record_failure()
                    raise ProviderError(
                        self.config.name, 
                        f"HTTP {response.status}: {error_text}",
                        is_rate_limit=(response.status == 429)
                    )
                
                data = await response.json()
                content = data["result"]["alternatives"][0]["message"]["text"].strip()
                
                latency_ms = (time.time() - start_time) * 1000
                tokens_used = TokenUsage(
                    input_tokens=self._estimate_tokens(prompt),
                    output_tokens=self._estimate_tokens(content)
                )
                
                cost = self._calculate_cost(tokens_used.total_tokens)
                
                # Cache successful response
                self._cache_response(cache_key, content)
                self.metrics.record_success(latency_ms)
                
                return AIResponse(
                    content=content,
                    provider=self.config.name,
                    model=self.config.model or 'yandexgpt',
                    tokens_used=tokens_used,
                    cost=cost,
                    latency_ms=latency_ms,
                    metadata=data
                )
                
        except Exception as e:
            self.metrics.record_failure()
            logger.error(f"YandexGPT request failed: {e}")
            if isinstance(e, ProviderError):
                raise
            raise ProviderError(self.config.name, str(e))

class MockProvider(AIProviderBase):
    """Mock provider for testing and fallback"""
    
    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        """Return mock response for testing"""
        await asyncio.sleep(0.1)  # Simulate latency
        
        model = kwargs.get('model', 'mock-model-v1')
        
        # Generate contextual mock response
        if "error" in prompt.lower():
            content = "Mock error simulation: This is a simulated error response for testing."
        elif "code" in prompt.lower():
            content = f"```python\n# Mock code response\ndef example():\n    return 'mock_result'\n```"
        else:
            content = f"Mock response for: {prompt[:100]}..."
        
        tokens_used = TokenUsage(
            input_tokens=self._estimate_tokens(prompt),
            output_tokens=self._estimate_tokens(content)
        )
        
        self.metrics.record_success(100.0)
        
        return AIResponse(
            content=content,
            provider=self.config.name,
            model=model,
            tokens_used=tokens_used,
            cost=0.0,
            latency_ms=100.0,
            metadata={"mock": True, "timestamp": datetime.now().isoformat()}
        )

class AIAsyncClient:
    """
    Production-ready AI client with multiple provider support
    
    Features:
    - Intelligent provider selection based on cost and performance
    - Response caching to reduce API calls and costs
    - Circuit breaker pattern for failing providers
    - Automatic fallback and retry logic
    - Cost tracking and budget management
    - Simple configuration via dictionary
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.providers: Dict[str, AIProviderBase] = {}
        self.provider_configs: Dict[str, ProviderConfig] = {}
        
        # Cost tracking
        self.daily_cost = 0.0
        self.daily_budget = float(config.get('daily_budget', 10.0))
        
        # Performance tracking
        self._global_stats = {
            'total_requests': 0,
            'cache_hits': 0,
            'cost_saved': 0.0
        }
        
        self._setup_providers()
    
    def _setup_providers(self) -> None:
        """Initialize providers from configuration"""
        provider_classes = {
            'ollama': OllamaProvider,
            'huggingface': HuggingFaceProvider,
            'groq': GroqProvider,
            'openai': OpenAIProvider,
            'yandexgpt': YandexGPTProvider,
            'mock': MockProvider,
        }
        
        successful_providers = 0
        
        # Process each provider configuration
        for provider_name, provider_settings in self.config.items():
            if provider_name in ['daily_budget', 'cost_alerts']:
                continue  # Skip global settings
            
            try:
                # Create provider configuration
                config = self._create_provider_config(provider_name, provider_settings)
                
                # Get provider class
                provider_class = provider_classes.get(provider_name, MockProvider)
                
                # Create provider instance
                provider = provider_class(config)
                
                self.providers[provider_name] = provider
                self.provider_configs[provider_name] = config
                
                logger.info(f"✅ Configured {provider_name} provider (free: {config.is_free})")
                successful_providers += 1
                
            except Exception as e:
                logger.error(f"❌ Failed to configure {provider_name}: {e}")
                
                # Create fallback mock provider
                try:
                    mock_config = ProviderConfig(
                        name=f"{provider_name}_fallback",
                        provider_type=ProviderType.MOCK,
                        is_free=True,
                        priority=1
                    )
                    mock_provider = MockProvider(mock_config)
                    
                    self.providers[f"{provider_name}_fallback"] = mock_provider
                    self.provider_configs[f"{provider_name}_fallback"] = mock_config
                    
                    logger.info(f"🔄 Created fallback for {provider_name}")
                except Exception as fallback_error:
                    logger.error(f"Failed to create fallback: {fallback_error}")
        
        # Ensure at least one provider exists
        if not self.providers:
            logger.warning("No providers configured, creating default mock")
            default_config = ProviderConfig(
                name="default_mock",
                provider_type=ProviderType.MOCK,
                is_free=True
            )
            self.providers["default_mock"] = MockProvider(default_config)
            self.provider_configs["default_mock"] = default_config
        
        logger.info(f"🚀 Initialized with {len(self.providers)} providers ({successful_providers} successful)")
    
    def _create_provider_config(self, provider_name: str, provider_settings: Dict[str, Any]) -> ProviderConfig:
        """Create provider configuration from settings"""
        
        # Map provider names to types
        provider_type_mapping = {
            'ollama': ProviderType.OLLAMA,
            'huggingface': ProviderType.HUGGINGFACE,
            'groq': ProviderType.GROQ,
            'openai': ProviderType.OPENAI,
            'yandexgpt': ProviderType.YANDEXGPT,
            'mock': ProviderType.MOCK
        }
        
        provider_type = provider_type_mapping.get(provider_name, ProviderType.MOCK)
        
        # Safe value extraction with defaults
        def safe_get(key: str, default: Any, converter=None):
            value = provider_settings.get(key, default)
            if converter and value is not None:
                try:
                    return converter(value)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid {key} for {provider_name}: {value}, using {default}")
                    return default
            return value
        
        return ProviderConfig(
            name=provider_name,
            provider_type=provider_type,
            api_key=safe_get('api_key', None),
            base_url=safe_get('base_url', None),
            model=safe_get('model', None),
            max_tokens=safe_get('max_tokens', 4096, int),
            timeout=safe_get('timeout', 30, int),
            cost_per_1k_tokens=safe_get('cost_per_1k_tokens', 0.0, float),
            priority=safe_get('priority', 50, int),
            rate_limit=safe_get('rate_limit', 60, int),
            retry_attempts=safe_get('retry_attempts', 3, int),
            retry_delay=safe_get('retry_delay', 1.0, float),
            headers=provider_settings.get('headers', {})
        )
    
    def _select_best_provider(
        self, 
        task_complexity: TaskComplexity = TaskComplexity.MEDIUM,
        preferred_provider: Optional[str] = None
    ) -> str:
        """Select the best available provider"""
        
        # Use preferred provider if specified and healthy
        if preferred_provider and preferred_provider in self.providers:
            provider = self.providers[preferred_provider]
            if provider.metrics.is_healthy:
                return preferred_provider
        
        # Get healthy providers
        healthy_providers = []
        for name, provider in self.providers.items():
            if provider.metrics.is_healthy:
                config = self.provider_configs[name]
                # Check budget constraint
                if config.is_free or self.daily_cost < self.daily_budget:
                    healthy_providers.append((name, provider, config))
        
        if not healthy_providers:
            raise ProviderError("system", "No healthy providers available")
        
        # Score providers
        best_score = -1
        best_provider = None
        
        for name, provider, config in healthy_providers:
            score = 0
            
            # Heavily favor free providers
            if config.is_free:
                score += 100
            
            # Add priority score
            score += config.priority
            
            # Prefer providers with good track record
            score += provider.metrics.get_success_rate() * 50
            
            # Task complexity bonus
            if task_complexity == TaskComplexity.COMPLEX and config.provider_type == ProviderType.OPENAI:
                score += 20
            elif task_complexity == TaskComplexity.SIMPLE and config.is_free:
                score += 30
            
            # Penalize recent failures
            score -= provider.metrics.consecutive_failures * 10
            
            if score > best_score:
                best_score = score
                best_provider = name
        
        if not best_provider:
            # Fallback to any available provider
            best_provider = healthy_providers[0][0]
        
        logger.debug(f"🎯 Selected provider: {best_provider} (score: {best_score})")
        return best_provider
    
    async def _execute_with_retry(
        self, 
        provider: AIProviderBase, 
        method, 
        *args, 
        **kwargs
    ) -> AIResponse:
        """Execute provider method with retry logic"""
        last_exception = None
        
        for attempt in range(provider.config.retry_attempts):
            try:
                return await method(*args, **kwargs)
            except ProviderError as e:
                last_exception = e
                
                # Don't retry rate limits or authentication errors
                if e.is_rate_limit or e.error_code in ['auth_error', 'invalid_key']:
                    raise
                
                # Wait before retry
                if attempt < provider.config.retry_attempts - 1:
                    wait_time = provider.config.retry_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(f"Retry {attempt + 1} for {provider.config.name} in {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All retry attempts failed for {provider.config.name}")
                    raise
            except Exception as e:
                last_exception = e
                logger.error(f"Unexpected error in {provider.config.name}: {e}")
                raise ProviderError(provider.config.name, str(e))
        
        # Should not reach here, but just in case
        if last_exception:
            raise last_exception
        raise ProviderError(provider.config.name, "Unknown error in retry logic")
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
    
    async def initialize(self) -> None:
        """Initialize all providers"""
        tasks = []
        for provider in self.providers.values():
            tasks.append(provider.initialize())
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    provider_name = list(self.providers.keys())[i]
                    logger.warning(f"Failed to initialize {provider_name}: {result}")
    
    async def close(self) -> None:
        """Cleanup all providers"""
        tasks = []
        for provider in self.providers.values():
            tasks.append(provider.cleanup())
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        logger.info("🔄 AI client cleanup completed")
    
    async def ask(
        self,
        prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        task_complexity: TaskComplexity = TaskComplexity.MEDIUM,
        **kwargs
    ) -> str:
        """
        Ask AI providers for response with intelligent selection
        
        Args:
            prompt: Input text prompt
            provider: Specific provider to use (auto-select if None)
            model: Specific model to use
            max_tokens: Maximum tokens in response
            temperature: Response creativity (0.0-1.0)
            task_complexity: Task complexity for provider selection
            **kwargs: Additional parameters
        
        Returns:
            AI-generated response text
        """
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty")
        
        self._global_stats['total_requests'] += 1
        
        # Select best provider
        selected_provider = self._select_best_provider(task_complexity, provider)
        provider_instance = self.providers[selected_provider]
        provider_config = self.provider_configs[selected_provider]
        
        try:
            # Prepare request parameters
            request_kwargs = {
                'model': model or provider_config.model,
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
                if self.daily_cost > self.daily_budget * 0.8:
                    logger.warning(f"💰 Daily budget warning: ${self.daily_cost:.4f} / ${self.daily_budget:.2f}")
            
            # Log response info
            cache_info = " (cached)" if response.cached else ""
            logger.info(
                f"✅ {selected_provider} response: {response.tokens_used.total_tokens} tokens, "
                f"{response.latency_ms:.0f}ms, ${response.cost:.4f}{cache_info}"
            )
            
            return response.content
            
        except Exception as e:
            logger.error(f"Provider {selected_provider} failed: {e}")
            
            # Try fallback provider if available
            fallback_providers = [name for name in self.providers.keys() 
                                if name != selected_provider and 
                                self.providers[name].metrics.is_healthy]
            
            if fallback_providers:
                logger.info(f"Trying fallback provider: {fallback_providers[0]}")
                return await self.ask(
                    prompt, 
                    provider=fallback_providers[0], 
                    model=model,
                    max_tokens=max_tokens, 
                    temperature=temperature, 
                    task_complexity=task_complexity,
                    **kwargs
                )
            
            raise
    
    async def batch_ask(
        self, 
        prompts: List[str], 
        max_concurrency: int = 5,
        **kwargs
    ) -> List[str]:
        """
        Process multiple prompts concurrently
        
        Args:
            prompts: List of prompts to process
            max_concurrency: Maximum concurrent requests
            **kwargs: Additional parameters for ask()
        
        Returns:
            List of responses
        """
        semaphore = asyncio.Semaphore(max_concurrency)
        
        async def process_prompt(prompt: str) -> str:
            async with semaphore:
                try:
                    return await self.ask(prompt, **kwargs)
                except Exception as e:
                    logger.error(f"Failed to process prompt: {e}")
                    return f"Error: {str(e)}"
        
        tasks = [process_prompt(prompt) for prompt in prompts]
        return await asyncio.gather(*tasks)
    
    async def stream(
        self, 
        prompt: str, 
        provider: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        Stream response from AI provider
        
        Args:
            prompt: Input text prompt
            provider: Specific provider to use
            **kwargs: Additional parameters
        
        Yields:
            Response chunks as they arrive
        """
        selected_provider = self._select_best_provider(preferred_provider=provider)
        provider_instance = self.providers[selected_provider]
        
        async for chunk in provider_instance.stream(prompt, **kwargs):
            yield chunk
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive client statistics"""
        provider_stats = {}
        
        for name, provider in self.providers.items():
            config = self.provider_configs[name]
            metrics = provider.metrics
            
            provider_stats[name] = {
                "healthy": metrics.is_healthy,
                "total_requests": metrics.total_requests,
                "success_rate": f"{metrics.get_success_rate() * 100:.1f}%",
                "avg_response_time": f"{metrics.get_avg_response_time():.0f}ms",
                "consecutive_failures": metrics.consecutive_failures,
                "is_free": config.is_free,
                "cost_per_1k_tokens": config.cost_per_1k_tokens,
                "priority": config.priority
            }
        
        return {
            "providers": provider_stats,
            "global_stats": self._global_stats,
            "daily_cost": self.daily_cost,
            "daily_budget": self.daily_budget,
            "cache_size": len(_response_cache),
            "total_providers": len(self.providers),
            "healthy_providers": sum(1 for p in self.providers.values() if p.metrics.is_healthy)
        }

# Convenience functions for backwards compatibility
async def create_ai_client(config: Dict[str, Any]) -> AIAsyncClient:
    """Create and initialize AI client"""
    client = AIAsyncClient(config)
    await client.initialize()
    return client

async def quick_ask(prompt: str, config: Dict[str, Any], provider: str = None) -> str:
    """Quick ask function for simple use cases"""
    async with AIAsyncClient(config) as client:
        return await client.ask(prompt, provider=provider)

# Example usage
async def main():
    """Example usage of the AI client"""
    
    # Configuration example
    config = {
        "ollama": {
            "base_url": "http://localhost:11434",
            "model": "llama3.2:1b",
            "priority": 90,
            "cost_per_1k_tokens": 0.0
        },
        "huggingface": {
            "model": "microsoft/DialoGPT-medium",
            "priority": 80,
            "cost_per_1k_tokens": 0.0
        },
        "groq": {
            "api_key": "your_groq_key",
            "model": "llama3-8b-8192",
            "priority": 70,
            "cost_per_1k_tokens": 0.0001
        },
        "openai": {
            "api_key": "your_openai_key",
            "model": "gpt-3.5-turbo",
            "priority": 60,
            "cost_per_1k_tokens": 0.002
        },
        "daily_budget": 5.0
    }
    
    # Using the client
    async with AIAsyncClient(config) as client:
        # Single request
        response = await client.ask("What is artificial intelligence?")
        print(f"Response: {response[:100]}...")
        
        # Batch processing
        prompts = [
            "What is Python?",
            "Explain machine learning",
            "What is async programming?"
        ]
        responses = await client.batch_ask(prompts, max_concurrency=2)
        print(f"Batch responses: {len(responses)} received")
        
        # Get statistics
        stats = client.get_stats()
        print(f"Stats: {stats}")

if __name__ == "__main__":
    asyncio.run(main())