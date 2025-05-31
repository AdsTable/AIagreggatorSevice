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

# Import application - with error handling for clarity
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
    """Create standardized test products"""
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
            calls=float(9999),
            texts=float(9999),
            contract_duration_months=0,
            network_type="4G",
            available=True,
            raw_data={"type": "mobile"}
        ),
    ]

# === MOCK DATABASE ===
class MockDatabase:
    """Simple in-memory database for testing"""
    
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
        """Get products with optional filtering"""
        # Convert products to dictionaries using the correct method
        # Supports both Pydantic V1 and V2
        products = []
        for product in cls._products:
            if hasattr(product, "model_dump"):  # Pydantic V2
                products.append(product.model_dump())
            else:  # Pydantic V1
                products.append(product.dict())
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
    return MockDatabase.get_products()

# === TEST FUNCTIONS ===
class TestAPI:
    """API tests using simplified approach"""
    
    def setup_method(self):
        """Setup before each test"""
        # Clear the mock database
        MockDatabase.clear()
        
        # Override the get_session dependency
        app.dependency_overrides[get_session] = get_mock_session
        
        # Find and patch the search function
        # This approach avoids modifying routes directly
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
                
        finally:
            # Clear dependency overrides
            app.dependency_overrides.clear()

if __name__ == "__main__":
    print("=== FastAPI Test Suite ===")
    print("Running with diagnostic middleware to capture errors...")
    
    # Run all tests
    pytest.main(["-xvs", __file__])