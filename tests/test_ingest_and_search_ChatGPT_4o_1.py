# ✅ test_ingest_and_search.py — Final, CI-Ready https://chatgpt.com/share/6830d70a-0870-800d-bc5d-5728de21fa76

import pytest
import json
import math
import unittest.mock
from httpx import AsyncClient
from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from typing import List, AsyncIterator

from main import app
from database import get_session
from models import ProductDB, StandardizedProduct

# -------------------- Fixtures --------------------

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture(scope="session")
def engine():
    SQLModel.metadata.clear()
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

# -------------------- Mocks --------------------

@pytest.fixture()
def mocked_raw_data():
    return [
        {
            "source_url": "https://example.com/elec/plan_a",
            "category": "electricity_plan",
            "plan_title": "Green Power Plan",
            "provider_name_on_page": "GreenEnergy",
            "kwh_price_text": "0.18 EUR/kWh",
            "standing_charge_daily_text": "0.30 EUR/day",
            "contract_term_text": "12 months",
            "availability_status": "Available"
        },
        {
            "source_url": "https://example.com/mobile/plan_x",
            "category": "mobile_plan",
            "plan_title": "Unlimited Max",
            "provider_name_on_page": "Telenor",
            "monthly_price_text": "499 NOK",
            "data_allowance_text": "Unlimited",
            "calls_info": "Unlimited",
            "texts_info": "Unlimited",
            "contract_term_text": "No contract"
        }
    ]

# -------------------- Test: Ingest Flow --------------------

@pytest.mark.asyncio
@unittest.mock.patch("main.discover_and_extract_data")
async def test_ingest_endpoint(mock_discover, client, session, mocked_raw_data):
    mock_discover.return_value = mocked_raw_data

    response = await client.post("/ingest_data")
    assert response.status_code == 200
    assert response.json()["message"].lower().startswith("data ingestion")

    # Confirm discover_and_extract_data was called
    mock_discover.assert_called_once()

    # Validate what's stored
    result = await session.execute(select(ProductDB))
    products = result.scalars().all()
    assert len(products) >= 2
    names = [p.name for p in products]
    assert "Green Power Plan" in names
    assert "Unlimited Max" in names
