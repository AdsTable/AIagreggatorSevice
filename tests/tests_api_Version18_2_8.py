import os
import tempfile
import pytest
import asyncio
import json
from typing import List, Optional
from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from httpx import AsyncClient, ASGITransport

# Импорты приложения
try:
    from main import app
    from models import StandardizedProduct, ProductDB
    from database import get_session
    from data_storage import store_standardized_data
    from data_parser import (
        extract_float_with_units,
        extract_float_or_handle_unlimited,
        extract_duration_in_months,
        parse_availability,
        standardize_extracted_product,
        parse_and_standardize,
    )
except ImportError as e:
    print(f"Import error: {e}")
    print("Ensure all required modules are available.")

# ============================
# TEST DATABASE MANAGER
# ============================
class TestDatabaseManager:
    """
    Менеджер временной базы данных для тестов. Использует временный файл для полной изоляции.
    """
    def __init__(self):
        self.temp_db_file = None
        self.engine = None
        self.session_factory = None

    async def setup(self):
        """
        Создаёт новую базу данных и сбрасывает все таблицы.
        """
        self.temp_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db_file.close()
        db_url = f"sqlite+aiosqlite:///{self.temp_db_file.name}"
        self.engine = create_async_engine(db_url, echo=False, future=True, poolclass=NullPool)

        # Сбрасываем таблицы и создаём заново
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
            await conn.run_sync(SQLModel.metadata.create_all)

        self.session_factory = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    async def get_session(self) -> AsyncSession:
        """
        Возвращает новую сессию для взаимодействия с базой данных.
        """
        return self.session_factory()

    async def cleanup(self):
        """
        Удаляет базу данных после завершения тестов.
        """
        if self.engine:
            await self.engine.dispose()
        if self.temp_db_file and os.path.exists(self.temp_db_file.name):
            os.unlink(self.temp_db_file.name)

# ============================
# TEST FIXTURES
# ============================
@pytest.fixture(scope="function")
async def shared_db():
    """
    Создаёт временную базу данных перед каждым тестом.
    """
    db_manager = TestDatabaseManager()
    await db_manager.setup()
    yield db_manager
    await db_manager.cleanup()

@pytest.fixture(scope="function")
async def db_session(shared_db):
    """
    Возвращает новую сессию для взаимодействия с базой.
    """
    session = shared_db.session_factory()
    try:
        yield session
    finally:
        await session.close()

@pytest.fixture
def test_products():
    """
    Возвращает тестовые данные о продуктах.
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
    ]

@pytest.fixture
async def api_client(shared_db):
    """
    Возвращает клиент API с переопределением зависимости get_session.
    """
    async def get_test_session():
        session = shared_db.session_factory()
        try:
            yield session
        finally:
            await session.close()

    app.dependency_overrides[get_session] = get_test_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()

# ============================
# DATABASE TESTS
# ============================
class TestDatabase:
    @pytest.mark.asyncio
    async def test_session_fixture_works(self, db_session):
        result = await db_session.execute(select(1))
        assert result.scalar() == 1

    @pytest.mark.asyncio
    async def test_store_standardized_data(self, db_session, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        result = await db_session.execute(select(ProductDB))
        stored_products = result.scalars().all()
        assert len(stored_products) == len(test_products)

# ============================
# API TESTS
# ============================
class TestAPI:
    @pytest.mark.asyncio
    async def test_search_endpoint_no_filters(self, api_client, db_session, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        response = await api_client.get("/search")
        assert response.status_code == 200, response.text
        data = response.json()
        assert len(data) == len(test_products)
        if data:
            for field in ["source_url", "category", "name", "provider_name"]:
                assert field in data[0]

    @pytest.mark.asyncio
    async def test_search_endpoint_with_filters(self, api_client, db_session, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        response = await api_client.get("/search?product_type=electricity_plan")
        assert response.status_code == 200, response.text
        data = response.json()
        assert len(data) == 2
        response = await api_client.get("/search?provider=Provider X")
        assert response.status_code == 200, response.text
        data = response.json()
        assert len(data) == 1

    @pytest.mark.asyncio
    async def test_search_endpoint_empty_database(self, api_client):
        response = await api_client.get("/search")
        assert response.status_code == 200, response.text
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

# ============================
# DATA PARSER TESTS
# ============================
class TestDataParserFunctions:
    def test_extract_float_with_units(self):
        units = ["кВт·ч", "руб/кВт·ч"]
        unit_conversion = {"кВт·ч": 1.0, "руб/кВт·ч": 1.0}
        result = extract_float_with_units("15.5 кВт·ч", units, unit_conversion)
        assert result == 15.5

    def test_extract_duration_in_months(self):
        months = ["месяцев", "месяца"]
        years = ["год", "года"]
        result = extract_duration_in_months("1 год", months, years)
        assert result == 12

# ============================
# INTEGRATION TESTS
# ============================
class TestIntegration:
    @pytest.mark.asyncio
    async def test_workflow_electricity_plans(self, db_session, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        results = await db_session.execute(select(ProductDB))
        all_products = results.scalars().all()
        assert len(all_products) == len(test_products)