import pytest
import sys
import os
import json
import asyncio
from typing import Optional, List
from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from httpx import AsyncClient

# Correct import paths and dependencies
try:
    from main import app
    from database import get_session
    from models import StandardizedProduct, ProductDB
    from data_storage import store_standardized_data
    from data_parser import (
        extract_float_with_units,
        extract_float_or_handle_unlimited,
        extract_duration_in_months,
        parse_availability,
    )
except ImportError as e:
    pytest.fail(f"Import error: {e}")

# === TEST DATABASE SETUP ===

class TestDatabaseManager:
    """Manages test database lifecycle"""
    
    def __init__(self):
        self.engine = None
        self.session_factory = None
    
    async def setup(self):
        """Setup test database with proper cleanup"""
        db_url = "sqlite+aiosqlite:///:memory:"  # Use in-memory SQLite for tests
        self.engine = create_async_engine(
            db_url,
            echo=False,
            future=True,
        )
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)  # Drop all tables to avoid conflicts
            await conn.run_sync(SQLModel.metadata.create_all)  # Recreate all tables
        
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
    
    async def get_session(self) -> AsyncSession:
        """Get a new database session"""
        if not self.session_factory:
            await self.setup()
        return self.session_factory()
    
    async def cleanup(self):
        """Dispose engine after tests"""
        if self.engine:
            await self.engine.dispose()

# Global test database manager
test_db = TestDatabaseManager()

# === FIXTURES ===

@pytest.fixture(scope="session", autouse=True)
async def setup_test_environment():
    """Setup test environment once per session"""
    await test_db.setup()
    yield
    await test_db.cleanup()

@pytest.fixture
async def db_session():
    """Provide clean database session for each test"""
    session = await test_db.get_session()
    try:
        yield session
    finally:
        await session.close()

@pytest.fixture
def test_products():
    """Sample test data"""
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
            raw_data={"type": "electricity", "features": ["green", "fixed"]}
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
            raw_data={"type": "electricity", "features": ["variable"]}
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
            network_type="4G",
            available=True,
            raw_data={"type": "mobile", "features": ["unlimited_calls"]}
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
            network_type="5G",
            available=True,
            raw_data={"type": "mobile", "features": ["5G", "unlimited_data"]}
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
            available=True,
            raw_data={"type": "internet", "features": ["fiber", "unlimited"]}
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
            available=True,
            raw_data={"type": "internet", "features": ["dsl", "limited"]}
        ),
    ]

@pytest.fixture
async def api_client():
    """Create API client with test database"""
    async def get_test_session():
        session = await test_db.get_session()
        try:
            yield session
        finally:
            await session.close()
    
    # Override dependency
    app.dependency_overrides[get_session] = get_test_session
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()

# === TEST CLASSES ===

class TestDataParserFunctions:
    """Test data parsing helper functions"""
    
    def test_extract_float_with_units(self):
        units = ["кВт·ч", "руб/кВт·ч", "ГБ", "GB", "Mbps"]
        unit_conversion = {"кВт·ч": 1.0, "руб/кВт·ч": 1.0, "ГБ": 1.0, "GB": 1.0, "Mbps": 1.0}
        assert extract_float_with_units("15.5 кВт·ч", units, unit_conversion) == 15.5
    
    def test_extract_duration_in_months(self):
        month_terms = ["месяцев", "месяца", "months"]
        year_terms = ["год", "года", "лет", "year"]
        assert extract_duration_in_months("12 месяцев", month_terms, year_terms) == 12
    
    def test_parse_availability(self):
        assert parse_availability("available") is True
        assert parse_availability("unavailable") is False


class TestDatabase:
    """Test database operations"""
    
    @pytest.mark.asyncio
    async def test_session_fixture_works(self, db_session):
        """Test that database session works correctly"""
        result = await db_session.execute(select(1))
        assert result.scalar() == 1
    
    @pytest.mark.asyncio
    async def test_store_standardized_data(self, db_session, test_products):
        """Test storing standardized data"""
        await store_standardized_data(session=db_session, data=test_products)
        result = await db_session.execute(select(ProductDB))
        stored_products = result.scalars().all()
        assert len(stored_products) == len(test_products)


class TestSearchAndFilter:
    """Test search and filtering functionality"""
    
    @pytest.mark.asyncio
    async def test_search_all_products(self, db_session, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        result = await db_session.execute(select(ProductDB))
        all_products = result.scalars().all()
        assert len(all_products) == len(test_products)


class TestAPI:
    """Test FastAPI endpoints"""
    
    @pytest.mark.asyncio
    async def test_search_endpoint_no_filters(self, api_client, test_products):
        session = await test_db.get_session()
        await store_standardized_data(session=session, data=test_products)
        response = await api_client.get("/search")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == len(test_products)


class TestIntegration:
    """Integration tests combining multiple components"""
    
    @pytest.mark.asyncio
    async def test_full_workflow(self, db_session, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        result = await db_session.execute(select(ProductDB))
        all_products = result.scalars().all()
        assert len(all_products) == len(test_products)
