"""
FAILED tests_api_Version23.py::test_store_standardized_data - sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) no such table: productdb      
ERROR tests_api_Version23.py::test_search_endpoint_all_filters - TypeError: AsyncClient.__init__() got an unexpected keyword argument 'app'
ERROR tests_api_Version23.py::TestEdgeCasesAndJsonSafety::test_infinity_values_json_safe - TypeError: AsyncClient.__init__() got an unexpected keyword argument 'app'
ERROR tests_api_Version23.py::TestEdgeCasesAndJsonSafety::test_comprehensive_json_edge_cases - TypeError: AsyncClient.__init__() got an unexpected keyword argument 'app'
ERROR tests_api_Version23.py::TestEdgeCasesAndJsonSafety::test_large_dataset_json_consistency - TypeError: AsyncClient.__init__() got an unexpected keyword argument 'app'
ERROR tests_api_Version23.py::TestPerformance::test_empty_database_performance - TypeError: AsyncClient.__init__() got an unexpected keyword argument 'app'
ERROR tests_api_Version23.py::TestPerformance::test_complex_filtering_performance - TypeError: AsyncClient.__init__() got an unexpected keyword argument 'app'
ERROR tests_api_Version23.py::TestErrorHandling::test_invalid_parameters - TypeError: AsyncClient.__init__() got an unexpected keyword argument 'app'   
ERROR tests_api_Version23.py::TestErrorHandling::test_extreme_parameter_values - TypeError: AsyncClient.__init__() got an unexpected keyword argument 'app'
"""
# test_api.py

import pytest
import math
import json
import unittest.mock
from typing import List, AsyncIterator, Any, Dict
from httpx import AsyncClient
from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession as SQLAsyncSession

from main import app
from models import ProductDB, StandardizedProduct
from database import get_session

# ------------------------ JSON SAFETY UTILITIES ------------------------

def make_json_safe(obj: Any) -> Any:
    """Convert infinity and NaN values to JSON-safe equivalents"""
    if isinstance(obj, dict):
        return {k: make_json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_json_safe(item) for item in obj]
    elif isinstance(obj, float):
        if math.isinf(obj):
            return None  # Convert infinity to null for JSON safety
        elif math.isnan(obj):
            return None  # Convert NaN to null for JSON safety
    return obj

# ------------------------ DATABASE SETUP ------------------------

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture(scope="session")
def engine():
    SQLModel.metadata.clear()  # Prevent index duplication
    return create_async_engine(TEST_DB_URL, echo=False)

@pytest.fixture(scope="function")
async def session(engine) -> AsyncIterator[AsyncSession]:
    async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with async_session_factory() as s:
        yield s

@pytest.fixture()
async def client(session):
    async def override_get_session():
        yield session
    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(app=app, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()

@pytest.fixture()
def test_products() -> List[StandardizedProduct]:
    return [
        StandardizedProduct(
            source_url="https://example.com/elec/plan_a",
            category="electricity_plan",
            name="Elec Plan A",
            provider_name="Provider X",
            price_kwh=0.15,
            standing_charge=5.0,
            contract_duration_months=12,
            available=True,
            raw_data={"k": "v1"},
        ),
        StandardizedProduct(
            source_url="https://example.com/elec/plan_b",
            category="electricity_plan",
            name="Elec Plan B",
            provider_name="Provider Y",
            price_kwh=0.12,
            standing_charge=4.0,
            contract_duration_months=24,
            available=False,
            raw_data={"k": "v2"},
        ),
        StandardizedProduct(
            source_url="https://example.com/mobile/plan_c",
            category="mobile_plan",
            name="Mobile Plan C",
            provider_name="Provider X",
            monthly_cost=30.0,
            data_gb=100.0,
            calls=math.inf,
            texts=math.inf,
            contract_duration_months=0,
            raw_data={"k": "v3"},
        ),
        StandardizedProduct(
            source_url="https://example.com/mobile/plan_d",
            category="mobile_plan",
            name="Mobile Plan D",
            provider_name="Provider Z",
            monthly_cost=45.0,
            data_gb=math.inf,
            calls=500,
            texts=math.inf,
            contract_duration_months=12,
            raw_data={"k": "v4"},
        ),
        StandardizedProduct(
            source_url="https://example.com/internet/plan_e",
            category="internet_plan",
            name="Internet Plan E",
            provider_name="Provider Y",
            download_speed=500.0,
            upload_speed=50.0,
            connection_type="Fiber",
            data_cap_gb=math.inf,
            monthly_cost=60.0,
            contract_duration_months=24,
            raw_data={"k": "v5"},
        ),
        StandardizedProduct(
            source_url="https://example.com/internet/plan_f",
            category="internet_plan",
            name="Internet Plan F",
            provider_name="Provider X",
            download_speed=100.0,
            upload_speed=20.0,
            connection_type="DSL",
            data_cap_gb=500.0,
            monthly_cost=50.0,
            contract_duration_months=12,
            raw_data={"k": "v6"},
        ),
    ]

# ------------------------ UTILITY ------------------------

async def store_standardized_data(session: AsyncSession, data: List[StandardizedProduct]) -> None:
    for product in data:
        db_product = ProductDB(
            **product.model_dump(exclude={"raw_data"}),
            raw_data=product.raw_data
        )
        session.add(db_product)
    await session.commit()

# ------------------------ CORE API TESTS ------------------------

@pytest.mark.asyncio
async def test_store_standardized_data(session, test_products):
    result = await session.execute(select(ProductDB))
    assert result.scalars().first() is None

    await store_standardized_data(session, test_products)
    result = await session.execute(select(ProductDB))
    stored = result.scalars().all()

    assert len(stored) == len(test_products)
    names = {p.name for p in stored}
    assert names == {p.name for p in test_products}

@pytest.mark.asyncio
async def test_search_endpoint_all_filters(client, session, test_products):
    await store_standardized_data(session, test_products)

    # No filters
    r = await client.get("/search")
    assert r.status_code == 200
    assert len(r.json()) == len(test_products)

    # By type
    r = await client.get("/search", params={"product_type": "mobile_plan"})
    assert {p["name"] for p in r.json()} == {"Mobile Plan C", "Mobile Plan D"}

    # By provider
    r = await client.get("/search", params={"provider": "Provider X"})
    assert {p["name"] for p in r.json()} == {"Elec Plan A", "Mobile Plan C", "Internet Plan F"}

    # Min price (electricity)
    r = await client.get("/search", params={"product_type": "electricity_plan", "min_price": 0.13})
    assert {p["name"] for p in r.json()} == {"Elec Plan A"}

    # Min contract duration
    r = await client.get("/search", params={"min_contract_duration_months": 18})
    assert {p["name"] for p in r.json()} == {"Elec Plan B", "Internet Plan E"}

    # Max data gb
    r = await client.get("/search", params={"product_type": "mobile_plan", "max_data_gb": 200})
    assert {p["name"] for p in r.json()} == {"Mobile Plan C"}

    # Combined filters
    r = await client.get("/search", params={"product_type": "internet_plan", "provider": "Provider X", "max_data_gb": 600})
    assert {p["name"] for p in r.json()} == {"Internet Plan F"}

    # No results
    r = await client.get("/search", params={"product_type": "gas_plan"})
    assert r.status_code == 200
    assert r.json() == []

# ------------------------ JSON SAFETY & EDGE CASES ------------------------

class TestEdgeCasesAndJsonSafety:
    """Test JSON safety and edge case handling"""
    
    @pytest.mark.asyncio
    async def test_infinity_values_json_safe(self, client, session):
        """Test that infinity values are properly handled in JSON responses"""
        infinity_products = [
            StandardizedProduct(
                source_url="https://example.com/infinity_test",
                category="mobile_plan",
                name="Infinity Test Plan",
                provider_name="Test Provider",
                data_gb=math.inf,
                calls=math.inf,
                texts=math.inf,
                monthly_cost=50.0,
                raw_data={"unlimited": True}
            )
        ]
        
        await store_standardized_data(session, infinity_products)
        
        response = await client.get("/search")
        assert response.status_code == 200
        
        # Ensure response is valid JSON
        json_data = response.json()
        json_string = json.dumps(json_data)
        
        # Verify no 'inf' strings in JSON output
        assert 'inf' not in json_string
        assert '-inf' not in json_string
        
        # Verify JSON is parseable
        parsed = json.loads(json_string)
        assert len(parsed) == 1
        
        product = parsed[0]
        # Infinity values should be converted to null or handled appropriately
        assert product["data_gb"] is None or isinstance(product["data_gb"], (int, float))
        assert product["calls"] is None or isinstance(product["calls"], (int, float))
        assert product["texts"] is None or isinstance(product["texts"], (int, float))

    @pytest.mark.asyncio
    async def test_comprehensive_json_edge_cases(self, client, session):
        """Test comprehensive edge cases for JSON safety"""
        edge_case_products = [
            StandardizedProduct(
                source_url="https://example.com/edge_case",
                category="test_plan",
                name="Edge Case Plan",
                provider_name="",  # Empty string
                price_kwh=0.0,  # Zero value
                monthly_cost=math.inf,  # Infinity
                data_gb=float('inf'),  # Another infinity
                calls=0,  # Zero calls
                texts=math.inf,  # Infinity texts
                contract_duration_months=None,  # None value
                available=True,
                raw_data={"special_values": [math.inf, 0, None, "test"]}  # Mixed values
            )
        ]
        
        await store_standardized_data(session, edge_case_products)
        
        response = await client.get("/search")
        assert response.status_code == 200
        
        # Ensure response is valid JSON
        json_data = response.json()
        json_string = json.dumps(json_data)
        
        # Verify no problematic values in JSON
        assert 'inf' not in json_string
        assert '-inf' not in json_string
        assert 'NaN' not in json_string
        
        # Verify JSON is parseable and contains expected data
        parsed = json.loads(json_string)
        assert len(parsed) == 1
        
        product = parsed[0]
        assert product["name"] == "Edge Case Plan"
        assert product["provider_name"] == ""
        assert product["available"] is True
        
        # Check that infinity values are handled safely
        if product["monthly_cost"] is not None:
            assert isinstance(product["monthly_cost"], (int, float))
            assert not math.isinf(product["monthly_cost"])

    @pytest.mark.asyncio
    async def test_large_dataset_json_consistency(self, client, session):
        """Test JSON consistency with larger datasets containing edge cases"""
        large_dataset = []
        for i in range(50):
            product = StandardizedProduct(
                source_url=f"https://example.com/test_{i}",
                category="test_plan",
                name=f"Test Plan {i}",
                provider_name=f"Provider {i % 5}",
                monthly_cost=math.inf if i % 10 == 0 else 20.0 + i,  # Every 10th has infinity
                data_gb=math.inf if i % 7 == 0 else 100.0 + i,  # Every 7th has infinity
                calls=math.inf if i % 3 == 0 else 1000 + i,  # Every 3rd has infinity
                texts=math.inf,  # All have infinity
                available=i % 2 == 0,
                raw_data={"index": i, "has_infinity": i % 5 == 0}
            )
            large_dataset.append(product)
        
        await store_standardized_data(session, large_dataset)
        
        response = await client.get("/search")
        assert response.status_code == 200
        
        # Ensure all responses are JSON safe
        json_data = response.json()
        json_string = json.dumps(json_data)
        
        # Verify no infinity strings in large dataset response
        assert 'inf' not in json_string
        assert len(json_data) == 50
        
        # Spot check some products for proper infinity handling
        for product in json_data[:5]:  # Check first 5
            for field in ["monthly_cost", "data_gb", "calls", "texts"]:
                if product.get(field) is not None:
                    assert not isinstance(product[field], str) or 'inf' not in product[field]

# ------------------------ PERFORMANCE TESTS ------------------------

class TestPerformance:
    """Test API performance with various data scenarios"""
    
    @pytest.mark.asyncio
    async def test_empty_database_performance(self, client):
        """Test performance with empty database"""
        response = await client.get("/search")
        assert response.status_code == 200
        assert response.json() == []
        
        # Verify response time is reasonable (this is a basic check)
        assert response.elapsed.total_seconds() < 1.0

    @pytest.mark.asyncio
    async def test_complex_filtering_performance(self, client, session, test_products):
        """Test performance with complex filter combinations"""
        await store_standardized_data(session, test_products)
        
        # Complex multi-parameter search
        response = await client.get("/search", params={
            "product_type": "mobile_plan",
            "provider": "Provider X",
            "min_contract_duration_months": 0,
            "max_contract_duration_months": 12,
            "available_only": True
        })
        
        assert response.status_code == 200
        results = response.json()
        assert len(results) >= 0  # Should handle complex queries without errors

# ------------------------ ERROR HANDLING TESTS ------------------------

class TestErrorHandling:
    """Test error handling and edge cases"""
    
    @pytest.mark.asyncio
    async def test_invalid_parameters(self, client):
        """Test handling of invalid query parameters"""
        # Test with invalid numeric values
        response = await client.get("/search", params={"min_price": "invalid"})
        # Should handle gracefully (either 422 validation error or ignore invalid params)
        assert response.status_code in [200, 422]
        
        response = await client.get("/search", params={"max_contract_duration_months": -1})
        assert response.status_code == 200  # Should handle negative values gracefully

    @pytest.mark.asyncio
    async def test_extreme_parameter_values(self, client, session, test_products):
        """Test handling of extreme parameter values"""
        await store_standardized_data(session, test_products)
        
        # Test with very large numbers
        response = await client.get("/search", params={"min_price": 999999})
        assert response.status_code == 200
        assert response.json() == []  # Should return empty results
        
        # Test with very small numbers
        response = await client.get("/search", params={"max_price": 0.001})
        assert response.status_code == 200
        # Should return results or empty list without errors