# ✅ test_api.py (FINALISED & FIXED)

import pytest
import math
import json
import unittest.mock
from typing import List, AsyncIterator
from httpx import AsyncClient
from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession as SQLAsyncSession

from main import app
from models import ProductDB, StandardizedProduct
from database import get_session

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

# ------------------------ TESTS ------------------------

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

    # Combined
    r = await client.get("/search", params={"product_type": "internet_plan", "provider": "Provider X", "max_data_gb": 600})
    assert {p["name"] for p in r.json()} == {"Internet Plan F"}

    # No results
    r = await client.get("/search", params={"product_type": "gas_plan"})
    assert r.status_code == 200
    assert r.json() == []
