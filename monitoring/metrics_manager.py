# monitoring/metrics_manager.py
"""
Prometheus metrics manager with proper error handling and thread safety
"""
import threading
from typing import Dict, Optional
from prometheus_client import Counter, CollectorRegistry, REGISTRY
from prometheus_client.exposition import make_wsgi_app

class MetricsManager:
    """Thread-safe metrics manager to prevent duplicate registration"""
    
    def __init__(self, use_custom_registry: bool = True):
        self._lock = threading.Lock()
        self._metrics: Dict[str, Counter] = {}
        self._registry = CollectorRegistry() if use_custom_registry else REGISTRY
    
    def get_counter(self, name: str, description: str, 
                   labelnames: Optional[list] = None) -> Counter:
        """
        Get or create a Counter metric with duplicate protection
        
        Args:
            name: Metric name
            description: Metric description  
            labelnames: Label names for the metric
            
        Returns:
            Counter instance
        """
        with self._lock:
            if name in self._metrics:
                return self._metrics[name]
            
            # Check if metric already exists in registry
            if self._is_metric_registered(name):
                # Remove existing metric to avoid collision
                self._unregister_metric(name)
            
            try:
                counter = Counter(
                    name, 
                    description, 
                    labelnames or [],
                    registry=self._registry
                )
                self._metrics[name] = counter
                return counter
            except ValueError as e:
                if "Duplicated timeseries" in str(e):
                    # Fallback: try to get existing metric
                    return self._get_existing_metric(name)
                raise
    
    def _is_metric_registered(self, name: str) -> bool:
        """Check if metric is already registered"""
        try:
            # For custom registry
            if hasattr(self._registry, '_names_to_collectors'):
                return name in self._registry._names_to_collectors
            
            # For default registry - check collectors
            for collector in list(self._registry._collector_to_names.keys()):
                if hasattr(collector, '_name') and collector._name == name:
                    return True
            return False
        except (AttributeError, KeyError):
            return False
    
    def _unregister_metric(self, name: str) -> None:
        """Safely unregister existing metric"""
        try:
            collectors_to_remove = []
            for collector in list(self._registry._collector_to_names.keys()):
                if hasattr(collector, '_name') and collector._name == name:
                    collectors_to_remove.append(collector)
            
            for collector in collectors_to_remove:
                self._registry.unregister(collector)
                
        except (AttributeError, KeyError, ValueError):
            pass  # Metric wasn't registered or already removed
    
    def _get_existing_metric(self, name: str) -> Counter:
        """Attempt to retrieve existing metric as fallback"""
        for collector in self._registry._collector_to_names.keys():
            if hasattr(collector, '_name') and collector._name == name:
                return collector
        raise ValueError(f"Could not retrieve existing metric: {name}")
    
    def get_wsgi_app(self):
        """Get WSGI app for metrics exposition"""
        return make_wsgi_app(self._registry)
    
    def clear_metrics(self) -> None:
        """Clear all registered metrics (useful for testing)"""
        with self._lock:
            for collector in list(self._registry._collector_to_names.keys()):
                try:
                    self._registry.unregister(collector)
                except (KeyError, ValueError):
                    pass
            self._metrics.clear()

# Global instance (singleton pattern)
_metrics_manager = None
_manager_lock = threading.Lock()

def get_metrics_manager() -> MetricsManager:
    """Get global metrics manager instance"""
    global _metrics_manager
    with _manager_lock:
        if _metrics_manager is None:
            _metrics_manager = MetricsManager(use_custom_registry=True)
        return _metrics_manager