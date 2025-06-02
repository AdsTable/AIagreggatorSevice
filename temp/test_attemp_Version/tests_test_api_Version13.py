# test_api.py
import pytest
import sys
import os
import json
import asyncio
from typing import Dict, Any, List, Optional, AsyncIterator

# Add the parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import for FastAPI testing
from httpx import AsyncClient

# Import for database testing
from sqlmodel import SQLModel, Field, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker

# Import your application and models
from main import app
from database import get_session
from models import StandardizedProduct, ProductDB
from data_storage import store_standardized_data

# Import helper functions
from data_parser import (
    extract_float_with_units,
    extract_float_or_handle_unlimited,
    extract_duration_in_months,
    parse_availability,
    standardize_extracted_product,
    parse_and_standardize,
)

# Test database configuration
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

# Global test infrastructure
class TestDatabase:
    """Centralized test database management."""
    
    def __init__(self):
        self.engine = None
        self.session_maker = None
    
    async def setup(self):
        """Initialize test database."""
        if self.engine is None:
            self.engine = create_async_engine(
                TEST_DB_URL, 
                echo=False,
                future=True
            )
            
            # Create all tables
            async with self.engine.begin() as conn:
                await conn.run_sync(SQLModel.metadata.create_all)
            
            # Create session maker
            self.session_maker = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
    
    async def get_session(self) -> AsyncSession:
        """Get a new database session."""
        if self.session_maker is None:
            await self.setup()
        return self.session_maker()
    
    async def cleanup(self):
        """Clean up database resources."""
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self.session_maker = None

# Global test database instance
test_db = TestDatabase()

# --- FastAPI Dependency Override ---
async def get_test_session_for_api():
    """Dependency override for FastAPI - creates its own session."""
    session = await test_db.get_session()
    try:
        yield session
    finally:
        await session.close()

# --- Mock Functions ---
async def search_and_filter_products(
    session: AsyncSession,
    product_type: Optional[str] = None,
    provider: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_data_gb: Optional[float] = None,
    max_data_gb: Optional[float] = None,
    min_contract_duration_months: Optional[int] = None,
    max_contract_duration_months: Optional[int] = None,
    max_download_speed: Optional[float] = None
) -> List[StandardizedProduct]:
    """Mock function for searching and filtering products."""
    query = select(ProductDB)
    
    # Apply filters
    if product_type:
        query = query.where(ProductDB.category == product_type)
    if provider:
        query = query.where(ProductDB.provider_name == provider)
    if min_price is not None:
        query = query.where(ProductDB.price_kwh >= min_price)
    if max_price is not None:
        query = query.where(ProductDB.price_kwh <= max_price)
    if min_data_gb is not None:
        query = query.where(ProductDB.data_gb >= min_data_gb)
    if max_data_gb is not None:
        query = query.where(ProductDB.data_gb <= max_data_gb)
        query = query.where(ProductDB.data_cap_gb <= max_data_gb)
    if min_contract_duration_months is not None:
        query = query.where(ProductDB.contract_duration_months >= min_contract_duration_months)
    if max_contract_duration_months is not None:
        query = query.where(ProductDB.contract_duration_months <= max_contract_duration_months)
    if max_download_speed is not None:
        query = query.where(ProductDB.download_speed <= max_download_speed)
    
    result = await session.execute(query)
    db_products = result.scalars().all()
    
    # Convert back to StandardizedProduct
    standardized_products = []
    for db_product in db_products:
        raw_data = json.loads(db_product.raw_data_json) if db_product.raw_data_json else {}
        standardized_product = StandardizedProduct(
            source_url=db_product.source_url,
            category=db_product.category,
            name=db_product.name,
            provider_name=db_product.provider_name,
            price_kwh=db_product.price_kwh,
            standing_charge=db_product.standing_charge,
            contract_type=db_product.contract_type,
            monthly_cost=db_product.monthly_cost,
            contract_duration_months=db_product.contract_duration_months,
            data_gb=db_product.data_gb,
            calls=db_product.calls,
            texts=db_product.texts,
            network_type=db_product.network_type,
            download_speed=db_product.download_speed,
            upload_speed=db_product.upload_speed,
            connection_type=db_product.connection_type,
            data_cap_gb=db_product.data_cap_gb,
            available=db_product.available,
            raw_data=raw_data
        )
        standardized_products.append(standardized_product)
    
    return standardized_products

# --- Pytest Configuration ---
@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session", autouse=True)
async def setup_test_database():
    """Setup test database once for all tests."""
    await test_db.setup()
    yield
    await test_db.cleanup()

# --- Database Test Fixtures ---
@pytest.fixture
async def db_session():
    """
    Create an isolated database session for direct database testing.
    This fixture creates a real AsyncSession object with transaction isolation.
    """
    # Get a real session object (not a generator)
    session = await test_db.get_session()
    
    # Start transaction for isolation
    transaction = await session.begin()
    
    try:
        # Return the actual session object
        yield session
    finally:
        # Always rollback to ensure test isolation
        await transaction.rollback()
        await session.close()

# --- API Test Fixtures ---
@pytest.fixture
async def api_client():
    """
    Create test client for API testing with dependency override.
    This fixture handles FastAPI dependency injection properly.
    """
    # Override get_session dependency
    app.dependency_overrides[get_session] = get_test_session_for_api
    
    # Create async client
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    
    # Clean up dependency override
    app.dependency_overrides.clear()

# --- Test Data Fixtures ---
@pytest.fixture(name="test_products")
def test_products_fixture():
    """Provide test product data."""
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
            raw_data={"k": "v1"}
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
            raw_data={"k": "v2"}
        ),
        StandardizedProduct(
            source_url="https://example.com/mobile/plan_c",
            category="mobile_plan",
            name="Mobile Plan C",
            provider_name="Provider X",
            monthly_cost=30.0,
            data_gb=100.0,
            calls=float("inf"),
            texts=float("inf"),
            contract_duration_months=0,
            raw_data={"k": "v3"}
        ),
        StandardizedProduct(
            source_url="https://example.com/mobile/plan_d",
            category="mobile_plan",
            name="Mobile Plan D",
            provider_name="Provider Z",
            monthly_cost=45.0,
            data_gb=float("inf"),
            calls=500,
            texts=float("inf"),
            contract_duration_months=12,
            raw_data={"k": "v4"}
        ),
        StandardizedProduct(
            source_url="https://example.com/internet/plan_e",
            category="internet_plan",
            name="Internet Plan E",
            provider_name="Provider Y",
            download_speed=500.0,
            upload_speed=50.0,
            connection_type="Fiber",
            data_cap_gb=float("inf"),
            monthly_cost=60.0,
            contract_duration_months=24,
            raw_data={"k": "v5"}
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
            raw_data={"k": "v6"}
        ),
    ]

# --- Helper Function Tests ---
def test_extract_float_with_units():
    """Test float extraction with various units."""
    units = ["кВт·ч", "руб/кВт·ч", "ГБ"]
    unit_conversion = {"кВт·ч": 1.0, "руб/кВт·ч": 1.0, "ГБ": 1.0}
    
    assert extract_float_with_units("15.5 кВт·ч", units, unit_conversion) == 15.5
    assert extract_float_with_units("0.12 руб/кВт·ч", units, unit_conversion) == 0.12
    assert extract_float_with_units("100 ГБ", units, unit_conversion) == 100.0
    assert extract_float_with_units("no number", units, unit_conversion) is None

def test_extract_float_or_handle_unlimited():
    """Test handling of unlimited values."""
    unlimited_terms = ["безлимит", "unlimited", "неограниченно"]
    units = ["ГБ", "MB"]
    
    assert extract_float_or_handle_unlimited("безлимит", unlimited_terms, units) == float('inf')
    assert extract_float_or_handle_unlimited("unlimited", unlimited_terms, units) == float('inf')
    assert extract_float_or_handle_unlimited("100 ГБ", unlimited_terms, units) == 100.0
    assert extract_float_or_handle_unlimited("no number", unlimited_terms, units) is None

def test_parse_availability():
    """Test availability parsing."""
    assert parse_availability("в наличии") == True
    assert parse_availability("доступен") == True
    assert parse_availability("недоступен") == False
    assert parse_availability("unknown") == True

# --- Database Tests (using db_session fixture) ---
@pytest.mark.asyncio
async def test_session_fixture_works(db_session: AsyncSession):
    """Test that database session fixture works correctly."""
    result = await db_session.execute(select(1))
    assert result.scalar() == 1
    print("✓ Database session fixture is working correctly!")

@pytest.mark.asyncio
async def test_store_standardized_data(db_session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test data storage functionality."""
    # Verify database is empty initially
    result = await db_session.execute(select(ProductDB))
    existing = result.scalars().all()
    assert len(existing) == 0
    
    # Store test products
    await store_standardized_data(session=db_session, data=test_products)
    
    # Verify products were stored
    result = await db_session.execute(select(ProductDB))
    stored = result.scalars().all()
    assert len(stored) == len(test_products)
    
    # Check product names
    stored_names = {p.name for p in stored}
    expected_names = {p.name for p in test_products}
    assert stored_names == expected_names
    
    # Verify specific product details
    elec_plan = next((p for p in stored if p.name == "Elec Plan A"), None)
    assert elec_plan is not None
    assert elec_plan.category == "electricity_plan"
    assert elec_plan.price_kwh == 0.15
    assert json.loads(elec_plan.raw_data_json) == {"k": "v1"}

@pytest.mark.asyncio
async def test_search_and_filter_products(db_session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test search and filtering functionality."""
    # Ensure database is clean
    result = await db_session.execute(select(ProductDB))
    assert len(result.scalars().all()) == 0
    
    # Store test data
    await store_standardized_data(session=db_session, data=test_products)
    
    # Test: Search all products
    all_products = await search_and_filter_products(session=db_session)
    assert len(all_products) == len(test_products)
    assert {p.name for p in all_products} == {p.name for p in test_products}
    
    # Test: Filter by category
    electricity = await search_and_filter_products(session=db_session, product_type="electricity_plan")
    assert {p.name for p in electricity} == {"Elec Plan A", "Elec Plan B"}
    
    # Test: Filter by provider
    provider_x = await search_and_filter_products(session=db_session, provider="Provider X")
    assert {p.name for p in provider_x} == {"Elec Plan A", "Mobile Plan C", "Internet Plan F"}
    
    # Test: Filter by minimum price
    expensive_electricity = await search_and_filter_products(
        session=db_session,
        product_type="electricity_plan",
        min_price=0.13
    )
    assert {p.name for p in expensive_electricity} == {"Elec Plan A"}
    
    # Test: Filter by contract duration
    long_contracts = await search_and_filter_products(
        session=db_session,
        min_contract_duration_months=18
    )
    assert {p.name for p in long_contracts} == {"Elec Plan B", "Internet Plan E"}
    
    # Test: Filter by max data GB
    limited_data = await search_and_filter_products(
        session=db_session,
        product_type="mobile_plan", 
        max_data_gb=200
    )
    assert {p.name for p in limited_data} == {"Mobile Plan C"}
    
    # Test: No results case
    no_results = await search_and_filter_products(session=db_session, product_type="gas_plan")
    assert len(no_results) == 0

# --- API Tests (using api_client fixture) ---
@pytest.mark.asyncio
async def test_search_endpoint_no_filters(api_client: AsyncClient, db_session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test search endpoint with no filters."""
    # Store test data in database
    await store_standardized_data(session=db_session, data=test_products)
    
    # Test API endpoint
    response = await api_client.get("/search")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == len(test_products)
    
    # Verify response structure
    if data:
        sample_product = data[0]
        assert "source_url" in sample_product
        assert "category" in sample_product
        assert "name" in sample_product

@pytest.mark.asyncio
async def test_search_endpoint_filter_by_type(api_client: AsyncClient, db_session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test filtering search results by product type."""
    await store_standardized_data(session=db_session, data=test_products)
    
    response = await api_client.get("/search", params={"product_type": "mobile_plan"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert all(p["category"] == "mobile_plan" for p in data)
    assert any(p["name"] == "Mobile Plan C" for p in data)
    assert any(p["name"] == "Mobile Plan D" for p in data)

@pytest.mark.asyncio
async def test_search_endpoint_filter_by_min_price(api_client: AsyncClient, db_session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test filtering search results by minimum price."""
    await store_standardized_data(session=db_session, data=test_products)

    # Test electricity plans
    response_elec = await api_client.get("/search", params={"product_type": "electricity_plan", "min_price": 0.13})
    assert response_elec.status_code == 200
    data_elec = response_elec.json()
    assert len(data_elec) == 1
    assert data_elec[0]["name"] == "Elec Plan A"

    # Test internet plans
    response_internet = await api_client.get("/search", params={"product_type": "internet_plan", "min_price": 55.0})
    assert response_internet.status_code == 200
    data_internet = response_internet.json()
    assert len(data_internet) == 1
    assert data_internet[0]["name"] == "Internet Plan E"

@pytest.mark.asyncio
async def test_search_endpoint_filter_by_provider(api_client: AsyncClient, db_session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test filtering search results by provider name."""
    await store_standardized_data(session=db_session, data=test_products)
    
    response = await api_client.get("/search", params={"provider": "Provider X"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert all(p["provider_name"] == "Provider X" for p in data)
    assert any(p["name"] == "Elec Plan A" for p in data)
    assert any(p["name"] == "Mobile Plan C" for p in data)
    assert any(p["name"] == "Internet Plan F" for p in data)

@pytest.mark.asyncio
async def test_search_endpoint_filter_by_max_data_gb(api_client: AsyncClient, db_session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test filtering search results by maximum data allowance in GB."""
    await store_standardized_data(session=db_session, data=test_products)

    # Test mobile plans
    response_mobile = await api_client.get("/search", params={"product_type": "mobile_plan", "max_data_gb": 200.0})
    assert response_mobile.status_code == 200
    data_mobile = response_mobile.json()
    assert len(data_mobile) == 1
    assert data_mobile[0]["name"] == "Mobile Plan C"
    assert data_mobile[0]["data_gb"] == 100.0

    # Test internet plans
    response_internet = await api_client.get("/search", params={"product_type": "internet_plan", "max_data_cap_gb": 600.0})
    assert response_internet.status_code == 200
    data_internet = response_internet.json()
    assert len(data_internet) == 1
    assert data_internet[0]["name"] == "Internet Plan F"
    assert data_internet[0]["data_cap_gb"] == 500.0

@pytest.mark.asyncio
async def test_search_endpoint_filter_by_min_contract_duration(api_client: AsyncClient, db_session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test filtering search results by minimum contract duration in months."""
    await store_standardized_data(session=db_session, data=test_products)
    
    response = await api_client.get("/search", params={"min_contract_duration_months": 18})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert any(p["name"] == "Elec Plan B" for p in data)
    assert any(p["name"] == "Internet Plan E" for p in data)

@pytest.mark.asyncio
async def test_search_endpoint_combined_filters(api_client: AsyncClient, db_session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test filtering search results with multiple combined criteria."""
    await store_standardized_data(session=db_session, data=test_products)

    # Test combined filters
    response = await api_client.get(
        "/search",
        params={
            "product_type": "internet_plan",
            "provider": "Provider X",
            "max_data_cap_gb": 600.0
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Internet Plan F"
    assert data[0]["provider_name"] == "Provider X"
    assert data[0]["data_cap_gb"] == 500.0

    # Test speed filters
    response_speed = await api_client.get(
         "/search",
         params={
             "product_type": "internet_plan",
             "provider": "Provider Y",
             "max_download_speed": 600.0
         }
     )
    assert response_speed.status_code == 200
    data_speed = response_speed.json()
    assert len(data_speed) == 1
    assert data_speed[0]["name"] == "Internet Plan E"
    assert data_speed[0]["provider_name"] == "Provider Y"
    assert data_speed[0]["download_speed"] == 500.0

@pytest.mark.asyncio
async def test_search_endpoint_no_results(api_client: AsyncClient, db_session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test searching with criteria that yield no results."""
    await store_standardized_data(session=db_session, data=test_products)

    # Test non-existent product type
    response_type = await api_client.get("/search", params={"product_type": "gas_plan"})
    assert response_type.status_code == 200
    assert len(response_type.json()) == 0

    # Test filters that exclude all results
    response_filtered = await api_client.get("/search", params={"product_type": "electricity_plan", "min_price": 1.0})
    assert response_filtered.status_code == 200
    assert len(response_filtered.json()) == 0

@pytest.mark.asyncio
async def test_search_endpoint_all_filters(api_client: AsyncClient, db_session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test API search endpoint with various filters."""
    # Store test data
    await store_standardized_data(session=db_session, data=test_products)
    
    # Test by type
    response = await api_client.get("/search", params={"product_type": "mobile_plan"})
    assert response.status_code == 200
    assert {p["name"] for p in response.json()} == {"Mobile Plan C", "Mobile Plan D"}
    
    # Test combined filters
    response = await api_client.get("/search", params={
        "product_type": "internet_plan",
        "provider": "Provider X",
        "max_data_cap_gb": 600
    })
    assert response.status_code == 200
    assert {p["name"] for p in response.json()} == {"Internet Plan F"}
    
    # Test no results
    response = await api_client.get("/search", params={"product_type": "gas_plan"})
    assert response.status_code == 200
    assert response.json() == []

if __name__ == "__main__":
    # Run basic tests directly
    print("Running basic data parser tests...")
    
    try:
        test_extract_float_with_units()
        print("✓ Float extraction test passed")
    except Exception as e:
        print(f"✗ Float extraction test failed: {e}")
    
    try:
        test_extract_float_or_handle_unlimited()
        print("✓ Unlimited handling test passed")
    except Exception as e:
        print(f"✗ Unlimited handling test failed: {e}")
    
    try:
        test_parse_availability()
        print("✓ Availability parsing test passed")
    except Exception as e:
        print(f"✗ Availability parsing test failed: {e}")
    
    print("\nFor full test suite run: pytest test_api.py -v")
    print("Or run with more details: pytest test_api.py -v -s")