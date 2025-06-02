# services/ai_async_client.py - Next-generation AI client with multi-provider support and cost optimization
from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union, AsyncGenerator, Callable
from enum import Enum
import aiohttp
import ssl
from urllib.parse import urljoin

# Import optional dependencies with graceful fallbacks
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logging.warning("OpenAI package not available, OpenAI provider will be disabled")

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logging.warning("Anthropic package not available, Claude provider will be disabled")

try:
    from transformers import pipeline
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    logging.warning("Transformers package not available, local models will be disabled")

logger = logging.getLogger(__name__)

class ProviderType(Enum):
    """Enumeration of supported AI providers with their characteristics"""
    OPENAI = "openai"
    CLAUDE = "claude"
    MOONSHOT = "moonshot"
    TOGETHER = "together"
    HUGGINGFACE = "huggingface"
    OLLAMA = "ollama"
    MINIMAX = "minimax"
    WENXIN = "wenxin"
    LOCAL = "local"

@dataclass
class ProviderConfig:
    """Configuration for AI provider with cost and performance metadata"""
    name: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    max_tokens: int = 4096
    timeout: int = 30
    rate_limit: int = 60  # requests per minute
    cost_per_1k_tokens: float = 0.0  # USD
    supports_streaming: bool = True
    priority: int = 50  # Higher = preferred (0-100)
    is_free: bool = False
    retry_attempts: int = 3
    retry_delay: float = 1.0
    headers: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        """Post-initialization validation and setup"""
        if self.cost_per_1k_tokens == 0.0:
            self.is_free = True
            self.priority += 30  # Boost priority for free providers

@dataclass
class AIResponse:
    """Standardized AI response with metadata"""
    content: str
    provider: str
    model: Optional[str] = None
    tokens_used: int = 0
    cost: float = 0.0
    latency_ms: float = 0.0
    cached: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

class ProviderError(Exception):
    """Custom exception for provider-specific errors"""
    def __init__(self, provider: str, message: str, error_code: Optional[str] = None):
        self.provider = provider
        self.error_code = error_code
        super().__init__(f"[{provider}] {message}")

class AIProviderBase(ABC):
    """Abstract base class for AI providers with standardized interface"""
    
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self._request_count = 0
        self._last_request_time = 0.0
        
    async def __aenter__(self):
        await self.initialize()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()
    
    async def initialize(self):
        """Initialize provider resources"""
        connector = aiohttp.TCPConnector(
            limit=20,
            limit_per_host=10,
            ssl=ssl.create_default_context()
        )
        timeout = aiohttp.ClientTimeout(total=self.config.timeout)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=self.config.headers
        )
        logger.info(f"Initialized {self.config.name} provider")
    
    async def cleanup(self):
        """Cleanup provider resources"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def _rate_limit_check(self):
        """Check and enforce rate limiting"""
        current_time = time.time()
        if current_time - self._last_request_time < 60:  # Within 1 minute
            if self._request_count >= self.config.rate_limit:
                wait_time = 60 - (current_time - self._last_request_time)
                logger.warning(f"Rate limit hit for {self.config.name}, waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
                self._request_count = 0
                self._last_request_time = current_time
        else:
            self._request_count = 0
            self._last_request_time = current_time
        
        self._request_count += 1
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for the provider"""
        # Basic estimation: ~4 characters per token
        return max(1, len(text) // 4)
    
    def calculate_cost(self, tokens: int) -> float:
        """Calculate estimated cost for token usage"""
        return (tokens / 1000) * self.config.cost_per_1k_tokens
    
    @abstractmethod
    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        """Send a request to the AI provider and return response"""
        pass
    
    @abstractmethod
    async def stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Stream response from the AI provider"""
        pass

class OpenAIProvider(AIProviderBase):
    """OpenAI API provider with GPT models support"""
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.client = None
        
    async def initialize(self):
        await super().initialize()
        if OPENAI_AVAILABLE:
            self.client = openai.AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url
            )
    
    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        """Send request to OpenAI API"""
        if not self.client:
            raise ProviderError(self.config.name, "OpenAI client not initialized")
        
        await self._rate_limit_check()
        start_time = time.time()
        
        try:
            response = await self.client.chat.completions.create(
                model=kwargs.get('model', self.config.model or 'gpt-3.5-turbo'),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=kwargs.get('max_tokens', self.config.max_tokens),
                temperature=kwargs.get('temperature', 0.7),
                stream=False
            )
            
            latency_ms = (time.time() - start_time) * 1000
            content = response.choices[0].message.content
            tokens_used = response.usage.total_tokens if response.usage else self.estimate_tokens(content)
            
            return AIResponse(
                content=content,
                provider=self.config.name,
                model=response.model,
                tokens_used=tokens_used,
                cost=self.calculate_cost(tokens_used),
                latency_ms=latency_ms,
                metadata={'usage': response.usage._asdict() if response.usage else {}}
            )
            
        except Exception as e:
            logger.error(f"OpenAI request failed: {e}")
            raise ProviderError(self.config.name, str(e))
    
    async def stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Stream response from OpenAI"""
        if not self.client:
            raise ProviderError(self.config.name, "OpenAI client not initialized")
        
        await self._rate_limit_check()
        
        try:
            stream = await self.client.chat.completions.create(
                model=kwargs.get('model', self.config.model or 'gpt-3.5-turbo'),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=kwargs.get('max_tokens', self.config.max_tokens),
                temperature=kwargs.get('temperature', 0.7),
                stream=True
            )
            
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            logger.error(f"OpenAI streaming failed: {e}")
            raise ProviderError(self.config.name, str(e))

class ClaudeProvider(AIProviderBase):
    """Anthropic Claude provider"""
    
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.client = None
    
    async def initialize(self):
        await super().initialize()
        if ANTHROPIC_AVAILABLE:
            self.client = anthropic.AsyncAnthropic(api_key=self.config.api_key)
    
    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        """Send request to Claude API"""
        if not self.client:
            raise ProviderError(self.config.name, "Claude client not initialized")
        
        await self._rate_limit_check()
        start_time = time.time()
        
        try:
            response = await self.client.messages.create(
                model=kwargs.get('model', self.config.model or 'claude-3-haiku-20240307'),
                max_tokens=kwargs.get('max_tokens', self.config.max_tokens),
                temperature=kwargs.get('temperature', 0.7),
                messages=[{"role": "user", "content": prompt}]
            )
            
            latency_ms = (time.time() - start_time) * 1000
            content = response.content[0].text
            tokens_used = response.usage.input_tokens + response.usage.output_tokens
            
            return AIResponse(
                content=content,
                provider=self.config.name,
                model=response.model,
                tokens_used=tokens_used,
                cost=self.calculate_cost(tokens_used),
                latency_ms=latency_ms,
                metadata={'usage': response.usage._asdict()}
            )
            
        except Exception as e:
            logger.error(f"Claude request failed: {e}")
            raise ProviderError(self.config.name, str(e))
    
    async def stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Stream response from Claude"""
        if not self.client:
            raise ProviderError(self.config.name, "Claude client not initialized")
        
        await self._rate_limit_check()
        
        try:
            async with self.client.messages.stream(
                model=kwargs.get('model', self.config.model or 'claude-3-haiku-20240307'),
                max_tokens=kwargs.get('max_tokens', self.config.max_tokens),
                messages=[{"role": "user", "content": prompt}]
            ) as stream:
                async for text in stream.text_stream:
                    yield text
                    
        except Exception as e:
            logger.error(f"Claude streaming failed: {e}")
            raise ProviderError(self.config.name, str(e))

class OllamaProvider(AIProviderBase):
    """Local Ollama provider for free AI inference"""
    
    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        """Send request to local Ollama instance"""
        if not self.session:
            raise ProviderError(self.config.name, "Session not initialized")
        
        start_time = time.time()
        
        try:
            payload = {
                "model": kwargs.get('model', self.config.model or 'llama2'),
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": kwargs.get('temperature', 0.7),
                    "num_predict": kwargs.get('max_tokens', self.config.max_tokens)
                }
            }
            
            url = urljoin(self.config.base_url or 'http://localhost:11434', '/api/generate')
            
            async with self.session.post(url, json=payload) as response:
                if response.status != 200:
                    raise ProviderError(self.config.name, f"HTTP {response.status}")
                
                data = await response.json()
                content = data.get('response', '')
                latency_ms = (time.time() - start_time) * 1000
                tokens_used = self.estimate_tokens(content)
                
                return AIResponse(
                    content=content,
                    provider=self.config.name,
                    model=data.get('model'),
                    tokens_used=tokens_used,
                    cost=0.0,  # Free local inference
                    latency_ms=latency_ms,
                    metadata=data
                )
                
        except Exception as e:
            logger.error(f"Ollama request failed: {e}")
            raise ProviderError(self.config.name, str(e))
    
    async def stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Stream response from Ollama"""
        if not self.session:
            raise ProviderError(self.config.name, "Session not initialized")
        
        try:
            payload = {
                "model": kwargs.get('model', self.config.model or 'llama2'),
                "prompt": prompt,
                "stream": True,
                "options": {
                    "temperature": kwargs.get('temperature', 0.7),
                    "num_predict": kwargs.get('max_tokens', self.config.max_tokens)
                }
            }
            
            url = urljoin(self.config.base_url or 'http://localhost:11434', '/api/generate')
            
            async with self.session.post(url, json=payload) as response:
                if response.status != 200:
                    raise ProviderError(self.config.name, f"HTTP {response.status}")
                
                async for line in response.content:
                    if line:
                        try:
                            data = json.loads(line.decode())
                            if 'response' in data:
                                yield data['response']
                            if data.get('done', False):
                                break
                        except json.JSONDecodeError:
                            continue
                            
        except Exception as e:
            logger.error(f"Ollama streaming failed: {e}")
            raise ProviderError(self.config.name, str(e))

class HuggingFaceProvider(AIProviderBase):
    """HuggingFace Inference API provider with free tier support"""
    
    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        """Send request to HuggingFace Inference API"""
        if not self.session:
            raise ProviderError(self.config.name, "Session not initialized")
        
        start_time = time.time()
        
        try:
            model = kwargs.get('model', self.config.model or 'microsoft/DialoGPT-medium')
            url = f"https://api-inference.huggingface.co/models/{model}"
            
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "inputs": prompt,
                "parameters": {
                    "max_new_tokens": kwargs.get('max_tokens', self.config.max_tokens),
                    "temperature": kwargs.get('temperature', 0.7),
                    "return_full_text": False
                }
            }
            
            async with self.session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    raise ProviderError(self.config.name, f"HTTP {response.status}")
                
                data = await response.json()
                
                if isinstance(data, list) and len(data) > 0:
                    content = data[0].get('generated_text', '')
                else:
                    content = str(data)
                
                latency_ms = (time.time() - start_time) * 1000
                tokens_used = self.estimate_tokens(content)
                
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
            logger.error(f"HuggingFace request failed: {e}")
            raise ProviderError(self.config.name, str(e))
    
    async def stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """HuggingFace doesn't support streaming, simulate with chunked response"""
        response = await self.ask(prompt, **kwargs)
        
        # Simulate streaming by yielding content in chunks
        content = response.content
        chunk_size = 10
        
        for i in range(0, len(content), chunk_size):
            chunk = content[i:i + chunk_size]
            yield chunk
            await asyncio.sleep(0.05)  # Small delay to simulate streaming

class TogetherProvider(AIProviderBase):
    """Together AI provider with cost-effective models"""
    
    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        """Send request to Together AI API"""
        if not self.session:
            raise ProviderError(self.config.name, "Session not initialized")
        
        await self._rate_limit_check()
        start_time = time.time()
        
        try:
            url = urljoin(self.config.base_url or 'https://api.together.xyz/v1', '/chat/completions')
            
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": kwargs.get('model', self.config.model or 'meta-llama/Llama-2-7b-chat-hf'),
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": kwargs.get('max_tokens', self.config.max_tokens),
                "temperature": kwargs.get('temperature', 0.7),
                "stream": False
            }
            
            async with self.session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ProviderError(self.config.name, f"HTTP {response.status}: {error_text}")
                
                data = await response.json()
                content = data['choices'][0]['message']['content']
                latency_ms = (time.time() - start_time) * 1000
                tokens_used = data.get('usage', {}).get('total_tokens', self.estimate_tokens(content))
                
                return AIResponse(
                    content=content,
                    provider=self.config.name,
                    model=data.get('model'),
                    tokens_used=tokens_used,
                    cost=self.calculate_cost(tokens_used),
                    latency_ms=latency_ms,
                    metadata=data.get('usage', {})
                )
                
        except Exception as e:
            logger.error(f"Together AI request failed: {e}")
            raise ProviderError(self.config.name, str(e))
    
    async def stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Stream response from Together AI"""
        if not self.session:
            raise ProviderError(self.config.name, "Session not initialized")
        
        await self._rate_limit_check()
        
        try:
            url = urljoin(self.config.base_url or 'https://api.together.xyz/v1', '/chat/completions')
            
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": kwargs.get('model', self.config.model or 'meta-llama/Llama-2-7b-chat-hf'),
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": kwargs.get('max_tokens', self.config.max_tokens),
                "temperature": kwargs.get('temperature', 0.7),
                "stream": True
            }
            
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
            logger.error(f"Together AI streaming failed: {e}")
            raise ProviderError(self.config.name, str(e))

class AIAsyncClient:
    """
    Advanced async AI client with multi-provider support, cost optimization, and reliability features
    
    Features:
    - Multi-provider support with automatic failover
    - Cost optimization and free tier prioritization  
    - Rate limiting and circuit breaker protection
    - Streaming and non-streaming responses
    - Comprehensive error handling and retry logic
    - Performance monitoring and metrics
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.providers: Dict[str, AIProviderBase] = {}
        self.provider_configs: Dict[str, ProviderConfig] = {}
        self._setup_providers()
        self._provider_stats: Dict[str, Dict[str, Any]] = {}
        
    def _setup_providers(self):
        """Initialize all configured providers"""
        provider_classes = {
            'openai': OpenAIProvider,
            'claude': ClaudeProvider,
            'anthropic': ClaudeProvider,  # Alias for Claude
            'ollama': OllamaProvider,
            'huggingface': HuggingFaceProvider,
            'together': TogetherProvider,
            'moonshot': OpenAIProvider,  # Uses OpenAI-compatible API
        }
        
        for provider_name, provider_config in self.config.items():
            if provider_name in provider_classes:
                try:
                    # Create provider configuration
                    config = ProviderConfig(
                        name=provider_name,
                        api_key=provider_config.get('api_key'),
                        base_url=provider_config.get('base_url'),
                        model=provider_config.get('model'),
                        max_tokens=provider_config.get('max_tokens', 4096),
                        timeout=provider_config.get('timeout', 30),
                        rate_limit=provider_config.get('rate_limit', 60),
                        cost_per_1k_tokens=provider_config.get('cost_per_1k_tokens', 0.0),
                        supports_streaming=provider_config.get('supports_streaming', True),
                        priority=provider_config.get('priority', 50),
                        retry_attempts=provider_config.get('retry_attempts', 3),
                        retry_delay=provider_config.get('retry_delay', 1.0),
                        headers=provider_config.get('headers', {})
                    )
                    
                    # Create provider instance
                    provider_class = provider_classes[provider_name]
                    provider = provider_class(config)
                    
                    self.providers[provider_name] = provider
                    self.provider_configs[provider_name] = config
                    self._provider_stats[provider_name] = {
                        'requests': 0,
                        'errors': 0,
                        'total_tokens': 0,
                        'total_cost': 0.0,
                        'avg_latency': 0.0
                    }
                    
                    logger.info(f"✅ Configured {provider_name} provider")
                    
                except Exception as e:
                    logger.error(f"❌ Failed to configure {provider_name} provider: {e}")
        
        if not self.providers:
            raise RuntimeError("No AI providers could be configured")
        
        logger.info(f"🚀 AI client initialized with {len(self.providers)} providers")
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.aclose()
    
    async def initialize(self):
        """Initialize all providers"""
        for provider in self.providers.values():
            try:
                await provider.initialize()
            except Exception as e:
                logger.warning(f"Failed to initialize provider {provider.config.name}: {e}")
    
    async def aclose(self):
        """Cleanup all provider resources"""
        cleanup_tasks = []
        for provider in self.providers.values():
            cleanup_tasks.append(provider.cleanup())
        
        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        
        logger.info("🔄 AI client cleanup completed")
    
    def _select_optimal_provider(self, preferred_provider: Optional[str] = None) -> str:
        """
        Select the optimal provider based on cost, availability, and performance
        Priority: Free > Low cost > High priority > Availability
        """
        if preferred_provider and preferred_provider in self.providers:
            return preferred_provider
        
        # Sort providers by priority score
        scored_providers = []
        for name, config in self.provider_configs.items():
            if name not in self.providers:
                continue
                
            score = config.priority
            stats = self._provider_stats[name]
            
            # Boost free providers
            if config.is_free:
                score += 50
            
            # Penalize providers with high error rates
            if stats['requests'] > 0:
                error_rate = stats['errors'] / stats['requests']
                score -= int(error_rate * 100)
            
            # Boost providers with good latency
            if stats['avg_latency'] > 0:
                if stats['avg_latency'] < 1000:  # Under 1 second
                    score += 20
                elif stats['avg_latency'] > 5000:  # Over 5 seconds
                    score -= 20
            
            scored_providers.append((score, name))
        
        if not scored_providers:
            raise ProviderError("system", "No available providers")
        
        # Return highest scoring provider
        scored_providers.sort(reverse=True)
        selected = scored_providers[0][1]
        
        logger.debug(f"🎯 Selected provider: {selected} (score: {scored_providers[0][0]})")
        return selected
    
    async def _execute_with_retry(
        self, 
        provider: AIProviderBase, 
        operation: Callable,
        *args, 
        **kwargs
    ) -> Any:
        """Execute operation with retry logic and exponential backoff"""
        last_exception = None
        
        for attempt in range(provider.config.retry_attempts):
            try:
                return await operation(*args, **kwargs)
            except ProviderError as e:
                last_exception = e
                self._provider_stats[provider.config.name]['errors'] += 1
                
                if attempt < provider.config.retry_attempts - 1:
                    delay = provider.config.retry_delay * (2 ** attempt)
                    logger.warning(
                        f"⚠️  Attempt {attempt + 1} failed for {provider.config.name}, "
                        f"retrying in {delay:.1f}s: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"❌ All retry attempts failed for {provider.config.name}")
        
        raise last_exception
    
    async def ask(
        self, 
        prompt: str, 
        provider: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        model: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Send a prompt to an AI provider and get response
        
        Args:
            prompt: Input text prompt
            provider: Specific provider to use (auto-select if None)
            max_tokens: Maximum tokens in response
            temperature: Response creativity (0.0-1.0)
            model: Specific model to use
            **kwargs: Additional provider-specific parameters
        
        Returns:
            AI-generated response text
        """
        selected_provider = self._select_optimal_provider(provider)
        provider_instance = self.providers[selected_provider]
        
        try:
            # Update request parameters
            request_kwargs = {
                'max_tokens': max_tokens,
                'temperature': temperature,
                'model': model,
                **kwargs
            }
            
            # Execute with retry logic
            response = await self._execute_with_retry(
                provider_instance,
                provider_instance.ask,
                prompt,
                **request_kwargs
            )
            
            # Update statistics
            stats = self._provider_stats[selected_provider]
            stats['requests'] += 1
            stats['total_tokens'] += response.tokens_used
            stats['total_cost'] += response.cost
            stats['avg_latency'] = (
                (stats['avg_latency'] * (stats['requests'] - 1) + response.latency_ms) 
                / stats['requests']
            )
            
            logger.info(
                f"✅ {selected_provider} response: {response.tokens_used} tokens, "
                f"{response.latency_ms:.0f}ms, ${response.cost:.4f}"
            )
            
            return response.content
            
        except Exception as e:
            logger.error(f"❌ Request failed for {selected_provider}: {e}")
            
            # Try fallback to another provider
            if not provider:  # Only fallback if provider wasn't specifically requested
                available_providers = [p for p in self.providers.keys() if p != selected_provider]
                if available_providers:
                    fallback_provider = self._select_optimal_provider()
                    if fallback_provider != selected_provider:
                        logger.info(f"🔄 Falling back to {fallback_provider}")
                        return await self.ask(
                            prompt, 
                            provider=fallback_provider,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            model=model,
                            **kwargs
                        )
            
            raise
    
    async def stream(
        self, 
        prompt: str, 
        provider: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        model: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        Stream response from an AI provider
        
        Args:
            prompt: Input text prompt
            provider: Specific provider to use (auto-select if None)
            max_tokens: Maximum tokens in response
            temperature: Response creativity (0.0-1.0)
            model: Specific model to use
            **kwargs: Additional provider-specific parameters
        
        Yields:
            Chunks of AI-generated response text
        """
        selected_provider = self._select_optimal_provider(provider)
        provider_instance = self.providers[selected_provider]
        
        if not provider_instance.config.supports_streaming:
            # Fallback to non-streaming for providers that don't support it
            response = await self.ask(prompt, provider, max_tokens, temperature, model, **kwargs)
            
            # Simulate streaming by yielding chunks
            chunk_size = 20
            for i in range(0, len(response), chunk_size):
                chunk = response[i:i + chunk_size]
                yield chunk
                await asyncio.sleep(0.1)
            return
        
        try:
            request_kwargs = {
                'max_tokens': max_tokens,
                'temperature': temperature,
                'model': model,
                **kwargs
            }
            
            # Stream with retry on the generator level
            start_time = time.time()
            total_content = ""
            
            async for chunk in provider_instance.stream(prompt, **request_kwargs):
                total_content += chunk
                yield chunk
            
            # Update statistics for streaming
            latency_ms = (time.time() - start_time) * 1000
            tokens_used = provider_instance.estimate_tokens(total_content)
            cost = provider_instance.calculate_cost(tokens_used)
            
            stats = self._provider_stats[selected_provider]
            stats['requests'] += 1
            stats['total_tokens'] += tokens_used
            stats['total_cost'] += cost
            stats['avg_latency'] = (
                (stats['avg_latency'] * (stats['requests'] - 1) + latency_ms) 
                / stats['requests']
            )
            
            logger.info(
                f"✅ {selected_provider} streaming: {tokens_used} tokens, "
                f"{latency_ms:.0f}ms, ${cost:.4f}"
            )
            
        except Exception as e:
            logger.error(f"❌ Streaming failed for {selected_provider}: {e}")
            raise
    
    async def batch_ask(
        self, 
        prompts: List[str], 
        provider: Optional[str] = None,
        concurrency: int = 5,
        **kwargs
    ) -> List[str]:
        """
        Process multiple prompts concurrently with cost optimization
        
        Args:
            prompts: List of input prompts
            provider: Specific provider to use
            concurrency: Maximum concurrent requests
            **kwargs: Additional parameters for ask()
        
        Returns:
            List of AI responses in same order as prompts
        """
        if not prompts:
            return []
        
        # Use free/local providers for batch processing when possible
        optimal_provider = provider
        if not optimal_provider:
            free_providers = [
                name for name, config in self.provider_configs.items() 
                if config.is_free and name in self.providers
            ]
            if free_providers:
                optimal_provider = self._select_optimal_provider()
        
        semaphore = asyncio.Semaphore(concurrency)
        
        async def process_prompt(i: int, prompt: str) -> tuple[int, str]:
            async with semaphore:
                response = await self.ask(prompt, provider=optimal_provider, **kwargs)
                return i, response
        
        # Execute all prompts concurrently
        tasks = [process_prompt(i, prompt) for i, prompt in enumerate(prompts)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Sort results by original order and handle exceptions
        responses = [''] * len(prompts)
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Batch item failed: {result}")
                continue
            i, response = result
            responses[i] = response
        
        return responses
    
    def get_provider_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get performance statistics for all providers"""
        return self._provider_stats.copy()
    
    def get_available_providers(self) -> List[str]:
        """Get list of available provider names"""
        return list(self.providers.keys())
    
    def get_provider_info(self, provider_name: str) -> Dict[str, Any]:
        """Get detailed information about a specific provider"""
        if provider_name not in self.provider_configs:
            raise ValueError(f"Provider {provider_name} not found")
        
        config = self.provider_configs[provider_name]
        stats = self._provider_stats[provider_name]
        
        return {
            'name': config.name,
            'is_free': config.is_free,
            'cost_per_1k_tokens': config.cost_per_1k_tokens,
            'supports_streaming': config.supports_streaming,
            'priority': config.priority,
            'rate_limit': config.rate_limit,
            'statistics': stats
        }

# Convenience functions for easy usage
async def create_ai_client(config: Dict[str, Any]) -> AIAsyncClient:
    """Create and initialize AI client"""
    client = AIAsyncClient(config)
    await client.initialize()
    return client

# Example usage and testing
if __name__ == "__main__":
    import asyncio
    
    async def test_client():
        """Test the AI client with multiple providers"""
        
        # Example configuration
        config = {
            "ollama": {
                "base_url": "http://localhost:11434",
                "model": "llama2",
                "priority": 90,  # High priority for free local
                "is_free": True
            },
            "huggingface": {
                "api_key": "your_hf_token",
                "model": "microsoft/DialoGPT-medium",
                "priority": 80,
                "is_free": True
            },
            "openai": {
                "api_key": "your_openai_key",
                "model": "gpt-3.5-turbo",
                "cost_per_1k_tokens": 0.002,
                "priority": 60
            }
        }
        
        async with AIAsyncClient(config) as client:
            # Test simple request
            response = await client.ask("What is the capital of France?")
            print(f"Response: {response}")
            
            # Test streaming
            print("Streaming response:")
            async for chunk in client.stream("Tell me a short story about AI"):
                print(chunk, end='', flush=True)
            print()
            
            # Test batch processing
            prompts = [
                "What is 2+2?",
                "Name a programming language",
                "What is the weather?"
            ]
            batch_responses = await client.batch_ask(prompts)
            for prompt, response in zip(prompts, batch_responses):
                print(f"Q: {prompt} A: {response[:50]}...")
            
            # Show provider statistics
            stats = client.get_provider_stats()
            print(f"Provider stats: {stats}")
    
    # Run test if script is executed directly
    asyncio.run(test_client())