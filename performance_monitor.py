# performance_monitor.py - Future-proof performance monitoring with Python 3.13+ support
from __future__ import annotations

import asyncio
import functools
import logging
import sys
import time
import traceback
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import (
    Any, Awaitable, Callable, Dict, List, Optional, 
    TypeVar, Union, Protocol, runtime_checkable
)
from collections import defaultdict, deque
from prometheus_client import CollectorRegistry, Counter

# Type definitions for better code clarity
F = TypeVar('F', bound=Callable[..., Any])
AsyncF = TypeVar('AsyncF', bound=Callable[..., Awaitable[Any]])

logger = logging.getLogger(__name__)

class ErrorSeverity(Enum):
    """Error severity levels for better categorization"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class OperationType(Enum):
    """Types of operations for specialized monitoring"""
    AI_REQUEST = "ai_request"
    CACHE_OPERATION = "cache_operation"
    DATABASE_OPERATION = "database_operation"
    NETWORK_OPERATION = "network_operation"
    COMPUTATION = "computation"

@dataclass
class PerformanceThresholds:
    """Configurable performance thresholds"""
    warning_threshold: float = 5.0  # seconds
    error_threshold: float = 30.0   # seconds
    timeout_threshold: float = 60.0  # seconds
    
    # Dynamic thresholds based on operation type
    operation_thresholds: Dict[OperationType, float] = field(default_factory=lambda: {
        OperationType.AI_REQUEST: 10.0,
        OperationType.CACHE_OPERATION: 0.1,
        OperationType.DATABASE_OPERATION: 2.0,
        OperationType.NETWORK_OPERATION: 5.0,
        OperationType.COMPUTATION: 1.0,
    })
    
    def get_threshold(self, operation_type: OperationType) -> float:
        """Get threshold for specific operation type"""
        return self.operation_thresholds.get(operation_type, self.warning_threshold)

@dataclass
class OperationMetrics:
    """Comprehensive operation metrics"""
    operation_name: str
    operation_type: OperationType
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    success: bool = False
    error: Optional[Exception] = None
    error_type: Optional[str] = None
    error_severity: ErrorSeverity = ErrorSeverity.LOW
    provider: Optional[str] = None
    model: Optional[str] = None
    tokens_used: int = 0
    cost: float = 0.0
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def finalize(self, success: bool = True, error: Optional[Exception] = None) -> None:
        """Finalize metrics calculation"""
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        self.success = success
        self.error = error
        if error:
            self.error_type = type(error).__name__
            self.error_severity = self._categorize_error_severity(error)
    
    def _categorize_error_severity(self, error: Exception) -> ErrorSeverity:
        """Categorize error severity based on exception type"""
        critical_errors = (SystemExit, KeyboardInterrupt, MemoryError)
        high_errors = (ConnectionError, TimeoutError, asyncio.TimeoutError)
        medium_errors = (ValueError, TypeError, AttributeError)
        
        if isinstance(error, critical_errors):
            return ErrorSeverity.CRITICAL
        elif isinstance(error, high_errors):
            return ErrorSeverity.HIGH
        elif isinstance(error, medium_errors):
            return ErrorSeverity.MEDIUM
        else:
            return ErrorSeverity.LOW

@runtime_checkable
class MetricsCollector(Protocol):
    """Protocol for metrics collection backends"""
    
    def record_operation(self, metrics: OperationMetrics) -> None:
        """Record operation metrics"""
        ...
    
    def increment_counter(self, name: str, labels: Dict[str, str]) -> None:
        """Increment a counter metric"""
        ...
    
    def observe_histogram(self, name: str, value: float, labels: Dict[str, str]) -> None:
        """Observe a histogram metric"""
        ...

class PrometheusMetricsCollector:
    """Prometheus metrics collector implementation"""
    
    def __init__(self, enabled=True):
        """
        Initialize Prometheus metrics collector.

        Args:
            enabled (bool): Enable or disable metrics collection.
        """
        self.enabled = enabled
        # Initialize other components

    def collect(self):
        if not self.enabled:
            return
        # collect metrics
        if registry is not None and not isinstance(registry, CollectorRegistry):
            raise TypeError("registry must be a CollectorRegistry instance or None")

        self.registry = registry or CollectorRegistry()
    
    def _setup_prometheus(self) -> None:
        """Setup Prometheus metrics if available"""
        try:
            from prometheus_client import Counter, Histogram, Gauge
            
            self.request_counter = Counter(
            'ai_operations_total',
            'Total AI operations',
            ['operation', 'provider', 'status', 'error_type'],
            registry=self.registry
            )
            self.created_counter = Counter(
                'ai_operations_created',
                'Created AI operations',
                registry=self.registry
            )
            self.operations_gauge = Counter(
                'ai_operations',
                'In-progress AI operations',
                registry=self.registry
            )
            
            self.duration_histogram = Histogram(
                'ai_operation_duration_seconds',
                'AI operation duration',
                ['operation', 'provider', 'operation_type']
            )
            
            self.token_counter = Counter(
                'ai_tokens_used_total',
                'Total AI tokens used',
                ['provider', 'model']
            )
            
            self.cost_counter = Counter(
                'ai_cost_total',
                'Total AI cost',
                ['provider', 'model']
            )
            
            self.active_operations = Gauge(
                'ai_active_operations',
                'Currently active AI operations',
                ['operation_type']
            )
            
            self.enabled = True
            logger.info("✅ Prometheus metrics collector initialized")
            
        except ImportError:
            logger.warning("Prometheus client not available, metrics disabled")
    
    def record_operation(self, metrics: OperationMetrics) -> None:
        """Record operation in Prometheus"""
        if not self.enabled:
            return
        
        status = 'success' if metrics.success else 'error'
        error_type = metrics.error_type or 'none'
        
        # Record counter
        self.request_counter.labels(
            operation=metrics.operation_name,
            provider=metrics.provider or 'unknown',
            status=status,
            error_type=error_type
        ).inc()
        
        # Record duration
        if metrics.duration is not None:
            self.duration_histogram.labels(
                operation=metrics.operation_name,
                provider=metrics.provider or 'unknown',
                operation_type=metrics.operation_type.value
            ).observe(metrics.duration)
        
        # Record tokens and cost
        if metrics.tokens_used > 0:
            self.token_counter.labels(
                provider=metrics.provider or 'unknown',
                model=metrics.model or 'unknown'
            ).inc(metrics.tokens_used)
        
        if metrics.cost > 0:
            self.cost_counter.labels(
                provider=metrics.provider or 'unknown',
                model=metrics.model or 'unknown'
            ).inc(metrics.cost)
    
    def increment_counter(self, name: str, labels: Dict[str, str]) -> None:
        """Increment counter metric"""
        if not self.enabled:
            return
        # Implementation for custom counters
        pass
    
    def observe_histogram(self, name: str, value: float, labels: Dict[str, str]) -> None:
        """Observe histogram metric"""
        if not self.enabled:
            return
        # Implementation for custom histograms
        pass

class InMemoryMetricsCollector:
    """In-memory metrics collector for development/testing"""
    
    def __init__(self, max_entries: int = 1000):
        self.max_entries = max_entries
        self.operations: deque[OperationMetrics] = deque(maxlen=max_entries)
        self.counters: Dict[str, int] = defaultdict(int)
        self.histograms: Dict[str, List[float]] = defaultdict(list)
        
    def record_operation(self, metrics: OperationMetrics) -> None:
        """Record operation in memory"""
        self.operations.append(metrics)
    
    def increment_counter(self, name: str, labels: Dict[str, str]) -> None:
        """Increment counter metric"""
        key = f"{name}:{':'.join(f'{k}={v}' for k, v in sorted(labels.items()))}"
        self.counters[key] += 1
    
    def observe_histogram(self, name: str, value: float, labels: Dict[str, str]) -> None:
        """Observe histogram metric"""
        key = f"{name}:{':'.join(f'{k}={v}' for k, v in sorted(labels.items()))}"
        self.histograms[key].append(value)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        if not self.operations:
            return {}
        
        successful_ops = [op for op in self.operations if op.success]
        failed_ops = [op for op in self.operations if not op.success]
        
        durations = [op.duration for op in self.operations if op.duration is not None]
        
        stats = {
            'total_operations': len(self.operations),
            'successful_operations': len(successful_ops),
            'failed_operations': len(failed_ops),
            'success_rate': len(successful_ops) / len(self.operations) * 100 if self.operations else 0,
            'average_duration': sum(durations) / len(durations) if durations else 0,
            'total_tokens': sum(op.tokens_used for op in self.operations),
            'total_cost': sum(op.cost for op in self.operations),
            'error_breakdown': {},
            'provider_breakdown': {},
        }
        
        # Error breakdown
        for op in failed_ops:
            error_type = op.error_type or 'unknown'
            stats['error_breakdown'][error_type] = stats['error_breakdown'].get(error_type, 0) + 1
        
        # Provider breakdown
        for op in self.operations:
            provider = op.provider or 'unknown'
            if provider not in stats['provider_breakdown']:
                stats['provider_breakdown'][provider] = {
                    'operations': 0, 'successes': 0, 'failures': 0, 'avg_duration': 0
                }
            
            stats['provider_breakdown'][provider]['operations'] += 1
            if op.success:
                stats['provider_breakdown'][provider]['successes'] += 1
            else:
                stats['provider_breakdown'][provider]['failures'] += 1
        
        return stats

class PerformanceMonitor:
    """Centralized performance monitoring system"""
    
    def __init__(self, 
                 thresholds: Optional[PerformanceThresholds] = None,
                 metrics_collector: Optional[MetricsCollector] = None):
        self.thresholds = thresholds or PerformanceThresholds()
        self.metrics_collector = metrics_collector or self._create_default_collector()
        self.active_operations: Dict[str, OperationMetrics] = {}
        self._operation_id_counter = 0
    
    def _create_default_collector(self) -> MetricsCollector:
        """Create default metrics collector"""
        # Try Prometheus first, fallback to in-memory
        prometheus_collector = PrometheusMetricsCollector()
        if prometheus_collector.enabled:
            return prometheus_collector
        else:
            return InMemoryMetricsCollector()
    
    def _generate_operation_id(self) -> str:
        """Generate unique operation ID"""
        self._operation_id_counter += 1
        return f"op_{self._operation_id_counter}_{int(time.time() * 1000)}"
    
    @asynccontextmanager
    async def monitor_operation(self, 
                               operation_name: str,
                               operation_type: OperationType = OperationType.COMPUTATION,
                               metadata: Dict[str, Any] = None):
        """Context manager for monitoring operations"""
        operation_id = self._generate_operation_id()
        
        metrics = OperationMetrics(
            operation_name=operation_name,
            operation_type=operation_type,
            start_time=time.time(),
            metadata=metadata or {}
        )
        
        self.active_operations[operation_id] = metrics
        
        try:
            # Update active operations gauge
            if hasattr(self.metrics_collector, 'active_operations'):
                self.metrics_collector.active_operations.labels(
                    operation_type=operation_type.value
                ).inc()
            
            yield metrics
            
            # Operation completed successfully
            metrics.finalize(success=True)
            
        except Exception as e:
            # Handle traditional exceptions
            logger.error(f"Exception in {operation_name}: {e}")
            metrics.finalize(success=False, error=e)
            
            # Log detailed error information
            self._log_single_exception(operation_name, e)
            
            # Re-raise the exception
            raise
            
        finally:
            # Cleanup and record metrics
            self.active_operations.pop(operation_id, None)
            
            # Update active operations gauge
            if hasattr(self.metrics_collector, 'active_operations'):
                self.metrics_collector.active_operations.labels(
                    operation_type=operation_type.value
                ).dec()
            
            # Record final metrics
            self.metrics_collector.record_operation(metrics)
            
            # Check performance thresholds
            self._check_performance_thresholds(metrics)
            
    def _log_single_exception(self, operation_name: str, e: Exception):
        """Логирование информации о связанной с исключением операции"""
        logger.error(f"Operation: {operation_name} raised an error: {str(e)}")            
    
    def _extract_primary_exception(self, exception_group) -> Exception:
        """Extract the most severe exception from an exception group"""
        if hasattr(exception_group, 'exceptions'):
            # Find the most severe exception
            exceptions = list(exception_group.exceptions)
            
            # Priority order: Critical > High > Medium > Low
            severity_order = [
                (SystemExit, KeyboardInterrupt, MemoryError),  # Critical
                (ConnectionError, TimeoutError, asyncio.TimeoutError),  # High
                (ValueError, TypeError, AttributeError),  # Medium
            ]
            
            for severity_group in severity_order:
                for exc in exceptions:
                    if isinstance(exc, severity_group):
                        return exc
            
            # Return first exception if no priority match
            return exceptions[0] if exceptions else Exception("Unknown exception group error")
        
        return exception_group
    
    def _log_exception_group(self, operation_name: str, exception_group) -> None:
        """Log detailed information about exception group"""
        logger.error(f"🚨 Exception group in operation '{operation_name}':")
        
        if hasattr(exception_group, 'exceptions'):
            for i, exc in enumerate(exception_group.exceptions, 1):
                logger.error(f"  Exception {i}: {type(exc).__name__}: {exc}")
                logger.debug(f"  Traceback {i}: {''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))}")
        else:
            logger.error(f"  Single exception: {type(exception_group).__name__}: {exception_group}")
    
    def _log_single_exception(self, operation_name: str, exception: Exception) -> None:
        """Log detailed information about single exception"""
        logger.error(f"🚨 Exception in operation '{operation_name}': {type(exception).__name__}: {exception}")
        logger.debug(f"Traceback: {''.join(traceback.format_exception(type(exception), exception, exception.__traceback__))}")
    
    def _check_performance_thresholds(self, metrics: OperationMetrics) -> None:
        """Check and alert on performance thresholds"""
        if metrics.duration is None:
            return
        
        threshold = self.thresholds.get_threshold(metrics.operation_type)
        
        if metrics.duration > self.thresholds.error_threshold:
            logger.error(
                f"🐌 CRITICAL: Operation '{metrics.operation_name}' took {metrics.duration:.2f}s "
                f"(threshold: {self.thresholds.error_threshold}s)"
            )
        elif metrics.duration > threshold:
            logger.warning(
                f"⚠️  SLOW: Operation '{metrics.operation_name}' took {metrics.duration:.2f}s "
                f"(threshold: {threshold}s)"
            )
        elif metrics.duration > threshold * 0.8:
            logger.info(
                f"📊 Performance note: Operation '{metrics.operation_name}' took {metrics.duration:.2f}s "
                f"(80% of threshold: {threshold}s)"
            )

# Global performance monitor instance
_global_monitor: Optional[PerformanceMonitor] = None

def get_performance_monitor() -> PerformanceMonitor:
    """Get or create global performance monitor"""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = PerformanceMonitor()
    return _global_monitor

def set_performance_monitor(monitor: PerformanceMonitor) -> None:
    """Set custom performance monitor"""
    global _global_monitor
    _global_monitor = monitor

# Future-proof decorator implementations

def monitor_performance(
    operation_name: str,
    operation_type: OperationType = OperationType.COMPUTATION,
    **metadata
) -> Callable[[F], F]:
    """
    Enhanced performance monitoring decorator with Python 3.13+ exception group support
    
    Features:
    - Full compatibility with Python 3.13 exception groups
    - Detailed metrics collection and alerting
    - Configurable performance thresholds
    - Provider-specific monitoring for AI operations
    - Automatic error categorization and severity assessment
    
    Args:
        operation_name: Name of the operation for monitoring
        operation_type: Type of operation for specialized handling
        **metadata: Additional metadata to include in metrics
    
    Returns:
        Decorated function with comprehensive monitoring
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            monitor = get_performance_monitor()
            
            # Extract provider and model information for AI operations
            provider = kwargs.get('provider') or metadata.get('provider', 'unknown')
            model = kwargs.get('model') or metadata.get('model', 'unknown')
            
            operation_metadata = {
                'provider': provider,
                'model': model,
                'function_name': func.__name__,
                'module_name': func.__module__,
                **metadata
            }
            
            async with monitor.monitor_operation(
                operation_name=operation_name,
                operation_type=operation_type,
                **operation_metadata
            ) as metrics:
                # Update metrics with AI-specific information
                metrics.provider = provider
                metrics.model = model
                
                # Execute the function
                result = await func(*args, **kwargs)
                
                # Extract additional metrics from result if available
                if hasattr(result, 'tokens_used'):
                    metrics.tokens_used = getattr(result.tokens_used, 'total_tokens', 0)
                if hasattr(result, 'cost'):
                    metrics.cost = result.cost
                
                return result
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # For synchronous functions, we'll use a simpler approach
            start_time = time.time()
            operation_success = False
            error_info = None
            
            try:
                result = func(*args, **kwargs)
                operation_success = True
                return result
                
            except Exception as e:
                error_info = e
                raise
                
            finally:
                duration = time.time() - start_time
                
                # Create metrics for synchronous operation
                monitor = get_performance_monitor()
                sync_metrics = OperationMetrics(
                    operation_name=operation_name,
                    operation_type=operation_type,
                    start_time=start_time,
                    provider=kwargs.get('provider') or metadata.get('provider'),
                    model=kwargs.get('model') or metadata.get('model'),
                    metadata={
                        'function_name': func.__name__,
                        'module_name': func.__module__,
                        **metadata
                    }
                )
                sync_metrics.finalize(success=operation_success, error=error_info)
                
                # Record metrics
                monitor.metrics_collector.record_operation(sync_metrics)
                monitor._check_performance_thresholds(sync_metrics)
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

def monitor_ai_operation(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    operation_name: Optional[str] = None
) -> Callable[[AsyncF], AsyncF]:
    """
    Specialized decorator for AI operations with enhanced monitoring
    
    Args:
        provider: AI provider name
        model: AI model name
        operation_name: Custom operation name (defaults to function name)
    
    Returns:
        Decorated function with AI-specific monitoring
    """
    def decorator(func: AsyncF) -> AsyncF:
        actual_operation_name = operation_name or f"ai_{func.__name__}"
        
        return monitor_performance(
            operation_name=actual_operation_name,
            operation_type=OperationType.AI_REQUEST,
            provider=provider,
            model=model,
            ai_operation=True
        )(func)
    
    return decorator

def monitor_cache_operation(cache_type: str = "default") -> Callable[[F], F]:
    """Specialized decorator for cache operations"""
    def decorator(func: F) -> F:
        return monitor_performance(
            operation_name=f"cache_{func.__name__}",
            operation_type=OperationType.CACHE_OPERATION,
            cache_type=cache_type
        )(func)
    
    return decorator

def monitor_database_operation(table: Optional[str] = None) -> Callable[[F], F]:
    """Specialized decorator for database operations"""
    def decorator(func: F) -> F:
        return monitor_performance(
            operation_name=f"db_{func.__name__}",
            operation_type=OperationType.DATABASE_OPERATION,
            table=table
        )(func)
    
    return decorator

# Utility functions for metrics analysis

def get_performance_stats() -> Dict[str, Any]:
    """Get comprehensive performance statistics"""
    monitor = get_performance_monitor()
    if isinstance(monitor.metrics_collector, InMemoryMetricsCollector):
        return monitor.metrics_collector.get_stats()
    else:
        return {"message": "Statistics available in Prometheus metrics"}

def reset_performance_stats() -> None:
    """Reset performance statistics (for in-memory collector only)"""
    monitor = get_performance_monitor()
    if isinstance(monitor.metrics_collector, InMemoryMetricsCollector):
        monitor.metrics_collector.operations.clear()
        monitor.metrics_collector.counters.clear()
        monitor.metrics_collector.histograms.clear()

# Example usage demonstrating the improved decorator

if __name__ == "__main__":
    import asyncio
    
    # Configure custom thresholds
    custom_thresholds = PerformanceThresholds(
        warning_threshold=2.0,
        error_threshold=10.0,
        operation_thresholds={
            OperationType.AI_REQUEST: 5.0,
            OperationType.CACHE_OPERATION: 0.05,
        }
    )
    
    # Set up custom monitor
    custom_monitor = PerformanceMonitor(thresholds=custom_thresholds)
    set_performance_monitor(custom_monitor)
    
    @monitor_ai_operation(provider="openai", model="gpt-4")
    async def example_ai_request(prompt: str) -> str:
        """Example AI request function"""
        await asyncio.sleep(1)  # Simulate AI processing
        return f"Response to: {prompt}"
    
    @monitor_cache_operation(cache_type="redis")
    async def example_cache_get(key: str) -> Optional[str]:
        """Example cache operation"""
        await asyncio.sleep(0.01)  # Simulate cache lookup
        return f"cached_value_for_{key}"
    
    @monitor_performance("custom_computation", OperationType.COMPUTATION)
    async def example_computation(data: List[int]) -> int:
        """Example computation function"""
        await asyncio.sleep(0.5)  # Simulate computation
        return sum(data)
    
    async def main():
        """Test the monitoring system"""
        print("🔍 Testing performance monitoring system...")
        
        # Test AI operation
        result1 = await example_ai_request("What is machine learning?")
        print(f"AI Result: {result1}")
        
        # Test cache operation
        result2 = await example_cache_get("test_key")
        print(f"Cache Result: {result2}")
        
        # Test computation
        result3 = await example_computation([1, 2, 3, 4, 5])
        print(f"Computation Result: {result3}")
        
        # Test exception handling
        try:
            @monitor_performance("error_test", OperationType.COMPUTATION)
            async def error_function():
                raise ValueError("Test error for monitoring")
            
            await error_function()
        except ValueError:
            print("✅ Exception properly caught and monitored")
        
        # Display statistics
        stats = get_performance_stats()
        print("\n📊 Performance Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
    
    # Run the test
    asyncio.run(main())