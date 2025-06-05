# services/ai_async_client-2.py
import asyncio
import aiohttp
import time
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from collections import defaultdict
import statistics

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ProviderType(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    COHERE = "cohere"
    HUGGINGFACE = "huggingface"

class TaskComplexity(Enum):
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"

@dataclass
class ProviderConfig:
    name: str
    provider_type: ProviderType
    api_key: str
    base_url: str
    models: List[str]
    cost_per_token: float
    max_tokens: int
    rate_limit: int  # requests per minute
    timeout: int = 30
    quality_score: float = 1.0  # 0.0 to 1.0
    speed_score: float = 1.0    # 0.0 to 1.0

@dataclass
class ProviderMetrics:
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_response_time: float = 0.0
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    consecutive_failures: int = 0
    uptime_percentage: float = 100.0
    response_times: List[float] = None

    def __post_init__(self):
        if self.response_times is None:
            self.response_times = []

@dataclass
class CacheEntry:
    response: Any
    timestamp: datetime
    ttl: int  # seconds
    hit_count: int = 0

    def is_expired(self) -> bool:
        return datetime.now() > self.timestamp + timedelta(seconds=self.ttl)

class HealthMonitor:
    def __init__(self, check_interval: int = 60):
        self.check_interval = check_interval
        self.running = False
        self.health_checks = {}

    async def start_monitoring(self, providers: Dict[str, 'AIProvider']):
        self.running = True
        while self.running:
            await self.check_all_providers(providers)
            await asyncio.sleep(self.check_interval)

    async def check_all_providers(self, providers: Dict[str, 'AIProvider']):
        tasks = []
        for provider_name, provider in providers.items():
            tasks.append(self.check_provider_health(provider_name, provider))
        
        await asyncio.gather(*tasks, return_exceptions=True)

    async def check_provider_health(self, name: str, provider: 'AIProvider'):
        try:
            start_time = time.time()
            # Simple health check with minimal request
            response = await provider.generate_simple_response("test")
            response_time = time.time() - start_time
            
            self.health_checks[name] = {
                'status': 'healthy',
                'response_time': response_time,
                'last_check': datetime.now()
            }
            logger.info(f"Provider {name} health check: OK ({response_time:.2f}s)")
            
        except Exception as e:
            self.health_checks[name] = {
                'status': 'unhealthy',
                'error': str(e),
                'last_check': datetime.now()
            }
            logger.warning(f"Provider {name} health check failed: {e}")

    def stop_monitoring(self):
        self.running = False

class ResponseCache:
    def __init__(self, max_size: int = 1000, default_ttl: int = 3600):
        self.cache: Dict[str, CacheEntry] = {}
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.hits = 0
        self.misses = 0

    def _generate_key(self, prompt: str, model: str, params: Dict) -> str:
        """Generate cache key from request parameters"""
        cache_data = {
            'prompt': prompt,
            'model': model,
            'params': sorted(params.items())
        }
        return hashlib.md5(json.dumps(cache_data, sort_keys=True).encode()).hexdigest()

    def get(self, prompt: str, model: str, params: Dict) -> Optional[Any]:
        key = self._generate_key(prompt, model, params)
        
        if key in self.cache:
            entry = self.cache[key]
            if not entry.is_expired():
                entry.hit_count += 1
                self.hits += 1
                logger.debug(f"Cache hit for key: {key[:8]}...")
                return entry.response
            else:
                del self.cache[key]
        
        self.misses += 1
        logger.debug(f"Cache miss for key: {key[:8]}...")
        return None

    def set(self, prompt: str, model: str, params: Dict, response: Any, ttl: Optional[int] = None):
        if len(self.cache) >= self.max_size:
            self._evict_oldest()
        
        key = self._generate_key(prompt, model, params)
        ttl = ttl or self.default_ttl
        
        self.cache[key] = CacheEntry(
            response=response,
            timestamp=datetime.now(),
            ttl=ttl
        )
        logger.debug(f"Cached response for key: {key[:8]}...")

    def _evict_oldest(self):
        """Remove oldest cache entries when max size is reached"""
        if not self.cache:
            return
        
        # Remove expired entries first
        expired_keys = [k for k, v in self.cache.items() if v.is_expired()]
        for key in expired_keys:
            del self.cache[key]
        
        # If still over limit, remove least recently used
        if len(self.cache) >= self.max_size:
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k].timestamp)
            del self.cache[oldest_key]

    def get_stats(self) -> Dict:
        total_requests = self.hits + self.misses
        hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'total_entries': len(self.cache),
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': f"{hit_rate:.2f}%",
            'expired_entries': sum(1 for entry in self.cache.values() if entry.is_expired())
        }

class AIProvider:
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.metrics = ProviderMetrics()
        self.is_healthy = True
        self.last_request_time = 0
        self.request_count_window = []  # For rate limiting

    async def generate_response(self, prompt: str, model: str = None, **kwargs) -> Dict:
        """Generate response from AI provider"""
        if not self._check_rate_limit():
            raise Exception(f"Rate limit exceeded for provider {self.config.name}")
        
        model = model or self.config.models[0]
        start_time = time.time()
        
        try:
            self.metrics.total_requests += 1
            
            # Simulate API call (replace with actual provider API calls)
            async with aiohttp.ClientSession() as session:
                response = await self._make_api_request(session, prompt, model, **kwargs)
            
            response_time = time.time() - start_time
            self._update_success_metrics(response_time)
            
            return {
                'response': response,
                'model': model,
                'provider': self.config.name,
                'response_time': response_time,
                'tokens_used': len(prompt.split()) * 2  # Rough estimate
            }
            
        except Exception as e:
            self._update_failure_metrics()
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