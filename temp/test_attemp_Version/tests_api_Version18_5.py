import pytest
import sys
import os
import json
import asyncio
from typing import List, Optional
from httpx import AsyncClient
from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import text

# Ensure project root is on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import application components
try:
    import database as _database_module
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
    print(f"Import error: {e}")

# ------------------------------------------------------------------------------
# Patch out the app’s own create_db_and_tables so it does not re-create indexes
# on the real (file-backed) engine during each test-client startup.
# Tests will manage their own test_db engine separately.
# ------------------------------------------------------------------------------
async def _noop_create_db_and_tables():
    # no-op for test runs
    return
_database_module.create_db_and_tables = _noop_create_db_and_tables

# ------------------------------------------------------------------------------
# TestDatabaseManager: manages an in-memory SQLite DB for all tests
# ------------------------------------------------------------------------------
class TestDatabaseManager:
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self._engine_created = False

    async def setup_engine(self):
        if self._engine_created:
            return
        # Unique in-memory DB for this test session
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            echo=False,
            future=True,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._engine_created = True

    async def create_schema(self):
        # Drop any existing tables and re-create schema
        await self.setup_engine()
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
            await conn.run_sync(SQLModel.metadata.create_all)

    async def get_session(self) -> AsyncSession:
        await self.setup_engine()
        return self.session_factory()

    async def clear_data(self):
        if not self.engine:
            return
        async with self.engine.begin() as conn:
            for table in reversed(SQLModel.metadata.sorted_tables):
                await conn.execute(table.delete())

    async def dispose(self):
        if self.engine:
            await self.engine.dispose()
        self._engine_created = False
        self.engine = None
        self.session_factory = None

test_db = TestDatabaseManager()

# ------------------------------------------------------------------------------
# Pytest fixtures
# ------------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
async def manage_db_lifecycle():
    """
    Session-scoped fixture to set up and tear down the test database schema once.
    """
    await test_db.create_schema()
    yield
    await test_db.dispose()

@pytest.fixture(scope="function", autouse=True)
async def cleanup_data_per_test():
    """
    Function-scoped autouse fixture to clear all data before each test.
    """
    await test_db.clear_data()

@pytest.fixture
async def db_session() -> AsyncSession:
    """
    Provides a fresh AsyncSession connected to the in-memory test database.
    """
    session = await test_db.get_session()
    try:
        yield session
    finally:
        await session.close()

@pytest.fixture
def test_products() -> List[StandardizedProduct]:
    """
    A fixed set of sample StandardizedProduct instances for use in tests.
    """
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
            raw_data={"type": "electricity", "features": ["green", "fixed"]},
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
            raw_data={"type": "electricity", "features": ["variable"]},
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
            raw_data={"type": "mobile", "features": ["unlimited_calls"]},
        ),
        StandardizedProduct(
            source_url="https://example.com/mobile/plan_d",
            category="mobile_plan",
            name="Mobile Plan D",
            monthly_cost=45.0,
            provider_name="Provider Z",
            data_gb=float("inf"),
            calls=500,
            texts=float("inf"),
            contract_duration_months=12,
            network_type="5G",
            available=True,
            raw_data={"type": "mobile", "features": ["5G", "unlimited_data"]},
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
            raw_data={"type": "internet", "features": ["fiber", "unlimited"]},
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
            raw_data={"type": "internet", "features": ["dsl", "limited"]},
        ),
    ]

@pytest.fixture
async def api_client() -> AsyncClient:
    """
    Provides an AsyncClient for testing FastAPI endpoints,
    with get_session dependency overridden to use our in-memory session.
    """
    async def get_test_session_override():
        session = await test_db.get_session()
        try:
            yield session
        finally:
            await session.close()

    # Override the FastAPI dependency
    app.dependency_overrides[get_session] = get_test_session_override

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

    # Clean up override
    app.dependency_overrides.clear()


# ------------------------------------------------------------------------------
# Helper function tests
# ------------------------------------------------------------------------------

class TestDataParserFunctions:
    def test_extract_float_with_units(self):
        units = ["кВт·ч", "руб/кВт·ч", "ГБ", "GB", "Mbps"]
        conv = {u: 1.0 for u in units}
        # Basic valid
        assert extract_float_with_units("15.5 кВт·ч", units, conv) == 15.5
        # No number
        assert extract_float_with_units("no number", units, conv) is None

    def test_extract_float_or_handle_unlimited(self):
        unlimited = ["безлимит", "unlimited", "∞"]
        units = ["ГБ", "GB"]
        assert extract_float_or_handle_unlimited("unlimited", unlimited, units) == float("inf")
        assert extract_float_or_handle_unlimited("100 GB", unlimited, units) == 100.0

    def test_extract_duration_in_months(self):
        months = ["месяцев", "месяца", "months"]
        years = ["год", "years"]
        assert extract_duration_in_months("12 месяцев", months, years) == 12
        assert extract_duration_in_months("1 год", months, years) == 12
        assert extract_duration_in_months("без контракта", months, years) == 0

    def test_parse_availability(self):
        assert parse_availability("available") is True
        assert parse_availability("unavailable") is False
        assert parse_availability("unknown") is True


# ------------------------------------------------------------------------------
# Database and data-storage tests
# ------------------------------------------------------------------------------

class TestDatabase:
    @pytest.mark.asyncio
    async def test_session_fixture_works(self, db_session: AsyncSession):
        # Simple query
        r = await db_session.execute(select(1))
        assert r.scalar_one() == 1
        # Table exists
        tbl = ProductDB.__tablename__ or "productdb"
        q = await db_session.execute(
            text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{tbl}'")
        )
        assert q.scalar_one_or_none() == tbl

    @pytest.mark.asyncio
    async def test_store_and_retrieve(self, db_session: AsyncSession, test_products):
        # Initially empty
        r0 = await db_session.execute(select(ProductDB))
        assert r0.scalars().all() == []

        # Store and commit
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()

        # Retrieve
        r1 = await db_session.execute(select(ProductDB))
        stored = r1.scalars().all()
        assert len(stored) == len(test_products)
        names = {p.name for p in stored}
        assert "Elec Plan A" in names

    @pytest.mark.asyncio
    async def test_store_duplicates_updates(self, db_session: AsyncSession, test_products):
        # Store first two
        await store_standardized_data(session=db_session, data=test_products[:2])
        await db_session.commit()
        # Modify one
        mod = test_products[0].model_copy(deep=True)
        mod.price_kwh = 0.20
        # Store again plus new
        await store_standardized_data(session=db_session, data=[mod] + test_products[2:4])
        await db_session.commit()
        # Should have 4 total
        r2 = await db_session.execute(select(ProductDB))
        allp = r2.scalars().all()
        assert len(allp) == 4
        updated = next(p for p in allp if p.name == "Elec Plan A")
        assert updated.price_kwh == 0.20


# ------------------------------------------------------------------------------
# Search & filter tests
# ------------------------------------------------------------------------------

async def search_and_filter_products_local(
    session: AsyncSession, **kwargs
) -> List[StandardizedProduct]:
    from data_search import search_and_filter_products as _f
    return await _f(session=session, **kwargs)


class TestSearchAndFilter:
    @pytest.mark.asyncio
    async def test_search_all(self, db_session, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()
        res = await search_and_filter_products_local(db_session)
        assert len(res) == len(test_products)

    @pytest.mark.asyncio
    async def test_filter_by_category(self, db_session, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()
        elec = await search_and_filter_products_local(db_session, product_type="electricity_plan")
        assert {p.category for p in elec} == {"electricity_plan"}


# ------------------------------------------------------------------------------
# API endpoint tests
# ------------------------------------------------------------------------------

class TestAPI:
    @pytest.mark.asyncio
    async def test_search_endpoint(self, api_client, db_session, test_products):
        # prepare data
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()

        resp = await api_client.get("/search")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == len(test_products)

    @pytest.mark.asyncio
    async def test_search_with_filter(self, api_client, db_session, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()

        resp = await api_client.get("/search?category=electricity_plan")
        assert resp.status_code == 200
        body = resp.json()
        # All returned must match filter
        assert all(p["category"] == "electricity_plan" for p in body)