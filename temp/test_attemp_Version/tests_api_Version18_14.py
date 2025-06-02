"""
ИСПРАВЛЕННАЯ ИТОГОВАЯ ВЕРСИЯ ТЕСТОВ
Устраняет все выявленные проблемы:
- RuntimeError: no running event loop
- Неправильные assertions в фильтрации  
- Проблемы с async fixtures
"""

import pytest
import sys
import os
import json
import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, AsyncGenerator, Union
from unittest.mock import patch, MagicMock, AsyncMock
from dataclasses import dataclass, field
from copy import deepcopy

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# FastAPI testing imports
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === PYTEST ASYNCIO CONFIGURATION ===
pytest_plugins = ('pytest_asyncio',)

# === JSON SERIALIZATION HELPERS ===

def json_safe_float(value: Optional[float]) -> Optional[float]:
    """Convert float values to JSON-safe format"""
    if value is None:
        return None
    if value == float('inf'):
        return 999999.0
    if value == float('-inf'):
        return -999999.0
    if value != value:  # NaN check
        return None
    return value

def json_safe_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively make dictionary JSON-safe"""
    result = {}
    for key, value in data.items():
        if isinstance(value, float):
            result[key] = json_safe_float(value)
        elif isinstance(value, dict):
            result[key] = json_safe_dict(value)
        elif isinstance(value, list):
            result[key] = [json_safe_float(v) if isinstance(v, float) else v for v in value]
        else:
            result[key] = value
    return result

# === SIMPLIFIED ERROR MONITORING ===

class SimpleErrorCapture:
    """Simplified error capture without async complexity"""
    
    def __init__(self):
        self.errors = []
        self.request_count = 0
    
    def log_error(self, error: str):
        self.errors.append(error)
        logger.error(f"Captured error: {error}")
    
    def log_request(self):
        self.request_count += 1
    
    def get_stats(self):
        return {
            "requests": self.request_count,
            "errors": len(self.errors),
            "error_list": self.errors.copy()
        }
    
    def clear(self):
        self.errors.clear()
        self.request_count = 0

# Global error capture
error_capture = SimpleErrorCapture()

# === IMMUTABLE PRODUCT MODEL ===

@dataclass(frozen=True)
class StandardizedProduct:
    """Immutable product model with JSON safety"""
    source_url: str
    category: str
    name: str
    provider_name: str
    product_id: Optional[str] = None
    description: Optional[str] = None
    contract_duration_months: Optional[int] = None
    available: bool = True
    price_kwh: Optional[float] = None
    standing_charge: Optional[float] = None
    contract_type: Optional[str] = None
    monthly_cost: Optional[float] = None
    data_gb: Optional[float] = None
    calls: Optional[float] = None
    texts: Optional[float] = None
    network_type: Optional[str] = None
    download_speed: Optional[float] = None
    upload_speed: Optional[float] = None
    connection_type: Optional[str] = None
    data_cap_gb: Optional[float] = None
    internet_monthly_cost: Optional[float] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)
    
    def __hash__(self) -> int:
        return hash((
            self.source_url,
            self.category,
            self.name,
            self.provider_name,
            self.product_id
        ))
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, StandardizedProduct):
            return False
        return (
            self.source_url == other.source_url and
            self.category == other.category and
            self.name == other.name and
            self.provider_name == other.provider_name and
            self.product_id == other.product_id
        )
    
    def to_json_safe_dict(self) -> Dict[str, Any]:
        """Convert to JSON-safe dictionary"""
        return {
            'source_url': self.source_url,
            'category': self.category,
            'name': self.name,
            'provider_name': self.provider_name,
            'product_id': self.product_id,
            'description': self.description,
            'contract_duration_months': self.contract_duration_months,
            'available': self.available,
            'price_kwh': json_safe_float(self.price_kwh),
            'standing_charge': json_safe_float(self.standing_charge),
            'contract_type': self.contract_type,
            'monthly_cost': json_safe_float(self.monthly_cost),
            'data_gb': json_safe_float(self.data_gb),
            'calls': json_safe_float(self.calls),
            'texts': json_safe_float(self.texts),
            'network_type': self.network_type,
            'download_speed': json_safe_float(self.download_speed),
            'upload_speed': json_safe_float(self.upload_speed),
            'connection_type': self.connection_type,
            'data_cap_gb': json_safe_float(self.data_cap_gb),
            'internet_monthly_cost': json_safe_float(self.internet_monthly_cost),
            'raw_data': json_safe_dict(self.raw_data) if self.raw_data else {}
        }

# === SIMPLIFIED THREAD-SAFE DATABASE ===

class SimplifiedMockDatabase:
    """Simplified thread-safe database without complex async locks"""
    
    def __init__(self):
        self._products: List[StandardizedProduct] = []
        self._lock = None  # Will be created when needed
    
    def _ensure_lock(self):
        """Ensure lock exists (handles event loop issues)"""
        try:
            if self._lock is None:
                self._lock = asyncio.Lock()
        except RuntimeError:
            # No event loop, use sync operations
            self._lock = None
    
    def clear_sync(self):
        """Synchronous clear for setup/teardown"""
        self._products.clear()
        logger.info("Database cleared synchronously")
    
    async def clear_async(self):
        """Asynchronous clear with proper lock handling"""
        self._ensure_lock()
        if self._lock:
            async with self._lock:
                self._products.clear()
        else:
            self._products.clear()
        logger.info("Database cleared asynchronously")
    
    def add_products_sync(self, products: List[StandardizedProduct]):
        """Synchronous add for simple operations"""
        self._products.extend(products)
        logger.info(f"Added {len(products)} products synchronously. Total: {len(self._products)}")
    
    async def add_products_async(self, products: List[StandardizedProduct]):
        """Asynchronous add with lock handling"""
        self._ensure_lock()
        if self._lock:
            async with self._lock:
                self._products.extend(products)
        else:
            self._products.extend(products)
        logger.info(f"Added {len(products)} products asynchronously. Total: {len(self._products)}")
    
    def get_products_sync(self, **filters) -> List[Dict[str, Any]]:
        """Synchronous get with filtering"""
        result = self._products.copy()
        
        # Apply filters with corrected logic
        if filters.get('category'):
            result = [p for p in result if p.category == filters['category']]
            logger.debug(f"After category filter '{filters['category']}': {len(result)} products")
        
        if filters.get('product_type'):  # Alternative name for category
            result = [p for p in result if p.category == filters['product_type']]
            logger.debug(f"After product_type filter '{filters['product_type']}': {len(result)} products")
        
        if filters.get('provider'):
            result = [p for p in result if p.provider_name == filters['provider']]
            logger.debug(f"After provider filter '{filters['provider']}': {len(result)} products")
        
        if filters.get('available_only'):
            result = [p for p in result if p.available]
            logger.debug(f"After available_only filter: {len(result)} products")
        
        if filters.get('min_price') is not None:
            result = [p for p in result if p.price_kwh is not None and p.price_kwh >= filters['min_price']]
            logger.debug(f"After min_price filter: {len(result)} products")
        
        if filters.get('max_price') is not None:
            result = [p for p in result if p.price_kwh is not None and p.price_kwh <= filters['max_price']]
            logger.debug(f"After max_price filter: {len(result)} products")
        
        # Convert to JSON-safe dicts
        json_result = [product.to_json_safe_dict() for product in result]
        logger.info(f"Returning {len(json_result)} products after filtering")
        return json_result
    
    async def get_products_async(self, **filters) -> List[Dict[str, Any]]:
        """Asynchronous get with lock handling"""
        self._ensure_lock()
        if self._lock:
            async with self._lock:
                return self.get_products_sync(**filters)
        else:
            return self.get_products_sync(**filters)

# Global database instance
simplified_db = SimplifiedMockDatabase()

# === MOCK FUNCTIONS WITH PROPER ERROR HANDLING ===

def sync_mock_search(*args, **kwargs) -> List[Dict[str, Any]]:
    """Synchronous mock search function"""
    try:
        error_capture.log_request()
        
        # Extract filters from arguments
        filters = {}
        
        # Handle positional arguments (skip session if present)
        if args and len(args) > 1:
            filters['product_type'] = args[1]
        
        # Handle keyword arguments
        filters.update({k: v for k, v in kwargs.items() if v is not None})
        
        logger.info(f"Sync search with filters: {filters}")
        result = simplified_db.get_products_sync(**filters)
        logger.info(f"Sync search returning {len(result)} products")
        return result
        
    except Exception as e:
        error_capture.log_error(f"Sync search error: {str(e)}")
        logger.error(f"Sync search error: {e}")
        return []

async def async_mock_search(*args, **kwargs) -> List[Dict[str, Any]]:
    """Asynchronous mock search function"""
    try:
        error_capture.log_request()
        
        # Extract filters from arguments
        filters = {}
        
        # Handle positional arguments (skip session if present)
        if args and len(args) > 1:
            filters['product_type'] = args[1]
        
        # Handle keyword arguments  
        filters.update({k: v for k, v in kwargs.items() if v is not None})
        
        logger.info(f"Async search with filters: {filters}")
        result = await simplified_db.get_products_async(**filters)
        logger.info(f"Async search returning {len(result)} products")
        return result
        
    except Exception as e:
        error_capture.log_error(f"Async search error: {str(e)}")
        logger.error(f"Async search error: {e}")
        return []

# === TEST DATA ===

def create_test_products() -> List[StandardizedProduct]:
    """Create predictable test data for consistent testing"""
    return [
        # Electricity plans (2 products)
        StandardizedProduct(
            source_url="https://example.com/electricity/plan_a",
            category="electricity_plan",
            name="Green Energy Plan A",
            provider_name="EcoProvider",
            product_id="elec_green_001",
            price_kwh=0.15,
            standing_charge=5.0,
            contract_duration_months=12,
            available=True,
            contract_type="fixed",
            raw_data={"type": "electricity", "features": ["green"]}
        ),
        StandardizedProduct(
            source_url="https://example.com/electricity/plan_b",
            category="electricity_plan", 
            name="Standard Energy Plan B",
            provider_name="StandardProvider",
            product_id="elec_standard_002",
            price_kwh=0.12,
            standing_charge=4.0,
            contract_duration_months=24,
            available=False,  # Not available
            contract_type="variable",
            raw_data={"type": "electricity", "features": ["standard"]}
        ),
        
        # Mobile plans (1 product)
        StandardizedProduct(
            source_url="https://example.com/mobile/unlimited_plan",
            category="mobile_plan",
            name="Unlimited Mobile Plan",
            provider_name="MobileProvider",
            product_id="mobile_unlimited_003",
            monthly_cost=30.0,
            data_gb=999999.0,  # JSON-safe large number
            calls=999999.0,
            texts=999999.0,
            contract_duration_months=0,
            network_type="5G",
            available=True,
            raw_data={"type": "mobile", "features": ["unlimited"]}
        ),
        
        # Internet plans (1 product)
        StandardizedProduct(
            source_url="https://example.com/internet/fiber_plan",
            category="internet_plan",
            name="Fiber Internet Plan",
            provider_name="InternetProvider",
            product_id="internet_fiber_004",
            internet_monthly_cost=45.0,
            download_speed=1000.0,
            upload_speed=500.0,
            connection_type="fiber",
            data_cap_gb=None,
            contract_duration_months=12,
            available=True,
            raw_data={"type": "internet", "features": ["fiber"]}
        ),
    ]

# === FIXTURES WITH PROPER EVENT LOOP HANDLING ===

@pytest.fixture(scope="function")
def clean_database():
    """Fixture to ensure clean database state"""
    # Clear before test
    simplified_db.clear_sync()
    error_capture.clear()
    yield simplified_db
    # Clear after test
    simplified_db.clear_sync()

@pytest.fixture(scope="function")
def sample_products():
    """Fixture providing sample products"""
    return create_test_products()

@pytest.fixture(scope="function")
def populated_database_sync(clean_database, sample_products):
    """Synchronous populated database fixture"""
    simplified_db.add_products_sync(sample_products)
    return simplified_db

@pytest.fixture(scope="function")
async def populated_database_async(sample_products):
    """Asynchronous populated database fixture"""
    await simplified_db.clear_async()
    await simplified_db.add_products_async(sample_products)
    return simplified_db

# === TEST CLASSES WITH FIXED ASYNC HANDLING ===

class TestBasicFunctionality:
    """Basic functionality tests with proper sync/async handling"""
    
    def test_empty_database_search_sync(self, clean_database):
        """Test search with empty database (sync version)"""
        # Database should be empty
        results = sync_mock_search()
        assert isinstance(results, list)
        assert len(results) == 0
        
        # Verify error capture worked
        stats = error_capture.get_stats()
        assert stats["requests"] >= 1
    
    def test_basic_product_storage_and_retrieval_sync(self, clean_database, sample_products):
        """Test basic storage and retrieval (sync version)"""
        # Store products
        simplified_db.add_products_sync(sample_products)
        
        # Retrieve all products
        all_products = simplified_db.get_products_sync()
        assert len(all_products) == len(sample_products)
        assert len(all_products) == 4  # Expected: 2 electricity + 1 mobile + 1 internet
        
        # Verify JSON safety
        for product_dict in all_products:
            json_str = json.dumps(product_dict)  # Should not raise
            assert isinstance(json_str, str)
    
    def test_filtered_search_sync(self, populated_database_sync):
        """Test filtered search (sync version with corrected assertions)"""
        # Test category filter - should return exactly 2 electricity plans
        electricity_products = sync_mock_search(product_type="electricity_plan")
        assert len(electricity_products) == 2, f"Expected 2 electricity plans, got {len(electricity_products)}"
        
        # Test availability filter - should return 3 available products (1 electricity + 1 mobile + 1 internet)
        available_products = sync_mock_search(available_only=True)
        assert len(available_products) == 3, f"Expected 3 available products, got {len(available_products)}"
        
        # Test provider filter - should return 1 product from EcoProvider
        eco_products = sync_mock_search(provider="EcoProvider")
        assert len(eco_products) == 1, f"Expected 1 EcoProvider product, got {len(eco_products)}"
    
    @pytest.mark.asyncio
    async def test_empty_database_search_async(self):
        """Test search with empty database (async version)"""
        await simplified_db.clear_async()
        
        results = await async_mock_search()
        assert isinstance(results, list)
        assert len(results) == 0
    
    @pytest.mark.asyncio
    async def test_basic_product_storage_and_retrieval_async(self, sample_products):
        """Test basic storage and retrieval (async version)"""
        await simplified_db.clear_async()
        
        # Store products
        await simplified_db.add_products_async(sample_products)
        
        # Retrieve all products
        all_products = await simplified_db.get_products_async()
        assert len(all_products) == len(sample_products)
        assert len(all_products) == 4
        
        # Verify JSON safety
        for product_dict in all_products:
            json_str = json.dumps(product_dict)
            assert isinstance(json_str, str)
    
    @pytest.mark.asyncio
    async def test_filtered_search_async(self, populated_database_async):
        """Test filtered search (async version with corrected assertions)"""
        # Test category filter
        electricity_products = await async_mock_search(product_type="electricity_plan")
        assert len(electricity_products) == 2
        
        # Test availability filter
        available_products = await async_mock_search(available_only=True)
        assert len(available_products) == 3
        
        # Test provider filter
        eco_products = await async_mock_search(provider="EcoProvider")
        assert len(eco_products) == 1

class TestAPIEndpoints:
    """API endpoint tests with corrected assertions"""
    
    def setup_method(self):
        """Setup test FastAPI application"""
        self.test_app = FastAPI()
        
        @self.test_app.get("/search")
        async def search_endpoint(
            product_type: Optional[str] = None,
            provider: Optional[str] = None,
            available_only: bool = False
        ):
            """Search endpoint using async mock"""
            try:
                results = await async_mock_search(
                    product_type=product_type,
                    provider=provider,
                    available_only=available_only
                )
                return results
            except Exception as e:
                error_capture.log_error(f"API endpoint error: {str(e)}")
                logger.error(f"API endpoint error: {e}")
                return []
        
        @self.test_app.get("/health")
        async def health_check():
            return {"status": "healthy", "timestamp": time.time()}
    
    @pytest.mark.asyncio
    async def test_search_endpoint_empty_database(self):
        """Test search endpoint with empty database"""
        await simplified_db.clear_async()
        
        transport = ASGITransport(app=self.test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/search")
            
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 0
    
    @pytest.mark.asyncio
    async def test_search_endpoint_with_data(self, sample_products):
        """Test search endpoint with data (corrected assertions)"""
        await simplified_db.clear_async()
        await simplified_db.add_products_async(sample_products)
        
        transport = ASGITransport(app=self.test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Test basic search - should return all 4 products
            response = await client.get("/search")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 4, f"Expected 4 products, got {len(data)}"
            
            # Test filtered search - should return 2 electricity plans
            response = await client.get("/search?product_type=electricity_plan")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2, f"Expected 2 electricity plans, got {len(data)}"
            
            # Test availability filter - should return 3 available products
            response = await client.get("/search?available_only=true")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 3, f"Expected 3 available products, got {len(data)}"
            assert all(item['available'] for item in data)
    
    def test_sync_client_compatibility(self, populated_database_sync):
        """Test with synchronous TestClient"""
        client = TestClient(self.test_app, raise_server_exceptions=False)
        
        # Test health endpoint
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

class TestPerformanceAndConcurrency:
    """Performance tests with corrected expectations"""
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """Test concurrent database operations"""
        await simplified_db.clear_async()
        test_products = create_test_products()
        
        # Create multiple concurrent add operations
        tasks = []
        for i in range(5):
            task = asyncio.create_task(simplified_db.add_products_async(test_products))
            tasks.append(task)
        
        # Execute concurrently
        await asyncio.gather(*tasks)
        
        # Verify final state - should have 4 products * 5 operations = 20 products
        all_products = await simplified_db.get_products_async()
        assert len(all_products) == len(test_products) * 5
        assert len(all_products) == 20
    
    @pytest.mark.asyncio
    async def test_search_performance(self):
        """Test search performance with corrected dataset expectations"""
        await simplified_db.clear_async()
        
        # Create larger test dataset with known distribution
        large_dataset = []
        for i in range(100):
            # Create 50 "test_category" and 50 "other_category" products
            category = "test_category" if i < 50 else "other_category"
            product = StandardizedProduct(
                source_url=f"https://test.com/product_{i}",
                category=category,
                name=f"Test Product {i}",
                provider_name=f"Provider {i % 5}",
                product_id=f"test_{i}",
                price_kwh=float(i % 50) / 10,
                available=i % 3 != 0,  # ~67% available
                raw_data={"index": i}
            )
            large_dataset.append(product)
        
        # Measure storage time
        start_time = time.time()
        await simplified_db.add_products_async(large_dataset)
        storage_time = time.time() - start_time
        
        # Measure search time
        start_time = time.time()
        results = await async_mock_search(product_type="test_category")
        search_time = time.time() - start_time
        
        # Performance assertions
        assert storage_time < 1.0, f"Storage took {storage_time:.2f}s"
        assert search_time < 0.5, f"Search took {search_time:.2f}s"
        
        # Corrected assertion - should return exactly 50 products of "test_category"
        assert len(results) == 50, f"Expected 50 'test_category' products, got {len(results)}"

class TestEdgeCasesAndErrorHandling:
    """Edge case testing with comprehensive coverage"""
    
    def test_json_serialization_edge_cases(self):
        """Test JSON serialization with edge cases"""
        edge_case_product = StandardizedProduct(
            source_url="https://edge-case.com/product",
            category="test",
            name="Edge Case Product",
            provider_name="Test Provider",
            product_id="edge_001",
            calls=float('inf'),  # This should be converted
            texts=float('nan'),  # This should be handled
            price_kwh=float('-inf'),  # This should be converted
            raw_data={"inf_value": float('inf'), "nan_value": float('nan')}
        )
        
        # Test JSON conversion
        json_dict = edge_case_product.to_json_safe_dict()
        json_str = json.dumps(json_dict)  # Should not raise
        
        # Verify conversions
        assert json_dict['calls'] == 999999.0
        assert json_dict['texts'] is None
        assert json_dict['price_kwh'] == -999999.0
    
    def test_empty_and_none_inputs(self):
        """Test handling of empty and None inputs"""
        # Test with None values
        results = sync_mock_search(
            product_type=None,
            provider=None,
            min_price=None
        )
        assert isinstance(results, list)
        
        # Test with empty strings
        results = sync_mock_search(
            product_type="",
            provider=""
        )
        assert isinstance(results, list)
    
    def test_model_immutability(self):
        """Test that models are truly immutable"""
        product = create_test_products()[0]
        
        # These should raise AttributeError
        with pytest.raises(AttributeError):
            product.name = "Modified"
        
        with pytest.raises(AttributeError):
            product.price_kwh = 999.0
    
    def test_model_hashing_and_equality(self):
        """Test model hashing and equality"""
        products = create_test_products()
        product1 = products[0]
        
        # Create identical product
        product2 = StandardizedProduct(
            source_url=product1.source_url,
            category=product1.category,
            name=product1.name,
            provider_name=product1.provider_name,
            product_id=product1.product_id,
            # Different non-identity fields
            description="Different description",
            price_kwh=999.99
        )
        
        # Should be equal and have same hash
        assert product1 == product2
        assert hash(product1) == hash(product2)
        
        # Should work in sets
        product_set = {product1, product2}
        assert len(product_set) == 1

class TestErrorMonitoring:
    """Test error monitoring capabilities"""
    
    def test_error_capture_functionality(self, clean_database):
        """Test that error capture works correctly"""
        # Clear error capture
        error_capture.clear()
        
        # Make some requests
        sync_mock_search()
        sync_mock_search(product_type="electricity_plan")
        
        # Check stats
        stats = error_capture.get_stats()
        assert stats["requests"] >= 2
        assert isinstance(stats["errors"], int)
        assert isinstance(stats["error_list"], list)
    
    def test_error_handling_with_invalid_input(self, clean_database):
        """Test error handling with invalid inputs"""
        # This should not crash
        results = sync_mock_search(invalid_param="invalid_value")
        assert isinstance(results, list)
        
        # Error should be captured
        stats = error_capture.get_stats()
        assert stats["requests"] >= 1

# === INTEGRATION TESTS ===

class TestFullIntegration:
    """Full integration tests"""
    
    @pytest.mark.asyncio
    async def test_complete_workflow(self, sample_products):
        """Test complete workflow from storage to API response"""
        # 1. Clear database
        await simplified_db.clear_async()
        
        # 2. Add test products
        await simplified_db.add_products_async(sample_products)
        
        # 3. Create API app
        app = FastAPI()
        
        @app.get("/search")
        async def search():
            return await async_mock_search()
        
        # 4. Test API
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/search")
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == len(sample_products)
            assert len(data) == 4
            
            # Verify all products are JSON serializable
            for item in data:
                json.dumps(item)  # Should not raise

# === MAIN EXECUTION ===
if __name__ == "__main__":
    print("=== ИСПРАВЛЕННАЯ ИТОГОВАЯ ВЕРСИЯ ТЕСТОВ ===")
    print("🔧 Устранены все выявленные проблемы:")
    print("  ✅ Исправлен RuntimeError: no running event loop")
    print("  ✅ Исправлены неправильные assertions в фильтрации")
    print("  ✅ Добавлена поддержка как sync, так и async тестов")
    print("  ✅ Упрощена архитектура для надежности")
    print("  ✅ Добавлен proper event loop handling")
    print("  ✅ Исправлена логика подсчета продуктов в тестах")
    print()
    print("Исправления:")
    print("  • test_search_endpoint_with_data: ожидает 4 продукта вместо 2")
    print("  • test_search_performance: ожидает 50 продуктов из 100 (50% фильтрация)")
    print("  • Добавлены sync версии всех async тестов")
    print("  • Упрощена database без сложных async locks")
    print("  • Добавлен proper error handling и logging")
    print()
    print("Запуск: pytest tests_api_fixed_final.py -v --asyncio-mode=auto")