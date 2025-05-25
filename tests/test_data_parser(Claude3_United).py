# test_api.py - Claude-3 объединенная из Test_api-ok +test_api-claude-2 исправленна версия
import pytest
import sys
import os
import json
import math
import unittest.mock
from typing import AsyncIterator, List

# Add the parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import necessary components
from httpx import AsyncClient
from sqlmodel import SQLModel, select, Field
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from typing import Optional

# Import your application components
from main import app
from database import get_session
from models import StandardizedProduct
from data_storage import store_standardized_data

# Define ProductDB model for testing (with fixes for table redefinition)
class ProductDB(SQLModel, table=True):
    """Database model for storing standardized products"""
    __tablename__ = "productdb"
    __table_args__ = {'extend_existing': True}  # Allow table redefinition
    
    id: Optional[int] = Field(default=None, primary_key=True)
    source_url: str = Field(index=True)
    category: str = Field(index=True)
    name: Optional[str] = None
    provider_name: Optional[str] = Field(default=None, index=True)
    
    # Electricity-specific fields
    price_kwh: Optional[float] = None
    standing_charge: Optional[float] = None
    contract_type: Optional[str] = None
    
    # Mobile/Internet common fields
    monthly_cost: Optional[float] = None
    contract_duration_months: Optional[int] = None
    
    # Mobile-specific fields
    data_gb: Optional[float] = None
    calls: Optional[float] = None
    texts: Optional[float] = None
    network_type: Optional[str] = None
    
    # Internet-specific fields
    download_speed: Optional[float] = None
    upload_speed: Optional[float] = None
    connection_type: Optional[str] = None
    data_cap_gb: Optional[float] = None
    
    # Common fields
    available: Optional[bool] = Field(default=True)
    raw_data_json: Optional[str] = None

# --- Pytest Fixtures --- 

@pytest.fixture(name="engine", scope="function")
async def engine_fixture():
    """Fixture for creating and disposing of the async database engine."""
    # Clear metadata to prevent table redefinition errors
    SQLModel.metadata.clear()
    
    # Use in-memory SQLite database for testing
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    
    yield engine
    
    # Cleanup
    await engine.dispose()

@pytest.fixture(name="session")
async def session_fixture(engine) -> AsyncIterator[AsyncSession]:
    """Async database session fixture with proper transaction management."""
    # Create session factory
    async_session_factory = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    # Create session with transaction management
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

@pytest.fixture(name="client")
async def client_fixture(session: AsyncSession):
    """Fixture for creating AsyncClient with dependency override."""
    # Override get_session dependency
    async def override_get_session():
        return session
    
    app.dependency_overrides[get_session] = override_get_session
    
    # Create async client
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    
    # Cleanup dependency override
    app.dependency_overrides.clear()

@pytest.fixture(name="test_products")
def test_products_fixture() -> List[StandardizedProduct]:
    """Provides test products covering different scenarios."""
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
            calls=math.inf,
            texts=math.inf,
            contract_duration_months=0,
            raw_data={"k": "v3"}
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
            data_cap_gb=math.inf,
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

# --- Mock store_standardized_data function for testing ---
async def mock_store_standardized_data(session: AsyncSession, data: List[StandardizedProduct]) -> None:
    """Mock function to store standardized data in database"""
    for product in data:
        db_product = ProductDB(
            source_url=product.source_url,
            category=product.category,
            name=product.name,
            provider_name=product.provider_name,
            price_kwh=product.price_kwh,
            standing_charge=product.standing_charge,
            contract_type=product.contract_type,
            monthly_cost=product.monthly_cost,
            contract_duration_months=product.contract_duration_months,
            data_gb=product.data_gb,
            calls=product.calls,
            texts=product.texts,
            network_type=product.network_type,
            download_speed=product.download_speed,
            upload_speed=product.upload_speed,
            connection_type=product.connection_type,
            data_cap_gb=product.data_cap_gb,
            available=product.available,
            raw_data_json=json.dumps(product.raw_data) if product.raw_data else None
        )
        session.add(db_product)
    await session.commit()

# --- API Tests ---

@pytest.mark.asyncio
async def test_search_endpoint_no_filters(client: AsyncClient, session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test searching with no filters returns all products."""
    await mock_store_standardized_data(session=session, data=test_products)
    
    response = await client.get("/search")
    assert response.status_code == 200
    
    data = response.json()
    assert len(data) == len(test_products)
    
    if data:
        sample_product = data[0]
        assert "source_url" in sample_product
        assert "category" in sample_product
        assert "name" in sample_product

@pytest.mark.asyncio
async def test_search_endpoint_filter_by_type(client: AsyncClient, session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test filtering search results by product type."""
    await mock_store_standardized_data(session=session, data=test_products)
    
    response = await client.get("/search", params={"product_type": "mobile_plan"})
    assert response.status_code == 200
    
    data = response.json()
    assert len(data) == 2  # Mobile Plan C and D
    assert all(p["category"] == "mobile_plan" for p in data)
    assert any(p["name"] == "Mobile Plan C" for p in data)
    assert any(p["name"] == "Mobile Plan D" for p in data)

@pytest.mark.asyncio
async def test_search_endpoint_filter_by_provider(client: AsyncClient, session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test filtering search results by provider name."""
    await mock_store_standardized_data(session=session, data=test_products)
    
    response = await client.get("/search", params={"provider": "Provider X"})
    assert response.status_code == 200
    
    data = response.json()
    assert len(data) == 3  # Elec A, Mobile C, Internet F
    assert all(p["provider_name"] == "Provider X" for p in data)

@pytest.mark.asyncio
async def test_search_endpoint_filter_by_min_price(client: AsyncClient, session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test filtering search results by minimum price."""
    await mock_store_standardized_data(session=session, data=test_products)
    
    # Test electricity plans by price_kwh
    response = await client.get("/search", params={"product_type": "electricity_plan", "min_price": 0.13})
    assert response.status_code == 200
    
    data = response.json()
    assert len(data) == 1  # Only Elec Plan A (0.15) > 0.13
    assert data[0]["name"] == "Elec Plan A"

@pytest.mark.asyncio
async def test_search_endpoint_filter_by_max_data_gb(client: AsyncClient, session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test filtering search results by maximum data allowance."""
    await mock_store_standardized_data(session=session, data=test_products)
    
    # Test mobile plans with finite data limit
    response = await client.get("/search", params={"product_type": "mobile_plan", "max_data_gb": 200.0})
    assert response.status_code == 200
    
    data = response.json()
    assert len(data) == 1  # Only Mobile Plan C (100 GB) fits
    assert data[0]["name"] == "Mobile Plan C"
    assert data[0]["data_gb"] == 100.0

@pytest.mark.asyncio
async def test_search_endpoint_filter_by_min_contract_duration(client: AsyncClient, session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test filtering search results by minimum contract duration."""
    await mock_store_standardized_data(session=session, data=test_products)
    
    response = await client.get("/search", params={"min_contract_duration_months": 18})
    assert response.status_code == 200
    
    data = response.json()
    assert len(data) == 2  # Elec Plan B (24mo), Internet Plan E (24mo)
    names = [p["name"] for p in data]
    assert "Elec Plan B" in names
    assert "Internet Plan E" in names

@pytest.mark.asyncio
async def test_search_endpoint_combined_filters(client: AsyncClient, session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test filtering with multiple combined criteria."""
    await mock_store_standardized_data(session=session, data=test_products)
    
    response = await client.get(
        "/search",
        params={
            "product_type": "internet_plan",
            "provider": "Provider X",
            "max_data_gb": 600.0
        }
    )
    assert response.status_code == 200
    
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Internet Plan F"
    assert data[0]["provider_name"] == "Provider X"
    assert data[0]["data_cap_gb"] == 500.0

@pytest.mark.asyncio
async def test_search_endpoint_no_results(client: AsyncClient, session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test searching with criteria that yield no results."""
    await mock_store_standardized_data(session=session, data=test_products)
    
    # Search for non-existent product type
    response = await client.get("/search", params={"product_type": "gas_plan"})
    assert response.status_code == 200
    assert len(response.json()) == 0
    
    # Search with impossible price filter
    response = await client.get("/search", params={"product_type": "electricity_plan", "min_price": 1.0})
    assert response.status_code == 200
    assert len(response.json()) == 0

@pytest.mark.asyncio
@unittest.mock.patch("main.discover_and_extract_data")
async def test_ingest_data_endpoint(mock_discover_and_extract_data, client: AsyncClient, session: AsyncSession):
    """Test the /ingest_data endpoint with mocked data discovery."""
    # Mock raw data that would be returned by discover_and_extract_data
    mock_raw_data = [
        {
            "source_url": "https://example.com/elec/plan_a",
            "category": "electricity_plan",
            "plan_title": "Elec Plan A Raw",
            "provider_name_on_page": "Provider X",
            "kwh_price_text": "0.15 £/kWh",
            "standing_charge_daily_text": "5.0 £/day",
            "contract_term_text": "12 months",
            "availability_status": "Available"
        },
        {
            "source_url": "https://example.com/mobile/plan_c",
            "category": "mobile_plan",
            "plan_title": "Mobile Plan C Raw",
            "provider_name_on_page": "Provider X",
            "monthly_price_text": "30.0 $/month",
            "data_allowance_text": "Unlimited Data",
            "calls_info": "Unlimited Calls",
            "texts_info": "Unlimited Texts",
            "contract_term_text": "No contract"
        }
    ]
    
    # Configure mock
    mock_discover_and_extract_data.return_value = mock_raw_data
    
    # Make request to ingest endpoint
    response = await client.post("/ingest_data")
    
    # Verify response
    assert response.status_code == 200
    assert response.json() == {"message": "Data ingestion initiated"}
    
    # Verify mock was called
    mock_discover_and_extract_data.assert_called_once()
    
    # Verify data was processed and stored
    stored_products = await session.execute(select(ProductDB))
    stored_products_list = stored_products.scalars().all()
    
    # Should have at least the mocked products stored
    assert len(stored_products_list) >= len(mock_raw_data)
    
    # Verify specific products were stored
    stored_names = [p.name for p in stored_products_list]
    assert "Elec Plan A Raw" in stored_names
    assert "Mobile Plan C Raw" in stored_names