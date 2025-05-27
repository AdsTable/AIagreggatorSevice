import os
import sys
import json
import asyncio
import tempfile
from typing import List, Optional
from sqlalchemy import text
from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

import pytest

# Добавляем родительскую директорию в path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Импорты для FastAPI тестирования
from httpx import AsyncClient, ASGITransport
from fastapi.testclient import TestClient

# Импорты приложения
try:
    from main import app
    from database import get_session
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
    print("Make sure all required modules are available")

# ============================
# TEST DATABASE SETUP
# ============================
class TestDatabaseManager:
    """
    Менеджер тестовой базы данных, использующий временный файл.
    Это гарантирует, что для каждого теста создается чистая база данных.
    """
    def __init__(self):
        self.temp_db_file = None
        self.engine = None
        self.session_factory = None

    async def setup(self):
        self.temp_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db_file.close()
        db_url = f"sqlite+aiosqlite:///{self.temp_db_file.name}"
        # Используем NullPool, чтобы каждая сессия создавала новое соединение
        self.engine = create_async_engine(
            db_url,
            echo=False,
            future=True,
            poolclass=NullPool,
            connect_args={"check_same_thread": False}
        )
        async with self.engine.begin() as conn:
            # Сбрасываем таблицы если существуют и создаем заново
            await conn.run_sync(SQLModel.metadata.drop_all)
            await conn.run_sync(SQLModel.metadata.create_all)
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

    async def get_session(self) -> AsyncSession:
        return self.session_factory()

    async def cleanup(self):
        if self.engine:
            await self.engine.dispose()
        if self.temp_db_file and os.path.exists(self.temp_db_file.name):
            os.unlink(self.temp_db_file.name)

# Фикстура, создающая новую базу для каждого теста
@pytest.fixture(scope="function")
async def shared_db():
    db = TestDatabaseManager()
    await db.setup()
    yield db
    await db.cleanup()

@pytest.fixture(scope="function")
async def db_session(shared_db):
    session = shared_db.session_factory()
    try:
        yield session
    finally:
        await session.close()

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

# Фикстура для API-клиента, переопределяющая зависимость get_session
@pytest.fixture
async def api_client(shared_db):
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
# UNIT TESTS FOR HELPER FUNCTIONS
# ============================
class TestDataParserFunctions:
    def test_extract_float_with_units(self):
        units = ["кВт·ч", "руб/кВт·ч", "ГБ", "GB", "Mbps"]
        unit_conversion = {"кВт·ч": 1.0, "руб/кВт·ч": 1.0, "ГБ": 1.0, "GB": 1.0, "Mbps": 1.0}
        result = extract_float_with_units("15.5 кВт·ч", units, unit_conversion)
        assert result == 15.5, f"Expected 15.5, got {result}"

    def test_extract_float_or_handle_unlimited(self):
        unlimited_terms = ["безлимит", "unlimited", "неограниченно", "∞", "infinity"]
        units = ["ГБ", "GB", "MB"]
        result = extract_float_or_handle_unlimited("unlimited", unlimited_terms, units)
        assert result == float('inf')
        result = extract_float_or_handle_unlimited("100 ГБ", unlimited_terms, units)
        assert result == 100.0
        result = extract_float_or_handle_unlimited("no number", unlimited_terms, units)
        assert result is None

    def test_extract_duration_in_months(self):
        month_terms = ["месяцев", "месяца"]
        year_terms = ["год", "года", "лет"]
        result = extract_duration_in_months("12 месяцев", month_terms, year_terms)
        assert result == 12, f"Expected 12, got {result}"
        result = extract_duration_in_months("1 год", month_terms, year_terms)
        assert result == 12

    def test_parse_availability(self):
        for val in ["в наличии", "available", "недоступен", "unavailable", "", None]:
            result = parse_availability(val)
            assert isinstance(result, bool), f"For {val}, expected bool but got {type(result)}"

# ============================
# DATABASE TESTS
# ============================
class TestDatabase:
    @pytest.mark.asyncio
    async def test_session_fixture_works(self, db_session):
        result = await db_session.execute(select(1))
        assert result.scalar() == 1
        result = await db_session.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='productdb'"))
        table_exists = result.scalar() is not None
        assert table_exists

    @pytest.mark.asyncio
    async def test_store_standardized_data(self, db_session, test_products):
        result = await db_session.execute(select(ProductDB))
        assert len(result.scalars().all()) == 0
        await store_standardized_data(session=db_session, data=test_products)
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
        raw_data = json.loads(elec_plan.raw_data_json)
        assert raw_data["type"] == "electricity"
        assert "green" in raw_data["features"]

    @pytest.mark.asyncio
    async def test_store_duplicate_data(self, db_session, test_products):
        await store_standardized_data(session=db_session, data=test_products[:2])
        result = await db_session.execute(select(ProductDB))
        assert len(result.scalars().all()) == 2
        modified_product = test_products[0].model_copy()
        modified_product.price_kwh = 0.20
        await store_standardized_data(session=db_session, data=[modified_product] + test_products[2:4])
        result = await db_session.execute(select(ProductDB))
        all_products = result.scalars().all()
        assert len(all_products) == 4
        updated_product = next((p for p in all_products if p.name == "Elec Plan A"), None)
        assert updated_product.price_kwh == 0.20

# ============================
# SEARCH AND FILTER TESTS
# ============================
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
    query = select(ProductDB)
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
    standardized_products = []
    for db_product in db_products:
        raw_data = json.loads(db_product.raw_data_json) if db_product.raw_data_json else {}
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
    return standardized_products

class TestSearchAndFilter:
    @pytest.mark.asyncio
    async def test_search_all_products(self, db_session, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        results = await search_and_filter_products(session=db_session)
        assert len(results) == len(test_products)
        for product in results:
            assert isinstance(product, StandardizedProduct)

    @pytest.mark.asyncio
    async def test_search_by_category(self, db_session, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        electricity_plans = await search_and_filter_products(session=db_session, product_type="electricity_plan")
        expected_names = {"Elec Plan A", "Elec Plan B"}
        actual_names = {p.name for p in electricity_plans}
        assert actual_names == expected_names

    @pytest.mark.asyncio
    async def test_search_by_provider(self, db_session, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        provider_x_products = await search_and_filter_products(session=db_session, provider="Provider X")
        expected_names = {"Elec Plan A", "Mobile Plan C", "Internet Plan F"}
        actual_names = {p.name for p in provider_x_products}
        assert actual_names == expected_names

    @pytest.mark.asyncio
    async def test_search_by_price_range(self, db_session, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        expensive_electricity = await search_and_filter_products(session=db_session, product_type="electricity_plan", min_price=0.13)
        assert len(expensive_electricity) == 1
        assert expensive_electricity[0].name == "Elec Plan A"
        cheap_electricity = await search_and_filter_products(session=db_session, product_type="electricity_plan", max_price=0.13)
        assert len(cheap_electricity) == 1
        assert cheap_electricity[0].name == "Elec Plan B"

    @pytest.mark.asyncio
    async def test_search_by_contract_duration(self, db_session, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        long_contracts = await search_and_filter_products(session=db_session, min_contract_duration_months=18)
        expected_names = {"Elec Plan B", "Internet Plan E"}
        actual_names = {p.name for p in long_contracts}
        assert actual_names == expected_names

    @pytest.mark.asyncio
    async def test_search_available_only(self, db_session, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        available_products = await search_and_filter_products(session=db_session, available_only=True)
        unavailable_names = {"Elec Plan B"}
        actual_names = {p.name for p in available_products}
        expected_names = {p.name for p in test_products} - unavailable_names
        assert actual_names == expected_names

    @pytest.mark.asyncio
    async def test_search_no_results(self, db_session, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        no_results = await search_and_filter_products(session=db_session, product_type="gas_plan")
        assert len(no_results) == 0

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
        assert len(data) == 3
        response = await api_client.get("/search?product_type=electricity_plan&min_price=0.13")
        assert response.status_code == 200, response.text
        data = response.json()
        assert len(data) == 1
        response = await api_client.get("/search?provider=Provider X&max_contract_duration_months=12")
        assert response.status_code == 200, response.text
        data = response.json()
        assert len(data) == 3

    @pytest.mark.asyncio
    async def test_search_endpoint_validation(self, api_client):
        response = await api_client.get("/search?min_price=-1")
        assert response.status_code == 200, response.text
        response = await api_client.get("/search?min_contract_duration_months=-1")
        assert response.status_code == 200, response.text
        response = await api_client.get("/search?max_price=999999")
        assert response.status_code == 200, response.text

    @pytest.mark.asyncio
    async def test_search_endpoint_empty_database(self, api_client):
        response = await api_client.get("/search")
        assert response.status_code == 200, response.text
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_search_endpoint_json_response_format(self, api_client, db_session, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        response = await api_client.get("/search?product_type=mobile_plan")
        assert response.status_code == 200, response.text
        assert "application/json" in response.headers["content-type"]
        data = response.json()
        assert isinstance(data, list)
        if data:
            product = data[0]
            assert "raw_data" in product
            assert isinstance(product["raw_data"], dict)

# ============================
# INTEGRATION TESTS
# ============================
class TestIntegration:
    @pytest.mark.asyncio
    async def test_full_workflow_electricity_plans(self, db_session):
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
                raw_data={"tariff_type": "green", "source": "renewable", "exit_fees": 0}
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
                raw_data={"tariff_type": "standard", "price_cap": True, "exit_fees": 30}
            )
        ]
        await store_standardized_data(session=db_session, data=electricity_products)
        all_electricity = await search_and_filter_products(session=db_session, product_type="electricity_plan")
        assert len(all_electricity) == 2
        premium_plans = await search_and_filter_products(session=db_session, product_type="electricity_plan", min_price=0.17)
        assert len(premium_plans) == 1
        assert premium_plans[0].name == "Green Fixed Rate"

    @pytest.mark.asyncio
    async def test_full_workflow_mobile_plans(self, db_session):
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
                raw_data={"features": ["5G", "hotspot", "international"], "fair_use_policy": "40GB", "roaming": True}
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
                raw_data={"features": ["4G", "basic"], "overage_rate": "£2/GB", "roaming": False}
            )
        ]
        await store_standardized_data(session=db_session, data=mobile_products)
        fiveg_plans = await search_and_filter_products(session=db_session, network_type="5G")
        assert len(fiveg_plans) == 1
        assert fiveg_plans[0].name == "Unlimited 5G Pro"
        limited_data = await search_and_filter_products(session=db_session, product_type="mobile_plan", max_data_gb=50)
        assert len(limited_data) == 1
        assert limited_data[0].name == "Basic 4G Plan"

    @pytest.mark.asyncio
    async def test_full_workflow_internet_plans(self, db_session):
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
                raw_data={"technology": "FTTP", "setup_cost": 0, "router_included": True, "static_ip": "optional"}
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
                raw_data={"technology": "ADSL2+", "setup_cost": 50, "router_included": False, "line_rental": 18.99}
            )
        ]
        await store_standardized_data(session=db_session, data=internet_products)
        high_speed = await search_and_filter_products(session=db_session, product_type="internet_plan", max_download_speed=100)
        assert len(high_speed) == 1
        assert high_speed[0].name == "ADSL Basic"
        fiber_plans = await search_and_filter_products(session=db_session, connection_type="Fiber")
        assert len(fiber_plans) == 1
        assert fiber_plans[0].name == "Fiber Ultra 1000"
        fast_upload = await search_and_filter_products(session=db_session, min_upload_speed=50)
        assert len(fast_upload) == 1
        assert fast_upload[0].upload_speed == 1000.0

# ============================
# PERFORMANCE AND EDGE CASE TESTS
# ============================
class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_large_dataset_performance(self, db_session):
        large_dataset = []
        for i in range(100):
            product = StandardizedProduct(
                source_url=f"https://example.com/product_{i}",
                category="electricity_plan" if i % 3 == 0 else "mobile_plan" if i % 3 == 1 else "internet_plan",
                name=f"Test Product {i}",
                provider_name=f"Provider {i % 10}",
                price_kwh=0.10 + (i % 20) * 0.01,
                monthly_cost=20.0 + (i % 50) * 2.0,
                contract_duration_months=(i % 4) * 12,
                available=(i % 4) != 0,
                raw_data={"index": i, "batch": "performance_test"}
            )
            large_dataset.append(product)
        await store_standardized_data(session=db_session, data=large_dataset)
        import time
        start_time = time.time()
        results = await search_and_filter_products(session=db_session)
        end_time = time.time()
        search_time = end_time - start_time
        assert len(results) == 100
        assert search_time < 1.0
        start_time = time.time()
        filtered_results = await search_and_filter_products(session=db_session, provider="Provider 5", available_only=True, min_price=0.15)
        end_time = time.time()
        filtered_search_time = end_time - start_time
        assert len(filtered_results) > 0
        assert filtered_search_time < 1.0

    @pytest.mark.asyncio
    async def test_infinity_values_handling(self, db_session):
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
        results = await search_and_filter_products(session=db_session)
        assert len(results) == 1
        product = results[0]
        assert product.data_gb == float("inf")
        assert product.calls == float("inf")
        assert product.texts == float("inf")

    @pytest.mark.asyncio
    async def test_empty_string_and_none_values(self, db_session):
        edge_case_products = [
            StandardizedProduct(
                source_url="https://example.com/edge_case",
                category="electricity_plan",
                name="Edge Case Plan",
                provider_name="",
                price_kwh=0.15,
                contract_type=None,
                raw_data={}
            )
        ]
        await store_standardized_data(session=db_session, data=edge_case_products)
        results = await search_and_filter_products(session=db_session)
        assert len(results) == 1
        product = results[0]
        assert product.provider_name == ""
        assert product.contract_type is None
        assert product.raw_data == {}

    @pytest.mark.asyncio
    async def test_special_characters_in_data(self, db_session):
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
        results = await search_and_filter_products(session=db_session)
        assert len(results) == 1
        product = results[0]
        assert "émojis" in product.name
        assert "кириллицей" in product.provider_name
        assert "🚀" in product.raw_data.get("emoji", "")

# ============================
# ERROR HANDLING TESTS
# ============================
class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_database_connection_error_handling(self):
        from sqlalchemy.exc import OperationalError
        invalid_engine = create_async_engine("sqlite+aiosqlite:///invalid/path/test.db", poolclass=NullPool)
        invalid_session_factory = async_sessionmaker(invalid_engine, class_=AsyncSession)
        try:
            async with invalid_session_factory() as session:
                await session.execute(select(1))
            assert False, "Expected connection error"
        except Exception as e:
            assert True
        finally:
            await invalid_engine.dispose()

    @pytest.mark.asyncio
    async def test_malformed_json_in_raw_data(self, db_session):
        test_product = StandardizedProduct(
            source_url="https://example.com/json_test",
            category="test_plan",
            name="JSON Test Plan",
            provider_name="Test Provider",
            raw_data={"valid": "json"}
        )
        await store_standardized_data(session=db_session, data=[test_product])
        await db_session.execute(text("UPDATE productdb SET raw_data_json = '{invalid json' WHERE name = 'JSON Test Plan'"))
        await db_session.commit()
        results = await search_and_filter_products(session=db_session)
        assert len(results) == 1
        product = results[0]
        assert isinstance(product.raw_data, dict)

# ============================
# API ERROR TESTS
# ============================
class TestAPIErrors:
    @pytest.mark.asyncio
    async def test_api_with_database_error(self, api_client):
        response = await api_client.get("/search")
        assert response.status_code == 200, response.text
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_api_malformed_query_parameters(self, api_client):
        response = await api_client.get("/search?min_price=not_a_number")
        assert response.status_code in [200, 400, 422]
        long_string = "x" * 10000
        response = await api_client.get(f"/search?provider={long_string}")
        assert response.status_code in [200, 400, 414]