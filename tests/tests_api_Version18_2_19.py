import os
import sys
import uuid
import tempfile
import asyncio
import pytest
import json
from typing import Optional, List

from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from main import app
from database import get_session
from models import StandardizedProduct, ProductDB
from data_storage import store_standardized_data
from data_parser import (
    extract_float_with_units,
    extract_float_or_handle_unlimited,
    extract_duration_in_months,
    parse_availability,
)
from httpx import AsyncClient

# === Менеджер тестовой БД ===
class TestDatabaseManager:
    def __init__(self):
        self.engines = {}
        self.sync_engines = {}
        self.session_factories = {}
        self.db_files = {}
        self.temp_dir = tempfile.mkdtemp(prefix="test_db_")

    async def setup_for_class(self, class_name):
        db_file = os.path.join(self.temp_dir, f"{class_name}_{uuid.uuid4().hex}.db")
        self.db_files[class_name] = db_file
        db_url = f"sqlite+aiosqlite:///{db_file}"
        sync_db_url = f"sqlite:///{db_file}"

        # Сначала создаём sync engine для управления схемой
        sync_engine = create_engine(sync_db_url, future=True)
        SQLModel.metadata.drop_all(sync_engine)
        SQLModel.metadata.create_all(sync_engine)
        sync_engine.dispose()

        # Затем создаём async engine и сессионную фабрику для тестов
        engine = create_async_engine(db_url, echo=False, future=True, connect_args={"check_same_thread": False})
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        self.engines[class_name] = engine
        self.session_factories[class_name] = session_factory
        self.sync_engines[class_name] = sync_engine  # not used later, just for parity

    async def get_session(self, class_name):
        if class_name not in self.session_factories:
            await self.setup_for_class(class_name)
        return self.session_factories[class_name]()

    async def clear_data(self, class_name):
        if class_name in self.engines:
            async with self.engines[class_name].begin() as conn:
                await conn.execute(text("DELETE FROM productdb"))

    async def cleanup_for_class(self, class_name):
        if class_name in self.engines:
            await self.engines[class_name].dispose()
            del self.engines[class_name]
            del self.session_factories[class_name]
        file_path = self.db_files.get(class_name)
        if file_path and os.path.exists(file_path):
            os.unlink(file_path)
            del self.db_files[class_name]

    async def cleanup_all(self):
        for class_name in list(self.engines.keys()):
            await self.cleanup_for_class(class_name)
        if os.path.exists(self.temp_dir):
            os.rmdir(self.temp_dir)

test_db_manager = TestDatabaseManager()

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="class")
async def class_db_setup(request):
    class_name = request.node.name
    await test_db_manager.setup_for_class(class_name)
    yield
    await test_db_manager.cleanup_for_class(class_name)

@pytest.fixture
async def db_session(request, class_db_setup):
    class_name = request.node.cls.__name__
    await test_db_manager.clear_data(class_name)
    session = await test_db_manager.get_session(class_name)
    try:
        yield session
    finally:
        await session.close()

@pytest.fixture
async def api_client(request, class_db_setup):
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

# ==== Вспомогательная функция поиска ====
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

# ==== Тесты ====
@pytest.mark.usefixtures("class_db_setup")
class TestDataParserFunctions:
    def test_extract_float_with_units(self):
        units = ["кВт·ч", "руб/кВт·ч", "ГБ", "GB", "Mbps"]
        unit_conversion = {"кВт·ч": 1.0, "руб/кВт·ч": 1.0, "ГБ": 1.0, "GB": 1.0, "Mbps": 1.0}
        assert extract_float_with_units("15.5 кВт·ч", units, unit_conversion) == 15.5
    def test_extract_float_or_handle_unlimited(self):
        unlimited_terms = ["безлимит", "unlimited", "неограниченно", "∞", "infinity"]
        units = ["ГБ", "GB", "MB"]
        assert extract_float_or_handle_unlimited("безлимит", unlimited_terms, units) == float('inf')
    def test_extract_duration_in_months(self):
        month_terms = ["месяцев", "месяца", "months", "month"]
        year_terms = ["год", "года", "лет", "year", "years"]
        assert extract_duration_in_months("12 месяцев", month_terms, year_terms) == 12
    def test_parse_availability(self):
        assert parse_availability("available") is True

@pytest.mark.usefixtures("class_db_setup")
class TestDatabase:
    @pytest.mark.asyncio
    async def test_session_fixture_works(self, db_session):
        result = await db_session.execute(select(1))
        assert result.scalar() == 1

    @pytest.mark.asyncio
    async def test_store_standardized_data(self, db_session, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()
        result = await db_session.execute(select(ProductDB))
        stored_products = result.scalars().all()
        assert len(stored_products) == len(test_products)

    @pytest.mark.asyncio
    async def test_store_duplicate_data(self, db_session, test_products):
        await store_standardized_data(session=db_session, data=test_products[:2])
        await db_session.commit()
        modified_product = test_products[0].model_copy()
        modified_product.price_kwh = 0.20
        await store_standardized_data(session=db_session, data=[modified_product] + test_products[2:4])
        await db_session.commit()
        result = await db_session.execute(select(ProductDB))
        all_products = result.scalars().all()
        assert len(all_products) == 4

@pytest.mark.usefixtures("class_db_setup")
class TestSearchAndFilter:
    @pytest.mark.asyncio
    async def test_search_all_products(self, db_session, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()
        results = await search_and_filter_products(session=db_session)
        assert len(results) == len(test_products)

    @pytest.mark.asyncio
    async def test_search_by_category(self, db_session, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        await db_session.commit()
        electricity_plans = await search_and_filter_products(session=db_session, product_type="electricity_plan")
        expected_names = {"Elec Plan A", "Elec Plan B"}
        actual_names = {p.name for p in electricity_plans}
        assert actual_names == expected_names

@pytest.mark.usefixtures("class_db_setup")
class TestAPI:
    @pytest.mark.asyncio
    async def test_search_endpoint_no_filters(self, api_client, test_products):
        session = await test_db_manager.get_session(self.__class__.__name__)
        await store_standardized_data(session=session, data=test_products)
        await session.commit()
        await session.close()
        response = await api_client.get("/search")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == len(test_products)

# ==== Завершение: очистка ресурсов ====
@pytest.fixture(scope="session", autouse=True)
async def cleanup_all_resources(event_loop):
    yield
    await test_db_manager.cleanup_all()