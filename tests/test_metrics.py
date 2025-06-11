"""
Unit tests for metrics manager
"""
import pytest
from metrics_manager import MetricsManager

def test_duplicate_counter_prevention():
    """Test that duplicate counters are handled properly"""
    manager = MetricsManager(use_custom_registry=True)
    
    # Create same counter twice
    counter1 = manager.get_counter('test_counter', 'Test counter', ['label'])
    counter2 = manager.get_counter('test_counter', 'Test counter', ['label'])
    
    # Should return same instance
    assert counter1 is counter2

def test_metrics_isolation():
    """Test that different managers don't interfere"""
    manager1 = MetricsManager(use_custom_registry=True)
    manager2 = MetricsManager(use_custom_registry=True)
    
    counter1 = manager1.get_counter('test_counter', 'Test counter 1')
    counter2 = manager2.get_counter('test_counter', 'Test counter 2')
    
    # Should be different instances in different registries
    assert counter1 is not counter2

def test_thread_safety():
    """Test thread safety of metrics manager"""
    import threading
    import concurrent.futures
    
    manager = MetricsManager(use_custom_registry=True)
    results = []
    
    def create_counter(i):
        return manager.get_counter(f'counter_{i}', f'Counter {i}')
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(create_counter, i) for i in range(100)]
        results = [f.result() for f in futures]
    
    # All counters should be created successfully
    assert len(results) == 100
    assert all(r is not None for r in results)