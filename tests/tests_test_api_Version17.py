# FIXED VERSION - Replace your session creation functions with these:

import pytest
import sys
import os
import json
import asyncio
from typing import Dict, Any, List, Optional, AsyncIterator
from contextlib import asynccontextmanager

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# FastAPI testing imports
from httpx import AsyncClient

# Database imports
from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

# Application imports
from main import app
from database import get_session
from models import StandardizedProduct, ProductDB
from data_storage import store_standardized_data

# Helper functions
from data_parser import (
    extract_float_with_units,
    extract_float_or_handle_unlimited,
    extract_duration_in_months,
    parse_availability,
    standardize_extracted_product,
    parse_and_standardize,
)

# === FIXED SESSION CREATION ===

# Test database URL
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

# Global engine for reuse
_test_engine = None
_session_factory = None

async def get_test_engine():
    """Get or create test database engine."""
    global _test_engine, _session_factory
    
    if _test_engine is None:
        _test_engine = create_async_engine(
            TEST_DB_URL,
            echo=False,
            future=True,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False}
        )
        
        # Create tables
        async with _test_engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        
        # Create session factory
        _session_factory = async_sessionmaker(
            _test_engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
    
    return _test_engine, _session_factory

async def cleanup_test_engine():
    """Cleanup test resources."""
    global _test_engine, _session_factory
    if _test_engine:
        await _test_engine.dispose()
        _test_engine = None
        _session_factory = None

# === FIXED HELPER FUNCTIONS ===

async def create_test_session() -> AsyncSession:
    """FIXED: Создать тестовую сессию БД - возвращает РЕАЛЬНУЮ сессию!"""
    engine, factory = await get_test_engine()
    session = factory()  # This creates the actual AsyncSession object
    return session

async def create_isolated_session() -> AsyncSession:
    """FIXED: Создать изолированную сессию - возвращает РЕАЛЬНУЮ сессию!"""
    session = await create_test_session()
    # НЕ начинаем транзакцию здесь - это может вызвать проблемы
    return session

async def cleanup_session(session: AsyncSession):
    """Очистить сессию после теста."""
    try:
        if session.in_transaction():
            await session.rollback()
        await session.close()
    except Exception:
        pass  # Ignore cleanup errors

# FIXED: FastAPI dependency override
async def get_test_session_for_api():
    """FIXED: Dependency для FastAPI - правильный yield."""
    engine, factory = await get_test_engine()
    async with factory() as session:  # Используем context manager
        yield session

# === SEARCH FUNCTION (без изменений) ===
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
    """Search and filter products."""
    query = select(ProductDB)
    
    # Build filters
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
    
    # Convert to StandardizedProduct
    standardized_products = []
    for db_product in db_products:
        raw_data = json.loads(db_product.raw_data_json) if db_product.raw_data_json else {}
        product = StandardizedProduct(
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
        standardized_products.append(product)
    
    return standardized_products

# === PYTEST SETUP ===

@pytest.fixture(scope="session", autouse=True)
async def setup_test_db():
    """Setup test database once."""
    await get_test_engine()
    yield
    await cleanup_test_engine()

@pytest.fixture
def test_products():
    """Test data."""
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

# === HELPER TESTS (NON-ASYNC) ===

def test_extract_float_with_units():
    """Test float extraction."""
    units = ["кВт·ч", "руб/кВт·ч", "ГБ"]
    unit_conversion = {"кВт·ч": 1.0, "руб/кВт·ч": 1.0, "ГБ": 1.0}
    
    assert extract_float_with_units("15.5 кВт·ч", units, unit_conversion) == 15.5
    assert extract_float_with_units("0.12 руб/кВт·ч", units, unit_conversion) == 0.12
    assert extract_float_with_units("100 ГБ", units, unit_conversion) == 100.0
    assert extract_float_with_units("no number", units, unit_conversion) is None

def test_extract_float_or_handle_unlimited():
    """Test unlimited handling."""
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

# === FIXED DATABASE TESTS ===

@pytest.mark.asyncio
async def test_session_fixture_works():
    """Test session creation."""
    session = await create_test_session()
    try:
        result = await session.execute(select(1))
        assert result.scalar() == 1
        print("✓ Session works!")
    finally:
        await cleanup_session(session)

@pytest.mark.asyncio
async def test_store_standardized_data(test_products):
    """Test data storage."""
    session = await create_test_session()
    try:
        # Check empty
        result = await session.execute(select(ProductDB))
        assert len(result.scalars().all()) == 0
        
        # Store data
        await store_standardized_data(session=session, data=test_products)
        
        # Verify
        result = await session.execute(select(ProductDB))
        stored = result.scalars().all()
        assert len(stored) == len(test_products)
        
        # Check names
        stored_names = {p.name for p in stored}
        expected_names = {p.name for p in test_products}
        assert stored_names == expected_names
        
        # Check specific product
        elec_plan = next((p for p in stored if p.name == "Elec Plan A"), None)
        assert elec_plan is not None
        assert elec_plan.category == "electricity_plan"
        assert elec_plan.price_kwh == 0.15
        assert json.loads(elec_plan.raw_data_json) == {"k": "v1"}
        
    finally:
        await cleanup_session(session)

@pytest.mark.asyncio
async def test_search_and_filter_products(test_products):
    """Test search functionality."""
    session = await create_test_session()
    try:
        # Store test data
        await store_standardized_data(session=session, data=test_products)
        
        # Test: All products
        all_products = await search_and_filter_products(session=session)
        assert len(all_products) == len(test_products)
        
        # Test: By category
        electricity = await search_and_filter_products(session=session, product_type="electricity_plan")
        assert {p.name for p in electricity} == {"Elec Plan A", "Elec Plan B"}
        
        # Test: By provider
        provider_x = await search_and_filter_products(session=session, provider="Provider X")
        assert {p.name for p in provider_x} == {"Elec Plan A", "Mobile Plan C", "Internet Plan F"}
        
        # Test: By price
        expensive = await search_and_filter_products(
            session=session,
            product_type="electricity_plan",
            min_price=0.13
        )
        assert {p.name for p in expensive} == {"Elec Plan A"}
        
        # Test: By contract duration
        long_contracts = await search_and_filter_products(
            session=session,
            min_contract_duration_months=18
        )
        assert {p.name for p in long_contracts} == {"Elec Plan B", "Internet Plan E"}
        
        # Test: By data
        limited_data = await search_and_filter_products(
            session=session,
            product_type="mobile_plan",
            max_data_gb=200
        )
        assert {p.name for p in limited_data} == {"Mobile Plan C"}
        
        # Test: No results
        no_results = await search_and_filter_products(session=session, product_type="gas_plan")
        assert len(no_results) == 0
        
    finally:
        await cleanup_session(session)

# === FIXED API TESTS ===

@pytest.fixture
async def api_client():
    """Create API client."""
    app.dependency_overrides[get_session] = get_test_session_for_api
    try:
        async with AsyncClient(app=app, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_search_endpoint_no_filters(api_client, test_products):
    """Test API without filters."""
    # Setup data
    session = await create_test_session()
    try:
        await store_standardized_data(session=session, data=test_products)
    finally:
        await cleanup_session(session)
    
    # Test API
    response = await api_client.get("/search")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == len(test_products)
    
    if data:
        sample = data[0]
        assert "source_url" in sample
        assert "category" in sample
        assert "name" in sample

# Остальные API тесты остаются такими же, просто заменяем create_isolated_session на create_test_session
# ... (остальные тесты идентичны, только с исправленными функциями создания сессий)

if __name__ == "__main__":
    print("=== Running Tests ===")
    
    # Basic tests
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
    
    print("\nFull test suite: pytest test_api_final.py -v --asyncio-mode=auto")