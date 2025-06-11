# monitoring/metrics.py - Comprehensive monitoring with thread-safe metrics
from __future__ import annotations

import os
import sys
import time
import asyncio
import logging
import threading
import platform
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from contextlib import contextmanager

# Thread-safe metrics management
_metrics_lock = threading.Lock()
_metrics_registry = None

# Prometheus metrics (optional)
try:
    from prometheus_client import (
        Counter, Histogram, Gauge, CollectorRegistry, 
        generate_latest, start_http_server, REGISTRY
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

logger = logging.getLogger(__name__)

def metric_exists(name: str) -> bool:
    return name in REGISTRY._names_to_collectors

def get_or_create_counter(name, description, labelnames=None):
    if metric_exists(name):
        return REGISTRY._names_to_collectors[name]
    return Counter(name, description, labelnames or [])

def get_or_create_histogram(name, description, labelnames=None):
    if metric_exists(name):
        return REGISTRY._names_to_collectors[name]
    return Histogram(name, description, labelnames or [])

def get_or_create_gauge(name, description, labelnames=None):
    if metric_exists(name):
        return REGISTRY._names_to_collectors[name]
    return Gauge(name, description, labelnames or [])


@dataclass
class MetricValue:
    """Container for metric values with metadata"""
    value: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    labels: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

class ThreadSafeMetricsCollector:
    """Thread-safe metrics collection and analysis"""
    
    def __init__(self, use_custom_registry: bool = True):
        self._lock = threading.Lock()
        self._registry = CollectorRegistry() if use_custom_registry else None
        self.custom_metrics: Dict[str, List[MetricValue]] = {}
        self._prometheus_metrics: Dict[str, Any] = {}
        self.python_version = platform.python_version()
        
        if PROMETHEUS_AVAILABLE:
            self._setup_prometheus_metrics()
    
    def _safe_register_metric(self, metric_class, name: str, doc: str, 
                            labelnames: Optional[List[str]] = None, **kwargs):
        """Safely register a Prometheus metric avoiding duplicates"""
        with self._lock:
            if name in self._prometheus_metrics:
                return self._prometheus_metrics[name]
            
            try:
                metric = metric_class(
                    name, 
                    doc, 
                    labelnames or [],
                    registry=self._registry,
                    **kwargs
                )
                self._prometheus_metrics[name] = metric
                return metric
            except ValueError as e:
                if "Duplicated timeseries" in str(e):
                    # Try to get existing metric
                    logger.warning(f"Metric {name} already exists, attempting to retrieve")
                    return self._get_existing_metric(name)
                raise
    
    def _get_existing_metric(self, name: str):
        """Get existing metric from registry"""
        if self._registry:
            for collector in list(self._registry._collector_to_names.keys()):
                if hasattr(collector, '_name') and collector._name == name:
                    return collector
        raise ValueError(f"Could not retrieve existing metric: {name}")
    
    def _setup_prometheus_metrics(self):
        """Setup Prometheus metrics with duplicate protection"""
        if not PROMETHEUS_AVAILABLE:
            logger.warning("Prometheus client not available")
            return

        # AI-related metrics
        self.ai_requests = self._safe_register_metric(
            Counter, 'ai_requests_total', 'Total AI provider requests',
            ['provider', 'model', 'status']
        )

        self.ai_latency = self._safe_register_metric(
            Histogram, 'ai_request_latency_seconds', 'AI request latency',
            ['provider', 'model']
        )

        self.ai_tokens = self._safe_register_metric(
            Counter, 'ai_tokens_used_total', 'Total AI tokens consumed',
            ['provider', 'model']
        )

        self.ai_cost = self._safe_register_metric(
            Counter, 'ai_cost_total_usd', 'Total AI cost in USD',
            ['provider', 'model']
        )

        # Request/endpoint metrics
        self.request_count = self._safe_register_metric(
            Counter, 'ai_aggregator_requests_total', 'Total number of requests',
            ['method', 'endpoint', 'status']
        )

        self.request_duration = self._safe_register_metric(
            Histogram, 'ai_aggregator_request_duration_seconds', 'Request duration in seconds',
            ['method', 'endpoint']
        )

        # Cache metrics
        self.cache_operations = self._safe_register_metric(
            Counter, 'cache_operations_total', 'Cache operations',
            ['operation', 'cache_type', 'result']
        )

        self.cache_hit_ratio = self._safe_register_metric(
            Gauge, 'cache_hit_ratio', 'Cache hit ratio', ['cache_type']
        )

        # System metrics
        self.active_connections = self._safe_register_metric(
            Gauge, 'active_connections_current', 'Current active connections'
        )

        self.memory_usage = self._safe_register_metric(
            Gauge, 'memory_usage_bytes', 'Memory usage in bytes', ['type']
        )

        # Business metrics
        self.products_ingested = self._safe_register_metric(
            Counter, 'products_ingested_total', 'Total products ingested',
            ['category', 'provider']
        )

        self.data_quality_score = self._safe_register_metric(
            Histogram, 'data_quality_score', 'Data quality score distribution',
            ['category']
        )

    @contextmanager
    def time_operation(self, operation_name: str, labels: Optional[Dict[str, str]] = None):
        """Context manager for timing operations"""
        start_time = time.time()
        labels = labels or {}
        
        try:
            yield
            duration = time.time() - start_time
            
            # Record to custom metrics
            self.record_custom_metric(
                f"{operation_name}_duration",
                duration,
                labels
            )
            
            # Record to Prometheus if available
            if PROMETHEUS_AVAILABLE and hasattr(self, 'request_duration'):
                try:
                    self.request_duration.labels(**labels).observe(duration)
                except Exception as e:
                    logger.warning(f"Failed to record Prometheus metric: {e}")
                
        except Exception as e:
            duration = time.time() - start_time
            labels.update({"status": "error", "error_type": type(e).__name__})
            
            self.record_custom_metric(
                f"{operation_name}_duration",
                duration,
                labels
            )
            raise
    
    def record_custom_metric(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Record a custom metric value"""
        with self._lock:
            if name not in self.custom_metrics:
                self.custom_metrics[name] = []
            
            metric_value = MetricValue(
                value=value,
                labels=labels or {},
                timestamp=datetime.utcnow()
            )
            
            self.custom_metrics[name].append(metric_value)
            
            # Keep only last 1000 values per metric
            if len(self.custom_metrics[name]) > 1000:
                self.custom_metrics[name] = self.custom_metrics[name][-1000:]
    
    def record_ai_request(
        self, 
        provider: str, 
        model: str, 
        tokens: int, 
        cost: float, 
        latency: float,
        status: str = "success"
    ):
        """Record AI request metrics"""
        labels = {"provider": provider, "model": model or "unknown"}
        
        if PROMETHEUS_AVAILABLE:
            try:
                self.ai_requests.labels(**labels, status=status).inc()
                self.ai_tokens.labels(**labels).inc(tokens)
                self.ai_cost.labels(**labels).inc(cost)
                self.ai_latency.labels(**labels).observe(latency)
            except Exception as e:
                logger.warning(f"Failed to record Prometheus AI metrics: {e}")
        
        # Custom metrics
        self.record_custom_metric("ai_request_tokens", tokens, labels)
        self.record_custom_metric("ai_request_cost", cost, labels)
        self.record_custom_metric("ai_request_latency", latency, labels)
    
    def record_cache_operation(self, operation: str, cache_type: str, hit: bool):
        """Record cache operation metrics"""
        result = "hit" if hit else "miss"
        labels = {"operation": operation, "cache_type": cache_type, "result": result}
        
        if PROMETHEUS_AVAILABLE and hasattr(self, 'cache_operations'):
            try:
                self.cache_operations.labels(**labels).inc()
            except Exception as e:
                logger.warning(f"Failed to record cache metrics: {e}")
        
        self.record_custom_metric("cache_operation", 1, labels)
    
    def update_cache_hit_ratio(self, cache_type: str, hit_ratio: float):
        """Update cache hit ratio gauge"""
        if PROMETHEUS_AVAILABLE and hasattr(self, 'cache_hit_ratio'):
            try:
                self.cache_hit_ratio.labels(cache_type=cache_type).set(hit_ratio)
            except Exception as e:
                logger.warning(f"Failed to update cache hit ratio: {e}")
        
        self.record_custom_metric("cache_hit_ratio", hit_ratio, {"cache_type": cache_type})
    
    def get_metrics_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get metrics summary for the specified time period"""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        summary = {}
        
        with self._lock:
            for metric_name, values in self.custom_metrics.items():
                recent_values = [
                    v for v in values 
                    if v.timestamp >= cutoff_time
                ]
                
                if recent_values:
                    summary[metric_name] = {
                        "count": len(recent_values),
                        "sum": sum(v.value for v in recent_values),
                        "avg": sum(v.value for v in recent_values) / len(recent_values),
                        "min": min(v.value for v in recent_values),
                        "max": max(v.value for v in recent_values),
                        "latest": recent_values[-1].value,
                        "timestamp": recent_values[-1].timestamp.isoformat()
                    }
        
        return summary
    
    def export_prometheus_metrics(self) -> str:
        """Export metrics in Prometheus format"""
        if PROMETHEUS_AVAILABLE and self._registry:
            return generate_latest(self._registry).decode('utf-8')
        return "# Prometheus client not available\n"
    
    def clear_metrics(self):
        """Clear all metrics (useful for testing)"""
        with self._lock:
            self.custom_metrics.clear()
            if self._registry:
                # Clear Prometheus registry
                collectors = list(self._registry._collector_to_names.keys())
                for collector in collectors:
                    try:
                        self._registry.unregister(collector)
                    except (KeyError, ValueError):
                        pass
                self._prometheus_metrics.clear()

# Global metrics collector factory
def get_metrics_collector() -> ThreadSafeMetricsCollector:
    """Get global metrics collector instance"""
    global _metrics_registry
    with _metrics_lock:
        if _metrics_registry is None:
            _metrics_registry = ThreadSafeMetricsCollector(use_custom_registry=True)
        return _metrics_registry

# Global metrics collector instance
metrics_collector = get_metrics_collector()

class PerformanceMonitor:
    """Real-time performance monitoring and alerting"""
    
    def __init__(self, metrics_collector: ThreadSafeMetricsCollector):
        self.metrics = metrics_collector
        self.alerts: List[Dict[str, Any]] = []
        
        # Import settings here to avoid circular imports
        try:
            from config.settings import settings
            self.thresholds = {
                "high_latency": settings.monitoring.threshold_high_latency,
                "high_error_rate": settings.monitoring.threshold_high_error_rate,
                "low_cache_hit_ratio": settings.monitoring.threshold_low_cache_hit_ratio,
                "high_ai_cost_hourly": settings.monitoring.threshold_high_ai_cost_hourly,
            }
        except ImportError:
            logger.warning("Could not import settings, using default thresholds")
            self.thresholds = {
                "high_latency": 5.0,
                "high_error_rate": 0.1,
                "low_cache_hit_ratio": 0.7,
                "high_ai_cost_hourly": 50.0,
            }
    
    def check_thresholds(self) -> List[Dict[str, Any]]:
        """Check if any metrics exceed thresholds"""
        alerts = []
        summary = self.metrics.get_metrics_summary(hours=1)
        
        # Check AI request latency
        if "ai_request_latency" in summary:
            avg_latency = summary["ai_request_latency"]["avg"]
            if avg_latency > self.thresholds["high_latency"]:
                alerts.append({
                    "type": "high_latency",
                    "message": f"High AI latency: {avg_latency:.2f}s",
                    "value": avg_latency,
                    "threshold": self.thresholds["high_latency"],
                    "severity": "warning"
                })
        
        # Check AI costs
        if "ai_request_cost" in summary:
            hourly_cost = summary["ai_request_cost"]["sum"]
            if hourly_cost > self.thresholds["high_ai_cost_hourly"]:
                alerts.append({
                    "type": "high_ai_cost",
                    "message": f"High AI cost: ${hourly_cost:.2f}/hour",
                    "value": hourly_cost,
                    "threshold": self.thresholds["high_ai_cost_hourly"],
                    "severity": "critical"
                })
        
        # Check cache hit ratio
        if "cache_hit_ratio" in summary:
            hit_ratio = summary["cache_hit_ratio"]["latest"]
            if hit_ratio < self.thresholds["low_cache_hit_ratio"]:
                alerts.append({
                    "type": "low_cache_hit_ratio",
                    "message": f"Low cache hit ratio: {hit_ratio:.1%}",
                    "value": hit_ratio,
                    "threshold": self.thresholds["low_cache_hit_ratio"],
                    "severity": "warning"
                })
        
        return alerts
    
    async def start_monitoring(self, interval: int = 60):
        """Start continuous monitoring loop"""
        logger.info(f"Starting performance monitoring with {interval}s interval")
        
        while True:
            try:
                alerts = self.check_thresholds()
                for alert in alerts:
                    logger.warning(f"Performance alert: {alert['message']}")
                    # TODO: Send to alerting system (Slack, email, etc.)
                
                await asyncio.sleep(interval)
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(interval)

# Global performance monitor
performance_monitor = PerformanceMonitor(metrics_collector)

def setup_metrics_server(port: int = 9090):
    """Setup Prometheus metrics HTTP server"""
    if PROMETHEUS_AVAILABLE:
        try:
            # Import settings here to avoid circular imports
            from config.settings import settings
            if settings.monitoring.enable_metrics:
                start_http_server(port, registry=metrics_collector._registry)
                logger.info(f"Metrics server started on port {port}")
        except ImportError:
            logger.warning("Could not import settings for metrics server")
        except Exception as e:
            logger.error(f"Failed to start metrics server: {e}")

# Convenience function for backwards compatibility
def get_metrics():
    """Get metrics in Prometheus format"""
    return metrics_collector.export_prometheus_metrics()

# Export public API
__all__ = [
    'metrics_collector',
    'performance_monitor', 
    'setup_metrics_server',
    'get_metrics',
    'get_metrics_collector',
    'ThreadSafeMetricsCollector',
    'PerformanceMonitor',
    'MetricValue'
]