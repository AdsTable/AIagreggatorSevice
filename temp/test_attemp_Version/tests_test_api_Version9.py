# test_api.py
import pytest
import sys
import os
import json
from typing import Dict, Any, List, Optional, AsyncIterator, Generator, AsyncGenerator

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

# Create test database (use in-memory SQLite for testing)
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

# --- Session Management ---
class SessionHandler:
    """Handler for managing database sessions in tests."""
    
    def __init__(self):
        """Initialize session handler."""
        self.engine = None
        self.session_maker = None
    
    async def setup(self):
        """Set up database engine and create tables."""
        if self.engine is None:
            self.engine = create_async_engine(TEST_DB_URL, echo=False)
            
            # Create all tables
            async with self.engine.begin() as conn:
                await conn.run_sync(SQLModel.metadata.create_all)
            
            # Create session maker
            self.session_maker = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
    
    async def get_session(self):
        """Get a new database session."""
        if self.session_maker is None:
            await self.setup()
        return self.session_maker()
    
    async def dispose(self):
        """Dispose engine and cleanup resources."""
        if self.engine is not None:
            await self.engine.dispose()
            self.engine = None
            self.session_maker = None

# Create a session handler instance
session_handler = SessionHandler()

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
        # Filter out infinity values when max limit is specified
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

# --- Session Adapter ---
class SessionAdapter:
    """
    Adapter class that provides both direct access to session and
    FastAPI-compatible dependency with yield.
    """
    
    def __init__(self, session: AsyncSession):
        """Initialize with a session object."""
        self.session = session
    
    # Methods to directly use this object as session
    async def execute(self, *args, **kwargs):
        """Forward execute call to the underlying session."""
        return await self.session.execute(*args, **kwargs)
    
    async def commit(self):
        """Forward commit call to the underlying session."""
        return await self.session.commit()
    
    async def rollback(self):
        """Forward rollback call to the underlying session."""
        return await self.session.rollback()
    
    async def close(self):
        """Forward close call to the underlying session."""
        return await self.session.close()
    
    async def refresh(self, *args, **kwargs):
        """Forward refresh call to the underlying session."""
        return await self.session.refresh(*args, **kwargs)
    
    async def begin(self, *args, **kwargs):
        """Forward begin call to the underlying session."""
        return await self.session.begin(*args, **kwargs)
    
    async def get(self, *args, **kwargs):
        """Forward get call to the underlying session."""
        return await self.session.get(*args, **kwargs)
    
    def add(self, *args, **kwargs):
        """Forward add call to the underlying session."""
        return self.session.add(*args, **kwargs)
    
    def add_all(self, *args, **kwargs):
        """Forward add_all call to the underlying session."""
        return self.session.add_all(*args, **kwargs)
    
    def expunge(self, *args, **kwargs):
        """Forward expunge call to the underlying session."""
        return self.session.expunge(*args, **kwargs)
    
    def expunge_all(self, *args, **kwargs):
        """Forward expunge_all call to the underlying session."""
        return self.session.expunge_all(*args, **kwargs)
    
    def flush(self, *args, **kwargs):
        """Forward flush call to the underlying session."""
        return self.session.flush(*args, **kwargs)
    
    # FastAPI dependency injection pattern
    async def __call__(self) -> AsyncGenerator[AsyncSession, None]:
        """Make this class callable as a dependency provider."""
        yield self.session

# --- Fixtures ---
@pytest.fixture(scope="session", autouse=True)
async def setup_database():
    """Initialize the database before tests and clean up after."""
    await session_handler.setup()
    yield
    await session_handler.dispose()

@pytest.fixture
async def session():
    """Create a database session fixture for tests."""
    # Get an actual session
    raw_session = await session_handler.get_session()
    
    # Create our adapter that will be both a session and a dependency provider
    adapter = SessionAdapter(raw_session)
    
    # Start a transaction to isolate test data
    transaction = await adapter.begin()
    
    try:
        yield adapter  # Provide the adapter to tests
    finally:
        # Always rollback the transaction to isolate tests
        await transaction.rollback()
        await adapter.close()

@pytest.fixture
async def client(session):
    """Create a test client with dependency override."""
    # Our session is already an adapter that can be called as a dependency
    app.dependency_overrides[get_session] = session
    
    # Create and yield test client
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    
    # Clean up dependency override
    app.dependency_overrides.clear()

@pytest.fixture(name="test_products")
def test_products_fixture():
    """Fixture providing test products data."""
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
    assert parse_availability("unknown") == True  # Default to True

# --- Database Tests ---
@pytest.mark.asyncio
async def test_session_fixture_works(session: SessionAdapter):
    """Test that session fixture works correctly."""
    result = await session.execute(select(1))
    assert result.scalar() == 1
    print("✓ Session fixture is working correctly!")

@pytest.mark.asyncio
async def test_store_standardized_data(session: SessionAdapter, test_products: List[StandardizedProduct]):
    """Test data storage functionality."""
    # Ensure database is empty
    result = await session.execute(select(ProductDB))
    existing = result.scalars().all()
    assert len(existing) == 0
    
    # Store test products
    await store_standardized_data(session=session.session, data=test_products)
    
    # Verify storage
    result = await session.execute(select(ProductDB))
    stored = result.scalars().all()
    assert len(stored) == len(test_products)
    
    # Check names
    stored_names = {p.name for p in stored}
    expected_names = {p.name for p in test_products}
    assert stored_names == expected_names
    
    # Check specific product details
    elec_plan = next((p for p in stored if p.name == "Elec Plan A"), None)
    assert elec_plan is not None
    assert elec_plan.category == "electricity_plan"
    assert elec_plan.price_kwh == 0.15
    assert json.loads(elec_plan.raw_data_json) == {"k": "v1"}

@pytest.mark.asyncio
async def test_search_and_filter_products(session: SessionAdapter, test_products: List[StandardizedProduct]):
    """Test search and filtering functionality."""
    # Ensure database is clean
    result = await session.execute(select(ProductDB))
    assert len(result.scalars().all()) == 0
    
    # Store test data
    await store_standardized_data(session=session.session, data=test_products)
    
    # Test search all
    all_products = await search_and_filter_products(session=session.session)
    assert len(all_products) == len(test_products)
    assert {p.name for p in all_products} == {p.name for p in test_products}
    
    # Test filter by category
    electricity = await search_and_filter_products(session=session.session, product_type="electricity_plan")
    assert {p.name for p in electricity} == {"Elec Plan A", "Elec Plan B"}
    
    # Test filter by provider
    provider_x = await search_and_filter_products(session=session.session, provider="Provider X")
    assert {p.name for p in provider_x} == {"Elec Plan A", "Mobile Plan C", "Internet Plan F"}
    
    # Test minimum price filter (electricity_plan)
    expensive_electricity = await search_and_filter_products(
        session=session.session,
        product_type="electricity_plan",
        min_price=0.13
    )
    assert {p.name for p in expensive_electricity} == {"Elec Plan A"}
    
    # Test contract duration filter
    long_contracts = await search_and_filter_products(
        session=session.session,
        min_contract_duration_months=18
    )
    assert {p.name for p in long_contracts} == {"Elec Plan B", "Internet Plan E"}
    
    # Test max data GB filter (mobile_plan)
    limited_data = await search_and_filter_products(
        session=session.session,
        product_type="mobile_plan", 
        max_data_gb=200
    )
    assert {p.name for p in limited_data} == {"Mobile Plan C"}
    
    # Test no results
    no_results = await search_and_filter_products(session=session.session, product_type="gas_plan")
    assert len(no_results) == 0

# --- API Endpoint Tests ---
@pytest.mark.asyncio
async def test_search_endpoint_no_filters(client: AsyncClient, session: SessionAdapter, test_products: List[StandardizedProduct]):
    """Test search endpoint with no filters."""
    # Store test data
    await store_standardized_data(session=session.session, data=test_products)
    
    # Test: No filters
    response = await client.get("/search")
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
async def test_search_endpoint_filter_by_type(client: AsyncClient, session: SessionAdapter, test_products: List[StandardizedProduct]):
    """Test filtering search results by product type."""
    await store_standardized_data(session=session.session, data=test_products)
    
    response = await client.get("/search", params={"product_type": "mobile_plan"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2  # Should return two mobile plans
    assert all(p["category"] == "mobile_plan" for p in data)
    assert any(p["name"] == "Mobile Plan C" for p in data)
    assert any(p["name"] == "Mobile Plan D" for p in data)

@pytest.mark.asyncio
async def test_search_endpoint_filter_by_min_price(client: AsyncClient, session: SessionAdapter, test_products: List[StandardizedProduct]):
    """Test filtering search results by minimum price."""
    await store_standardized_data(session=session.session, data=test_products)

    # Filtering electricity plans by min_price
    response_elec = await client.get("/search", params={"product_type": "electricity_plan", "min_price": 0.13})
    assert response_elec.status_code == 200
    data_elec = response_elec.json()
    assert len(data_elec) == 1
    assert data_elec[0]["name"] == "Elec Plan A"

    # Filtering internet plans by min_price
    response_internet = await client.get("/search", params={"product_type": "internet_plan", "min_price": 55.0})
    assert response_internet.status_code == 200
    data_internet = response_internet.json()
    assert len(data_internet) == 1
    assert data_internet[0]["name"] == "Internet Plan E"

@pytest.mark.asyncio
async def test_search_endpoint_filter_by_provider(client: AsyncClient, session: SessionAdapter, test_products: List[StandardizedProduct]):
    """Test filtering search results by provider name."""
    await store_standardized_data(session=session.session, data=test_products)
    response = await client.get("/search", params={"provider": "Provider X"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert all(p["provider_name"] == "Provider X" for p in data)
    assert any(p["name"] == "Elec Plan A" for p in data)
    assert any(p["name"] == "Mobile Plan C" for p in data)
    assert any(p["name"] == "Internet Plan F" for p in data)

@pytest.mark.asyncio
async def test_search_endpoint_filter_by_max_data_gb(client: AsyncClient, session: SessionAdapter, test_products: List[StandardizedProduct]):
    """Test filtering search results by maximum data allowance in GB."""
    await store_standardized_data(session=session.session, data=test_products)

    # Filtering mobile plans by max_data_gb
    response_mobile = await client.get("/search", params={"product_type": "mobile_plan", "max_data_gb": 200.0})
    assert response_mobile.status_code == 200
    data_mobile = response_mobile.json()
    assert len(data_mobile) == 1
    assert data_mobile[0]["name"] == "Mobile Plan C"
    assert data_mobile[0]["data_gb"] == 100.0

    # Filtering internet plans by max_data_gb
    response_internet = await client.get("/search", params={"product_type": "internet_plan", "max_data_cap_gb": 600.0})
    assert response_internet.status_code == 200
    data_internet = response_internet.json()
    assert len(data_internet) == 1
    assert data_internet[0]["name"] == "Internet Plan F"
    assert data_internet[0]["data_cap_gb"] == 500.0

@pytest.mark.asyncio
async def test_search_endpoint_filter_by_min_contract_duration(client: AsyncClient, session: SessionAdapter, test_products: List[StandardizedProduct]):
    """Test filtering search results by minimum contract duration in months."""
    await store_standardized_data(session=session.session, data=test_products)
    response = await client.get("/search", params={"min_contract_duration_months": 18})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert any(p["name"] == "Elec Plan B" for p in data)
    assert any(p["name"] == "Internet Plan E" for p in data)

@pytest.mark.asyncio
async def test_search_endpoint_combined_filters(client: AsyncClient, session: SessionAdapter, test_products: List[StandardizedProduct]):
    """Test filtering search results with multiple combined criteria."""
    await store_standardized_data(session=session.session, data=test_products)

    # Filter for internet plans from Provider X with max data cap
    response = await client.get(
        "/search",
        params={
            "product_type": "internet_plan",
            "provider": "Provider X",
            "max_data_cap_gb": 600.0 # Internet Plan F has 500 GB data cap
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Internet Plan F"
    assert data[0]["provider_name"] == "Provider X"
    assert data[0]["data_cap_gb"] == 500.0

    # Test combined filtering: Internet plans from Provider Y with max download speed
    response_speed = await client.get(
         "/search",
         params={
             "product_type": "internet_plan",
             "provider": "Provider Y",
             "max_download_speed": 600.0 # Internet Plan E has 500 Mbps download speed
         }
     )
    assert response_speed.status_code == 200
    data_speed = response_speed.json()
    assert len(data_speed) == 1
    assert data_speed[0]["name"] == "Internet Plan E"
    assert data_speed[0]["provider_name"] == "Provider Y"
    assert data_speed[0]["download_speed"] == 500.0

@pytest.mark.asyncio
async def test_search_endpoint_no_results(client: AsyncClient, session: SessionAdapter, test_products: List[StandardizedProduct]):
    """Test searching with criteria that yield no results."""
    await store_standardized_data(session=session.session, data=test_products)

    # Search for a non-existent product type
    response_type = await client.get("/search", params={"product_type": "gas_plan"})
    assert response_type.status_code == 200
    assert len(response_type.json()) == 0

    # Search with filters that yield no results for an existing product type
    response_filtered = await client.get("/search", params={"product_type": "electricity_plan", "min_price": 1.0})
    assert response_filtered.status_code == 200
    assert len(response_filtered.json()) == 0

@pytest.mark.asyncio
async def test_search_endpoint_all_filters(client: AsyncClient, session: SessionAdapter, test_products: List[StandardizedProduct]):
    """Test API search endpoint with various filters."""
    # Store test data
    await store_standardized_data(session=session.session, data=test_products)
    
    # Test: Filter by type
    response = await client.get("/search", params={"product_type": "mobile_plan"})
    assert response.status_code == 200
    assert {p["name"] for p in response.json()} == {"Mobile Plan C", "Mobile Plan D"}
    
    # Test: Combined filters
    response = await client.get("/search", params={
        "product_type": "internet_plan",
        "provider": "Provider X",
        "max_data_cap_gb": 600
    })
    assert response.status_code == 200
    assert {p["name"] for p in response.json()} == {"Internet Plan F"}
    
    # Test: No results
    response = await client.get("/search", params={"product_type": "gas_plan"})
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