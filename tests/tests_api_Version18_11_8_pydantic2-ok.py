"""
Updated Version18_11_8 for Pydantic 2.x compatibility
"""

import pytest
import sys
import os
import json
import logging
from typing import Dict, Any, List, Optional, Union

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Configure detailed logging for error diagnosis
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
logger = logging.getLogger(__name__)

# Standard testing imports
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

# Import updated models
try:
    from main import app
    from database import get_session
    from models import StandardizedProduct
except ImportError as e:
    logger.error(f"Import error: {e}")
    logger.error("Make sure you're running tests from the project root directory")
    raise

# === EXCEPTION MONITORING ===
class ErrorCaptureMiddleware:
    """Special testing middleware to capture errors that would normally result in 500 responses"""
    
    def __init__(self, app):
        self.app = app
        self.last_exception = None
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
            
        self.last_exception = None
        
        # Custom send function to capture status
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status = message["status"]
                if status == 500:
                    logger.error(f"⚠️ 500 error detected in response! Exception: {self.last_exception}")
                    if self.last_exception:
                        logger.error(f"Exception details: {str(self.last_exception)}")
            await send(message)
        
        # Try to run the request and capture any exceptions
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            self.last_exception = e
            logger.exception("Uncaught exception in middleware:")
            # Re-raise to let FastAPI handle it normally
            raise

# Add the middleware to capture errors
app.middleware_stack = None  # Force rebuild of middleware stack
app.add_middleware(ErrorCaptureMiddleware)

# === MOCK TEST DATA ===
def create_test_products():
    """Create standardized test products using Pydantic 2.x"""
    return [
        StandardizedProduct(
            source_url="https://example.com/product1",
            category="electricity_plan",
            name="Test Electricity Plan A",
            provider_name="Provider X",
            product_id="test-elec-001",
            price_kwh=0.15,
            standing_charge=5.0,
            contract_duration_months=12,
            available=True,
            raw_data={"type": "electricity", "features": ["green"]}
        ),
        StandardizedProduct(
            source_url="https://example.com/product2",
            category="electricity_plan",
            name="Test Electricity Plan B",
            provider_name="Provider Y",
            product_id="test-elec-002",
            price_kwh=0.12,
            standing_charge=4.0,
            contract_duration_months=24,
            available=False,
            raw_data={"type": "electricity", "features": ["standard"]}
        ),
        StandardizedProduct(
            source_url="https://example.com/product3",
            category="mobile_plan",
            name="Test Mobile Plan",
            provider_name="Provider X",
            product_id="test-mobile-001",
            monthly_cost=30.0,
            data_gb=100.0,
            calls=float('inf'),  # Will be serialized as 999999.0
            texts=float('inf'),  # Will be serialized as 999999.0
            contract_duration_months=0,
            network_type="4G",
            available=True,
            raw_data={"type": "mobile"}
        ),
    ]

# === MOCK DATABASE ===
class MockDatabase:
    """Simple in-memory database for testing with Pydantic 2.x support"""
    
    _products = []
    
    @classmethod
    def clear(cls):
        """Clear all stored products"""
        cls._products = []
    
    @classmethod
    def add_products(cls, products):
        """Add products to the database"""
        cls._products.extend(products)
    
    @classmethod
    def get_products(cls, **filters):
        """Get products with optional filtering - using Pydantic 2.x methods"""
        products = []
        for product in cls._products:
            # Use model_dump() for Pydantic 2.x compatibility
            if hasattr(product, "model_dump"):
                products.append(product.model_dump())
            elif hasattr(product, "dict"):  # Fallback for compatibility
                products.append(product.dict())
            else:
                # Manual conversion for other types
                products.append({
                    "source_url": getattr(product, "source_url", ""),
                    "category": getattr(product, "category", ""),
                    "name": getattr(product, "name", ""),
                    "provider_name": getattr(product, "provider_name", ""),
                    "available": getattr(product, "available", True)
                })
        return products

# === MOCK SESSION ===
class MockAsyncSession:
    """Mock SQLAlchemy AsyncSession"""
    
    def __init__(self):
        """Initialize mock session"""
        self.closed = False
    
    async def execute(self, *args, **kwargs):
        """Mock query execution"""
        # Return a mock result with scalars.all() that returns our products
        result = MagicMock()
        result.scalars.return_value.all.return_value = MockDatabase._products
        return result
    
    async def commit(self):
        """Mock commit"""
        pass
    
    async def close(self):
        """Mock close"""
        self.closed = True

async def get_mock_session():
    """AsyncSession factory for dependency injection"""
    session = MockAsyncSession()
    try:
        yield session
    finally:
        await session.close()

# === MOCK SEARCH FUNCTION ===
async def mock_search_function(*args, **kwargs):
    """Mock implementation for search_and_filter_products"""
    logger.debug(f"Mock search function called with args: {args}, kwargs: {kwargs}")
    # Return JSON-safe data using Pydantic 2.x serialization
    products = MockDatabase.get_products()
    # Convert to JSON-safe format
    json_safe_products = []
    for product_dict in products:
        # Handle infinity values that might be in the data
        safe_dict = {}
        for key, value in product_dict.items():
            if isinstance(value, float):
                if value == float('inf'):
                    safe_dict[key] = 999999.0
                elif value == float('-inf'):
                    safe_dict[key] = -999999.0
                elif value != value:  # NaN check
                    safe_dict[key] = None
                else:
                    safe_dict[key] = value
            else:
                safe_dict[key] = value
        json_safe_products.append(safe_dict)
    return json_safe_products

# === TEST FUNCTIONS ===
class TestAPI:
    """API tests using Pydantic 2.x compatible approach"""
    
    def setup_method(self):
        """Setup before each test"""
        # Clear the mock database
        MockDatabase.clear()
        
        # Override the get_session dependency
        app.dependency_overrides[get_session] = get_mock_session
        
        # Find and patch the search function
        import main
        search_function_names = [
            'search_and_filter_products',
            'search_products',
            'get_products',
            'query_products'
        ]
        
        self.patches = []
        for name in search_function_names:
            if hasattr(main, name):
                patch_obj = patch.object(main, name, mock_search_function)
                patch_obj.start()
                self.patches.append(patch_obj)
                logger.info(f"Patched search function: {name}")
    
    def teardown_method(self):
        """Cleanup after each test"""
        # Stop all patches
        for p in self.patches:
            p.stop()
        
        # Clear dependency overrides
        app.dependency_overrides.clear()
    
    def test_search_endpoint_empty_database(self):
        """Test search endpoint with empty database"""
        # Make sure database is empty
        MockDatabase.clear()
        
        # Create test client
        client = TestClient(app, raise_server_exceptions=False)
        
        # Call the search endpoint
        response = client.get("/search")
        
        # Log detailed response info for debugging
        logger.info(f"Status code: {response.status_code}")
        logger.info(f"Response headers: {response.headers}")
        logger.info(f"Response body: {response.text[:500]}")
        
        # Make assertions with detailed error messages
        if response.status_code != 200:
            logger.error(f"Request failed with status {response.status_code}")
            logger.error(f"Response content: {response.text}")
        
        assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), f"Expected list response, got {type(data).__name__}"
        assert len(data) == 0, f"Expected empty list, got {len(data)} items"
    
    def test_search_endpoint_with_data(self):
        """Test search endpoint with test data"""
        # Add test products to mock database
        MockDatabase.add_products(create_test_products())
        
        # Create test client
        client = TestClient(app, raise_server_exceptions=False)
        
        # Call the search endpoint
        response = client.get("/search")
        
        # Log detailed response info for debugging
        logger.info(f"Status code: {response.status_code}")
        logger.info(f"Response body preview: {response.text[:200]}...")
        
        # Make assertions with detailed error messages
        assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), f"Expected list response, got {type(data).__name__}"
        assert len(data) == 3, f"Expected 3 products, got {len(data)}"
        
        # Test JSON safety - infinity values should be converted
        mobile_plan = next((p for p in data if p.get("category") == "mobile_plan"), None)
        if mobile_plan:
            assert mobile_plan.get("calls") == 999999.0, "Infinity should be converted to 999999.0"
            assert mobile_plan.get("texts") == 999999.0, "Infinity should be converted to 999999.0"

    def test_pydantic2_serialization(self):
        """Test Pydantic 2.x specific serialization"""
        products = create_test_products()
        
        for product in products:
            # Test model_dump method
            data = product.model_dump()
            assert isinstance(data, dict)
            assert "source_url" in data
            assert "category" in data
            
            # Test JSON mode serialization (handles infinity/NaN)
            json_data = product.model_dump(mode="json")
            assert isinstance(json_data, dict)
            
            # Test to_json_safe_dict method
            safe_data = product.to_json_safe_dict()
            assert isinstance(safe_data, dict)
            
            # Verify JSON serialization works
            json_str = json.dumps(safe_data)
            assert isinstance(json_str, str)

@pytest.mark.asyncio
async def test_search_endpoint_async():
    """Async test for search endpoint using AsyncClient"""
    # Setup test data
    MockDatabase.clear()
    MockDatabase.add_products(create_test_products())
    
    # Override dependencies
    app.dependency_overrides[get_session] = get_mock_session
    
    # Patch search function
    import main
    with patch.object(main, 'search_and_filter_products', side_effect=mock_search_function):
        try:
            # Use AsyncClient with ASGITransport
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Make request
                response = await client.get("/search")
                
                # Check response
                assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}: {response.text}"
                data = response.json()
                assert isinstance(data, list)
                assert len(data) == 3
                
                # Verify JSON safety
                for item in data:
                    json_str = json.dumps(item)
                    assert isinstance(json_str, str)
                
        finally:
            # Clear dependency overrides
            app.dependency_overrides.clear()

if __name__ == "__main__":
    print("=== FastAPI Test Suite - Pydantic 2.x Compatible ===")
    print("Running with diagnostic middleware and Pydantic 2.x features...")
    
    # Run all tests
    pytest.main(["-xvs", __file__])