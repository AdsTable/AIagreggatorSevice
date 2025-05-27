import pytest
import pytest_asyncio
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from sqlmodel import SQLModel, select
from fastapi import FastAPI
from httpx import AsyncClient
import json

# Предположим, что в вашем проекте есть эти модули:
# from main import app
# from database import get_session
# from models import StandardizedProduct, ProductDB
# from data_storage import store_standardized_data
# from data_parser import (
#     extract_float_with_units,
#     extract_float_or_handle_unlimited,
#     extract_duration_in_months,
#     parse_availability,
# )

###############################################################################
#                          Примерная модель и функции                         #
###############################################################################
class ProductDB(SQLModel, table=True):
    id: int | None = None
    name: str | None
    category: str | None
    provider_name: str | None
    available: bool | None
    raw_data_json: str | None

async def store_standardized_data(session: AsyncSession, data: list):
    for product in data:
        obj = ProductDB(
            name=product["name"],
            category=product["category"],
            provider_name=product["provider_name"],
            available=product["available"],
            raw_data_json=json.dumps(product.get("raw_data", {}))
        )
        session.add(obj)
    await session.commit()

###############################################################################
#                      Менеджер тестовой БД для v21                           #
###############################################################################
class TestDatabaseManagerV21:
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self._setup_complete = False

    async def setup(self):
        if not self._setup_complete:
            db_url = "sqlite+aiosqlite:///:memory:"
            self.engine = create_async_engine(db_url, echo=False, future=True)
            self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
            async with self.engine.begin() as conn:
                await conn.run_sync(SQLModel.metadata.create_all)
            self._setup_complete = True

    async def get_session(self):
        if not self._setup_complete:
            await self.setup()
        return self.session_factory()

    async def clear_all_data(self):
        if self.engine and self._setup_complete:
            async with self.engine.begin() as conn:
                await conn.execute(text("DELETE FROM productdb"))

    async def cleanup(self):
        if self.engine:
            await self.engine.dispose()
        self._setup_complete = False

test_db_v21 = TestDatabaseManagerV21()

###############################################################################
#                              Фикстуры для v21                               #
###############################################################################
@pytest_asyncio.fixture(scope="session")
async def event_loop_v21():
    loop = asyncio.get_event_loop()
    yield loop

@pytest_asyncio.fixture(scope="session")
async def database_manager_v21():
    await test_db_v21.setup()
    yield test_db_v21
    await test_db_v21.cleanup()

@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_test_environment_v21(database_manager_v21):
    await database_manager_v21.clear_all_data()
    yield

@pytest_asyncio.fixture
async def db_session_v21(database_manager_v21):
    session = await database_manager_v21.get_session()
    try:
        yield session
    finally:
        await session.rollback()

@pytest_asyncio.fixture
async def api_client_v21(db_session_v21):
    app = FastAPI()

    @app.get("/v21/search")
    async def search_endpoint_v21():
        res = await db_session_v21.execute(select(ProductDB))
        items = res.scalars().all()
        return [{"name": x.name, "category": x.category, "provider": x.provider_name} for x in items]

    async with AsyncClient(app=app, base_url="http://test_v21") as client:
        yield client

@pytest.fixture
def test_products_v21():
    return [
        {
            "name": "Mobile Plan A",
            "category": "mobile_plan",
            "provider_name": "ProviderA",
            "available": True,
            "raw_data": {"some": "data"}
        },
        {
            "name": "Internet Plan B",
            "category": "internet_plan",
            "provider_name": "ProviderB",
            "available": True,
            "raw_data": {"network": "fiber"}
        }
    ]

###############################################################################
#                 Тесты для v21 (Database, Search, API и т.д.)               #
###############################################################################
@pytest.mark.asyncio
class TestAPIV21:
    async def test_search_endpoint_no_filters_v21(self, api_client_v21, db_session_v21, test_products_v21):
        # Предварительно сохраняем тестовые данные
        await store_standardized_data(db_session_v21, test_products_v21)
        response = await api_client_v21.get("/v21/search")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        names = [item["name"] for item in data]
        assert "Mobile Plan A" in names
        assert "Internet Plan B" in names

    async def test_search_endpoint_empty_database_v21(self, api_client_v21):
        response = await api_client_v21.get("/v21/search")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0