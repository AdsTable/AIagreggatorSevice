import pytest
import sys
import os
import json
import asyncio
from typing import Dict, Any, List, Optional
from unittest.mock import patch, MagicMock

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# FastAPI testing imports
from httpx import AsyncClient

# Database imports
from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import text

# Application imports
try:
    from main import app # Важно: если main.app создает таблицы при импорте, это может быть источником конфликта.
    from database import get_session # Зависимость для переопределения в FastAPI
    from models import StandardizedProduct, ProductDB
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
    # Убедитесь, что структура проекта позволяет эти импорты.

# === TEST DATABASE SETUP ===
class TestDatabaseManager:
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self._engine_created = False
        self._tables_created = False # Не используется в новой логике, но можно оставить для ясности

    async def setup_engine_and_session_factory(self):
        if self._engine_created:
            return
        db_url = "sqlite+aiosqlite:///:memory:" # База данных в памяти для тестов
        self.engine = create_async_engine(
            db_url,
            echo=False, # Можно установить True для отладки SQL запросов
            future=True,
            poolclass=StaticPool, # Гарантирует, что все подключения используют одну и ту же БД в памяти
            connect_args={"check_same_thread": False} # Необходимо для SQLite в асинхронном контексте
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False # Важно для тестов, чтобы объекты оставались доступными после commit
        )
        self._engine_created = True

    async def create_db_tables(self):
        if not self._engine_created:
            await self.setup_engine_and_session_factory()
        
        # Гарантируем создание таблиц на чистой основе
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all) # Удаляем все существующие таблицы (если есть)
            await conn.run_sync(SQLModel.metadata.create_all) # Создаем таблицы
        # self._tables_created = True # Помечаем, что таблицы созданы (если нужно отслеживать)


    async def get_session(self) -> AsyncSession:
        if not self.session_factory: # Проверка, что session_factory было создано
            # Это не должно происходить, если фикстуры настроены правильно
            await self.setup_engine_and_session_factory()
        return self.session_factory()

    async def clear_all_data(self):
        if self.engine: # Убедимся, что engine существует
            async with self.engine.begin() as conn:
                # Удаляем данные из всех таблиц в правильном порядке (учитывая зависимости)
                for table in reversed(SQLModel.metadata.sorted_tables):
                    await conn.execute(table.delete())
        # else:
            # print("Warning: clear_all_data called when DB engine is not available.")

    async def dispose_engine(self):
        if self.engine:
            await self.engine.dispose()
        self._engine_created = False
        # self._tables_created = False
        self.engine = None
        self.session_factory = None

test_db = TestDatabaseManager() # Глобальный экземпляр менеджера БД

# === PYTEST FIXTURES ===

@pytest.fixture(scope="session", autouse=True)
async def manage_db_lifecycle():
    """Управляет жизненным циклом БД на уровне сессии: создание engine и таблиц."""
    await test_db.setup_engine_and_session_factory() # 1. Создаем engine и session factory
    await test_db.create_db_tables()                 # 2. Создаем таблицы (с drop_all внутри)
    yield                                            # Тесты выполняются здесь
    await test_db.dispose_engine()                   # 3. Очищаем engine в конце сессии

@pytest.fixture(scope="function", autouse=True)
async def clear_db_data_before_each_test():
    """Очищает ДАННЫЕ из таблиц перед каждым тестом. Схема остается."""
    # manage_db_lifecycle (session, autouse) уже создал engine и таблицы.
    await test_db.clear_all_data()

@pytest.fixture
async def db_session() -> AsyncSession:
    """Предоставляет экземпляр сессии БД для теста."""
    # clear_db_data_before_each_test (function, autouse) уже очистил данные.
    session = await test_db.get_session()
    try:
        yield session
    finally:
        await session.close()

@pytest.fixture
def test_products():
    # Данные остаются без изменений
    return [
        StandardizedProduct(source_url="https://example.com/elec/plan_a", category="electricity_plan", name="Elec Plan A", provider_name="Provider X", price_kwh=0.15, standing_charge=5.0, contract_duration_months=12, available=True, raw_data={"type": "electricity", "features": ["green", "fixed"]}),
        StandardizedProduct(source_url="https://example.com/elec/plan_b", category="electricity_plan", name="Elec Plan B", provider_name="Provider Y", price_kwh=0.12, standing_charge=4.0, contract_duration_months=24, available=False, raw_data={"type": "electricity", "features": ["variable"]}),
        StandardizedProduct(source_url="https://example.com/mobile/plan_c", category="mobile_plan", name="Mobile Plan C", provider_name="Provider X", monthly_cost=30.0, data_gb=100.0, calls=float("inf"), texts=float("inf"), contract_duration_months=0, network_type="4G", available=True, raw_data={"type": "mobile", "features": ["unlimited_calls"]}),
        StandardizedProduct(source_url="https://example.com/mobile/plan_d", category="mobile_plan", name="Mobile Plan D", provider_name="Provider Z", monthly_cost=45.0, data_gb=float("inf"), calls=500, texts=float("inf"), contract_duration_months=12, network_type="5G", available=True, raw_data={"type": "mobile", "features": ["5G", "unlimited_data"]}),
        StandardizedProduct(source_url="https://example.com/internet/plan_e", category="internet_plan", name="Internet Plan E", provider_name="Provider Y", download_speed=500.0, upload_speed=50.0, connection_type="Fiber", data_cap_gb=float("inf"), monthly_cost=60.0, contract_duration_months=24, available=True, raw_data={"type": "internet", "features": ["fiber", "unlimited"]}),
        StandardizedProduct(source_url="https://example.com/internet/plan_f", category="internet_plan", name="Internet Plan F", provider_name="Provider X", download_speed=100.0, upload_speed=20.0, connection_type="DSL", data_cap_gb=500.0, monthly_cost=50.0, contract_duration_months=12, available=True, raw_data={"type": "internet", "features": ["dsl", "limited"]}),
    ]

@pytest.fixture
async def api_client() -> AsyncClient:
    """Предоставляет HTTP клиент для тестирования API, с переопределенной зависимостью сессии БД."""
    async def get_test_session_override(): # Эта функция будет использоваться FastAPI
        session_for_app = await test_db.get_session()
        try:
            yield session_for_app
        finally:
            await session_for_app.close()
    
    original_get_session_dependency = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = get_test_session_override
    
    try:
        async with AsyncClient(app=app, base_url="http://test") as client_instance:
            yield client_instance
    finally: # Восстанавливаем оригинальную зависимость (если была) или удаляем переопределение
        if original_get_session_dependency:
            app.dependency_overrides[get_session] = original_get_session_dependency
        elif get_session in app.dependency_overrides:
            del app.dependency_overrides[get_session]

# === SEARCH FUNCTION (логика конвертации ProductDB в StandardizedProduct улучшена) ===
async def search_and_filter_products(
    session: AsyncSession,
    product_type: Optional[str] = None, provider: Optional[str] = None,
    min_price: Optional[float] = None, max_price: Optional[float] = None,
    min_data_gb: Optional[float] = None, max_data_gb: Optional[float] = None,
    min_contract_duration_months: Optional[int] = None, max_contract_duration_months: Optional[int] = None,
    max_download_speed: Optional[float] = None, min_upload_speed: Optional[float] = None,
    connection_type: Optional[str] = None, network_type: Optional[str] = None,
    available_only: bool = False
) -> List[StandardizedProduct]:
    query = select(ProductDB)
    filters = []
    if product_type: filters.append(ProductDB.category == product_type)
    if provider: filters.append(ProductDB.provider_name == provider)
    
    # Фильтры по цене (пример: применяются к price_kwh)
    # В реальном приложении может потребоваться более сложная логика в зависимости от product_type
    if min_price is not None: filters.append(ProductDB.price_kwh >= min_price) 
    if max_price is not None: filters.append(ProductDB.price_kwh <= max_price)

    if min_data_gb is not None: filters.append(ProductDB.data_gb >= min_data_gb)
    if max_data_gb is not None: filters.append(ProductDB.data_gb <= max_data_gb)
    # Если ProductDB.data_cap_gb существует и релевантен:
    # if hasattr(ProductDB, 'data_cap_gb') and max_data_gb is not None:
    #     filters.append(ProductDB.data_cap_gb <= max_data_gb)


    if min_contract_duration_months is not None: filters.append(ProductDB.contract_duration_months >= min_contract_duration_months)
    if max_contract_duration_months is not None: filters.append(ProductDB.contract_duration_months <= max_contract_duration_months)
    
    if max_download_speed is not None: filters.append(ProductDB.download_speed <= max_download_speed)
    if min_upload_speed is not None: filters.append(ProductDB.upload_speed >= min_upload_speed)
    
    if connection_type: filters.append(ProductDB.connection_type == connection_type)
    if network_type: filters.append(ProductDB.network_type == network_type)
    if available_only: filters.append(ProductDB.available == True)
    
    if filters: query = query.where(*filters)
    
    result = await session.execute(query)
    db_products = result.scalars().all()
    
    standardized_products = []
    for db_product in db_products:
        raw_data = {}
        if db_product.raw_data_json:
            try:
                raw_data = json.loads(db_product.raw_data_json)
            except json.JSONDecodeError:
                # print(f"Warning: Malformed JSON for product {db_product.name or db_product.source_url}. Raw: '{db_product.raw_data_json}'")
                pass # Оставляем raw_data пустым словарем

        # Собираем данные для StandardizedProduct, обеспечивая наличие всех полей
        product_data_args = {}
        for field_name, field_model in StandardizedProduct.model_fields.items():
            if field_name == 'raw_data':
                product_data_args[field_name] = raw_data
            elif hasattr(db_product, field_name):
                product_data_args[field_name] = getattr(db_product, field_name)
            else:
                # Если поле отсутствует в db_product, используем значение по умолчанию из StandardizedProduct, если оно есть
                # Pydantic v2: field_model.default
                # Для обязательных полей без значения по умолчанию будет None, что может вызвать ошибку валидации,
                # если поле не Optional. Это указывает на несоответствие моделей.
                product_data_args[field_name] = field_model.default if field_model.is_required() == False else None


        try:
            product = StandardizedProduct(**product_data_args)
            standardized_products.append(product)
        except Exception as e: 
            # print(f"Error converting ProductDB to StandardizedProduct for {getattr(db_product, 'name', 'N/A')}: {e}")
            # print(f"Product data attempted: {product_data_args}")
            pass # Пропускаем продукт или обрабатываем ошибку иначе
            
    return standardized_products

# === UNIT TESTS FOR HELPER FUNCTIONS ===
class TestDataParserFunctions:
    # Эти тесты не должны зависеть от состояния БД.
    # Если они все еще падают с ошибкой БД, это указывает на очень глубокую проблему
    # с тем, как pytest или что-то еще инициализирует БД до их выполнения.
    # С новыми `autouse` фикстурами, `manage_db_lifecycle` выполнится до них.
    def test_extract_float_with_units(self):
        units = ["кВт·ч", "руб/кВт·ч", "ГБ", "GB", "Mbps"]
        unit_conversion = {"кВт·ч": 1.0, "руб/кВт·ч": 1.0, "ГБ": 1.0, "GB": 1.0, "Mbps": 1.0}
        assert extract_float_with_units("15.5 кВт·ч", units, unit_conversion) == 15.5
        assert extract_float_with_units("no number", units, unit_conversion) is None
    
    def test_extract_float_or_handle_unlimited(self):
        unlimited_terms = ["безлимит", "unlimited", "неограниченно", "∞", "infinity"]
        units = ["ГБ", "GB", "MB"]
        assert extract_float_or_handle_unlimited("unlimited", unlimited_terms, units) == float('inf')
        assert extract_float_or_handle_unlimited("100 ГБ", unlimited_terms, units) == 100.0

    def test_extract_duration_in_months(self):
        month_terms = ["месяцев", "месяца", "months", "month", "мес.", "мес"]
        year_terms = ["год", "года", "лет", "year", "years", "г.", "л."]
        assert extract_duration_in_months("12 месяцев", month_terms, year_terms) == 12
        assert extract_duration_in_months("1 год", month_terms, year_terms) == 12
        assert extract_duration_in_months("без контракта", month_terms, year_terms) == 0
    
    def test_parse_availability(self):
        assert parse_availability("available") == True
        assert parse_availability("unavailable") == False
        assert parse_availability("unknown") == True

# === DATABASE TESTS ===
# Важно: если store_standardized_data не делает commit, его нужно делать в тестах.
# Для простоты, предположим, что store_standardized_data или используемые им операции сессии
# требуют явного commit для фиксации изменений перед последующими запросами в том же тесте.
# Однако, если сессия используется как context manager (async with session.begin():), commit автоматический.
# В текущей реализации db_session, commit не автоматический для операций внутри yield.
class TestDatabase:
    @pytest.mark.asyncio
    async def test_session_fixture_works(self, db_session: AsyncSession):
        result = await db_session.execute(select(1))
        assert result.scalar_one() == 1
        
        table_name = ProductDB.__tablename__ if hasattr(ProductDB, '__tablename__') else 'productdb'
        table_exists_res = await db_session.execute(
            text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        )
        assert table_exists_res.scalar_one_or_none() is not None
    
    @pytest.mark.asyncio
    async def test_store_standardized_data(self, db_session: AsyncSession, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit() # Явный commit
        
        result_after = await db_session.execute(select(ProductDB))
        stored_db_products = result_after.scalars().all()
        assert len(stored_db_products) == len(test_products)
        
        # ... (остальные проверки)

    @pytest.mark.asyncio
    async def test_store_duplicate_data(self, db_session: AsyncSession, test_products):
        await store_standardized_data(session=db_session, data=test_products[:2])
        await db_session.commit()

        modified_product = test_products[0].model_copy(deep=True)
        modified_product.price_kwh = 0.20
        
        await store_standardized_data(session=db_session, data=[modified_product] + test_products[2:4])
        await db_session.commit()
        
        result_final = await db_session.execute(select(ProductDB))
        all_db_products = result_final.scalars().all()
        assert len(all_db_products) == 4
        # ... (остальные проверки)

# === SEARCH AND FILTER TESTS ===
class TestSearchAndFilter:
    @pytest.mark.asyncio
    async def test_search_all_products(self, db_session: AsyncSession, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()
        results = await search_and_filter_products(session=db_session)
        assert len(results) == len(test_products)

    # ... (остальные тесты поиска и фильтрации с await db_session.commit() после store_standardized_data)
    @pytest.mark.asyncio
    async def test_search_by_category(self, db_session: AsyncSession, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()
        electricity_plans = await search_and_filter_products(session=db_session, product_type="electricity_plan")
        assert {p.name for p in electricity_plans} == {"Elec Plan A", "Elec Plan B"}

    @pytest.mark.asyncio
    async def test_search_by_provider(self, db_session: AsyncSession, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()
        provider_x_products = await search_and_filter_products(session=db_session, provider="Provider X")
        assert {p.name for p in provider_x_products} == {"Elec Plan A", "Mobile Plan C", "Internet Plan F"}

    @pytest.mark.asyncio
    async def test_search_by_price_range(self, db_session: AsyncSession, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()
        # ... (тесты)

    @pytest.mark.asyncio
    async def test_search_by_contract_duration(self, db_session: AsyncSession, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()
        # ... (тесты)

    @pytest.mark.asyncio
    async def test_search_by_data_limits(self, db_session: AsyncSession, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()
        # ... (тесты)

    @pytest.mark.asyncio
    async def test_search_by_connection_properties(self, db_session: AsyncSession, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()
        # ... (тесты)

    @pytest.mark.asyncio
    async def test_search_available_only(self, db_session: AsyncSession, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()
        # ... (тесты)
    
    @pytest.mark.asyncio
    async def test_search_complex_filters(self, db_session: AsyncSession, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()
        # ... (тесты)

    @pytest.mark.asyncio
    async def test_search_no_results(self, db_session: AsyncSession, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()
        # ... (тесты)


# === API TESTS ===
class TestAPI:
    @pytest.mark.asyncio
    async def test_search_endpoint_no_filters(self, api_client: AsyncClient, db_session: AsyncSession, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit() # Данные должны быть в БД до вызова API
        
        response = await api_client.get("/search")
        assert response.status_code == 200
        assert len(response.json()) == len(test_products)

    @pytest.mark.asyncio
    async def test_search_endpoint_with_filters(self, api_client: AsyncClient, db_session: AsyncSession, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()
        # ... (тесты API с фильтрами)

    @pytest.mark.asyncio
    async def test_search_endpoint_validation(self, api_client: AsyncClient):
        response_bad_type = await api_client.get("/search?min_price=not_a_number")
        assert response_bad_type.status_code == 422

    @pytest.mark.asyncio
    async def test_search_endpoint_empty_database(self, api_client: AsyncClient, db_session: AsyncSession):
        # db_session здесь для того, чтобы убедиться, что clear_db_data_before_each_test отработала
        # и база действительно пуста перед вызовом API.
        count_res = await db_session.execute(select(func.count()).select_from(ProductDB))
        assert count_res.scalar_one() == 0
        
        response = await api_client.get("/search")
        assert response.status_code == 200
        assert len(response.json()) == 0
    
    @pytest.mark.asyncio
    async def test_search_endpoint_json_response_format(self, api_client: AsyncClient, db_session: AsyncSession, test_products):
        # ... (тест формата JSON ответа)
        pass # Placeholder

# === INTEGRATION TESTS ===
class TestIntegration:
    @pytest.mark.asyncio
    async def test_full_workflow_electricity_plans(self, db_session: AsyncSession):
        # ... (код теста с await db_session.commit() после store_standardized_data)
        pass # Placeholder

    @pytest.mark.asyncio
    async def test_full_workflow_mobile_plans(self, db_session: AsyncSession):
        # ... (код теста)
        pass

    @pytest.mark.asyncio
    async def test_full_workflow_internet_plans(self, db_session: AsyncSession):
        # ... (код теста)
        pass

# === PERFORMANCE AND EDGE CASE TESTS ===
class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_large_dataset_performance(self, db_session: AsyncSession):
        # ... (код теста с await db_session.commit())
        pass

    @pytest.mark.asyncio
    async def test_infinity_values_handling(self, db_session: AsyncSession):
        # ... (код теста)
        pass

    @pytest.mark.asyncio
    async def test_empty_string_and_none_values(self, db_session: AsyncSession):
        # ... (код теста)
        pass

    @pytest.mark.asyncio
    async def test_special_characters_in_data(self, db_session: AsyncSession):
        # ... (код теста)
        pass

# === ERROR HANDLING TESTS ===
class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_database_connection_error_handling(self):
        # Этот тест проверяет создание engine с невалидным URL, не затрагивая test_db
        with pytest.raises(Exception): 
            invalid_engine = create_async_engine("sqlite+aiosqlite:///nonexistent_path/test.db")
            try:
                async with invalid_engine.connect() as conn: # Попытка соединения должна упасть
                    await conn.execute(select(1))
            finally:
                if invalid_engine: await invalid_engine.dispose()
    
    @pytest.mark.asyncio
    async def test_malformed_json_in_raw_data(self, db_session: AsyncSession):
        # Используем db_session, который уже настроен и таблицы созданы
        from sqlalchemy import func # для select(func.count())
        await db_session.execute(
            text("INSERT INTO productdb (source_url, category, name, raw_data_json) VALUES (:s, :cat, :n, :raw)"),
            [{"s": "https://example.com/bad_json", "cat": "test_bad", "n": "Bad JSON Plan", "raw": "{'invalid_json: True"}]
        )
        await db_session.commit()
        
        results = await search_and_filter_products(session=db_session)
        bad_json_product = next((p for p in results if p.name == "Bad JSON Plan"), None)
        assert bad_json_product is not None, "Продукт с некорректным JSON не найден"
        assert bad_json_product.raw_data == {}, "Некорректный JSON должен приводить к пустому raw_data"

# === API ERROR TESTS ===
class TestAPIErrors:
    @pytest.mark.asyncio
    async def test_api_with_database_error_simulated(self, api_client: AsyncClient):
        # ... (код теста)
        pass

    @pytest.mark.asyncio
    async def test_api_malformed_query_parameters(self, api_client: AsyncClient):
        # ... (код теста)
        pass

# === MAIN EXECUTION ===
if __name__ == "__main__":
    print("Для запуска тестов используйте команду: pytest tests_api_Version18.py -v --asyncio-mode=auto")
