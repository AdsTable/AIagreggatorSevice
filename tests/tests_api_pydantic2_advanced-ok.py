"""
Advanced Pydantic 2.x API tests with FastAPI integration
"""

import pytest
import asyncio
import json
import math
from typing import List, Dict, Any, Optional
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

# Import application and models
from main import app
from models import StandardizedProduct, ProductDB
from database import get_session


class MockAsyncSession:
    """Mock SQLAlchemy AsyncSession for testing."""
    
    def __init__(self):
        self.products = []
        self.committed = False
        self.closed = False
    
    def add_all(self, products):
        """Mock add_all method."""
        self.products.extend(products)
    
    async def commit(self):
        """Mock commit method."""
        self.committed = True
    
    async def rollback(self):
        """Mock rollback method."""
        pass
    
    async def exec(self, query):
        """Mock exec method."""
        result = AsyncMock()
        # Convert stored products to StandardizedProduct for return
        standardized_products = []
        for product in self.products:
            if isinstance(product, ProductDB):
                standardized_products.append(product.to_standardized_product())
            else:
                standardized_products.append(product)
        result.all.return_value = standardized_products
        return result
    
    async def close(self):
        """Mock close method."""
        self.closed = True


class MockDatabase:
    """Mock database for testing."""
    
    def __init__(self):
        self.products = []
    
    def clear(self):
        """Clear all products."""
        self.products = []
    
    def add_products(self, products: List[StandardizedProduct]):
        """Add products to mock database."""
        self.products.extend(products)
    
    def get_all_products(self) -> List[Dict[str, Any]]:
        """Get all products as JSON-safe dictionaries."""
        return [product.to_json_safe_dict() for product in self.products]


# Global mock database instance
mock_db = MockDatabase()


async def get_mock_session():
    """Mock session factory."""
    session = MockAsyncSession()
    session.products = [ProductDB(
        id=i+1,
        category=product.category,
        source_url=product.source_url,
        name=product.name,
        provider_name=product.provider_name,
        product_id=product.product_id,
        description=product.description,
        contract_duration_months=product.contract_duration_months,
        available=product.available,
        price_kwh=product.price_kwh,
        standing_charge=product.standing_charge,
        contract_type=product.contract_type,
        monthly_cost=product.monthly_cost,
        data_gb=product.data_gb,
        calls=product.calls,
        texts=product.texts,
        network_type=product.network_type,
        download_speed=product.download_speed,
        upload_speed=product.upload_speed,
        connection_type=product.connection_type,
        data_cap_gb=product.data_cap_gb,
        internet_monthly_cost=product.internet_monthly_cost,
        raw_data_json=product.raw_data
    ) for i, product in enumerate(mock_db.products)]
    
    try:
        yield session
    finally:
        await session.close()


def create_test_products() -> List[StandardizedProduct]:
    """Create test products using Pydantic 2.x."""
    return [
        StandardizedProduct(
            category="electricity_plan",
            source_url="https://test.com/electricity1",
            name="Green Energy Plan",
            provider_name="EcoEnergy Corp",
            product_id="ECO-001",
            price_kwh=0.15,
            standing_charge=8.0,
            contract_type="Fixed",
            contract_duration_months=12,
            available=True,
            raw_data={"renewable": True, "source": "solar"}
        ),
        StandardizedProduct(
            category="mobile_plan",
            source_url="https://test.com/mobile1",
            name="Unlimited Everything",
            provider_name="MegaMobile",
            product_id="MM-UNLIM-001",
            monthly_cost=50.0,
            data_gb=float("inf"),  # Unlimited data
            calls=float("inf"),    # Unlimited calls
            texts=float("inf"),    # Unlimited texts
            network_type="5G",
            contract_duration_months=24,
            available=True,
            raw_data={"unlimited": True, "network": "5G"}
        ),
        StandardizedProduct(
            category="internet_plan",
            source_url="https://test.com/internet1",
            name="Fiber Gigabit",
            provider_name="FastNet ISP",
            product_id="FN-GIGA-001",
            download_speed=1000.0,
            upload_speed=1000.0,
            connection_type="Fiber",
            monthly_cost=80.0,
            data_cap_gb=float("inf"),  # Unlimited data
            contract_duration_months=12,
            available=True,
            raw_data={"fiber": True, "symmetric": True}
        )
    ]


class TestPydantic2FastAPIIntegration:
    """Test Pydantic 2.x integration with FastAPI."""
    
    def setup_method(self):
        """Setup before each test."""
        mock_db.clear()
        app.dependency_overrides[get_session] = get_mock_session
    
    def teardown_method(self):
        """Cleanup after each test."""
        app.dependency_overrides.clear()
    
    def test_health_endpoint(self):
        """Test health endpoint returns Pydantic version info."""
        client = TestClient(app)
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "2.0.0"
        assert data["pydantic_version"] == "2.x"
    
    def test_search_endpoint_empty_database(self):
        """Test search endpoint with empty database."""
        client = TestClient(app)
        response = client.get("/search")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0
    
    def test_search_endpoint_with_data(self):
        """Test search endpoint with test data using Pydantic 2.x serialization."""
        # Add test products to mock database
        mock_db.add_products(create_test_products())
        
        client = TestClient(app)
        response = client.get("/search")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 3
        
        # Verify JSON-safe serialization (infinity values should be converted)
        mobile_plan = next((p for p in data if p["category"] == "mobile_plan"), None)
        assert mobile_plan is not None
        assert mobile_plan["data_gb"] == 999999.0  # inf -> 999999.0
        assert mobile_plan["calls"] == 999999.0    # inf -> 999999.0
        assert mobile_plan["texts"] == 999999.0    # inf -> 999999.0
    
    def test_search_with_filters(self):
        """Test search endpoint with various filters."""
        mock_db.add_products(create_test_products())
        
        client = TestClient(app)
        
        # Test product type filter
        response = client.get("/search?product_type=electricity_plan")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["category"] == "electricity_plan"
        
        # Test provider filter
        response = client.get("/search?provider=MegaMobile")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["provider_name"] == "MegaMobile"
        
        # Test min_price filter
        response = client.get("/search?min_price=60")
        assert response.status_code == 200
        data = response.json()
        # Should return internet plan (80.0) but not electricity plan based on monthly_cost
        filtered_results = [p for p in data if p.get("monthly_cost", 0) >= 60]
        assert len(filtered_results) >= 1
    
    def test_detailed_search_endpoint(self):
        """Test the detailed search endpoint with metadata."""
        mock_db.add_products(create_test_products())
        
        client = TestClient(app)
        response = client.get("/search/detailed?product_type=mobile_plan")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "products" in data
        assert "total_count" in data
        assert "filters_applied" in data
        
        assert isinstance(data["products"], list)
        assert data["total_count"] == len(data["products"])
        assert data["filters_applied"]["product_type"] == "mobile_plan"
        
        # Verify product data is properly serialized
        if data["products"]:
            product = data["products"][0]
            assert product["category"] == "mobile_plan"
            # Check infinity handling
            assert product["data_gb"] == 999999.0

    @pytest.mark.asyncio
    async def test_async_search_endpoint(self):
        """Test search endpoint using AsyncClient."""
        mock_db.add_products(create_test_products())
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/search")
            
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 3
            
            # Verify all products have required fields
            for product in data:
                assert "category" in product
                assert "source_url" in product
                assert "available" in product
                
                # Verify JSON-safe serialization
                json_str = json.dumps(product)
                parsed = json.loads(json_str)
                assert parsed == product

    def test_json_serialization_edge_cases(self):
        """Test JSON serialization with various edge cases."""
        # Create product with edge case values
        edge_case_product = StandardizedProduct(
            category="electricity_plan",
            source_url="https://test.com/edge",
            name="Edge Case Product",
            price_kwh=float("inf"),
            standing_charge=float("nan"),
            data_gb=-float("inf"),
            raw_data={
                "nested_inf": float("inf"),
                "nested_nan": float("nan"),
                "nested_dict": {
                    "deep_inf": float("inf"),
                    "normal_value": 42.0
                },
                "nested_list": [float("inf"), float("nan"), 3.14]
            }
        )
        
        mock_db.add_products([edge_case_product])
        
        client = TestClient(app)
        response = client.get("/search")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        
        product = data[0]
        
        # Verify infinity/NaN handling
        assert product["price_kwh"] == 999999.0   # inf -> 999999.0
        assert product["standing_charge"] is None  # NaN -> None
        assert product["data_gb"] == -999999.0     # -inf -> -999999.0
        
        # Verify nested handling
        assert product["raw_data"]["nested_inf"] == 999999.0
        assert product["raw_data"]["nested_nan"] is None
        assert product["raw_data"]["nested_dict"]["deep_inf"] == 999999.0
        assert product["raw_data"]["nested_dict"]["normal_value"] == 42.0
        assert product["raw_data"]["nested_list"][0] == 999999.0  # inf
        assert product["raw_data"]["nested_list"][1] is None      # NaN
        assert product["raw_data"]["nested_list"][2] == 3.14      # normal

    def test_validation_errors(self):
        """Test validation errors are properly handled."""
        client = TestClient(app)
        
        # Test invalid ingestion request
        invalid_request = {
            "source_identifier": "",  # Empty string should fail
            "category": "invalid_category"  # Invalid category
        }
        
        response = client.post("/ingest_data", json=invalid_request)
        assert response.status_code == 422  # Validation error
        
        error_detail = response.json()["detail"]
        assert any("source_identifier" in str(error) for error in error_detail)


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])