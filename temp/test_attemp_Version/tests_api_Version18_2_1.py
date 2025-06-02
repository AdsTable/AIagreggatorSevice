import pytest
import pytest_asyncio
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from sqlmodel import SQLModel, select
from fastapi import FastAPI
from fastapi.testclient import TestClient
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
#                            Примерные модели и функции                       #
###############################################################################

# Упрощённая модель (замените на вашу)
class ProductDB(SQLModel, table=True):
    id: int | None = None
    name: str | None
    category: str | None
    provider_name: str | None
    available: bool | None
    raw_data_json: str | None

# Упрощённая функция парсинга
def extract_float_with_units(value: str, units=None, unit_conversion=None):
    try:
        return float(value.split()[0])
    except:
        return None

def extract_float_or_handle_unlimited(value: str, unlimited_terms=None, units=None):
    if value.lower() in ["unlimited", "∞"]:
        return float('inf')
    try:
        return float(value)
    except:
        return None

def extract_duration_in_months(value: str, month_terms=None, year_terms=None):
    # Допускаем, что "12 months" -> 12
    if "month" in value.lower():
        return 12
    if "year" in value.lower():
        return 12
    return None

def parse_availability(value: str):
    if value.lower() in ["available", "true", "in_stock", "in stock"]:
        return True
    return False

# Заглушка для функции сохранения
async def store_standardized_data(session: AsyncSession, data: list):
    for product in data:
        # Пример: Передаём словарь и создаём новый объект
        db_obj = ProductDB(
            name=product["name"],
            category=product["category"],
            provider_name=product["provider_name"],
            available=product["available"],
            raw_data_json=json.dumps(product.get("raw_data", {}))
        )
        session.add(db_obj)
    await session.commit()

###############################################################################
#                          Менеджер тестовой базы данных                      #
###############################################################################
class TestDatabaseManager:
    """Управляет тестовой БД в рамках тестов."""
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self._setup_complete = False

    async def setup(self):
        if not self._setup_complete:
            # Используем in-memory sqlite
            db_url = "sqlite+aiosqlite:///:memory:"
            self.engine = create_async_engine(db_url, echo=False, future=True)
            self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

            # Создаём таблицы
            async with self.engine.begin() as conn:
                await conn.run_sync(SQLModel.metadata.create_all)
            self._setup_complete = True

    async def get_session(self):
        # Возвращаем новую сессию
        if not self._setup_complete:
            await self.setup()
        return self.session_factory()

    async def clear_all_data(self):
        # Очищаем данные (пример)
        if self.engine and self._setup_complete:
            async with self.engine.begin() as conn:
                await conn.execute(text("DELETE FROM productdb"))

    async def cleanup(self):
        if self.engine:
            await self.engine.dispose()
        self._setup_complete = False

# Глобальный экземпляр менеджера
test_db = TestDatabaseManager()

###############################################################################
#                          Фикстуры для pytest-asyncio                        #
###############################################################################
@pytest_asyncio.fixture(scope="session")
async def event_loop():
    loop = asyncio.get_event_loop()
    yield loop

@pytest_asyncio.fixture(scope="session")
async def database_manager():
    await test_db.setup()
    yield test_db
    await test_db.cleanup()

@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_test_environment(database_manager):
    await database_manager.clear_all_data()
    yield

@pytest_asyncio.fixture
async def db_session(database_manager):
    session = await database_manager.get_session()
    try:
        yield session
    finally:
        await session.rollback()

@pytest_asyncio.fixture
async def api_client(db_session):
    """
    Пример интеграции с FastAPI. Если у вас есть готовое приложение (app), 
    используйте его, переопределяйте зависимость get_session и т.д.
    """
    app = FastAPI()

    @app.get("/search")
    async def search_endpoint():
        # Приведём упрощённый пример выборки
        results = await db_session.execute(select(ProductDB))
        items = results.scalars().all()
        return [{"name": p.name, "category": p.category, "provider_name": p.provider_name} for p in items]

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

###############################################################################
#                         Пример тестовых данных                              #
###############################################################################
@pytest.fixture
def test_products():
    return [
        {
            "name": "Test Product 1",
            "category": "mobile_plan",
            "provider_name": "Provider X",
            "available": True,
            "raw_data": {"some": "data"}
        },
        {
            "name": "Test Product 2",
            "category": "electricity_plan",
            "provider_name": "Provider Y",
            "available": False,
            "raw_data": {"other": "info"}
        }
    ]

###############################################################################
#                      Тесты для парсинга данных (Unit Tests)                #
###############################################################################
class TestDataParserFunctions:
    def test_extract_float_with_units(self):
        val = extract_float_with_units("15.5 kWh")
        assert val == 15.5

    def test_extract_float_or_handle_unlimited(self):
        val_inf = extract_float_or_handle_unlimited("unlimited")
        assert val_inf == float('inf')
        val_num = extract_float_or_handle_unlimited("123.45")
        assert val_num == 123.45

    def test_extract_duration_in_months(self):
        val = extract_duration_in_months("12 months", ["months"], ["years"])
        assert val == 12

    def test_parse_availability(self):
        val = parse_availability("AVAILABLE")
        assert val is True
        val_false = parse_availability("unknown_value")
        assert val_false is False

###############################################################################
#                       Тесты для работы с БД (Database Tests)               #
###############################################################################
@pytest.mark.asyncio
class TestDatabase:
    async def test_session_fixture_works(self, db_session):
        result = await db_session.execute("SELECT 1")
        single_val = result.fetchone()
        assert single_val[0] == 1

    async def test_store_standardized_data(self, db_session, test_products):
        # Проверяем, что таблица пуста
        result = await db_session.execute(select(ProductDB))
        assert len(result.scalars().all()) == 0

        # Сохраняем тестовые продукты
        await store_standardized_data(db_session, test_products)

        # Проверяем, что записались
        result = await db_session.execute(select(ProductDB))
        db_items = result.scalars().all()
        assert len(db_items) == 2

        # Проверяем поля
        for idx, prod in enumerate(db_items):
            assert prod.name == test_products[idx]["name"]

###############################################################################
#                 Тесты для поиска/фильтрации данных (Search Tests)          #
###############################################################################
@pytest.mark.asyncio
class TestSearchAndFilter:
    async def test_search_all_products(self, db_session, test_products):
        await store_standardized_data(db_session, test_products)
        # Пример теста — проверим, что всё сохранилось
        result = await db_session.execute(select(ProductDB))
        db_items = result.scalars().all()
        assert len(db_items) == len(test_products)

###############################################################################
#                     Тесты API (API Tests)                                   #
###############################################################################
@pytest.mark.asyncio
class TestAPI:
    async def test_search_endpoint_no_filters(self, api_client, db_session, test_products):
        # Наполняем БД
        await store_standardized_data(db_session, test_products)
        response = await api_client.get("/search")
        assert response.status_code == 200
        data = response.json()
        # Должны получить все продукты
        assert len(data) == 2
        names = [item["name"] for item in data]
        assert "Test Product 1" in names
        assert "Test Product 2" in names

###############################################################################
#                  Пример интеграционных тестов (Integration)                #
###############################################################################
@pytest.mark.asyncio
class TestIntegration:
    async def test_full_workflow_electricity_plans(self, db_session):
        # Упрощённый пример
        data = [
            {
                "name": "Elec Plan A",
                "category": "electricity_plan",
                "provider_name": "ProviderX",
                "available": True,
                "raw_data": {"param": "value"}
            }
        ]
        # Сохраняем
        await store_standardized_data(db_session, data)

        # Проверяем
        result = await db_session.execute(select(ProductDB).where(ProductDB.category=="electricity_plan"))
        rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].name == "Elec Plan A"