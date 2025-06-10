# services/ai_async_client.py
"""
Unified AI Client - Optimized async implementation with multiple provider support
Combines cost-effectiveness, performance, and simplicity
Combined from # ai_async_client__complex_async-3.py and ai_async_client__complex_async-4.py
"""
import asyncio
import aiohttp
import json
import logging
import time
import hashlib
import yaml
import os
from typing import Dict, Any, Optional, List, AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global response cache
_response_cache: Dict[str, tuple[str, float]] = {}
CACHE_TTL = 3600  # 1 hour

class ProviderType(Enum):
    """Supported AI providers prioritized by cost-effectiveness"""
    OPENAI = "openai"
    YANDEXGPT = "yandexgpt"
    OLLAMA = "ollama"
    HUGGINGFACE = "huggingface"
    GROQ = "groq"
    MOCK = "mock"

@dataclass
class ProviderConfig:
    """Provider configuration with cost optimization"""
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
    headers: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        """Auto-configure based on provider type"""
        if self.cost_per_1k_tokens <= 0.001:
            self.is_free = True
            self.priority += 30

@dataclass
class AIResponse:
    """AI response with metadata"""
    content: str
    provider: str
    model: Optional[str] = None
    tokens_used: int = 0
    cost: float = 0.0
    latency_ms: float = 0.0
    cached: bool = False

class ProviderError(Exception):
    """Provider-specific error"""
    def __init__(self, provider: str, message: str):
        self.provider = provider
        super().__init__(f"[{provider}] {message}")

class BaseProvider(ABC):
    """Base provider class with common functionality"""
    
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self._failures = 0
        self._last_failure_time = 0.0
        
    async def initialize(self):
        """Initialize HTTP session"""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers=self.config.headers
            )
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count"""
        return max(1, len(text) // 4)  # Rough estimation: 4 chars per token
    
    def _calculate_cost(self, tokens: int) -> float:
        """Calculate cost"""
        return (tokens / 1000) * self.config.cost_per_1k_tokens
    
    def _get_cache_key(self, prompt: str, **kwargs) -> str:
        """Generate cache key"""
        cache_data = {
            'prompt': prompt,
            'model': kwargs.get('model', self.config.model),
            'provider': self.config.name
        }
        return hashlib.md5(json.dumps(cache_data, sort_keys=True).encode()).hexdigest()
    
    def _get_cached_response(self, cache_key: str) -> Optional[str]:
        """Get cached response"""
        if cache_key in _response_cache:
            response, timestamp = _response_cache[cache_key]
            if time.time() - timestamp < CACHE_TTL:
                return response
            del _response_cache[cache_key]
        return None
    
    def _cache_response(self, cache_key: str, response: str):
        """Cache response"""
        _response_cache[cache_key] = (response, time.time())
        # Simple cache cleanup
        if len(_response_cache) > 1000:
            oldest_keys = sorted(_response_cache.keys(), 
                               key=lambda k: _response_cache[k][1])[:200]
            for key in oldest_keys:
                del _response_cache[key]
    
    def _is_healthy(self) -> bool:
        """Check if provider is healthy"""
        if self._failures >= 3:
            return time.time() - self._last_failure_time > 300  # 5 min cooldown
        return True
    
    def _record_success(self):
        """Record successful request"""
        self._failures = max(0, self._failures - 1)
    
    def _record_failure(self):
        """Record failed request"""
        self._failures += 1
        self._last_failure_time = time.time()
    
    @abstractmethod
    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        """Ask provider for response"""
        pass

class OpenAIProvider(BaseProvider):
    """OpenAI provider implementation"""
    
    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        if not self._is_healthy():
            raise ProviderError(self.config.name, "Provider unhealthy")
        
        # Check cache
        cache_key = self._get_cache_key(prompt, **kwargs)
        cached_response = self._get_cached_response(cache_key)
        if cached_response:
            return AIResponse(
                content=cached_response,
                provider=self.config.name,
                tokens_used=self._estimate_tokens(cached_response),
                cost=0.0,
                latency_ms=1.0,
                cached=True
            )
        
        start_time = time.time()
        try:
            await self.initialize()
            
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": kwargs.get('model', self.config.model or 'gpt-3.5-turbo'),
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": kwargs.get('max_tokens', self.config.max_tokens),
                "temperature": kwargs.get('temperature', 0.7)
            }
            
            url = f"{self.config.base_url or 'https://api.openai.com/v1'}/chat/completions"
            
            async with self.session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    self._record_failure()
                    text = await response.text()
                    raise ProviderError(self.config.name, f"HTTP {response.status}: {text}")
                
                data = await response.json()
                content = data['choices'][0]['message']['content'].strip()
                
                latency_ms = (time.time() - start_time) * 1000
                tokens_used = data.get('usage', {}).get('total_tokens', 
                                                        self._estimate_tokens(content))
                cost = self._calculate_cost(tokens_used)
                
                # Cache response
                self._cache_response(cache_key, content)
                self._record_success()
                
                return AIResponse(
                    content=content,
                    provider=self.config.name,
                    model=data.get('model'),
                    tokens_used=tokens_used,
                    cost=cost,
                    latency_ms=latency_ms
                )
        
        except Exception as e:
            self._record_failure()
            raise ProviderError(self.config.name, str(e))

class YandexGPTProvider(BaseProvider):
    """YandexGPT provider implementation"""
    
    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        if not self._is_healthy():
            raise ProviderError(self.config.name, "Provider unhealthy")
        
        # Check cache
        cache_key = self._get_cache_key(prompt, **kwargs)
        cached_response = self._get_cached_response(cache_key)
        if cached_response:
            return AIResponse(
                content=cached_response,
                provider=self.config.name,
                tokens_used=self._estimate_tokens(cached_response),
                cost=0.0,
                latency_ms=1.0,
                cached=True
            )
        
        start_time = time.time()
        try:
            await self.initialize()
            
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
                    self._record_failure()
                    text = await response.text()
                    raise ProviderError(self.config.name, f"HTTP {response.status}: {text}")
                
                data = await response.json()
                content = data["result"]["alternatives"][0]["message"]["text"].strip()
                
                latency_ms = (time.time() - start_time) * 1000
                tokens_used = self._estimate_tokens(content)
                cost = self._calculate_cost(tokens_used)
                
                # Cache response
                self._cache_response(cache_key, content)
                self._record_success()
                
                return AIResponse(
                    content=content,
                    provider=self.config.name,
                    model=self.config.model,
                    tokens_used=tokens_used,
                    cost=cost,
                    latency_ms=latency_ms
                )
        
        except Exception as e:
            self._record_failure()
            raise ProviderError(self.config.name, str(e))

class OllamaProvider(BaseProvider):
    """Ollama local provider implementation"""
    
    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        if not self._is_healthy():
            raise ProviderError(self.config.name, "Provider unhealthy")
        
        # Check cache
        cache_key = self._get_cache_key(prompt, **kwargs)
        cached_response = self._get_cached_response(cache_key)
        if cached_response:
            return AIResponse(
                content=cached_response,
                provider=self.config.name,
                tokens_used=self._estimate_tokens(cached_response),
                cost=0.0,
                latency_ms=1.0,
                cached=True
            )
        
        start_time = time.time()
        try:
            await self.initialize()
            
            payload = {
                "model": kwargs.get('model', self.config.model or 'llama3.2:1b'),
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": kwargs.get('temperature', 0.7),
                    "num_predict": kwargs.get('max_tokens', self.config.max_tokens),
                }
            }
            
            url = f"{self.config.base_url or 'http://localhost:11434'}/api/generate"
            
            async with self.session.post(url, json=payload) as response:
                if response.status != 200:
                    self._record_failure()
                    text = await response.text()
                    raise ProviderError(self.config.name, f"HTTP {response.status}: {text}")
                
                data = await response.json()
                content = data.get('response', '').strip()
                
                if not content:
                    raise ProviderError(self.config.name, "Empty response")
                
                latency_ms = (time.time() - start_time) * 1000
                tokens_used = self._estimate_tokens(content)
                
                # Cache response
                self._cache_response(cache_key, content)
                self._record_success()
                
                return AIResponse(
                    content=content,
                    provider=self.config.name,
                    model=data.get('model'),
                    tokens_used=tokens_used,
                    cost=0.0,  # Free
                    latency_ms=latency_ms
                )
        
        except Exception as e:
            self._record_failure()
            raise ProviderError(self.config.name, str(e))

class MockProvider(BaseProvider):
    """Mock provider for testing"""
    
    async def ask(self, prompt: str, **kwargs) -> AIResponse:
        await asyncio.sleep(0.1)  # Simulate latency
        
        content = f"Mock response to: {prompt[:100]}..."
        tokens_used = self._estimate_tokens(content)
        
        return AIResponse(
            content=content,
            provider=self.config.name,
            model="mock-model",
            tokens_used=tokens_used,
            cost=0.0,
            latency_ms=100.0
        )

class AIClient:
    """
    Unified AI client with multiple provider support
    Features:
    - Async support for better performance
    - Automatic provider selection based on cost/performance
    - Response caching to reduce costs
    - Circuit breaker for failing providers
    - Simple configuration via YAML
    """
    
    def __init__(self, config_path: str = "ai_integrations.yaml"):
        self.providers: Dict[str, BaseProvider] = {}
        self.config = self._load_config(config_path)
        self._setup_providers()
        self._daily_cost = 0.0
        self._daily_budget = 10.0  # Default $10 daily budget
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load and process configuration"""
        try:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)
            
            # Expand environment variables
            for provider, settings in config.items():
                for key, value in settings.items():
                    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                        env_key = value[2:-1]
                        config[provider][key] = os.getenv(env_key)
            
            return config
        except FileNotFoundError:
            logger.warning(f"Config file {config_path} not found, using defaults")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        return {
            "ollama": {
                "base_url": "http://localhost:11434",
                "model": "llama3.2:1b",
                "cost_per_1k_tokens": 0.0,
                "priority": 90
            },
            "mock": {
                "cost_per_1k_tokens": 0.0,
                "priority": 10
            }
        }
    
    def _setup_providers(self):
        """Setup providers from configuration"""
        provider_classes = {
            "openai": OpenAIProvider,
            "yandexgpt": YandexGPTProvider,
            "ollama": OllamaProvider,
            "mock": MockProvider
        }
        
        for name, settings in self.config.items():
            try:
                provider_type = ProviderType(name)
                config = ProviderConfig(
                    name=name,
                    provider_type=provider_type,
                    api_key=settings.get("api_key"),
                    base_url=settings.get("base_url"),
                    model=settings.get("model"),
                    max_tokens=settings.get("max_tokens", 4096),
                    timeout=settings.get("timeout", 30),
                    cost_per_1k_tokens=settings.get("cost_per_1k_tokens", 0.0),
                    priority=settings.get("priority", 50),
                    headers=settings.get("headers", {})
                )
                
                provider_class = provider_classes.get(name, MockProvider)
                self.providers[name] = provider_class(config)
                
                logger.info(f"✅ Configured {name} provider")
                
            except Exception as e:
                logger.error(f"❌ Failed to configure {name}: {e}")
        
        # Ensure at least one provider
        if not self.providers:
            logger.warning("No providers configured, adding mock provider")
            config = ProviderConfig(
                name="mock",
                provider_type=ProviderType.MOCK,
                cost_per_1k_tokens=0.0,
                priority=10
            )
            self.providers["mock"] = MockProvider(config)
    
    def _select_provider(self, preferred_provider: Optional[str] = None) -> str:
        """Select best available provider"""
        if preferred_provider and preferred_provider in self.providers:
            provider = self.providers[preferred_provider]
            if provider._is_healthy():
                return preferred_provider
        
        # Sort by priority (higher is better) and health
        healthy_providers = [
            (name, provider) for name, provider in self.providers.items()
            if provider._is_healthy()
        ]
        
        if not healthy_providers:
            raise ProviderError("system", "No healthy providers available")
        
        # Select highest priority provider
        best_provider = max(healthy_providers, 
                           key=lambda x: x[1].config.priority)
        return best_provider[0]
    
    async def ask(self, 
                  prompt: str, 
                  provider: Optional[str] = None,
                  model: Optional[str] = None,
                  max_tokens: Optional[int] = None,
                  temperature: float = 0.7,
                  **kwargs) -> str:
        """
        Ask AI providers for response with automatic provider selection
        
        Args:
            prompt: Input text prompt
            provider: Specific provider to use (auto-select if None)
            model: Specific model to use
            max_tokens: Maximum tokens in response
            temperature: Response creativity (0.0-1.0)
            **kwargs: Additional parameters
        
        Returns:
            AI-generated response text
        """
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty")
        
        # Select provider
        selected_provider = self._select_provider(provider)
        provider_instance = self.providers[selected_provider]
        
        try:
            # Execute request
            response = await provider_instance.ask(
                prompt,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )
            
            # Update cost tracking
            self._daily_cost += response.cost
            
            # Log response info
            cache_info = " (cached)" if response.cached else ""
            logger.info(
                f"✅ {selected_provider} response: {response.tokens_used} tokens, "
                f"{response.latency_ms:.0f}ms, ${response.cost:.4f}{cache_info}"
            )
            
            return response.content
            
        except Exception as e:
            logger.error(f"Provider {selected_provider} failed: {e}")
            # Try fallback provider if available
            if len(self.providers) > 1:
                fallback_providers = [name for name in self.providers.keys() 
                                    if name != selected_provider and 
                                    self.providers[name]._is_healthy()]
                if fallback_providers:
                    logger.info(f"Trying fallback provider: {fallback_providers[0]}")
                    return await self.ask(prompt, fallback_providers[0], model, 
                                        max_tokens, temperature, **kwargs)
            raise
    
    async def batch_ask(self, 
                       prompts: List[str], 
                       max_concurrency: int = 5,
                       **kwargs) -> List[str]:
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
                return await self.ask(prompt, **kwargs)
        
        tasks = [process_prompt(prompt) for prompt in prompts]
        return await asyncio.gather(*tasks)
    
    async def close(self):
        """Close all provider connections"""
        cleanup_tasks = [provider.cleanup() for provider in self.providers.values()]
        await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        logger.info("🔄 AI client closed")
    
    async def __aenter__(self):
        """Async context manager entry"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics"""
        provider_stats = {}
        for name, provider in self.providers.items():
            provider_stats[name] = {
                "healthy": provider._is_healthy(),
                "failures": provider._failures,
                "cost_per_1k_tokens": provider.config.cost_per_1k_tokens,
                "priority": provider.config.priority,
                "is_free": provider.config.is_free
            }
        
        return {
            "providers": provider_stats,
            "daily_cost": self._daily_cost,
            "daily_budget": self._daily_budget,
            "cache_size": len(_response_cache),
            "total_providers": len(self.providers),
            "healthy_providers": sum(1 for p in self.providers.values() if p._is_healthy())
        }

# Compatibility functions for existing code
def create_ai_client(config_path: str = "ai_integrations.yaml") -> AIClient:
    """Create AI client instance"""
    return AIClient(config_path)

async def quick_ask(prompt: str, provider: str = None) -> str:
    """Quick ask function for simple use cases"""
    async with AIClient() as client:
        return await client.ask(prompt, provider=provider)

# Example usage
async def main():
    """Example usage of the unified AI client"""
    
    # Example configuration file structure
    config_example = {
        "openai": {
            "api_key": "${OPENAI_API_KEY}",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-3.5-turbo",
            "cost_per_1k_tokens": 0.002,
            "priority": 70,
            "max_tokens": 4096
        },
        "yandexgpt": {
            "api_key": "${YANDEX_API_KEY}",
            "base_url": "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
            "model": "gpt://b1g4bn3k4gm8r3tvjc0p/yandexgpt-lite",
            "cost_per_1k_tokens": 0.001,
            "priority": 60
        },
        "ollama": {
            "base_url": "http://localhost:11434",
            "model": "llama3.2:1b",
            "cost_per_1k_tokens": 0.0,
            "priority": 90
        }
    }
    
    # Using the client
    async with AIClient() as client:
        # Single request
        response = await client.ask("What is artificial intelligence?")
        print(f"Response: {response}")
        
        # With specific provider
        response = await client.ask("Explain machine learning", provider="ollama")
        print(f"Ollama response: {response}")
        
        # Batch processing
        prompts = [
            "What is Python?",
            "Explain async programming",
            "What is machine learning?"
        ]
        responses = await client.batch_ask(prompts, max_concurrency=2)
        print(f"Batch responses: {len(responses)} received")
        
        # Get statistics
        stats = client.get_stats()
        print(f"Stats: {stats}")

if __name__ == "__main__":
    asyncio.run(main())