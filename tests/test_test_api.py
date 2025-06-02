Объединенные все тесты - с ошибкой. Для анализа тольео.
import pytest
import sys
import os
import math
import json
import asyncio
from typing import Dict, Any, List, Optional, AsyncIterator

# --- Импортируем компоненты приложения ---
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from main import app
from database import get_session
from models import StandardizedProduct, ProductDB
from data_storage import store_standardized_data, search_and_filter_products

from httpx import AsyncClient
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker

# --- Тесты парсера (data_parser) ---

@pytest.mark.parametrize("raw,expected", [
    ("15.5 USD/kWh", 15.5),
    ("20 GB", 20.0),
    ("5", 5.0),
    ("invalid", None),
    (None, None),
    ("", None),
    (" 10.2 ", 10.2),
])
def test_parse_float_with_units(raw, expected):
    from data_parser import parse_float_with_units
    assert parse_float_with_units(raw) == expected

@pytest.mark.parametrize("raw,expected", [
    ("unlimited", float("inf")),
    ("Unlimited", float("inf")),
    ("not unlimited", None),
    (None, None),
    ("", None),
    (123, None)
])
def test_parse_unlimited(raw, expected):
    from data_parser import parse_unlimited
    assert parse_unlimited(raw) == expected

@pytest.mark.parametrize("raw,expected", [
    ("12-month contract", 12),
    ("24mo", 24),
    ("no contract", 0),
    ("cancel anytime", 0),
    ("1 year", 12),
    ("2 yr", 24),
    ("invalid", None),
    (None, None),
    ("", None),
    ("36months", 36)
])
def test_parse_contract_duration(raw, expected):
    from data_parser import parse_contract_duration
    assert parse_contract_duration(raw) == expected

@pytest.mark.parametrize("raw,expected", [
    ("Available", True),
    ("In Stock", True),
    ("active", True),
    ("Expired", False),
    ("Sold Out", False),
    ("inactive", False),
    ("Some text about status", True), # Default
    (None, True),
    ("", True)
])
def test_parse_availability(raw, expected):
    from data_parser import parse_availability
    assert parse_availability(raw) == expected

@pytest.mark.parametrize("raw,expected", [
    ("50 GB", 50.0),
    ("Unlimited data", float("inf")),
    ("invalid", None),
    (None, None)
])
def test_parse_data_allowance(raw, expected):
    from data_parser import parse_data_allowance
    assert parse_data_allowance(raw) == expected

@pytest.mark.parametrize("raw,expected", [
    ("120 minutes", 120),
    ("Unlimited calls", float("inf")),
    (300, 300),
    ("invalid", None),
    (None, None)
])
def test_parse_unlimited_or_minutes(raw, expected):
    from data_parser import parse_unlimited_or_minutes
    assert parse_unlimited_or_minutes(raw) == expected

@pytest.mark.parametrize("raw,expected", [
    ("500 texts", 500),
    ("Unlimited texts", float("inf")),
    (1000, 1000),
    ("invalid", None),
    (None, None)
])
def test_parse_unlimited_or_count(raw, expected):
    from data_parser import parse_unlimited_or_count
    assert parse_unlimited_or_count(raw) == expected

# --- Фикстуры базы данных и клиента ---

@pytest.fixture(scope="function")
async def engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest.fixture(scope="function")
async def session(engine) -> AsyncIterator[AsyncSession]:
    async_session_factory = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session_factory() as session:
        yield session

@pytest.fixture(scope="function")
async def client(session: AsyncSession):
    # Переопределяем зависимость FastAPI для тестовой сессии
    async def override_get_session():
        yield session
    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

@pytest.fixture
def test_products():
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

# --- Тесты для store_standardized_data и search_and_filter_products ---

@pytest.mark.asyncio
async def test_store_and_search_products(session: AsyncSession, test_products: List[StandardizedProduct]):
    await store_standardized_data(session=session, data=test_products)
    all_products = await search_and_filter_products(session=session)
    assert len(all_products) == len(test_products)
    # Проверка фильтрации по категории
    elec = await search_and_filter_products(session=session, product_type="electricity_plan")
    assert all(p.category == "electricity_plan" for p in elec)
    # Проверка фильтрации по провайдеру
    x_products = await search_and_filter_products(session=session, provider="Provider X")
    assert all(p.provider_name == "Provider X" for p in x_products)
    # Проверка фильтрации по максимальному объему данных
    mobile_max_data = await search_and_filter_products(session=session, product_type="mobile_plan", max_data_gb=150.0)
    assert all((p.data_gb or 0) <= 150.0 for p in mobile_max_data if p.data_gb is not None)
    # Проверка фильтрации по минимальному сроку
    elec_min_contract = await search_and_filter_products(session=session, product_type="electricity_plan", min_contract_duration_months=18)
    assert all((p.contract_duration_months or 0) >= 18 for p in elec_min_contract)
    # Комбинированная фильтрация
    internet_provider_x_max_datacap = await search_and_filter_products(
        session=session,
        product_type="internet_plan",
        provider="Provider X",
        max_data_gb=600.0
    )
    assert all(p.provider_name == "Provider X" and (p.data_cap_gb or 0) <= 600.0 for p in internet_provider_x_max_datacap)
    # Проверка отсутствия результатов
    no_results = await search_and_filter_products(session=session, product_type="gas_plan")
    assert len(no_results) == 0

# --- Тесты API эндпоинтов ---

@pytest.mark.asyncio
async def test_search_endpoint_all_filters(client: AsyncClient, session: AsyncSession, test_products: List[StandardizedProduct]):
    await store_standardized_data(session, test_products)
    # Нет фильтров
    r = await client.get("/search")
    assert r.status_code == 200
    assert len(r.json()) == len(test_products)
    # По категории
    r = await client.get("/search", params={"product_type": "mobile_plan"})
    assert {p["name"] for p in r.json()} == {"Mobile Plan C", "Mobile Plan D"}
    # По провайдеру
    r = await client.get("/search", params={"provider": "Provider X"})
    assert {p["name"] for p in r.json()} == {"Elec Plan A", "Mobile Plan C", "Internet Plan F"}
    # По min_price
    r = await client.get("/search", params={"product_type": "electricity_plan", "min_price": 0.13})
    assert {p["name"] for p in r.json()} == {"Elec Plan A"}
    # По min_contract_duration
    r = await client.get("/search", params={"min_contract_duration_months": 18})
    assert {p["name"] for p in r.json()} == {"Elec Plan B", "Internet Plan E"}
    # По max_data_gb
    r = await client.get("/search", params={"product_type": "mobile_plan", "max_data_gb": 200})
    assert {p["name"] for p in r.json()} == {"Mobile Plan C"}
    # Комбинированные фильтры
    r = await client.get("/search", params={"product_type": "internet_plan", "provider": "Provider X", "max_data_gb": 600})
    assert {p["name"] for p in r.json()} == {"Internet Plan F"}
    # Нет результатов
    r = await client.get("/search", params={"product_type": "gas_plan"})
    assert r.json() == []

# --- Пример теста с моком для /ingest_data ---

@pytest.mark.asyncio
async def test_ingest_data_endpoint(monkeypatch, client: AsyncClient, session: AsyncSession):
    # Мокаем функцию discover_and_extract_data
    from main import discover_and_extract_data
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
        }
    ]
    monkeypatch.setattr("main.discover_and_extract_data", lambda *args, **kwargs: mock_raw_data)
    response = await client.post("/ingest_data")
    assert response.status_code == 200
    assert "message" in response.json()

# --- Проверка работоспособности сессии ---

@pytest.mark.asyncio
async def test_session_fixture_works(session: AsyncSession):
    result = await session.execute(select(1))
    assert result.scalar() == 1
