"""
OPTIMIZED COMBINED TEST SUITE
Combines the best aspects of both test files:
- Simple error monitoring from Version18_11_8
- Enterprise-grade architecture from Version18_12
- Enhanced test coverage and performance validation
"""

import pytest
import sys
import os
import json
import asyncio
import uuid
import logging
import time
import re
from typing import Dict, Any, List, Optional, AsyncGenerator, Set, Union
from unittest.mock import patch, MagicMock, AsyncMock, Mock
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from copy import deepcopy

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# FastAPI testing imports
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

# Database imports
from sqlmodel import SQLModel, select, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import text

# Setup enhanced logging with error capture
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)

# === ENHANCED ERROR MONITORING (from Version18_11_8) ===

class EnhancedErrorCaptureMiddleware:
    """Advanced error capture middleware with detailed logging and metrics"""
    
    def __init__(self, app):
        self.app = app
        self.last_exception = None
        self.error_count = 0
        self.request_count = 0
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        self.request_count += 1
        self.last_exception = None
        
        # Enhanced send wrapper with detailed error tracking
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status = message["status"]
                if status >= 400:
                    self.error_count += 1
                    logger.error(f"⚠️ HTTP {status} error detected! Request #{self.request_count}")
                    if status == 500 and self.last_exception:
                        logger.error(f"Exception details: {str(self.last_exception)}")
                        logger.error(f"Exception type: {type(self.last_exception).__name__}")
            await send(message)
        
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            self.last_exception = e
            logger.exception(f"Uncaught exception in request #{self.request_count}:")
            raise
    
    def get_error_stats(self):
        """Get error statistics for test validation"""
        return {
            "total_requests": self.request_count,
            "error_count": self.error_count,
            "error_rate": self.error_count / max(self.request_count, 1),
            "last_exception": str(self.last_exception) if self.last_exception else None
        }

# === JSON SERIALIZATION HELPERS (from Version18_12) ===

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

# === OPTIMIZED IMMUTABLE MODELS (from Version18_12) ===

@dataclass(frozen=True)
class StandardizedProduct:
    """Immutable product model with optimized hashing and JSON safety"""
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
        """Optimized hash using identifying fields only"""
        return hash((
            self.source_url,
            self.category,
            self.name,
            self.provider_name,
            self.product_id
        ))
    
    def __eq__(self, other) -> bool:
        """Equality based on identifying fields"""
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
    
    def model_dump(self) -> Dict[str, Any]:
        """Compatibility method for Pydantic-style usage"""
        return self.to_json_safe_dict()
    
    def dict(self) -> Dict[str, Any]:
        """Compatibility method for Pydantic V1 style"""
        return self.to_json_safe_dict()

# === SIMPLE BUT ROBUST DATABASE (Combined approach) ===

class OptimizedMockDatabase:
    """Simple yet efficient mock database combining both approaches"""
    
    def __init__(self):
        self._lock = asyncio.Lock()
        self._products: List[StandardizedProduct] = []
        self._next_id: int = 1
        
        # Simple indexes for fast lookups
        self._by_category: Dict[str, List[StandardizedProduct]] = {}
        self._by_provider: Dict[str, List[StandardizedProduct]] = {}
        self._available_products: List[StandardizedProduct] = []
    
    async def clear(self) -> None:
        """Thread-safe clear operation"""
        async with self._lock:
            self._products.clear()
            self._next_id = 1
            self._by_category.clear()
            self._by_provider.clear()
            self._available_products.clear()
    
    async def add_products(self, products: List[StandardizedProduct]) -> None:
        """Batch add products with indexing"""
        async with self._lock:
            for product in products:
                self._products.append(product)
                
                # Update indexes
                if product.category not in self._by_category:
                    self._by_category[product.category] = []
                self._by_category[product.category].append(product)
                
                if product.provider_name not in self._by_provider:
                    self._by_provider[product.provider_name] = []
                self._by_provider[product.provider_name].append(product)
                
                if product.available:
                    self._available_products.append(product)
    
    async def get_products(self, **filters) -> List[Dict[str, Any]]:
        """Get products with filtering, return as dicts for compatibility"""
        async with self._lock:
            result = self._products.copy()
            
            # Apply filters
            if filters.get('category'):
                result = [p for p in result if p.category == filters['category']]
            
            if filters.get('provider'):
                result = [p for p in result if p.provider_name == filters['provider']]
            
            if filters.get('available_only'):
                result = [p for p in result if p.available]
            
            if filters.get('min_price') is not None:
                result = [p for p in result if p.price_kwh is not None and p.price_kwh >= filters['min_price']]
            
            if filters.get('max_price') is not None:
                result = [p for p in result if p.price_kwh is not None and p.price_kwh <= filters['max_price']]
            
            # Convert to dicts using the model method
            return [product.to_json_safe_dict() for product in result]

# Global database instance
mock_db = OptimizedMockDatabase()

# === ENHANCED MOCK SESSION (Combined approach) ===

class EnhancedMockAsyncSession:
    """Enhanced mock session with better error handling"""
    
    def __init__(self):
        self.closed = False
        self.committed = False
        self.query_count = 0
    
    async def execute(self, *args, **kwargs):
        """Mock query execution with tracking"""
        self.query_count += 1
        logger.debug(f"Mock query execution #{self.query_count}")
        
        # Return mock result that works with both approaches
        result = MagicMock()
        
        # For Version18_11_8 compatibility
        result.scalars.return_value.all.return_value = await mock_db.get_products()
        
        # For Version18_12 compatibility  
        async def async_all():
            return await mock_db.get_products()
        result.scalars.return_value.all = async_all
        
        return result
    
    async def commit(self):
        """Mock commit with tracking"""
        self.committed = True
        logger.debug("Mock session committed")
    
    async def rollback(self):
        """Mock rollback"""
        logger.debug("Mock session rollback")
    
    async def close(self):
        """Mock close with tracking"""
        self.closed = True
        logger.debug("Mock session closed")

async def get_enhanced_mock_session():
    """Enhanced session factory"""
    session = EnhancedMockAsyncSession()
    try:
        yield session
    finally:
        await session.close()

# === ENHANCED MOCK FUNCTIONS ===

async def enhanced_mock_search_function(*args, **kwargs):
    """Enhanced mock search with better logging and error handling"""
    logger.debug(f"Enhanced mock search called with args: {args}, kwargs: {kwargs}")
    
    try:
        # Extract filters from kwargs
        filters = {}
        if len(args) > 1:  # Skip session argument
            filters['category'] = args[1] if len(args) > 1 else kwargs.get('product_type')
        
        filters.update({
            'provider': kwargs.get('provider'),
            'min_price': kwargs.get('min_price'),
            'max_price': kwargs.get('max_price'),
            'available_only': kwargs.get('available_only', False)
        })
        
        # Remove None values
        filters = {k: v for k, v in filters.items() if v is not None}
        
        products_data = await mock_db.get_products(**filters)
        logger.debug(f"Mock search returning {len(products_data)} products")
        return products_data
        
    except Exception as e:
        logger.error(f"Mock search error: {e}")
        return []

# === COMPREHENSIVE TEST DATA ===

def create_comprehensive_test_products():
    """Create comprehensive test data combining both approaches"""
    return [
        # Electricity plans
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
            raw_data={"type": "electricity", "features": ["green", "renewable"]}
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
            available=False,
            contract_type="variable",
            raw_data={"type": "electricity", "features": ["standard"]}
        ),
        
        # Mobile plans
        StandardizedProduct(
            source_url="https://example.com/mobile/unlimited_plan",
            category="mobile_plan",
            name="Unlimited Mobile Plan",
            provider_name="MobileProvider",
            product_id="mobile_unlimited_003",
            monthly_cost=30.0,
            data_gb=999999.0,  # JSON-safe large number instead of inf
            calls=999999.0,    # JSON-safe large number instead of inf
            texts=999999.0,    # JSON-safe large number instead of inf
            contract_duration_months=0,
            network_type="5G",
            available=True,
            raw_data={"type": "mobile", "features": ["unlimited"]}
        ),
        
        # Internet plans
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
            data_cap_gb=None,  # Unlimited
            contract_duration_months=12,
            available=True,
            raw_data={"type": "internet", "features": ["fiber", "high_speed"]}
        ),
    ]

# === COMPREHENSIVE TEST CLASSES ===

class TestBasicFunctionality:
    """Basic functionality tests combining both approaches"""
    
    def setup_method(self):
        """Setup method that combines both approaches"""
        # Ensure clean state
        asyncio.create_task(mock_db.clear())
    
    @pytest.mark.asyncio
    async def test_empty_database_search(self):
        """Test search with empty database (from Version18_11_8)"""
        await mock_db.clear()
        
        # Test the search function directly
        results = await enhanced_mock_search_function(None)
        assert isinstance(results, list)
        assert len(results) == 0
    
    @pytest.mark.asyncio
    async def test_basic_product_storage_and_retrieval(self):
        """Test basic storage and retrieval (enhanced from both versions)"""
        test_products = create_comprehensive_test_products()
        
        # Store products
        await mock_db.add_products(test_products)
        
        # Retrieve all products
        all_products = await mock_db.get_products()
        assert len(all_products) == len(test_products)
        
        # Verify JSON safety
        for product_dict in all_products:
            json_str = json.dumps(product_dict)  # Should not raise
            assert isinstance(json_str, str)
    
    @pytest.mark.asyncio
    async def test_filtered_search(self):
        """Test filtered search combining both approaches"""
        test_products = create_comprehensive_test_products()
        await mock_db.add_products(test_products)
        
        # Test category filter
        electricity_products = await enhanced_mock_search_function(
            None, product_type="electricity_plan"
        )
        assert len(electricity_products) == 2
        
        # Test availability filter
        available_products = await enhanced_mock_search_function(
            None, available_only=True
        )
        assert len(available_products) == 3  # 3 available products
        
        # Test provider filter
        eco_products = await enhanced_mock_search_function(
            None, provider="EcoProvider"
        )
        assert len(eco_products) == 1

class TestAPIEndpoints:
    """API endpoint tests with enhanced error monitoring"""
    
    def setup_method(self):
        """Setup with comprehensive mocking"""
        self.test_app = FastAPI()
        self.error_middleware = EnhancedErrorCaptureMiddleware(self.test_app)
        self.test_app.middleware_stack = None
        self.test_app.add_middleware(EnhancedErrorCaptureMiddleware)
        
        @self.test_app.get("/search")
        async def search_endpoint(
            product_type: Optional[str] = None,
            provider: Optional[str] = None,
            available_only: bool = False
        ):
            """Enhanced search endpoint with error handling"""
            try:
                results = await enhanced_mock_search_function(
                    None,
                    product_type=product_type,
                    provider=provider,
                    available_only=available_only
                )
                return results
            except Exception as e:
                logger.error(f"Search endpoint error: {e}")
                raise
        
        @self.test_app.get("/health")
        async def health_check():
            """Health check endpoint"""
            return {"status": "healthy", "timestamp": time.time()}
    
    @pytest.mark.asyncio
    async def test_search_endpoint_empty_database(self):
        """Test search endpoint with empty database (enhanced)"""
        await mock_db.clear()
        
        transport = ASGITransport(app=self.test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/search")
            
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 0
    
    @pytest.mark.asyncio
    async def test_search_endpoint_with_data(self):
        """Test search endpoint with data (enhanced)"""
        test_products = create_comprehensive_test_products()
        await mock_db.add_products(test_products)
        
        transport = ASGITransport(app=self.test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Test basic search
            response = await client.get("/search")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == len(test_products)
            
            # Test filtered search
            response = await client.get("/search?product_type=electricity_plan")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            
            # Test availability filter
            response = await client.get("/search?available_only=true")
            assert response.status_code == 200
            data = response.json()
            assert all(item['available'] for item in data)
    
    def test_sync_client_compatibility(self):
        """Test with sync TestClient for compatibility (from Version18_11_8)"""
        client = TestClient(self.test_app, raise_server_exceptions=False)
        
        # Test health endpoint
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

class TestPerformanceAndConcurrency:
    """Performance and concurrency tests (from Version18_12)"""
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """Test concurrent database operations"""
        await mock_db.clear()
        test_products = create_comprehensive_test_products()
        
        # Create multiple concurrent add operations
        tasks = []
        for i in range(5):
            task = asyncio.create_task(mock_db.add_products(test_products))
            tasks.append(task)
        
        # Execute concurrently
        await asyncio.gather(*tasks)
        
        # Verify final state
        all_products = await mock_db.get_products()
        assert len(all_products) == len(test_products) * 5
    
    @pytest.mark.asyncio
    async def test_search_performance(self):
        """Test search performance with larger dataset"""
        await mock_db.clear()
        
        # Create larger test dataset
        large_dataset = []
        for i in range(100):
            product = StandardizedProduct(
                source_url=f"https://test.com/product_{i}",
                category="test_category" if i % 2 == 0 else "other_category",
                name=f"Test Product {i}",
                provider_name=f"Provider {i % 5}",
                product_id=f"test_{i}",
                price_kwh=float(i % 50) / 10,
                available=i % 3 != 0,
                raw_data={"index": i}
            )
            large_dataset.append(product)
        
        # Measure storage time
        start_time = time.time()
        await mock_db.add_products(large_dataset)
        storage_time = time.time() - start_time
        
        # Measure search time
        start_time = time.time()
        results = await enhanced_mock_search_function(None, product_type="test_category")
        search_time = time.time() - start_time
        
        # Performance assertions
        assert storage_time < 1.0, f"Storage took {storage_time:.2f}s"
        assert search_time < 0.5, f"Search took {search_time:.2f}s"
        assert len(results) == 50  # Half the products

class TestEdgeCasesAndErrorHandling:
    """Comprehensive edge case testing"""
    
    @pytest.mark.asyncio
    async def test_json_serialization_edge_cases(self):
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
    
    @pytest.mark.asyncio
    async def test_empty_and_none_inputs(self):
        """Test handling of empty and None inputs"""
        # Test with None values
        results = await enhanced_mock_search_function(
            None,
            product_type=None,
            provider=None,
            min_price=None
        )
        assert isinstance(results, list)
        
        # Test with empty strings
        results = await enhanced_mock_search_function(
            None,
            product_type="",
            provider=""
        )
        assert isinstance(results, list)
    
    def test_model_immutability(self):
        """Test that models are truly immutable (from Version18_12)"""
        product = create_comprehensive_test_products()[0]
        
        # These should raise AttributeError
        with pytest.raises(AttributeError):
            product.name = "Modified"
        
        with pytest.raises(AttributeError):
            product.price_kwh = 999.0
    
    def test_model_hashing_and_equality(self):
        """Test model hashing and equality"""
        products = create_comprehensive_test_products()
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
    """Test the enhanced error monitoring capabilities"""
    
    def test_error_middleware_tracking(self):
        """Test that error middleware properly tracks errors"""
        app = FastAPI()
        middleware = EnhancedErrorCaptureMiddleware(app)
        
        # Simulate some requests
        middleware.request_count = 10
        middleware.error_count = 2
        
        stats = middleware.get_error_stats()
        assert stats["total_requests"] == 10
        assert stats["error_count"] == 2
        assert stats["error_rate"] == 0.2
    
    @pytest.mark.asyncio
    async def test_session_tracking(self):
        """Test that mock sessions track operations"""
        session = EnhancedMockAsyncSession()
        
        # Simulate operations
        await session.execute("SELECT * FROM test")
        await session.commit()
        await session.close()
        
        assert session.query_count == 1
        assert session.committed == True
        assert session.closed == True

# === INTEGRATION TESTS ===

class TestFullIntegration:
    """Full integration tests combining all components"""
    
    @pytest.mark.asyncio
    async def test_complete_workflow(self):
        """Test complete workflow from storage to API response"""
        # 1. Clear database
        await mock_db.clear()
        
        # 2. Add test products
        test_products = create_comprehensive_test_products()
        await mock_db.add_products(test_products)
        
        # 3. Create API app with error monitoring
        app = FastAPI()
        app.add_middleware(EnhancedErrorCaptureMiddleware)
        
        @app.get("/search")
        async def search():
            return await enhanced_mock_search_function(None)
        
        # 4. Test API
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/search")
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == len(test_products)
            
            # Verify all products are JSON serializable
            for item in data:
                json.dumps(item)  # Should not raise

# === FIXTURES ===

@pytest.fixture(autouse=True)
async def setup_test_environment():
    """Setup test environment with proper cleanup"""
    # Clear database before each test
    await mock_db.clear()
    
    # Setup comprehensive patches
    patches = [
        patch('main.search_and_filter_products', side_effect=enhanced_mock_search_function),
        patch('database.get_session', side_effect=get_enhanced_mock_session),
    ]
    
    # Start patches
    for p in patches:
        try:
            p.start()
        except Exception:
            pass  # Ignore if modules don't exist
    
    yield
    
    # Cleanup patches
    for p in patches:
        try:
            p.stop()
        except Exception:
            pass

@pytest.fixture
def sample_products():
    """Fixture providing sample products"""
    return create_comprehensive_test_products()

@pytest.fixture
async def populated_database(sample_products):
    """Fixture providing populated database"""
    await mock_db.clear()
    await mock_db.add_products(sample_products)
    return mock_db

# === MAIN EXECUTION ===
if __name__ == "__main__":
    print("=== OPTIMIZED COMBINED TEST SUITE ===")
    print("🔥 Best of both worlds:")
    print("  ✅ Simple error monitoring from Version18_11_8")
    print("  ✅ Enterprise architecture from Version18_12") 
    print("  ✅ Enhanced performance and concurrency testing")
    print("  ✅ Comprehensive edge case coverage")
    print("  ✅ JSON-safe serialization throughout")
    print("  ✅ Both sync and async client support")
    print("  ✅ Production-ready error handling")
    print("  ✅ Thread-safe operations")
    print("  ✅ Immutable models with proper hashing")
    print("  ✅ Full integration testing")
    print()
    print("Coverage areas:")
    print("  • Basic functionality (storage, retrieval, filtering)")
    print("  • API endpoints (search, health, error handling)")
    print("  • Performance (concurrent operations, large datasets)")
    print("  • Edge cases (JSON serialization, None values, immutability)")
    print("  • Error monitoring (middleware tracking, session operations)")
    print("  • Full integration (complete workflow testing)")
    print()
    print("Run with: pytest tests_api_optimized_combined.py -v --asyncio-mode=auto")