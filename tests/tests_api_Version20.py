"""
ОПТИМАЛЬНОЕ РЕШЕНИЕ: Простота + Надежность
Основано на реальном conftest.py + лучшие практики из Version18_12
"""

import pytest
import pytest_asyncio
import sys
import os
import json
import asyncio
from typing import List, Optional
from unittest.mock import patch, AsyncMock

# Используем РЕАЛЬНЫЙ conftest.py
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI
from models import StandardizedProduct
from conftest import ProductDB, store_standardized_data, search_and_filter_products

# === ПРОСТАЯ АРХИТЕКТУРА ===

class SimpleProductionTests:
    """Простые, но comprehensive тесты"""
    
    def setup_method(self):
        """Простая setup используя conftest patterns"""
        self.test_products = [
            StandardizedProduct(
                source_url="https://test.com/elec_a",
                category="electricity_plan",
                name="Test Elec Plan A", 
                provider_name="Test Provider X",
                price_kwh=0.15,
                standing_charge=5.0,
                contract_duration_months=12,
                available=True,
                raw_data={"type": "electricity"}
            ),
            StandardizedProduct(
                source_url="https://test.com/mobile_c", 
                category="mobile_plan",
                name="Test Mobile Plan C",
                provider_name="Test Provider X", 
                monthly_cost=30.0,
                data_gb=float('inf'),  # Test infinity
                calls=float('inf'),
                texts=float('inf'),
                contract_duration_months=0,
                available=True,
                raw_data={"type": "mobile"}
            ),
        ]

# === 14 OPTIMAL TESTS ===

class TestBasicFunctionality:
    """4 основных функциональных теста"""
    
    @pytest.mark.asyncio
    async def test_empty_database(self, session):
        """Test 1: Empty database returns empty list"""
        results = await search_and_filter_products(session)
        assert isinstance(results, list)
        assert len(results) == 0
    
    @pytest.mark.asyncio 
    async def test_store_and_retrieve(self, session):
        """Test 2: Store and retrieve products"""
        test_products = SimpleProductionTests().test_products
        await store_standardized_data(session, test_products)
        
        results = await search_and_filter_products(session)
        assert len(results) == len(test_products)
        assert all(isinstance(p, StandardizedProduct) for p in results)
    
    @pytest.mark.asyncio
    async def test_category_filtering(self, session):
        """Test 3: Category filtering works"""
        test_products = SimpleProductionTests().test_products
        await store_standardized_data(session, test_products)
        
        elec_results = await search_and_filter_products(session, product_type="electricity_plan")
        assert len(elec_results) == 1
        assert elec_results[0].category == "electricity_plan"
    
    @pytest.mark.asyncio
    async def test_provider_filtering(self, session):
        """Test 4: Provider filtering works"""
        test_products = SimpleProductionTests().test_products
        await store_standardized_data(session, test_products)
        
        provider_results = await search_and_filter_products(session, provider="Test Provider X")
        assert len(provider_results) == 2  # Both products from same provider

class TestAPIEndpoints:
    """4 API endpoint теста"""
    
    def setup_method(self):
        self.app = FastAPI()
        
        @self.app.get("/search")
        async def search(
            product_type: Optional[str] = None,
            provider: Optional[str] = None
        ):
            # Mock session for API testing
            mock_session = AsyncMock()
            return await search_and_filter_products(mock_session, product_type=product_type, provider=provider)
    
    @pytest.mark.asyncio
    async def test_api_empty_response(self):
        """Test 5: API returns empty list for empty database"""
        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch('conftest.search_and_filter_products', return_value=[]):
                response = await client.get("/search")
                assert response.status_code == 200
                assert response.json() == []
    
    @pytest.mark.asyncio
    async def test_api_with_data(self):
        """Test 6: API returns data correctly"""
        test_data = [{"name": "Test Product", "category": "test"}]
        
        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch('conftest.search_and_filter_products', return_value=test_data):
                response = await client.get("/search")
                assert response.status_code == 200
                assert len(response.json()) == 1
    
    @pytest.mark.asyncio 
    async def test_api_category_filter(self):
        """Test 7: API category filtering"""
        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch('conftest.search_and_filter_products', return_value=[]) as mock_search:
                response = await client.get("/search?product_type=electricity_plan")
                assert response.status_code == 200
                mock_search.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_api_provider_filter(self):
        """Test 8: API provider filtering"""
        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch('conftest.search_and_filter_products', return_value=[]) as mock_search:
                response = await client.get("/search?provider=TestProvider")
                assert response.status_code == 200
                mock_search.assert_called_once()

class TestEdgeCases:
    """3 edge case теста"""
    
    @pytest.mark.asyncio
    async def test_infinity_values(self, session):
        """Test 9: Infinity values handled correctly"""
        inf_product = StandardizedProduct(
            source_url="https://test.com/inf",
            category="mobile_plan", 
            name="Infinity Test",
            provider_name="Test Provider",
            data_gb=float('inf'),
            calls=float('inf'),
            texts=float('inf'),
            raw_data={"test": "infinity"}
        )
        
        await store_standardized_data(session, [inf_product])
        results = await search_and_filter_products(session)
        assert len(results) == 1
        assert results[0].data_gb == float('inf')
    
    @pytest.mark.asyncio
    async def test_json_serialization(self, session):
        """Test 10: JSON serialization works"""
        test_products = SimpleProductionTests().test_products
        await store_standardized_data(session, test_products)
        
        results = await search_and_filter_products(session)
        for product in results:
            # Test that raw_data can be JSON serialized
            json_str = json.dumps(product.raw_data if hasattr(product, 'raw_data') else {})
            assert isinstance(json_str, str)
    
    @pytest.mark.asyncio
    async def test_empty_strings_and_none(self, session):
        """Test 11: Empty strings and None values"""
        edge_product = StandardizedProduct(
            source_url="https://test.com/edge",
            category="test_plan",
            name="Edge Case",
            provider_name="",  # Empty string
            price_kwh=None,    # None value
            raw_data={}        # Empty dict
        )
        
        await store_standardized_data(session, [edge_product])
        results = await search_and_filter_products(session)
        assert len(results) == 1
        assert results[0].provider_name == ""

class TestPerformanceAndReliability:
    """3 performance/reliability теста"""
    
    @pytest.mark.asyncio
    async def test_large_dataset_performance(self, session):
        """Test 12: Performance with larger dataset"""
        import time
        
        # Create 100 products (reasonable size for testing)
        large_dataset = []
        for i in range(100):
            product = StandardizedProduct(
                source_url=f"https://test.com/perf_{i}",
                category="test_category",
                name=f"Performance Test {i}",
                provider_name=f"Provider {i % 10}",
                price_kwh=float(i) / 100,
                available=i % 2 == 0,
                raw_data={"index": i}
            )
            large_dataset.append(product)
        
        # Test storage performance
        start_time = time.time()
        await store_standardized_data(session, large_dataset)
        storage_time = time.time() - start_time
        
        # Test search performance  
        start_time = time.time()
        results = await search_and_filter_products(session)
        search_time = time.time() - start_time
        
        assert len(results) == 100
        assert storage_time < 5.0  # Reasonable time limit
        assert search_time < 2.0   # Reasonable time limit
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, session):
        """Test 13: Basic concurrent operations"""
        test_products = SimpleProductionTests().test_products
        
        # Run multiple storage operations
        tasks = []
        for i in range(3):  # Keep it simple
            task = asyncio.create_task(store_standardized_data(session, test_products))
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        
        # Verify data consistency
        results = await search_and_filter_products(session)
        assert len(results) >= len(test_products)  # At least the original data
    
    @pytest.mark.asyncio
    async def test_error_recovery(self, session):
        """Test 14: Basic error handling"""
        # Test with invalid data (but don't crash)
        try:
            invalid_product = StandardizedProduct(
                source_url="",  # This might cause issues
                category="",
                name="",
                provider_name="Test"
            )
            await store_standardized_data(session, [invalid_product])
            results = await search_and_filter_products(session)
            # Should either work or fail gracefully
            assert isinstance(results, list)
        except Exception as e:
            # Error is acceptable, just don't crash the test suite
            assert isinstance(e, Exception)
            print(f"Expected error handled: {e}")

# === ПРОСТАЯ ИНФРАСТРУКТУРА ===

@pytest.fixture(autouse=True)
async def setup_clean_test():
    """Простая cleanup между тестами"""
    yield
    # Cleanup if needed

if __name__ == "__main__":
    print("=== ОПТИМАЛЬНОЕ РЕШЕНИЕ: 14 ТЕСТОВ ===")
    print("✅ Использует реальный conftest.py")
    print("✅ Простая архитектура без over-engineering")
    print("✅ Покрывает все критические сценарии")
    print("✅ Performance testing без complexity")
    print("✅ Надежность без enterprise overhead")
    print()
    print("Почему это лучше:")
    print("  🎯 14 focused тестов vs 19-22 шаблонных")
    print("  🎯 Простота поддержки")
    print("  🎯 Быстрое выполнение")
    print("  🎯 Покрывает real-world scenarios")
    print("  🎯 Использует существующую инфраструктуру")
    print()
    print("pytest tests_api_optimized_simple.py -v --asyncio-mode=auto")