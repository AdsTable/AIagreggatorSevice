# test_api.py
import pytest
import sys
import os
import json
from typing import Dict, Any, List, Optional, AsyncIterator

# Add the parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import for FastAPI testing
from httpx import AsyncClient

# Import for database testing
from sqlmodel import SQLModel, Field, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker

# Import your application and models
from main import app
from database import get_session
from models import StandardizedProduct, ProductDB
from data_storage import store_standardized_data

# Import helper functions
from data_parser import (
    extract_float_with_units,
    extract_float_or_handle_unlimited,
    extract_duration_in_months,
    parse_availability,
    standardize_extracted_product,
    parse_and_standardize,
)

# Create test database (use in-memory SQLite for testing)
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

# --- Управление сессиями базы данных ---
class SessionManager:
    """Менеджер сессий для тестирования."""
    
    def __init__(self):
        self.engine = None
        self.session_maker = None
        self._active_session = None
    
    async def setup(self):
        """Инициализация движка и создание таблиц."""
        self.engine = create_async_engine(TEST_DB_URL, echo=False)
        
        # Создаем таблицы
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        
        # Создаем фабрику сессий
        self.session_maker = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
    
    async def get_session(self) -> AsyncSession:
        """Получить новую сессию."""
        if not self.session_maker:
            await self.setup()
        
        session = self.session_maker()
        self._active_session = session
        return session
    
    async def cleanup(self):
        """Закрыть движок и освободить ресурсы."""
        if self._active_session:
            await self._active_session.close()
            self._active_session = None
        
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self.session_maker = None

# Создаем экземпляр менеджера сессий
session_manager = SessionManager()

# --- Мок-функции для тестов ---
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
    """Мок-функция для поиска и фильтрации продуктов."""
    query = select(ProductDB)
    
    # Применяем фильтры
    if product_type:
        query = query.where(ProductDB.category == product_type)
    if provider:
        query = query.where(ProductDB.provider_name == provider)
    if min_price is not None:
        query = query.where(ProductDB.price_kwh >= min_price)
    if max_price is not None:
        query = query.where(ProductDB.price_kwh <= max_price)
    if min_data_gb is not None:
        query = query.where(ProductDB.data_gb >= min_data_gb)
    if max_data_gb is not None:
        # Фильтруем unlimited значения
        query = query.where(ProductDB.data_gb <= max_data_gb)
        query = query.where(ProductDB.data_cap_gb <= max_data_gb)
    if min_contract_duration_months is not None:
        query = query.where(ProductDB.contract_duration_months >= min_contract_duration_months)
    if max_contract_duration_months is not None:
        query = query.where(ProductDB.contract_duration_months <= max_contract_duration_months)
    if max_download_speed is not None:
        query = query.where(ProductDB.download_speed <= max_download_speed)
    
    result = await session.execute(query)
    db_products = result.scalars().all()
    
    # Преобразуем обратно в StandardizedProduct
    standardized_products = []
    for db_product in db_products:
        raw_data = json.loads(db_product.raw_data_json) if db_product.raw_data_json else {}
        standardized_product = StandardizedProduct(
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
        standardized_products.append(standardized_product)
    
    return standardized_products

# --- Фикстуры для тестирования ---
@pytest.fixture(scope="session", autouse=True)
async def setup_teardown():
    """Настройка БД перед всеми тестами и очистка после."""
    await session_manager.setup()
    yield
    await session_manager.cleanup()

@pytest.fixture
async def db():
    """Фикстура для доступа к менеджеру сессий."""
    return session_manager

@pytest.fixture
async def session():
    """Создание сессии для теста с автоматической транзакцией."""
    session = await session_manager.get_session()
    
    # Начинаем транзакцию
    transaction = await session.begin()
    try:
        # Предоставляем сессию тесту
        yield session
    finally:
        # Откатываем транзакцию после теста
        await transaction.rollback()
        # Закрываем сессию
        await session.close()

# Класс для переопределения зависимости сессии в тестах
class TestSessionProvider:
    """Класс для предоставления тестовой сессии в качестве зависимости."""
    
    def __init__(self, session):
        self.session = session
    
    async def __call__(self):
        """Эмулирует поведение оригинальной зависимости get_session."""
        yield self.session

@pytest.fixture
async def client(session):
    """Создание тестового клиента с переопределенной зависимостью."""
    # Создаем провайдер сессии для тестов
    provider = TestSessionProvider(session)
    
    # Переопределяем зависимость
    app.dependency_overrides[get_session] = provider
    
    # Создаем и возвращаем клиент для тестирования
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    
    # Очищаем переопределения после теста
    app.dependency_overrides.clear()

@pytest.fixture(name="test_products")
def test_products_fixture():
    """Тестовые данные продуктов."""
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

# --- Тесты вспомогательных функций ---
def test_extract_float_with_units():
    """Тест извлечения чисел с единицами измерения."""
    units = ["кВт·ч", "руб/кВт·ч", "ГБ"]
    unit_conversion = {"кВт·ч": 1.0, "руб/кВт·ч": 1.0, "ГБ": 1.0}
    
    assert extract_float_with_units("15.5 кВт·ч", units, unit_conversion) == 15.5
    assert extract_float_with_units("0.12 руб/кВт·ч", units, unit_conversion) == 0.12
    assert extract_float_with_units("100 ГБ", units, unit_conversion) == 100.0
    assert extract_float_with_units("no number", units, unit_conversion) is None

def test_extract_float_or_handle_unlimited():
    """Тест обработки безлимитных значений."""
    unlimited_terms = ["безлимит", "unlimited", "неограниченно"]
    units = ["ГБ", "MB"]
    
    assert extract_float_or_handle_unlimited("безлимит", unlimited_terms, units) == float('inf')
    assert extract_float_or_handle_unlimited("unlimited", unlimited_terms, units) == float('inf')
    assert extract_float_or_handle_unlimited("100 ГБ", unlimited_terms, units) == 100.0
    assert extract_float_or_handle_unlimited("no number", unlimited_terms, units) is None

def test_parse_availability():
    """Тест парсинга доступности."""
    assert parse_availability("в наличии") == True
    assert parse_availability("доступен") == True
    assert parse_availability("недоступен") == False
    assert parse_availability("unknown") == True  # По умолчанию True

# --- Тесты базы данных ---
@pytest.mark.asyncio
async def test_session_fixture_works(session: AsyncSession):
    """Проверка работы фикстуры сессии."""
    # Выполнение простого запроса
    result = await session.execute(select(1))
    assert result.scalar() == 1
    print("✓ Session fixture is working correctly!")

@pytest.mark.asyncio
async def test_store_standardized_data(session: AsyncSession, test_products: List[StandardizedProduct]):
    """Тест сохранения данных в БД."""
    # Проверяем, что БД пуста
    result = await session.execute(select(ProductDB))
    existing = result.scalars().all()
    assert len(existing) == 0
    
    # Сохраняем тестовые продукты
    await store_standardized_data(session=session, data=test_products)
    
    # Проверяем, что продукты сохранились
    result = await session.execute(select(ProductDB))
    stored = result.scalars().all()
    assert len(stored) == len(test_products)
    
    # Проверяем имена продуктов
    stored_names = {p.name for p in stored}
    expected_names = {p.name for p in test_products}
    assert stored_names == expected_names
    
    # Проверяем детали конкретного продукта
    elec_plan = next((p for p in stored if p.name == "Elec Plan A"), None)
    assert elec_plan is not None
    assert elec_plan.category == "electricity_plan"
    assert elec_plan.price_kwh == 0.15
    assert json.loads(elec_plan.raw_data_json) == {"k": "v1"}

@pytest.mark.asyncio
async def test_search_and_filter_products(session: AsyncSession, test_products: List[StandardizedProduct]):
    """Тест поиска и фильтрации продуктов."""
    # Проверяем, что БД пуста
    result = await session.execute(select(ProductDB))
    assert len(result.scalars().all()) == 0
    
    # Сохраняем тестовые продукты
    await store_standardized_data(session=session, data=test_products)
    
    # Тестируем поиск всех продуктов
    all_products = await search_and_filter_products(session=session)
    assert len(all_products) == len(test_products)
    assert {p.name for p in all_products} == {p.name for p in test_products}
    
    # Тестируем фильтр по типу продукта
    electricity = await search_and_filter_products(session=session, product_type="electricity_plan")
    assert {p.name for p in electricity} == {"Elec Plan A", "Elec Plan B"}
    
    # Тестируем фильтр по провайдеру
    provider_x = await search_and_filter_products(session=session, provider="Provider X")
    assert {p.name for p in provider_x} == {"Elec Plan A", "Mobile Plan C", "Internet Plan F"}
    
    # Тестируем фильтр по минимальной цене
    expensive_electricity = await search_and_filter_products(
        session=session,
        product_type="electricity_plan",
        min_price=0.13
    )
    assert {p.name for p in expensive_electricity} == {"Elec Plan A"}
    
    # Тестируем фильтр по длительности контракта
    long_contracts = await search_and_filter_products(
        session=session,
        min_contract_duration_months=18
    )
    assert {p.name for p in long_contracts} == {"Elec Plan B", "Internet Plan E"}
    
    # Тестируем фильтр по максимальному объему данных
    limited_data = await search_and_filter_products(
        session=session,
        product_type="mobile_plan", 
        max_data_gb=200
    )
    assert {p.name for p in limited_data} == {"Mobile Plan C"}
    
    # Тестируем случай без результатов
    no_results = await search_and_filter_products(session=session, product_type="gas_plan")
    assert len(no_results) == 0

# --- Тесты API ---
@pytest.mark.asyncio
async def test_search_endpoint_no_filters(client: AsyncClient, session: AsyncSession, test_products: List[StandardizedProduct]):
    """Тест поиска без фильтров."""
    # Сохраняем тестовые данные
    await store_standardized_data(session=session, data=test_products)
    
    # Тестируем поиск без фильтров
    response = await client.get("/search")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == len(test_products)
    
    # Проверяем структуру ответа
    if data:
        sample_product = data[0]
        assert "source_url" in sample_product
        assert "category" in sample_product
        assert "name" in sample_product

@pytest.mark.asyncio
async def test_search_endpoint_filter_by_type(client: AsyncClient, session: AsyncSession, test_products: List[StandardizedProduct]):
    """Тест фильтрации по типу продукта."""
    await store_standardized_data(session=session, data=test_products)
    
    response = await client.get("/search", params={"product_type": "mobile_plan"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2  # Должно быть 2 мобильных плана
    assert all(p["category"] == "mobile_plan" for p in data)
    assert any(p["name"] == "Mobile Plan C" for p in data)
    assert any(p["name"] == "Mobile Plan D" for p in data)

@pytest.mark.asyncio
async def test_search_endpoint_filter_by_min_price(client: AsyncClient, session: AsyncSession, test_products: List[StandardizedProduct]):
    """Тест фильтрации по минимальной цене."""
    await store_standardized_data(session=session, data=test_products)

    # Тест с тарифами электричества
    response_elec = await client.get("/search", params={"product_type": "electricity_plan", "min_price": 0.13})
    assert response_elec.status_code == 200
    data_elec = response_elec.json()
    assert len(data_elec) == 1
    assert data_elec[0]["name"] == "Elec Plan A"

    # Тест с интернет-тарифами
    response_internet = await client.get("/search", params={"product_type": "internet_plan", "min_price": 55.0})
    assert response_internet.status_code == 200
    data_internet = response_internet.json()
    assert len(data_internet) == 1
    assert data_internet[0]["name"] == "Internet Plan E"

@pytest.mark.asyncio
async def test_search_endpoint_filter_by_provider(client: AsyncClient, session: AsyncSession, test_products: List[StandardizedProduct]):
    """Тест фильтрации по провайдеру."""
    await store_standardized_data(session=session, data=test_products)
    
    response = await client.get("/search", params={"provider": "Provider X"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert all(p["provider_name"] == "Provider X" for p in data)
    assert any(p["name"] == "Elec Plan A" for p in data)
    assert any(p["name"] == "Mobile Plan C" for p in data)
    assert any(p["name"] == "Internet Plan F" for p in data)

@pytest.mark.asyncio
async def test_search_endpoint_filter_by_max_data_gb(client: AsyncClient, session: AsyncSession, test_products: List[StandardizedProduct]):
    """Тест фильтрации по максимальному объему данных."""
    await store_standardized_data(session=session, data=test_products)

    # Тест с мобильными тарифами
    response_mobile = await client.get("/search", params={"product_type": "mobile_plan", "max_data_gb": 200.0})
    assert response_mobile.status_code == 200
    data_mobile = response_mobile.json()
    assert len(data_mobile) == 1
    assert data_mobile[0]["name"] == "Mobile Plan C"
    assert data_mobile[0]["data_gb"] == 100.0

    # Тест с интернет-тарифами
    response_internet = await client.get("/search", params={"product_type": "internet_plan", "max_data_cap_gb": 600.0})
    assert response_internet.status_code == 200
    data_internet = response_internet.json()
    assert len(data_internet) == 1
    assert data_internet[0]["name"] == "Internet Plan F"
    assert data_internet[0]["data_cap_gb"] == 500.0

@pytest.mark.asyncio
async def test_search_endpoint_filter_by_min_contract_duration(client: AsyncClient, session: AsyncSession, test_products: List[StandardizedProduct]):
    """Тест фильтрации по минимальной длительности контракта."""
    await store_standardized_data(session=session, data=test_products)
    
    response = await client.get("/search", params={"min_contract_duration_months": 18})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert any(p["name"] == "Elec Plan B" for p in data)
    assert any(p["name"] == "Internet Plan E" for p in data)

@pytest.mark.asyncio
async def test_search_endpoint_combined_filters(client: AsyncClient, session: AsyncSession, test_products: List[StandardizedProduct]):
    """Тест комбинированных фильтров."""
    await store_standardized_data(session=session, data=test_products)

    # Тест комбинированных фильтров - интернет-тариф от Provider X с ограничением данных
    response = await client.get(
        "/search",
        params={
            "product_type": "internet_plan",
            "provider": "Provider X",
            "max_data_cap_gb": 600.0
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Internet Plan F"
    assert data[0]["provider_name"] == "Provider X"
    assert data[0]["data_cap_gb"] == 500.0

    # Тест комбинированных фильтров - интернет-тариф от Provider Y с ограничением скорости
    response_speed = await client.get(
         "/search",
         params={
             "product_type": "internet_plan",
             "provider": "Provider Y",
             "max_download_speed": 600.0
         }
     )
    assert response_speed.status_code == 200
    data_speed = response_speed.json()
    assert len(data_speed) == 1
    assert data_speed[0]["name"] == "Internet Plan E"
    assert data_speed[0]["provider_name"] == "Provider Y"
    assert data_speed[0]["download_speed"] == 500.0

@pytest.mark.asyncio
async def test_search_endpoint_no_results(client: AsyncClient, session: AsyncSession, test_products: List[StandardizedProduct]):
    """Тест поиска без результатов."""
    await store_standardized_data(session=session, data=test_products)

    # Тест с несуществующим типом продукта
    response_type = await client.get("/search", params={"product_type": "gas_plan"})
    assert response_type.status_code == 200
    assert len(response_type.json()) == 0

    # Тест с фильтрами, исключающими все результаты
    response_filtered = await client.get("/search", params={"product_type": "electricity_plan", "min_price": 1.0})
    assert response_filtered.status_code == 200
    assert len(response_filtered.json()) == 0

@pytest.mark.asyncio
async def test_search_endpoint_all_filters(client: AsyncClient, session: AsyncSession, test_products: List[StandardizedProduct]):
    """Тест различных комбинаций фильтров."""
    await store_standardized_data(session=session, data=test_products)
    
    # Тест по типу продукта
    response = await client.get("/search", params={"product_type": "mobile_plan"})
    assert response.status_code == 200
    assert {p["name"] for p in response.json()} == {"Mobile Plan C", "Mobile Plan D"}
    
    # Тест с комбинированными фильтрами
    response = await client.get("/search", params={
        "product_type": "internet_plan",
        "provider": "Provider X",
        "max_data_cap_gb": 600
    })
    assert response.status_code == 200
    assert {p["name"] for p in response.json()} == {"Internet Plan F"}
    
    # Тест без результатов
    response = await client.get("/search", params={"product_type": "gas_plan"})
    assert response.status_code == 200
    assert response.json() == []

if __name__ == "__main__":
    # Запуск базовых тестов
    print("Running basic data parser tests...")
    
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
    
    print("\nFor full test suite run: pytest test_api.py -v")
    print("Or run with more details: pytest test_api.py -v -s")