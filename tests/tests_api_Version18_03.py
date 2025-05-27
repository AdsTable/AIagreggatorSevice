import pytest
import sys
import os
import json
import asyncio
import uuid
import logging
from typing import Dict, Any, List, Optional
from unittest.mock import patch, MagicMock
from contextlib import asynccontextmanager

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# FastAPI testing imports
from httpx import AsyncClient
from fastapi.testclient import TestClient

# Database imports
from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import text, MetaData
from sqlalchemy.engine import Engine

# Application imports
try:
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
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure all required modules are available")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === IMPROVED TEST DATABASE SETUP ===

class IsolatedTestDatabase:
    """
    Полностью изолированная тестовая база данных с правильным управлением жизненным циклом
    """
    
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self.db_id = str(uuid.uuid4())[:8]
        self._is_initialized = False
        
    async def initialize(self):
        """Инициализация изолированной in-memory базы данных"""
        if self._is_initialized:
            return
            
        # Используем in-memory SQLite для максимальной изоляции
        database_url = f"sqlite+aiosqlite:///:memory:"
        
        self.engine = create_async_engine(
            database_url,
            echo=False,
            future=True,
            poolclass=StaticPool,
            connect_args={
                "check_same_thread": False,
                "timeout": 30,
                "isolation_level": None  # Для in-memory БД
            }
        )
        
        # Создание сессии factory
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=True,
            autocommit=False
        )
        
        # Создание схемы БД
        await self._create_schema()
        self._is_initialized = True
        logger.info(f"Инициализирована изолированная БД {self.db_id}")
    
    async def _create_schema(self):
        """Безопасное создание схемы с обработкой конфликтов индексов"""
        try:
            async with self.engine.begin() as conn:
                # Создаем все таблицы и индексы
                await conn.run_sync(SQLModel.metadata.create_all)
                logger.info(f"Схема БД {self.db_id} создана успешно")
        except Exception as e:
            logger.error(f"Ошибка создания схемы БД {self.db_id}: {e}")
            # Для in-memory БД пытаемся пересоздать движок
            await self._reinitialize_engine()
    
    async def _reinitialize_engine(self):
        """Переинициализация движка БД при критических ошибках"""
        if self.engine:
            await self.engine.dispose()
        
        # Создаем новый движок
        database_url = f"sqlite+aiosqlite:///:memory:"
        self.engine = create_async_engine(
            database_url,
            echo=False,
            future=True,
            poolclass=StaticPool,
            connect_args={
                "check_same_thread": False,
                "timeout": 30,
                "isolation_level": None
            }
        )
        
        # Пересоздаем session factory
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        # Создаем схему заново
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        
        logger.info(f"БД {self.db_id} переинициализирована")
    
    @asynccontextmanager
    async def get_session(self):
        """Контекстный менеджер для получения сессии БД"""
        if not self._is_initialized:
            await self.initialize()
        
        async with self.session_factory() as session:
            try:
                yield session
            except Exception as e:
                logger.error(f"Ошибка сессии БД {self.db_id}: {e}")
                await session.rollback()
                raise
            finally:
                await session.close()
    
    async def clear_data(self):
        """Очистка всех данных без удаления структуры"""
        if not self._is_initialized:
            return
            
        try:
            async with self.get_session() as session:
                # Очищаем данные из всех таблиц
                await session.execute(text("DELETE FROM productdb"))
                await session.commit()
                logger.info(f"Данные БД {self.db_id} очищены")
        except Exception as e:
            logger.error(f"Ошибка очистки данных БД {self.db_id}: {e}")
            # При ошибке пересоздаем БД
            await self._reinitialize_engine()
    
    async def cleanup(self):
        """Финальная очистка ресурсов"""
        if self.engine:
            await self.engine.dispose()
            logger.info(f"БД {self.db_id} очищена")
        self._is_initialized = False

# === FIXTURE MANAGEMENT ===

@pytest.fixture(scope="function")
async def isolated_db():
    """Изолированная БД для каждого теста"""
    db = IsolatedTestDatabase()
    await db.initialize()
    try:
        yield db
    finally:
        await db.cleanup()

@pytest.fixture
async def db_session(isolated_db):
    """Сессия БД с автоматической очисткой"""
    async with isolated_db.get_session() as session:
        yield session

@pytest.fixture
def test_products():
    """Тестовые данные продуктов"""
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
async def api_client(isolated_db):
    """API клиент с изолированной БД"""
    async def get_test_session():
        async with isolated_db.get_session() as session:
            yield session
    
    # Переопределяем зависимость
    app.dependency_overrides[get_session] = get_test_session
    
    try:
        async with AsyncClient(app=app, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()

# === УЛУЧШЕННАЯ ФУНКЦИЯ ПОИСКА ===

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
    max_download_speed: Optional[float] = None,
    min_upload_speed: Optional[float] = None,
    connection_type: Optional[str] = None,
    network_type: Optional[str] = None,
    available_only: bool = False
) -> List[StandardizedProduct]:
    """Поиск и фильтрация продуктов с улучшенной обработкой ошибок"""
    try:
        query = select(ProductDB)
        
        # Построение фильтров
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
        if min_upload_speed is not None:
            filters.append(ProductDB.upload_speed >= min_upload_speed)
        if connection_type:
            filters.append(ProductDB.connection_type == connection_type)
        if network_type:
            filters.append(ProductDB.network_type == network_type)
        if available_only:
            filters.append(ProductDB.available == True)
        
        if filters:
            query = query.where(*filters)
        
        result = await session.execute(query)
        db_products = result.scalars().all()
        
        # Конвертация в StandardizedProduct с обработкой ошибок
        standardized_products = []
        for db_product in db_products:
            try:
                # Безопасная обработка JSON
                raw_data = db_product.raw_data_json or {}
                if isinstance(raw_data, str):
                    try:
                        raw_data = json.loads(raw_data)
                    except (json.JSONDecodeError, TypeError):
                        logger.warning(f"Некорректный JSON для продукта {db_product.id}")
                        raw_data = {}
                
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
            except Exception as e:
                logger.error(f"Ошибка конвертации продукта {db_product.id}: {e}")
                continue
        
        return standardized_products
        
    except Exception as e:
        logger.error(f"Ошибка в search_and_filter_products: {e}")
        return []

# === UNIT TESTS FOR HELPER FUNCTIONS ===

class TestDataParserFunctions:
    """Тестирование функций парсинга данных"""
    
    def test_extract_float_with_units(self):
        """Тест извлечения float с единицами измерения"""
        units = ["кВт·ч", "руб/кВт·ч", "ГБ", "GB", "Mbps"]
        unit_conversion = {"кВт·ч": 1.0, "руб/кВт·ч": 1.0, "ГБ": 1.0, "GB": 1.0, "Mbps": 1.0}
        
        # Валидные извлечения
        assert extract_float_with_units("15.5 кВт·ч", units, unit_conversion) == 15.5
        assert extract_float_with_units("0.12 руб/кВт·ч", units, unit_conversion) == 0.12
        assert extract_float_with_units("100 ГБ", units, unit_conversion) == 100.0
        assert extract_float_with_units("50.5 GB", units, unit_conversion) == 50.5
        assert extract_float_with_units("1000 Mbps", units, unit_conversion) == 1000.0
        
        # Невалидные извлечения
        assert extract_float_with_units("no number", units, unit_conversion) is None
        assert extract_float_with_units("", units, unit_conversion) is None
        assert extract_float_with_units("15.5 unknown_unit", units, unit_conversion) is None
    
    def test_extract_float_or_handle_unlimited(self):
        """Тест обработки безлимитных значений"""
        unlimited_terms = ["безлимит", "unlimited", "неограниченно", "∞", "infinity"]
        units = ["ГБ", "GB", "MB"]
        
        # Безлимитные случаи
        assert extract_float_or_handle_unlimited("безлимит", unlimited_terms, units) == float('inf')
        assert extract_float_or_handle_unlimited("unlimited", unlimited_terms, units) == float('inf')
        assert extract_float_or_handle_unlimited("неограниченно", unlimited_terms, units) == float('inf')
        assert extract_float_or_handle_unlimited("∞", unlimited_terms, units) == float('inf')
        
        # Обычные числовые случаи
        assert extract_float_or_handle_unlimited("100 ГБ", unlimited_terms, units) == 100.0
        assert extract_float_or_handle_unlimited("50.5 GB", unlimited_terms, units) == 50.5
        
        # Невалидные случаи
        assert extract_float_or_handle_unlimited("no number", unlimited_terms, units) is None
        assert extract_float_or_handle_unlimited("", unlimited_terms, units) is None
    
    def test_extract_duration_in_months(self):
        """Тест извлечения продолжительности"""
        # Валидные продолжительности
        assert extract_duration_in_months("12 месяцев") == 12
        assert extract_duration_in_months("24 месяца") == 24
        assert extract_duration_in_months("1 год") == 12
        assert extract_duration_in_months("2 года") == 24
        assert extract_duration_in_months("6 months") == 6
        assert extract_duration_in_months("1 year") == 12
        
        # Специальные случаи
        assert extract_duration_in_months("без контракта") == 0
        assert extract_duration_in_months("no contract") == 0
        assert extract_duration_in_months("prepaid") == 0
        
        # Невалидные случаи
        assert extract_duration_in_months("invalid") is None
        assert extract_duration_in_months("") is None
    
    def test_parse_availability(self):
        """Тест парсинга доступности"""
        # Доступные случаи
        assert parse_availability("в наличии") == True
        assert parse_availability("доступен") == True
        assert parse_availability("available") == True
        assert parse_availability("в продаже") == True
        assert parse_availability("active") == True
        
        # Недоступные случаи
        assert parse_availability("недоступен") == False
        assert parse_availability("нет в наличии") == False
        assert parse_availability("unavailable") == False
        assert parse_availability("discontinued") == False
        assert parse_availability("out of stock") == False
        
        # Случай по умолчанию (неизвестно)
        assert parse_availability("unknown") == True
        assert parse_availability("") == True
        assert parse_availability(None) == True

# === DATABASE TESTS ===

class TestDatabase:
    """Тестирование операций с базой данных"""
    
    @pytest.mark.asyncio
    async def test_session_fixture_works(self, db_session):
        """Тест корректной работы fixture сессии БД"""
        # Тест базового запроса
        result = await db_session.execute(select(1))
        assert result.scalar() == 1
        
        # Тест существования таблицы
        result = await db_session.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='productdb'"))
        table_exists = result.scalar() is not None
        assert table_exists
    
    @pytest.mark.asyncio
    async def test_store_standardized_data(self, db_session, test_products):
        """Тест сохранения стандартизированных данных"""
        # Проверка пустой БД
        result = await db_session.execute(select(ProductDB))
        assert len(result.scalars().all()) == 0
        
        # Сохранение тестовых данных
        await store_standardized_data(session=db_session, data=test_products)
        
        # Проверка сохранения данных
        result = await db_session.execute(select(ProductDB))
        stored_products = result.scalars().all()
        assert len(stored_products) == len(test_products)
        
        # Проверка всех названий
        stored_names = {p.name for p in stored_products}
        expected_names = {p.name for p in test_products}
        assert stored_names == expected_names
        
        # Проверка деталей конкретного продукта
        elec_plan = next((p for p in stored_products if p.name == "Elec Plan A"), None)
        assert elec_plan is not None
        assert elec_plan.category == "electricity_plan"
        assert elec_plan.provider_name == "Provider X"
        assert elec_plan.price_kwh == 0.15
        assert elec_plan.standing_charge == 5.0
        assert elec_plan.contract_duration_months == 12
        assert elec_plan.available == True
        
        # Проверка raw data
        raw_data = elec_plan.raw_data_json
        assert raw_data["type"] == "electricity"
        assert "green" in raw_data["features"]
    
    @pytest.mark.asyncio
    async def test_store_duplicate_data(self, db_session, test_products):
        """Тест сохранения дублирующихся данных"""
        # Сохранение начальных данных
        await store_standardized_data(session=db_session, data=test_products[:2])
        
        # Проверка начального сохранения
        result = await db_session.execute(select(ProductDB))
        assert len(result.scalars().all()) == 2
        
        # Сохранение перекрывающихся данных
        modified_product = test_products[0].model_copy()
        modified_product.price_kwh = 0.20  # Изменение цены
        
        await store_standardized_data(session=db_session, data=[modified_product] + test_products[2:4])
        
        # Должно быть 4 продукта всего (2 оригинальных + 2 новых, с 1 обновленным)
        result = await db_session.execute(select(ProductDB))
        all_products = result.scalars().all()
        assert len(all_products) == 4
        
        # Проверка обновления цены
        updated_product = next((p for p in all_products if p.name == "Elec Plan A"), None)
        assert updated_product.price_kwh == 0.20

# === SEARCH AND FILTER TESTS ===

class TestSearchAndFilter:
    """Тестирование функций поиска и фильтрации"""
    
    @pytest.mark.asyncio
    async def test_search_all_products(self, db_session, test_products):
        """Тест поиска всех продуктов без фильтров"""
        await store_standardized_data(session=db_session, data=test_products)
        
        results = await search_and_filter_products(session=db_session)
        assert len(results) == len(test_products)
        
        # Проверка типов продуктов
        for product in results:
            assert isinstance(product, StandardizedProduct)
    
    @pytest.mark.asyncio
    async def test_search_by_category(self, db_session, test_products):
        """Тест фильтрации по категории продукта"""
        await store_standardized_data(session=db_session, data=test_products)
        
        # Тест планов электричества
        electricity_plans = await search_and_filter_products(
            session=db_session, 
            product_type="electricity_plan"
        )
        expected_names = {"Elec Plan A", "Elec Plan B"}
        actual_names = {p.name for p in electricity_plans}
        assert actual_names == expected_names
        
        # Тест мобильных планов
        mobile_plans = await search_and_filter_products(
            session=db_session, 
            product_type="mobile_plan"
        )
        expected_names = {"Mobile Plan C", "Mobile Plan D"}
        actual_names = {p.name for p in mobile_plans}
        assert actual_names == expected_names
        
        # Тест интернет планов
        internet_plans = await search_and_filter_products(
            session=db_session, 
            product_type="internet_plan"
        )
        expected_names = {"Internet Plan E", "Internet Plan F"}
        actual_names = {p.name for p in internet_plans}
        assert actual_names == expected_names
    
    @pytest.mark.asyncio
    async def test_search_by_provider(self, db_session, test_products):
        """Тест фильтрации по провайдеру"""
        await store_standardized_data(session=db_session, data=test_products)
        
        provider_x_products = await search_and_filter_products(
            session=db_session, 
            provider="Provider X"
        )
        expected_names = {"Elec Plan A", "Mobile Plan C", "Internet Plan F"}
        actual_names = {p.name for p in provider_x_products}
        assert actual_names == expected_names

# === API TESTS ===

class TestAPI:
    """Тестирование FastAPI эндпоинтов"""
    
    @pytest.mark.asyncio
    async def test_search_endpoint_no_filters(self, api_client, test_products, isolated_db):
        """Тест эндпоинта поиска без фильтров"""
        # Настройка данных
        async with isolated_db.get_session() as session:
            await store_standardized_data(session=session, data=test_products)
        
        # Тест API
        response = await api_client.get("/search")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data) == len(test_products)
        
        # Проверка структуры ответа
        if data:
            sample = data[0]
            required_fields = ["source_url", "category", "name", "provider_name"]
            for field in required_fields:
                assert field in sample
    
    @pytest.mark.asyncio
    async def test_search_endpoint_empty_database(self, api_client):
        """Тест эндпоинта поиска с пустой БД"""
        response = await api_client.get("/search")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0

# === MAIN EXECUTION ===

if __name__ == "__main__":
    print("=== Запуск улучшенного набора тестов ===")
    print("Ключевые улучшения:")
    print("✅ Полностью изолированные in-memory базы данных")
    print("✅ Правильное управление жизненным циклом")
    print("✅ Устранение конфликтов индексов")
    print("✅ Улучшенное логирование и обработка ошибок")
    print("✅ Контекстные менеджеры для сессий")
    print("✅ Автоматическая очистка ресурсов")
    print()
    print("Для запуска исправленного набора тестов:")
    print("pytest tests_api_Version18_fixed.py -v --asyncio-mode=auto")
    print()
    print("Для запуска конкретных категорий тестов:")
    print("pytest tests_api_Version18_fixed.py::TestDatabase -v")
    print("pytest tests_api_Version18_fixed.py::TestSearchAndFilter -v")
    print("pytest tests_api_Version18_fixed.py::TestAPI -v")