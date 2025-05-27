# test_api.py
import pytest
import pytest_asyncio
import sys
import os
import json
import asyncio
from typing import Dict, Any, List, Optional, AsyncIterator, AsyncContextManager
from contextlib import asynccontextmanager

# Add the parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import for FastAPI testing
from httpx import AsyncClient
import httpx

# Import for database testing
from sqlmodel import SQLModel, Field, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

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

# Modern test database configuration
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

# === Modern Session Factory Pattern ===
class AsyncSessionFactory:
    """Modern session factory using best practices 2025."""
    
    def __init__(self):
        self._engine = None
        self._session_factory = None
    
    async def initialize(self):
        """Initialize the async engine and session factory."""
        if self._engine is None:
            self._engine = create_async_engine(
                TEST_DB_URL,
                echo=False,
                future=True,
                poolclass=StaticPool,
                pool_pre_ping=True,
                connect_args={"check_same_thread": False}
            )
            
            # Create tables
            async with self._engine.begin() as conn:
                await conn.run_sync(SQLModel.metadata.create_all)
            
            # Create session factory
            self._session_factory = async_sessionmaker(
                self._engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
                autocommit=False
            )
    
    @asynccontextmanager
    async def get_session(self) -> AsyncContextManager[AsyncSession]:
        """Get a session with proper context management."""
        if self._session_factory is None:
            await self.initialize()
        
        async with self._session_factory() as session:
            yield session
    
    @asynccontextmanager
    async def get_transactional_session(self) -> AsyncContextManager[AsyncSession]:
        """Get a session with transaction rollback for test isolation."""
        if self._session_factory is None:
            await self.initialize()
        
        async with self._session_factory() as session:
            async with session.begin() as transaction:
                try:
                    yield session
                finally:
                    await transaction.rollback()
    
    async def close(self):
        """Close the engine and cleanup."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None

# Global session factory instance
session_factory = AsyncSessionFactory()

# === FastAPI Dependency Override ===
async def get_test_session_dependency():
    """Modern dependency override for FastAPI."""
    async with session_factory.get_session() as session:
        yield session

# === Mock Functions ===
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
    """Modern implementation of search and filter function."""
    query = select(ProductDB)
    
    # Apply filters efficiently
    filters = []
    if product_type:
        filters.append(ProductDB.category == product_type)
    if provider:
        filters.append(ProductDB.provider_name == provider)
    if min_price is not None:
        filters.append(ProductDB.price_kwh >= min_price)
    if max_price is not None:
        filters.append(ProductDB.price_kwh <= max_price)
    if min_data_gb is not None:
        filters.append(ProductDB.data_gb >= min_data_gb)
    if max_data_gb is not None:
        filters.extend([
            ProductDB.data_gb <= max_data_gb,
            ProductDB.data_cap_gb <= max_data_gb
        ])
    if min_contract_duration_months is not None:
        filters.append(ProductDB.contract_duration_months >= min_contract_duration_months)
    if max_contract_duration_months is not None:
        filters.append(ProductDB.contract_duration_months <= max_contract_duration_months)
    if max_download_speed is not None:
        filters.append(ProductDB.download_speed <= max_download_speed)
    
    if filters:
        query = query.where(*filters)
    
    result = await session.execute(query)
    db_products = result.scalars().all()
    
    # Convert to StandardizedProduct objects
    return [
        StandardizedProduct(
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
            raw_data=json.loads(db_product.raw_data_json) if db_product.raw_data_json else {}
        )
        for db_product in db_products
    ]

# === Modern Pytest Configuration ===
@pytest_asyncio.fixture(scope="session")
async def setup_test_environment():
    """Initialize test environment once per session."""
    await session_factory.initialize()
    yield
    await session_factory.close()

@pytest_asyncio.fixture
async def db_session():
    """
    Get a database session with automatic transaction rollback.
    Uses modern context manager approach.
    """
    async with session_factory.get_transactional_session() as session:
        yield session

@pytest_asyncio.fixture
async def api_client(setup_test_environment):
    """
    Create FastAPI test client with proper dependency override.
    """
    # Override dependency
    app.dependency_overrides[get_session] = get_test_session_dependency
    
    try:
        async with AsyncClient(app=app, base_url="http://test") as client:
            yield client
    finally:
        # Always clean up
        app.dependency_overrides.clear()

@pytest.fixture(name="test_products")
def test_products_fixture():
    """Test data fixture."""
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

# === Helper Function Tests (Non-async) ===
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

# === Database Tests (Using Modern Async Context Managers) ===
@pytest_asyncio.asyncio
async def test_session_fixture_works(db_session: AsyncSession):
    """Test that database session works correctly."""
    result = await db_session.execute(select(1))
    assert result.scalar() == 1
    print("✓ Modern database session is working correctly!")

@pytest_asyncio.asyncio
async def test_store_standardized_data(db_session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test data storage with modern approach."""
    # Verify initial state
    result = await db_session.execute(select(ProductDB))
    existing = result.scalars().all()
    assert len(existing) == 0
    
    # Store products
    await store_standardized_data(session=db_session, data=test_products)
    
    # Verify storage
    result = await db_session.execute(select(ProductDB))
    stored = result.scalars().all()
    assert len(stored) == len(test_products)
    
    # Validate stored data
    stored_names = {p.name for p in stored}
    expected_names = {p.name for p in test_products}
    assert stored_names == expected_names
    
    # Check specific product
    elec_plan = next((p for p in stored if p.name == "Elec Plan A"), None)
    assert elec_plan is not None
    assert elec_plan.category == "electricity_plan"
    assert elec_plan.price_kwh == 0.15
    assert json.loads(elec_plan.raw_data_json) == {"k": "v1"}

@pytest_asyncio.asyncio
async def test_search_and_filter_products(db_session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test search functionality with comprehensive filtering."""
    # Ensure clean state
    result = await db_session.execute(select(ProductDB))
    assert len(result.scalars().all()) == 0
    
    # Store test data
    await store_standardized_data(session=db_session, data=test_products)
    
    # Test: Search all
    all_products = await search_and_filter_products(session=db_session)
    assert len(all_products) == len(test_products)
    assert {p.name for p in all_products} == {p.name for p in test_products}
    
    # Test: Filter by category
    electricity = await search_and_filter_products(session=db_session, product_type="electricity_plan")
    assert {p.name for p in electricity} == {"Elec Plan A", "Elec Plan B"}
    
    # Test: Filter by provider
    provider_x = await search_and_filter_products(session=db_session, provider="Provider X")
    assert {p.name for p in provider_x} == {"Elec Plan A", "Mobile Plan C", "Internet Plan F"}
    
    # Test: Complex filtering
    expensive_electricity = await search_and_filter_products(
        session=db_session,
        product_type="electricity_plan",
        min_price=0.13
    )
    assert {p.name for p in expensive_electricity} == {"Elec Plan A"}
    
    # Test: Contract duration
    long_contracts = await search_and_filter_products(
        session=db_session,
        min_contract_duration_months=18
    )
    assert {p.name for p in long_contracts} == {"Elec Plan B", "Internet Plan E"}
    
    # Test: Data limits
    limited_data = await search_and_filter_products(
        session=db_session,
        product_type="mobile_plan", 
        max_data_gb=200
    )
    assert {p.name for p in limited_data} == {"Mobile Plan C"}
    
    # Test: No results
    no_results = await search_and_filter_products(session=db_session, product_type="gas_plan")
    assert len(no_results) == 0

# === API Tests (Using Modern FastAPI Testing) ===
@pytest_asyncio.asyncio
async def test_search_endpoint_no_filters(api_client: AsyncClient, db_session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test API endpoint without filters."""
    # Setup data
    await store_standardized_data(session=db_session, data=test_products)
    
    # Test endpoint
    response = await api_client.get("/search")
    assert response.status_code == 200
    
    data = response.json()
    assert len(data) == len(test_products)
    
    # Validate response structure
    if data:
        sample = data[0]
        required_fields = ["source_url", "category", "name"]
        assert all(field in sample for field in required_fields)

@pytest_asyncio.asyncio
async def test_search_endpoint_filter_by_type(api_client: AsyncClient, db_session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test API filtering by product type."""
    await store_standardized_data(session=db_session, data=test_products)
    
    response = await api_client.get("/search", params={"product_type": "mobile_plan"})
    assert response.status_code == 200
    
    data = response.json()
    assert len(data) == 2
    assert all(p["category"] == "mobile_plan" for p in data)
    
    names = {p["name"] for p in data}
    assert names == {"Mobile Plan C", "Mobile Plan D"}

@pytest_asyncio.asyncio
async def test_search_endpoint_filter_by_min_price(api_client: AsyncClient, db_session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test API filtering by minimum price."""
    await store_standardized_data(session=db_session, data=test_products)

    # Test electricity plans
    response = await api_client.get("/search", params={
        "product_type": "electricity_plan", 
        "min_price": 0.13
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Elec Plan A"

    # Test internet plans
    response = await api_client.get("/search", params={
        "product_type": "internet_plan", 
        "min_price": 55.0
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Internet Plan E"

@pytest_asyncio.asyncio
async def test_search_endpoint_filter_by_provider(api_client: AsyncClient, db_session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test API filtering by provider."""
    await store_standardized_data(session=db_session, data=test_products)
    
    response = await api_client.get("/search", params={"provider": "Provider X"})
    assert response.status_code == 200
    
    data = response.json()
    assert len(data) == 3
    assert all(p["provider_name"] == "Provider X" for p in data)
    
    names = {p["name"] for p in data}
    assert names == {"Elec Plan A", "Mobile Plan C", "Internet Plan F"}

@pytest_asyncio.asyncio
async def test_search_endpoint_filter_by_max_data_gb(api_client: AsyncClient, db_session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test API filtering by data limits."""
    await store_standardized_data(session=db_session, data=test_products)

    # Mobile plans
    response = await api_client.get("/search", params={
        "product_type": "mobile_plan", 
        "max_data_gb": 200.0
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Mobile Plan C"
    assert data[0]["data_gb"] == 100.0

    # Internet plans
    response = await api_client.get("/search", params={
        "product_type": "internet_plan", 
        "max_data_cap_gb": 600.0
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Internet Plan F"
    assert data[0]["data_cap_gb"] == 500.0

@pytest_asyncio.asyncio
async def test_search_endpoint_filter_by_min_contract_duration(api_client: AsyncClient, db_session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test API filtering by contract duration."""
    await store_standardized_data(session=db_session, data=test_products)
    
    response = await api_client.get("/search", params={"min_contract_duration_months": 18})
    assert response.status_code == 200
    
    data = response.json()
    assert len(data) == 2
    
    names = {p["name"] for p in data}
    assert names == {"Elec Plan B", "Internet Plan E"}

@pytest_asyncio.asyncio
async def test_search_endpoint_combined_filters(api_client: AsyncClient, db_session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test API with multiple combined filters."""
    await store_standardized_data(session=db_session, data=test_products)

    # Combined filters test 1
    response = await api_client.get("/search", params={
        "product_type": "internet_plan",
        "provider": "Provider X",
        "max_data_cap_gb": 600.0
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Internet Plan F"
    assert data[0]["provider_name"] == "Provider X"
    assert data[0]["data_cap_gb"] == 500.0

    # Combined filters test 2
    response = await api_client.get("/search", params={
        "product_type": "internet_plan",
        "provider": "Provider Y",
        "max_download_speed": 600.0
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Internet Plan E"
    assert data[0]["provider_name"] == "Provider Y"
    assert data[0]["download_speed"] == 500.0

@pytest_asyncio.asyncio
async def test_search_endpoint_no_results(api_client: AsyncClient, db_session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test API with filters that return no results."""
    await store_standardized_data(session=db_session, data=test_products)

    # Non-existent product type
    response = await api_client.get("/search", params={"product_type": "gas_plan"})
    assert response.status_code == 200
    assert len(response.json()) == 0

    # Impossible filter combination
    response = await api_client.get("/search", params={
        "product_type": "electricity_plan", 
        "min_price": 1.0
    })
    assert response.status_code == 200
    assert len(response.json()) == 0

@pytest_asyncio.asyncio
async def test_search_endpoint_all_filters(api_client: AsyncClient, db_session: AsyncSession, test_products: List[StandardizedProduct]):
    """Comprehensive API filtering test."""
    await store_standardized_data(session=db_session, data=test_products)
    
    # Filter by type
    response = await api_client.get("/search", params={"product_type": "mobile_plan"})
    assert response.status_code == 200
    names = {p["name"] for p in response.json()}
    assert names == {"Mobile Plan C", "Mobile Plan D"}
    
    # Complex combination
    response = await api_client.get("/search", params={
        "product_type": "internet_plan",
        "provider": "Provider X",
        "max_data_cap_gb": 600
    })
    assert response.status_code == 200
    names = {p["name"] for p in response.json()}
    assert names == {"Internet Plan F"}
    
    # No results
    response = await api_client.get("/search", params={"product_type": "gas_plan"})
    assert response.status_code == 200
    assert response.json() == []

if __name__ == "__main__":
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
    print("Or with async support: pytest test_api.py -v --asyncio-mode=auto")