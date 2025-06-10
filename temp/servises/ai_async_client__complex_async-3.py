# services/ai_async_client-3.py - Enhanced AI client optimized for cost-effectiveness and performance
# https://claude.ai/chat/25cec1e7-314e-435b-9a20-8213b49cc952
from __future__ import annotations
import asyncio
import json
import logging
import time
import os
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union, AsyncGenerator, Callable
from enum import Enum
import aiohttp
import ssl
from urllib.parse import urljoin

# Cache for response caching to save tokens and costs
_response_cache: Dict[str, tuple[str, float]] = {}  # hash -> (response, timestamp)
CACHE_TTL = 3600  # 1 hour cache TTL

logger = logging.getLogger(__name__)

class ProviderType(Enum):
    """Enumeration of supported AI providers with cost optimization focus"""
    # Free and low-cost providers prioritized
    OLLAMA = "ollama"              # Local, completely free
    HUGGINGFACE = "huggingface"    # Free tier available
    TOGETHER = "together"          # Cost-effective
    GROQ = "groq"                  # Very fast and affordable
    OPENROUTER = "openrouter"      # Access to multiple models at low cost
    COHERE = "cohere"              # Free tier + affordable
    REPLICATE = "replicate"        # Pay-per-use, cost-effective
    DEEPSEEK = "deepseek"          # Very affordable Chinese provider
    MOONSHOT = "moonshot"          # Affordable alternative
    OPENAI = "openai"              # Fallback for premium needs
    CLAUDE = "claude"              # Fallback for premium needs
    MOCK = "mock"                  # Testing and ultimate fallback

@dataclass
class ProviderConfig:
    """Enhanced provider configuration with cost optimization"""
    name: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    max_tokens: int = 4096
    timeout: int = 30
    rate_limit: int = 100  # Increased default for better throughput
    cost_per_1k_tokens: float = 0.0
    supports_streaming: bool = True
    priority: int = 50
    is_free: bool = False
    retry_attempts: int = 2  # Reduced for faster failover
    retry_delay: float = 0.5  # Faster retry
    headers: Dict[str, str] = field(default_factory=dict)
    # New optimization fields
    max_context_length: int = 4096
    supports_function_calling: bool = False
    supports_vision: bool = False
    region: str = "global"  # For latency optimization
    quality_tier: str = "standard"  # "basic", "standard", "premium"

    def __post_init__(self):
        """Enhanced post-initialization with better defaults"""
        # Type safety
        self.max_tokens = max(1, int(self.max_tokens or 4096))
        self.timeout = max(5, int(self.timeout or 30))
        self.rate_limit = max(1, int(self.rate_limit or 100))
        self.priority = max(0, min(100, int(self.priority or 50)))
        self.retry_attempts = max(1, int(self.retry_attempts or 2))
        self.cost_per_1k_tokens = max(0.0, float(self.cost_per_1k_tokens or 0.0))
        self.retry_delay = max(0.1, float(self.retry_delay or 0.5))
        
        # Auto-configure free providers
        if self.cost_per_1k_tokens <= 0.001:  # Practically free
            self.is_free = True
            self.priority += 40
        elif self.cost_per_1k_tokens <= 0.01:  # Very cheap
            self.priority += 20
        
        # Boost local providers
        if self.name in ["ollama", "local"]:
            self.is_free = True
            self.priority += 50

@dataclass
class AIResponse:
    """Enhanced AI response with caching and optimization metadata"""
    content: str
    provider: str
    model: Optional[str] = None
    tokens_used: int = 0
    cost: float = 0.0
    latency_ms: float = 0.0
    cached: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    # New fields for optimization
    quality_score: float = 1.0  # 0-1, based on response quality heuristics
    from_cache: bool = False
    cache_key: Optional[str] = None

class ProviderError(Exception):
    """Enhanced exception with recovery suggestions"""
    def __init__(self, provider: str, message: str, error_code: Optional[str] = None, 
                 suggestion: Optional[str] = None):
        self.provider = provider
        self.error_code = error_code
        self.suggestion = suggestion
        super().__init__(f"[{provider}] {message}")

class AIProviderBase(ABC):
    """Enhanced base class with caching and optimization"""
    
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self._request_count = 0
        self._last_request_time = 0.0
        self._circuit_breaker_failures = 0
        self._circuit_breaker_last_failure = 0.0
        self._circuit_breaker_threshold = 5

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()

    async def initialize(self):
        """Initialize with optimized connection settings"""
        try:
            # Optimized connector for better performance
            connector = aiohttp.TCPConnector(
                limit=50,  # Increased connection pool
                limit_per_host=20,
                ssl=ssl.create_default_context(),
                enable_cleanup_closed=True,
                keepalive_timeout=30,
                ttl_dns_cache=300
            )
            
            timeout = aiohttp.ClientTimeout(
                total=self.config.timeout,
                connect=min(10, self.config.timeout // 3)
            )
            
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers=self.config.headers
            )
            logger.debug(f"Initialized {self.config.name} provider")
        except Exception as e:
            logger.warning(f"Failed to initialize {self.config.name}: {e}")

    async def cleanup(self):
        """Enhanced cleanup"""
        if self.session and not self.session.closed:
            try:
                await self.session.close()
                await asyncio.sleep(0.1)  # Give time for cleanup
            except Exception as e:
                logger.warning(f"Error during {self.config.name} cleanup: {e}")

    def _is_circuit_breaker_open(self) -> bool:
        """Circuit breaker pattern for failing providers"""
        if self._circuit_breaker_failures >= self._circuit_breaker_threshold:
            if time.time() - self._circuit_breaker_last_failure < 60:  # 1 minute cooldown
                return True
            else:
                # Reset after cooldown
                self._circuit_breaker_failures = 0
        return False

    def _record_success(self):
        """Record successful request"""
        self._circuit_breaker_failures = max(0, self._circuit_breaker_failures - 1)

    def _record_failure(self):
        """Record failed request"""
        self._circuit_breaker_failures += 1
        self._circuit_breaker_last_failure = time.time()

    def estimate_tokens(self, text: str) -> int:
        """Improved token estimation"""
        # More accurate estimation based on research
        # English: ~4 chars per token, code: ~3 chars per token
        avg_chars_per_token = 3.5 if any(c in text for c in "{}[]();") else 4
        return max(1, int(len(text) / avg_chars_per_token))

    def calculate_cost(self, tokens: int) -> float:
        """Calculate cost with precision"""
        return round((tokens / 1000) * self.config.cost_per_1k_tokens, 6)

    def _get_cache_key(self, prompt: str, **kwargs) -> str:
        """Generate cache key for request"""
        # Create deterministic hash from prompt and parameters
        cache_data = {
            'prompt': prompt,
            'model': kwargs.get('model', self.config.model),
            'temperature': kwargs.get('temperature', 0.7),
            'max_tokens': kwargs.get('max_tokens', self.config.max_tokens)
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
                # Remove expired entry
                del _response_cache[cache_key]
        return None

    def _cache_response(self, cache_key: str, response: str):
        """Cache response with TTL"""
        _response_cache[cache_key] = (response, time.time())
        # Simple cache size management
        if len(_response_cache) > 1000:
            # Remove oldest 20% of entries
            sorted_items = sorted(_response_cache.items(), key=lambda x: x[1][1])
            for key, _ in sorted_items[:200]:
                del _response_cache[key]

    @abstractmethod
    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        pass

    @abstractmethod
    async def stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        pass

class OllamaProvider(AIProviderBase):
    """Optimized Ollama provider - completely free local AI"""
    
    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        if self._is_circuit_breaker_open():
            raise ProviderError(self.config.name, "Circuit breaker open", 
                              suggestion="Check if Ollama is running locally")
        
        # Check cache first
        cache_key = self._get_cache_key(prompt, **kwargs)
        cached_response = self._get_cached_response(cache_key)
        if cached_response:
            logger.debug(f"Cache hit for {self.config.name}")
            return AIResponse(
                content=cached_response,
                provider=self.config.name,
                model=kwargs.get('model', self.config.model),
                tokens_used=self.estimate_tokens(cached_response),
                cost=0.0,
                latency_ms=1.0,  # Virtually instant from cache
                cached=True,
                from_cache=True,
                cache_key=cache_key
            )

        start_time = time.time()
        try:
            if not self.session:
                raise ProviderError(self.config.name, "Session not initialized")

            payload = {
                "model": kwargs.get('model', self.config.model or 'llama3.2:1b'),  # Use smaller model by default
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": kwargs.get('temperature', 0.7),
                    "num_predict": kwargs.get('max_tokens', self.config.max_tokens),
                    "num_ctx": min(kwargs.get('context_length', 4096), 8192),  # Optimize context
                    "top_p": 0.9,  # Better quality/speed balance
                    "repeat_penalty": 1.1
                }
            }

            url = urljoin(self.config.base_url or 'http://localhost:11434', '/api/generate')
            
            async with self.session.post(url, json=payload) as response:
                if response.status != 200:
                    self._record_failure()
                    error_text = await response.text()
                    raise ProviderError(self.config.name, f"HTTP {response.status}: {error_text}",
                                      suggestion="Ensure Ollama is running and model is installed")
                
                data = await response.json()
                content = data.get('response', '').strip()
                
                if not content:
                    raise ProviderError(self.config.name, "Empty response received")

                latency_ms = (time.time() - start_time) * 1000
                tokens_used = self.estimate_tokens(content)
                
                # Cache the response
                self._cache_response(cache_key, content)
                self._record_success()

                return AIResponse(
                    content=content,
                    provider=self.config.name,
                    model=data.get('model', self.config.model),
                    tokens_used=tokens_used,
                    cost=0.0,
                    latency_ms=latency_ms,
                    metadata=data,
                    cache_key=cache_key
                )

        except Exception as e:
            self._record_failure()
            logger.error(f"Ollama request failed: {e}")
            raise ProviderError(self.config.name, str(e), 
                              suggestion="Check Ollama installation and model availability")

    async def stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        if self._is_circuit_breaker_open():
            raise ProviderError(self.config.name, "Circuit breaker open")

        try:
            payload = {
                "model": kwargs.get('model', self.config.model or 'llama3.2:1b'),
                "prompt": prompt,
                "stream": True,
                "options": {
                    "temperature": kwargs.get('temperature', 0.7),
                    "num_predict": kwargs.get('max_tokens', self.config.max_tokens),
                    "num_ctx": min(kwargs.get('context_length', 4096), 8192),
                    "top_p": 0.9
                }
            }

            url = urljoin(self.config.base_url or 'http://localhost:11434', '/api/generate')
            
            async with self.session.post(url, json=payload) as response:
                if response.status != 200:
                    self._record_failure()
                    raise ProviderError(self.config.name, f"HTTP {response.status}")

                accumulated_content = ""
                async for line in response.content:
                    if line:
                        try:
                            data = json.loads(line.decode())
                            if chunk := data.get('response', ''):
                                accumulated_content += chunk
                                yield chunk
                            if data.get('done', False):
                                # Cache the complete response
                                cache_key = self._get_cache_key(prompt, **kwargs)
                                self._cache_response(cache_key, accumulated_content)
                                self._record_success()
                                break
                        except json.JSONDecodeError:
                            continue

        except Exception as e:
            self._record_failure()
            logger.error(f"Ollama streaming failed: {e}")
            raise ProviderError(self.config.name, str(e))

class HuggingFaceProvider(AIProviderBase):
    """Optimized HuggingFace provider with free tier focus"""
    
    # List of good free models on HuggingFace
    FREE_MODELS = [
        "microsoft/DialoGPT-medium",
        "facebook/blenderbot-400M-distill",
        "microsoft/DialoGPT-small",
        "HuggingFaceH4/zephyr-7b-beta",
        "mistralai/Mistral-7B-Instruct-v0.1"
    ]

    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        if self._is_circuit_breaker_open():
            raise ProviderError(self.config.name, "Circuit breaker open")

        # Check cache first
        cache_key = self._get_cache_key(prompt, **kwargs)
        cached_response = self._get_cached_response(cache_key)
        if cached_response:
            return AIResponse(
                content=cached_response,
                provider=self.config.name,
                tokens_used=self.estimate_tokens(cached_response),
                cost=0.0,
                latency_ms=1.0,
                cached=True,
                from_cache=True
            )

        start_time = time.time()
        try:
            model = kwargs.get('model', self.config.model or self.FREE_MODELS[0])
            url = f"https://api-inference.huggingface.co/models/{model}"
            
            headers = {"Content-Type": "application/json"}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"

            # Optimize payload for better results
            payload = {
                "inputs": prompt,
                "parameters": {
                    "max_new_tokens": min(kwargs.get('max_tokens', 512), 1024),  # Limit for free tier
                    "temperature": kwargs.get('temperature', 0.7),
                    "top_p": 0.9,
                    "do_sample": True,
                    "return_full_text": False
                },
                "options": {
                    "wait_for_model": True,  # Wait if model is loading
                    "use_cache": True
                }
            }

            async with self.session.post(url, json=payload, headers=headers) as response:
                if response.status == 503:
                    # Model loading, wait and retry once
                    await asyncio.sleep(3)
                    async with self.session.post(url, json=payload, headers=headers) as retry_response:
                        response = retry_response

                if response.status == 429:
                    self._record_failure()
                    raise ProviderError(self.config.name, "Rate limited", 
                                      suggestion="Try again in a few minutes or use API key")

                if response.status != 200:
                    self._record_failure()
                    error_text = await response.text()
                    raise ProviderError(self.config.name, f"HTTP {response.status}: {error_text}")

                data = await response.json()
                
                # Handle different response formats
                if isinstance(data, list) and data:
                    content = data[0].get('generated_text', '').strip()
                elif isinstance(data, dict):
                    content = data.get('generated_text', str(data)).strip()
                else:
                    content = str(data).strip()

                if not content:
                    raise ProviderError(self.config.name, "Empty response")

                latency_ms = (time.time() - start_time) * 1000
                tokens_used = self.estimate_tokens(content)
                
                # Cache successful response
                self._cache_response(cache_key, content)
                self._record_success()

                return AIResponse(
                    content=content,
                    provider=self.config.name,
                    model=model,
                    tokens_used=tokens_used,
                    cost=0.0,  # Free tier
                    latency_ms=latency_ms,
                    metadata=data if isinstance(data, dict) else {},
                    cache_key=cache_key
                )

        except Exception as e:
            self._record_failure()
            logger.error(f"HuggingFace request failed: {e}")
            raise ProviderError(self.config.name, str(e),
                              suggestion="Try different model or add API key for better limits")

    async def stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        # HuggingFace doesn't support streaming, simulate with chunked response
        response = await self.ask(prompt, **kwargs)
        content = response.content
        
        # Simulate realistic streaming
        words = content.split()
        chunk_size = 3  # Stream 3 words at a time
        
        for i in range(0, len(words), chunk_size):
            chunk = ' '.join(words[i:i + chunk_size])
            if i + chunk_size < len(words):
                chunk += ' '
            yield chunk
            await asyncio.sleep(0.05)  # Realistic streaming delay

class GroqProvider(AIProviderBase):
    """Groq provider - extremely fast and affordable"""
    
    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        if self._is_circuit_breaker_open():
            raise ProviderError(self.config.name, "Circuit breaker open")

        # Check cache
        cache_key = self._get_cache_key(prompt, **kwargs)
        cached_response = self._get_cached_response(cache_key)
        if cached_response:
            return AIResponse(
                content=cached_response,
                provider=self.config.name,
                tokens_used=self.estimate_tokens(cached_response),
                cost=0.0,
                latency_ms=1.0,
                cached=True,
                from_cache=True
            )

        start_time = time.time()
        try:
            url = urljoin(self.config.base_url or 'https://api.groq.com/openai/v1', '/chat/completions')
            
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": kwargs.get('model', self.config.model or 'llama3-8b-8192'),
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": kwargs.get('max_tokens', self.config.max_tokens),
                "temperature": kwargs.get('temperature', 0.7),
                "stream": False
            }

            async with self.session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    self._record_failure()
                    error_text = await response.text()
                    raise ProviderError(self.config.name, f"HTTP {response.status}: {error_text}")

                data = await response.json()
                content = data['choices'][0]['message']['content'].strip()
                
                latency_ms = (time.time() - start_time) * 1000
                tokens_used = data.get('usage', {}).get('total_tokens', self.estimate_tokens(content))
                cost = self.calculate_cost(tokens_used)
                
                self._cache_response(cache_key, content)
                self._record_success()

                return AIResponse(
                    content=content,
                    provider=self.config.name,
                    model=data.get('model'),
                    tokens_used=tokens_used,
                    cost=cost,
                    latency_ms=latency_ms,
                    metadata=data.get('usage', {}),
                    cache_key=cache_key
                )

        except Exception as e:
            self._record_failure()
            logger.error(f"Groq request failed: {e}")
            raise ProviderError(self.config.name, str(e))

    async def stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        # Similar implementation to non-streaming but with stream=True
        try:
            url = urljoin(self.config.base_url or 'https://api.groq.com/openai/v1', '/chat/completions')
            
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": kwargs.get('model', self.config.model or 'llama3-8b-8192'),
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": kwargs.get('max_tokens', self.config.max_tokens),
                "temperature": kwargs.get('temperature', 0.7),
                "stream": True
            }

            accumulated_content = ""
            async with self.session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    self._record_failure()
                    raise ProviderError(self.config.name, f"HTTP {response.status}")

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
                                        if content := delta.get('content', ''):
                                            accumulated_content += content
                                            yield content
                                except json.JSONDecodeError:
                                    continue

                # Cache complete response
                if accumulated_content:
                    cache_key = self._get_cache_key(prompt, **kwargs)
                    self._cache_response(cache_key, accumulated_content)
                    self._record_success()

        except Exception as e:
            self._record_failure()
            logger.error(f"Groq streaming failed: {e}")
            raise ProviderError(self.config.name, str(e))

class MockProvider(AIProviderBase):
    """Enhanced mock provider for testing and ultimate fallback"""
    
    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        await asyncio.sleep(0.1)  # Simulate network latency
        
        # Generate more realistic mock responses
        mock_responses = [
            f"This is a mock response to your query: '{prompt[:100]}...' The system is currently using a fallback provider.",
            f"Mock AI response: I understand you're asking about '{prompt[:50]}...'. This is a simulated response for testing purposes.",
            f"Simulated response: Your prompt '{prompt[:75]}...' has been processed by the mock provider. Please configure a real AI provider for actual responses."
        ]
        
        content = mock_responses[hash(prompt) % len(mock_responses)]
        tokens_used = self.estimate_tokens(content)
        
        return AIResponse(
            content=content,
            provider=self.config.name,
            model="mock-model-v1",
            tokens_used=tokens_used,
            cost=0.0,
            latency_ms=100.0,
            metadata={"mock": True, "prompt_length": len(prompt)}
        )

    async def stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        response = await self.ask(prompt, **kwargs)
        content = response.content
        
        # Stream response word by word
        words = content.split()
        for word in words:
            yield word + ' '
            await asyncio.sleep(0.02)

class AIAsyncClient:
    """
    Enhanced AI client optimized for cost-effectiveness, speed, and reliability
    
    Key optimizations:
    - Intelligent provider selection based on cost and performance
    - Response caching to minimize API calls
    - Circuit breaker pattern for failing providers
    - Free and low-cost provider prioritization
    - Optimized connection pooling and timeouts
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.providers: Dict[str, AIProviderBase] = {}
        self.provider_configs: Dict[str, ProviderConfig] = {}
        self._provider_stats: Dict[str, Dict[str, Any]] = {}
        self._total_requests = 0
        self._total_cost_saved = 0.0
        
        # Provider class mapping optimized for cost-effectiveness
        self.provider_classes = {
            'ollama': OllamaProvider,         # FREE - Local AI
            'huggingface': HuggingFaceProvider,  # FREE tier available
            'groq': GroqProvider,            # Very fast and affordable
            'together': GroqProvider,        # Reuse Groq implementation for Together API
            'openrouter': GroqProvider,      # Reuse for OpenRouter API  
            'cohere': GroqProvider,          # Reuse for Cohere API
            'deepseek': GroqProvider,        # Reuse for DeepSeek API
            'moonshot': GroqProvider,        # Reuse for Moonshot API
            'openai': MockProvider,          # Use mock for now (expensive)
            'claude': MockProvider,          # Use mock for now (expensive)
            'mock': MockProvider,
        }
        
        self._setup_providers()

    def _setup_providers(self):
        """Setup providers with enhanced error handling and optimization"""
        successful_providers = 0
        
        # Always ensure we have a local Ollama option if not configured
        if 'ollama' not in self.config:
            self.config['ollama'] = {
                'base_url': 'http://localhost:11434',
                'model': 'llama3.2:1b',  # Lightweight default
                'priority': 95,
                'cost_per_1k_tokens': 0.0
            }
        
        # Always ensure we have a HuggingFace option
        if 'huggingface' not in self.config:
            self.config['huggingface'] = {
                'model': 'microsoft/DialoGPT-medium',
                'priority': 85,
                'cost_per_1k_tokens': 0.0
            }

        for provider_name, provider_config in self.config.items():
            try:
                config = self._create_provider_config(provider_name, provider_config)
                provider_class = self.provider_classes.get(provider_name, MockProvider)
                provider = provider_class(config)
                
                self.providers[provider_name] = provider
                self.provider_configs[provider_name] = config
                self._provider_stats[provider_name] = {
                    'requests': 0,
                    'errors': 0,
                    'total_tokens': 0,
                    'total_cost': 0.0,
                    'avg_latency': 0.0,
                    'cache_hits': 0,
                    'last_used': 0.0,
                    'success_rate': 1.0
                }
                
                logger.info(f"✅ Configured {provider_name} provider (priority: {config.priority}, free: {config.is_free})")
                successful_providers += 1
                
            except Exception as e:
                logger.error(f"❌ Failed to configure {provider_name}: {e}")
                
                # Create mock fallback
                try:
                    mock_config = ProviderConfig(
                        name=f"{provider_name}_mock",
                        is_free=True,
                        priority=5
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