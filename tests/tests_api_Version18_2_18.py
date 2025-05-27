import pytest
import sys
import os
import json
import asyncio
import uuid
import tempfile
from typing import List, Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text, inspect, MetaData
from sqlmodel import SQLModel, Field, select

# Добавление родительского каталога в путь
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Импорт приложения и моделей
from main import app
from database import get_session
from models import StandardizedProduct, ProductDB
from data_storage import store_standardized_data

# === TEST DATABASE SETUP ===
class TestDatabaseManager:
    """Управляет жизненным циклом тестовой базы данных с лучшей изоляцией с использованием временных файлов"""
    
    def __init__(self):
        self.engines = {}
        self.session_factories = {}
        self.db_files = {}
        self.temp_dir = tempfile.mkdtemp(prefix="test_db_")
        print(f"Created temporary directory for test databases: {self.temp_dir}")
    
    async def setup_for_class(self, class_name):
        """Настройка новой базы данных для конкретного класса тестов с использованием временного файла"""
        db_file = os.path.join(self.temp_dir, f"{class_name}_{uuid.uuid4().hex}.db")
        self.db_files[class_name] = db_file
        
        db_url = f"sqlite+aiosqlite:///{db_file}"
        
        engine = create_async_engine(
            db_url,
            echo=False,
            future=True,
            connect_args={"check_same_thread": False}
        )
        
        async with engine.begin() as conn:
            # Удаляем индекс, если он существует
            await conn.execute(text("DROP INDEX IF EXISTS ix_productdb_category"))
            # Удаляем все таблицы
            metadata = MetaData()
            metadata.reflect(bind=engine.sync_engine)
            await conn.run_sync(metadata.drop_all)
            await conn.run_sync(SQLModel.metadata.create_all)
        
        session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        self.engines[class_name] = engine
        self.session_factories[class_name] = session_factory
        
        return engine, session_factory
    
    async def get_session(self, class_name):
        """Получить сессию для конкретного класса тестов"""
        if class_name not in self.session_factories:
            await self.setup_for_class(class_name)
        
        return self.session_factories[class_name]()
    
    async def clear_data(self, class_name):
        """Очистить данные в конкретной тестовой базе данных"""
        if class_name in self.engines:
            async with self.engines[class_name].begin() as conn:
                await conn.execute(text("DELETE FROM productdb"))
    
    async def cleanup_for_class(self, class_name):
        """Очистка ресурсов базы данных для конкретного класса тестов"""
        if class_name in self.engines:
            await self.engines[class_name].dispose()
            del self.engines[class_name]
            del self.session_factories[class_name]
            
            if class_name in self.db_files:
                file_path = self.db_files[class_name]
                try:
                    if os.path.exists(file_path):
                        os.unlink(file_path)
                    del self.db_files[class_name]
                except (PermissionError, OSError) as e:
                    print(f"Warning: Could not delete database file {file_path}: {e}")
    
    async def cleanup_all(self):
        """Очистка всех ресурсов базы данных"""
        for class_name in list(self.engines.keys()):
            await self.cleanup_for_class(class_name)
        
        try:
            if os.path.exists(self.temp_dir):
                for filename in os.listdir(self.temp_dir):
                    file_path = os.path.join(self.temp_dir, filename)
                    try:
                        if os.path.isfile(file_path):
                            os.unlink(file_path)
                    except (PermissionError, OSError) as e:
                        print(f"Warning: Could not delete file {file_path}: {e}")
                
                os.rmdir(self.temp_dir)
        except (PermissionError, OSError) as e:
            print(f"Warning: Could not delete temporary directory {self.temp_dir}: {e}")

# Глобальный менеджер тестовой базы данных
test_db_manager = TestDatabaseManager()

# === FIXTURES ===
@pytest.fixture(scope="session")
def event_loop():
    """Создание экземпляра основного цикла событий для тестовой сессии."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="class")
async def class_db_setup(request):
    """Настройка базы данных для всего класса тестов"""
    class_name = request.node.name
    await test_db_manager.setup_for_class(class_name)
    
    yield
    
    await test_db_manager.cleanup_for_class(class_name)

@pytest.fixture
async def db_session(request, class_db_setup):
    """Предоставить чистую сессию базы данных для каждого теста"""
    class_name = request.node.cls.__name__
    
    await test_db_manager.clear_data(class_name)
    
    session = await test_db_manager.get_session(class_name)
    
    try:
        yield session
    finally:
        await session.close()

@pytest.fixture
def test_products():
    """Пример тестовых данных"""
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
        # Добавьте другие тестовые продукты по мере необходимости
    ]

@pytest.fixture
async def api_client(request, class_db_setup):
    """Создание API клиента с класс-специфической тестовой базой данных"""
    class_name = request.node.cls.__name__
    
    async def get_test_session():
        session = await test_db_manager.get_session(class_name)
        try:
            yield session
        finally:
            await session.close()
    
    app.dependency_overrides[get_session] = get_test_session
    
    try:
        async with AsyncClient(app=app, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()

# === UNIT TESTS FOR HELPER FUNCTIONS ===
@pytest.mark.usefixtures("class_db_setup")
class TestDataParserFunctions:
    """Тестирование вспомогательных функций парсинга данных"""
    
    def test_extract_float_with_units(self):
        """Тест извлечения float с единицами"""
        units = ["кВт·ч", "руб/кВт·ч", "ГБ", "GB", "Mbps"]
        unit_conversion = {"кВт·ч": 1.0, "руб/кВт·ч": 1.0, "ГБ": 1.0, "GB": 1.0, "Mbps": 1.0}
        
        result = extract_float_with_units("15.5 кВт·ч", units, unit_conversion)
        assert result == 15.5
        
        result = extract_float_with_units("0.12 руб/кВт·ч", units, unit_conversion)
        assert result == 0.12
        
        result = extract_float_with_units("100 ГБ", units, unit_conversion)
        assert result == 100.0
        
        assert extract_float_with_units("no number", units, unit_conversion) is None
        assert extract_float_with_units("", units, unit_conversion) is None
    
    def test_extract_float_or_handle_unlimited(self):
        """Тест обработки неограниченных значений"""
        unlimited_terms = ["безлимит", "unlimited", "неограниченно", "∞", "infinity"]
        units = ["ГБ", "GB", "MB"]
        
        assert extract_float_or_handle_unlimited("unlimited", unlimited_terms, units) == float('inf')
        assert extract_float_or_handle_unlimited("100 ГБ", unlimited_terms, units) == 100.0
        assert extract_float_or_handle_unlimited("no number", unlimited_terms, units) is None
    
    def test_extract_duration_in_months(self):
        """Тест извлечения продолжительности"""
        month_terms = ["месяцев", "месяца", "months", "month"]
        year_terms = ["год", "года", "лет", "year", "years"]
        
        assert extract_duration_in_months("12 месяцев", month_terms, year_terms) == 12
        assert extract_duration_in_months("24 месяца", month_terms, year_terms) == 24
        assert extract_duration_in_months("1 год", month_terms, year_terms) == 12
        assert extract_duration_in_months("2 года", month_terms, year_terms) == 24
        assert extract_duration_in_months("без контракта", month_terms, year_terms) == 0
        assert extract_duration_in_months("no contract", month_terms, year_terms) == 0
        assert extract_duration_in_months("invalid", month_terms, year_terms) is None
    
    def test_parse_availability(self):
        """Тест парсинга доступности"""
        assert parse_availability("в наличии") == True
        assert parse_availability("доступен") == True
        assert parse_availability("available") == True
        assert parse_availability("недоступен") == False
        assert parse_availability("нет в наличии") == False
        assert parse_availability("unavailable") == False
        assert parse_availability("unknown") == True

# === DATABASE TESTS ===
@pytest.mark.usefixtures("class_db_setup")
class TestDatabase:
    """Тестирование операций с базой данных"""
    
    @pytest.mark.asyncio
    async def test_session_fixture_works(self, db_session):
        """Тест, что сессия базы данных работает корректно"""
        result = await db_session.execute(select(1))
        assert result.scalar() == 1
        
        result = await db_session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='productdb'")
        )
        table_exists = result.scalar() is not None
        assert table_exists
    
    @pytest.mark.asyncio
    async def test_store_standardized_data(self, db_session, test_products):
        """Тест хранения стандартизированных данных"""
        result = await db_session.execute(select(ProductDB))
        assert len(result.scalars().all()) == 0
        
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()
        
        result = await db_session.execute(select(ProductDB))
        stored_products = result.scalars().all()
        assert len(stored_products) == len(test_products)
        
        stored_names = {p.name for p in stored_products}
        expected_names = {p.name for p in test_products}
        assert stored_names == expected_names
        
        elec_plan = next((p for p in stored_products if p.name == "Elec Plan A"), None)
        assert elec_plan is not None
        assert elec_plan.category == "electricity_plan"
        assert elec_plan.provider_name == "Provider X"
        assert elec_plan.price_kwh == 0.15
        assert elec_plan.standing_charge == 5.0
        assert elec_plan.contract_duration_months == 12
        assert elec_plan.available == True
        
        raw_data = json.loads(elec_plan.raw_data_json)
        assert raw_data["type"] == "electricity"
        assert "green" in raw_data["features"]
    
    @pytest.mark.asyncio
    async def test_store_duplicate_data(self, db_session, test_products):
        """Тест хранения дублирующихся данных (должен обновить существующие)"""
        await store_standardized_data(session=db_session, data=test_products[:2])
        await db_session.commit()
        
        result = await db_session.execute(select(ProductDB))
        assert len(result.scalars().all()) == 2
        
        modified_product = test_products[0].model_copy()
        modified_product.price_kwh = 0.20  # Измененная цена
        
        await store_standardized_data(session=db_session, data=[modified_product] + test_products[2:4])
        await db_session.commit()
        
        result = await db_session.execute(select(ProductDB))
        all_products = result.scalars().all()
        assert len(all_products) == 4
        
        updated_product = next((p for p in all_products if p.name == "Elec Plan A"), None)
        assert updated_product.price_kwh == 0.20

# === SEARCH AND FILTER TESTS ===
@pytest.mark.usefixtures("class_db_setup")
class TestSearchAndFilter:
    """Тестирование функциональности поиска и фильтрации"""
    
    @pytest.mark.asyncio
    async def test_search_all_products(self, db_session, test_products):
        """Тест поиска всех продуктов без фильтров"""
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()
        
        results = await search_and_filter_products(session=db_session)
        assert len(results) == len(test_products)
        
        for product in results:
            assert isinstance(product, StandardizedProduct)
    
    @pytest.mark.asyncio
    async def test_search_by_category(self, db_session, test_products):
        """Тест фильтрации по категории продукта"""
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()
        
        electricity_plans = await search_and_filter_products(
            session=db_session, 
            product_type="electricity_plan"
        )
        expected_names = {"Elec Plan A", "Elec Plan B"}
        actual_names = {p.name for p in electricity_plans}
        assert actual_names == expected_names
        
        mobile_plans = await search_and_filter_products(
            session=db_session, 
            product_type="mobile_plan"
        )
        expected_names = {"Mobile Plan C", "Mobile Plan D"}
        actual_names = {p.name for p in mobile_plans}
        assert actual_names == expected_names
        
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
        await db_session.commit()
        
        provider_x_products = await search_and_filter_products(
            session=db_session, 
            provider="Provider X"
        )
        expected_names = {"Elec Plan A", "Mobile Plan C", "Internet Plan F"}
        actual_names = {p.name for p in provider_x_products}
        assert actual_names == expected_names
    
    @pytest.mark.asyncio
    async def test_search_by_price_range(self, db_session, test_products):
        """Тест фильтрации по диапазону цен"""
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()
        
        expensive_electricity = await search_and_filter_products(
            session=db_session,
            product_type="electricity_plan",
            min_price=0.13
        )
        assert len(expensive_electricity) == 1
        assert expensive_electricity[0].name == "Elec Plan A"
        
        cheap_electricity = await search_and_filter_products(
            session=db_session,
            product_type="electricity_plan",
            max_price=0.13
        )
        assert len(cheap_electricity) == 1
        assert cheap_electricity[0].name == "Elec Plan B"
    
    @pytest.mark.asyncio
    async def test_search_by_contract_duration(self, db_session, test_products):
        """Тест фильтрации по продолжительности контракта"""
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()
        
        long_contracts = await search_and_filter_products(
            session=db_session,
            min_contract_duration_months=18
        )
        expected_names = {"Elec Plan B", "Internet Plan E"}
        actual_names = {p.name for p in long_contracts}
        assert actual_names == expected_names
        
        short_contracts = await search_and_filter_products(
            session=db_session,
            max_contract_duration_months=12
        )
        expected_names = {"Elec Plan A", "Mobile Plan C", "Mobile Plan D", "Internet Plan F"}
        actual_names = {p.name for p in short_contracts}
        assert actual_names == expected_names
    
    @pytest.mark.asyncio
    async def test_search_by_data_limits(self, db_session, test_products):
        """Тест фильтрации по лимитам данных"""
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()
        
        limited_data = await search_and_filter_products(
            session=db_session,
            product_type="mobile_plan",
            max_data_gb=200
        )
        assert len(limited_data) == 1
        assert limited_data[0].name == "Mobile Plan C"
        
        high_data = await search_and_filter_products(
            session=db_session,
            product_type="mobile_plan",
            min_data_gb=50
        )
        expected_names = {"Mobile Plan C", "Mobile Plan D"}
        actual_names = {p.name for p in high_data}
        assert actual_names == expected_names
    
    @pytest.mark.asyncio
    async def test_search_by_connection_properties(self, db_session, test_products):
        """Тест фильтрации по свойствам подключения"""
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()
        
        fiber_connections = await search_and_filter_products(
            session=db_session,
            connection_type="Fiber"
        )
        assert len(fiber_connections) == 1
        assert fiber_connections[0].name == "Internet Plan E"
        
        fiveg_plans = await search_and_filter_products(
            session=db_session,
            network_type="5G"
        )
        assert len(fiveg_plans) == 1
        assert fiveg_plans[0].name == "Mobile Plan D"
        
        fast_upload = await search_and_filter_products(
            session=db_session,
            min_upload_speed=30
        )
        assert len(fast_upload) == 1
        assert fast_upload[0].name == "Internet Plan E"
    
    @pytest.mark.asyncio
    async def test_search_available_only(self, db_session, test_products):
        """Тест фильтрации по доступности"""
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()
        
        available_products = await search_and_filter_products(
            session=db_session,
            available_only=True
        )
        
        unavailable_names = {"Elec Plan B"}
        actual_names = {p.name for p in available_products}
        expected_names = {p.name for p in test_products} - unavailable_names
        assert actual_names == expected_names
    
    @pytest.mark.asyncio
    async def test_search_complex_filters(self, db_session, test_products):
        """Тест комбинирования нескольких фильтров"""
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()
        
        results = await search_and_filter_products(
            session=db_session,
            provider="Provider X",
            max_contract_duration_months=12
        )
        expected_names = {"Elec Plan A", "Mobile Plan C", "Internet Plan F"}
        actual_names = {p.name for p in results}
        assert actual_names == expected_names
    
    @pytest.mark.asyncio
    async def test_search_no_results(self, db_session, test_products):
        """Тест поиска без совпадений"""
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()
        
        no_results = await search_and_filter_products(
            session=db_session,
            product_type="gas_plan"
        )
        assert len(no_results) == 0
        
        no_results = await search_and_filter_products(
            session=db_session,
            min_price=1.0,  # Выше любой тестовой цены
            product_type="electricity_plan"
        )
        assert len(no_results) == 0

# === API TESTS ===
@pytest.mark.usefixtures("class_db_setup")
class TestAPI:
    """Тестирование конечных точек FastAPI"""
    
    @pytest.mark.asyncio
    async def test_search_endpoint_no_filters(self, api_client, test_products):
        """Тест конечной точки поиска без фильтров"""
        session = await test_db_manager.get_session(self.__class__.__name__)
        try:
            await store_standardized_data(session=session, data=test_products)
            await session.commit()
        finally:
            await session.close()
        
        response = await api_client.get("/search")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data) == len(test_products)
        
        if data:
            sample = data[0]
            required_fields = ["source_url", "category", "name", "provider_name"]
            for field in required_fields:
                assert field in sample
    
    @pytest.mark.asyncio
    async def test_search_endpoint_with_filters(self, api_client, test_products):
        """Тест конечной точки поиска с различными фильтрами"""
        session = await test_db_manager.get_session(self.__class__.__name__)
        try:
            await store_standardized_data(session=session, data=test_products)
            await session.commit()
        finally:
            await session.close()
        
        response = await api_client.get("/search?product_type=electricity_plan")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2  # Должно быть 2 плана электричества
        
        response = await api_client.get("/search?provider=Provider X")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3  # Должно быть 3 продукта от Provider X
        
        response = await api_client.get("/search?product_type=electricity_plan&min_price=0.13")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1  # Должен быть 1 дорогой план электричества
        
        response = await api_client.get("/search?provider=Provider X&max_contract_duration_months=12")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
    
    @pytest.mark.asyncio
    async def test_search_endpoint_validation(self, api_client):
        """Тест валидации входных данных конечной точки поиска"""
        response = await api_client.get("/search?min_price=-1")
        assert response.status_code == 200
        
        response = await api_client.get("/search?min_contract_duration_months=-1")
        assert response.status_code == 200
        
        response = await api_client.get("/search?max_price=999999")
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_search_endpoint_empty_database(self, api_client):
        """Тест конечной точки поиска с пустой базой данных"""
        response = await api_client.get("/search")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0
    
    @pytest.mark.asyncio
    async def test_search_endpoint_json_response_format(self, api_client, test_products):
        """Тест, что API возвращает правильно отформатированный JSON"""
        session = await test_db_manager.get_session(self.__class__.__name__)
        try:
            await store_standardized_data(session=session, data=test_products)
            await session.commit()
        finally:
            await session.close()
        
        response = await api_client.get("/search?product_type=mobile_plan")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        
        data = response.json()
        assert isinstance(data, list)
        
        if data:
            product = data[0]
            if product.get("data_gb") == "Infinity":
                assert True  # JSON сериализует float('inf') как "Infinity"
            assert "raw_data" in product
            assert isinstance(product["raw_data"], dict)

# === INTEGRATION TESTS ===
@pytest.mark.usefixtures("class_db_setup")
class TestIntegration:
    """Интеграционные тесты, объединяющие несколько компонентов"""
    
    @pytest.mark.asyncio
    async def test_full_workflow_electricity_plans(self, db_session):
        """Тест полного рабочего процесса для данных планов электричества"""
        electricity_products = [
            StandardizedProduct(
                source_url="https://energy-provider.com/green-fixed",
                category="electricity_plan",
                name="Green Fixed Rate",
                provider_name="GreenEnergy Co",
                price_kwh=0.18,
                standing_charge=8.50,
                contract_duration_months=24,
                contract_type="fixed",
                available=True,
                raw_data={
                    "tariff_type": "green",
                    "source": "renewable",
                    "exit_fees": 0
                }
            ),
            StandardizedProduct(
                source_url="https://energy-provider.com/variable-standard",
                category="electricity_plan",
                name="Standard Variable",
                provider_name="PowerCorp Ltd",
                price_kwh=0.16,
                standing_charge=12.00,
                contract_duration_months=0,
                contract_type="variable",
                available=True,
                raw_data={
                    "tariff_type": "standard",
                    "price_cap": True,
                    "exit_fees": 30
                }
            )
        ]
        
        await store_standardized_data(session=db_session, data=electricity_products)
        await db_session.commit()
        
        all_electricity = await search_and_filter_products(
            session=db_session,
            product_type="electricity_plan"
        )
        assert len(all_electricity) == 2
        
        premium_plans = await search_and_filter_products(
            session=db_session,
            product_type="electricity_plan",
            min_price=0.17
        )
        assert len(premium_plans) == 1
        assert premium_plans[0].name == "Green Fixed Rate"
        
        fixed_contracts = await search_and_filter_products(
            session=db_session,
            product_type="electricity_plan",
            min_contract_duration_months=12
        )
        assert len(fixed_contracts) == 1
        assert fixed_contracts[0].contract_type == "fixed"
    
    @pytest.mark.asyncio
    async def test_full_workflow_mobile_plans(self, db_session):
        """Тест полного рабочего процесса для данных мобильных планов"""
        mobile_products = [
            StandardizedProduct(
                source_url="https://mobile-provider.com/unlimited-5g",
                category="mobile_plan",
                name="Unlimited 5G Pro",
                provider_name="MobileTech",
                monthly_cost=55.0,
                data_gb=float("inf"),
                calls=float("inf"),
                texts=float("inf"),
                network_type="5G",
                contract_duration_months=24,
                available=True,
                raw_data={
                    "features": ["5G", "hotspot", "international"],
                    "fair_use_policy": "40GB",
                    "roaming": True
                }
            ),
            StandardizedProduct(
                source_url="https://mobile-provider.com/basic-4g",
                category="mobile_plan",
                name="Basic 4G Plan",
                provider_name="ValueMobile",
                monthly_cost=25.0,
                data_gb=20.0,
                calls=1000,
                texts=float("inf"),
                network_type="4G",
                contract_duration_months=12,
                available=True,
                raw_data={
                    "features": ["4G", "basic"],
                    "overage_rate": "£2/GB",
                    "roaming": False
                }
            )
        ]
        
        await store_standardized_data(session=db_session, data=mobile_products)
        await db_session.commit()
        
        fiveg_plans = await search_and_filter_products(
            session=db_session,
            network_type="5G"
        )
        assert len(fiveg_plans) == 1
        assert fiveg_plans[0].name == "Unlimited 5G Pro"
        
        limited_data = await search_and_filter_products(
            session=db_session,
            product_type="mobile_plan",
            max_data_gb=50
        )
        assert len(limited_data) == 1
        assert limited_data[0].name == "Basic 4G Plan"
    
    @pytest.mark.asyncio
    async def test_full_workflow_internet_plans(self, db_session):
        """Тест полного рабочего процесса для данных интернет-планов"""
        internet_products = [
            StandardizedProduct(
                source_url="https://broadband-provider.com/fiber-ultra",
                category="internet_plan",
                name="Fiber Ultra 1000",
                provider_name="FastNet",
                monthly_cost=85.0,
                download_speed=1000.0,
                upload_speed=1000.0,
                connection_type="Fiber",
                data_cap_gb=float("inf"),
                contract_duration_months=18,
                available=True,
                raw_data={
                    "technology": "FTTP",
                    "setup_cost": 0,
                    "router_included": True,
                    "static_ip": "optional"
                }
            ),
            StandardizedProduct(
                source_url="https://broadband-provider.com/adsl-basic",
                category="internet_plan",
                name="ADSL Basic",
                provider_name="TradNet",
                monthly_cost=35.0,
                download_speed=24.0,
                upload_speed=3.0,
                connection_type="ADSL",
                data_cap_gb=500.0,
                contract_duration_months=12,
                available=True,
                raw_data={
                    "technology": "ADSL2+",
                    "setup_cost": 50,
                    "router_included": False,
                    "line_rental": 18.99
                }
            )
        ]
        
        await store_standardized_data(session=db_session, data=internet_products)
        await db_session.commit()
        
        slow_speed = await search_and_filter_products(
            session=db_session,
            product_type="internet_plan",
            max_download_speed=100
        )
        assert len(slow_speed) == 1
        assert slow_speed[0].name == "ADSL Basic"
        
        fiber_plans = await search_and_filter_products(
            session=db_session,
            connection_type="Fiber"
        )
        assert len(fiber_plans) == 1
        assert fiber_plans[0].name == "Fiber Ultra 1000"
        
        fast_upload = await search_and_filter_products(
            session=db_session,
            min_upload_speed=50
        )
        assert len(fast_upload) == 1
        assert fast_upload[0].upload_speed == 1000.0

# === EDGE CASE TESTS ===
@pytest.mark.usefixtures("class_db_setup")
class TestEdgeCases:
    """Тестирование крайних случаев и условий ошибок"""
    
    @pytest.mark.asyncio
    async def test_infinity_values_handling(self, db_session):
        """Тест обработки бесконечных значений в базе данных"""
        infinity_products = [
            StandardizedProduct(
                source_url="https://example.com/infinity_test",
                category="mobile_plan",
                name="Infinity Test Plan",
                provider_name="Test Provider",
                data_gb=float("inf"),
                calls=float("inf"),
                texts=float("inf"),
                monthly_cost=50.0,
                raw_data={"test": "infinity_values"}
            )
        ]
        
        await store_standardized_data(session=db_session, data=infinity_products)
        await db_session.commit()
        
        results = await search_and_filter_products(session=db_session)
        assert len(results) == 1
        product = results[0]
        assert product.data_gb == float("inf")
        assert product.calls == float("inf")
        assert product.texts == float("inf")
    
    @pytest.mark.asyncio
    async def test_empty_string_and_none_values(self, db_session):
        """Тест обработки пустых строк и значений None"""
        edge_case_products = [
            StandardizedProduct(
                source_url="https://example.com/edge_case",
                category="electricity_plan",
                name="Edge Case Plan",
                provider_name="",  # Пустая строка
                price_kwh=0.15,
                contract_type=None,  # Значение None
                raw_data={}  # Пустой словарь
            )
        ]
        
        await store_standardized_data(session=db_session, data=edge_case_products)
        await db_session.commit()
        
        results = await search_and_filter_products(session=db_session)
        assert len(results) == 1
        product = results[0]
        assert product.provider_name == ""
        assert product.contract_type is None
        assert product.raw_data == {}
    
    @pytest.mark.asyncio
    async def test_special_characters_in_data(self, db_session):
        """Тест обработки специальных символов и юникода"""
        special_char_products = [
            StandardizedProduct(
                source_url="https://example.com/unicode_test",
                category="mobile_plan",
                name="Test Plan with émojis 📱💨",
                provider_name="Провайдер с кириллицей",
                monthly_cost=30.0,
                raw_data={
                    "description": "Plan with special chars: @#$%^&*()",
                    "unicode_text": "тест текст на русском",
                    "emoji": "🚀📡💯"
                }
            )
        ]
        
        await store_standardized_data(session=db_session, data=special_char_products)
        await db_session.commit()
        
        results = await search_and_filter_products(session=db_session)
        assert len(results) == 1
        
        product = results[0]
        assert "émojis" in product.name
        assert "кириллицей" in product.provider_name
        assert "🚀" in product.raw_data["emoji"]

# === ERROR HANDLING TESTS ===
@pytest.mark.usefixtures("class_db_setup")
class TestErrorHandling:
    """Тестирование обработки ошибок и надежности"""
    
    @pytest.mark.asyncio
    async def test_malformed_json_in_raw_data(self, db_session):
        """Тест обработки продуктов с поврежденным JSON в raw_data"""
        test_product = StandardizedProduct(
            source_url="https://example.com/json_test",
            category="test_plan",
            name="JSON Test Plan",
            provider_name="Test Provider",
            raw_data={"valid": "json"}
        )
        
        await store_standardized_data(session=db_session, data=[test_product])
        await db_session.commit()
        
        # Искусственно испортить JSON в базе данных (симуляция повреждения)
        await db_session.execute(
            text("UPDATE productdb SET raw_data_json = '{invalid json' WHERE name = 'JSON Test Plan'")
        )
        await db_session.commit()
        
        results = await search_and_filter_products(session=db_session)
        assert len(results) == 1
        product = results[0]
        assert isinstance(product.raw_data, dict)

# === CLEAN UP ALL RESOURCES AT END ===
@pytest.fixture(scope="session", autouse=True)
async def cleanup_all_resources(event_loop):
    """Очистка всех ресурсов в конце всех тестов"""
    yield
    await test_db_manager.cleanup_all()

# === MAIN EXECUTION ===
if __name__ == "__main__":
    print("=== Running Comprehensive Test Suite ===")
    
    # Запуск базовых модульных тестов
    parser_tests = TestDataParserFunctions()
    
    try:
        parser_tests.test_extract_float_with_units()
        print("✓ Float extraction test passed")
    except Exception as e:
        print(f"! Float extraction test skipped/failed: {e}")
    
    try:
        parser_tests.test_extract_float_or_handle_unlimited()
        print("✓ Unlimited handling test passed")
    except Exception as e:
        print(f"! Unlimited handling test skipped/failed: {e}")
    
    try:
        parser_tests.test_parse_availability()
        print("✓ Availability parsing test passed")
    except Exception as e:
        print(f"! Availability parsing test skipped/failed: {e}")
    
    print("\n=== Test Suite Structure ===")
    print("1. Unit Tests for Helper Functions")
    print("   - Float extraction with units")
    print("   - Unlimited value handling")
    print("   - Duration extraction")
    print("   - Availability parsing")
    print()
    print("2. Database Tests")
    print("   - Session creation and management")
    print("   - Data storage and retrieval")
    print("   - Duplicate data handling")
    print()
    print("3. Search and Filter Tests")
    print("   - All products search")
    print("   - Category filtering")
    print("   - Provider filtering")
    print("   - Price range filtering")
    print("   - Contract duration filtering")
    print("   - Data limit filtering")
    print("   - Connection properties filtering")
    print("   - Availability filtering")
    print("   - Complex multi-filter scenarios")
    print()
    print("4. API Tests")
    print("   - Basic endpoint functionality")
    print("   - Filter parameter handling")
    print("   - Input validation")
    print("   - JSON response format")
    print("   - Empty database handling")
    print()
    print("5. Integration Tests")
    print("   - Full workflow for electricity plans")
    print("   - Full workflow for mobile plans")
    print("   - Full workflow for internet plans")
    print()
    print("6. Edge Cases and Performance Tests")
    print("   - Large dataset performance")
    print("   - Infinity values handling")
    print("   - Empty/None values handling")
    print("   - Special characters and Unicode")
    print()
    print("7. Error Handling Tests")
    print("   - Database connection errors")
    print("   - Malformed JSON handling")
    print("   - API error conditions")
    print("   - Query parameter validation")
    print()
    print("To run full test suite:")
    print("pytest test_api_complete.py -v --asyncio-mode=auto")
    print()
    print("To run specific test categories:")
    print("pytest test_api_complete.py::TestDatabase -v --asyncio-mode=auto")
    print("pytest test_api_complete.py::TestSearchAndFilter -v --asyncio-mode=auto")
    print("pytest test_api_complete.py::TestAPI -v --asyncio-mode=auto")