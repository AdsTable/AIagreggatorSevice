# monitoring/metrics.py - Comprehensive monitoring with custom metrics
from __future__ import annotations

import time
import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from contextlib import contextmanager

try:
    from prometheus_client import (
        Counter, Histogram, Gauge, Info, Enum,
        CollectorRegistry, generate_latest,
        start_http_server
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

from config.settings import settings

logger = logging.getLogger(__name__)

@dataclass
class MetricValue:
    """Container for metric values with metadata"""
    value: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    labels: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

class MetricsCollector:
    """Advanced metrics collection and analysis"""
    
    def __init__(self, registry: Optional[CollectorRegistry] = None):
        self.registry = registry or CollectorRegistry()
        self.custom_metrics: Dict[str, List[MetricValue]] = {}
        self._setup_prometheus_metrics()
        self.python_version = platform.python_version()  # Get current Python version dynamically
        
    def _setup_prometheus_metrics(self):
        """Setup Prometheus metrics if available"""
        if not PROMETHEUS_AVAILABLE:
            logger.warning("Prometheus client not available")
            return
            
        # Application metrics
        self.request_count = Counter(
            'ai_aggregator_requests_total',
            'Total number of requests',
            ['method', 'endpoint', 'status'],
            registry=self.registry
        )
        
        self.request_duration = Histogram(
            'ai_aggregator_request_duration_seconds',
            'Request duration in seconds',
            ['method', 'endpoint'],
            registry=self.registry
        )
        
        # AI-specific metrics
        self.ai_requests = Counter(
            'ai_requests_total',
            'Total AI provider requests',
            ['provider', 'model', 'status'],
            registry=self.registry
        )
        
        self.ai_tokens = Counter(
            'ai_tokens_used_total',
            'Total AI tokens consumed',
            ['provider', 'model'],
            registry=self.registry
        )
        
        self.ai_cost = Counter(
            'ai_cost_total_usd',
            'Total AI cost in USD',
            ['provider', 'model'],
            registry=self.registry
        )
        
        self.ai_latency = Histogram(
            'ai_request_latency_seconds',
            'AI request latency',
            ['provider', 'model'],
            registry=self.registry
        )
        
        # Cache metrics
        self.cache_operations = Counter(
            'cache_operations_total',
            'Cache operations',
            ['operation', 'cache_type', 'result'],
            registry=self.registry
        )
        
        self.cache_hit_ratio = Gauge(
            'cache_hit_ratio',
            'Cache hit ratio',
            ['cache_type'],
            registry=self.registry
        )
        
        # System metrics
        self.active_connections = Gauge(
            'active_connections_current',
            'Current active connections',
            registry=self.registry
        )
        
        self.memory_usage = Gauge(
            'memory_usage_bytes',
            'Memory usage in bytes',
            ['type'],
            registry=self.registry
        )
        
        # Business metrics
        self.products_ingested = Counter(
            'products_ingested_total',
            'Total products ingested',
            ['category', 'provider'],
            registry=self.registry
        )
        
        self.data_quality_score = Histogram(
            'data_quality_score',
            'Data quality score distribution',
            ['category'],
            registry=self.registry
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
                self.request_duration.labels(**labels).observe(duration)
                
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
            self.ai_requests.labels(**labels, status=status).inc()
            self.ai_tokens.labels(**labels).inc(tokens)
            self.ai_cost.labels(**labels).inc(cost)
            self.ai_latency.labels(**labels).observe(latency)
        
        # Custom metrics
        self.record_custom_metric("ai_request_tokens", tokens, labels)
        self.record_custom_metric("ai_request_cost", cost, labels)
        self.record_custom_metric("ai_request_latency", latency, labels)
    
    def record_cache_operation(self, operation: str, cache_type: str, hit: bool):
        """Record cache operation metrics"""
        result = "hit" if hit else "miss"
        labels = {"operation": operation, "cache_type": cache_type, "result": result}
        
        if PROMETHEUS_AVAILABLE:
            self.cache_operations.labels(**labels).inc()
        
        self.record_custom_metric("cache_operation", 1, labels)
    
    def update_cache_hit_ratio(self, cache_type: str, hit_ratio: float):
        """Update cache hit ratio gauge"""
        if PROMETHEUS_AVAILABLE:
            self.cache_hit_ratio.labels(cache_type=cache_type).set(hit_ratio)
        
        self.record_custom_metric("cache_hit_ratio", hit_ratio, {"cache_type": cache_type})
    
    def get_metrics_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get metrics summary for the specified time period"""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        summary = {}
        
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
        if PROMETHEUS_AVAILABLE:
            return generate_latest(self.registry).decode('utf-8')
        return "# Prometheus client not available\n"

# Global metrics collector instance
metrics_collector = MetricsCollector()

class PerformanceMonitor:
    """Real-time performance monitoring and alerting"""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics = metrics_collector
        self.alerts: List[Dict[str, Any]] = []
        self.thresholds = {
            "high_latency": 5.0,  # seconds
            "high_error_rate": 0.1,  # 10%
            "low_cache_hit_ratio": 0.7,  # 70%
            "high_ai_cost_hourly": 50.0,  # USD
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
    if PROMETHEUS_AVAILABLE and settings.monitoring.enable_metrics:
        try:
            start_http_server(port, registry=metrics_collector.registry)
            logger.info(f"Metrics server started on port {port}")
        except Exception as e:
            logger.error(f"Failed to start metrics server: {e}")