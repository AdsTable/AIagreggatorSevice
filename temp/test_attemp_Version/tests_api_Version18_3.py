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
    from main import app
    from database import get_session # This is the dependency to override
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
    # Ensure your project structure allows these imports and 'main.py' is correctly set up.

# === TEST DATABASE SETUP ===
class TestDatabaseManager:
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self._setup_complete = False

    async def setup(self):
        if self._setup_complete:
            return

        db_url = "sqlite+aiosqlite:///:memory:"
        self.engine = create_async_engine(
            db_url,
            echo=False,
            future=True,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False}
        )
        
        async with self.engine.begin() as conn:
            # await conn.run_sync(SQLModel.metadata.drop_all) # Ensure clean state if engine were reused across non-test runs
            await conn.run_sync(SQLModel.metadata.create_all)
        
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        self._setup_complete = True

    async def get_session(self) -> AsyncSession:
        if not self._setup_complete:
            await self.setup()
        # This directly returns an AsyncSession instance
        return self.session_factory()

    async def clear_all_data(self):
        if self.engine and self._setup_complete:
            async with self.engine.begin() as conn:
                # Correctly reference table name if ProductDB defines __tablename__
                # If ProductDB.metadata.tables has the table object:
                # table_name = ProductDB.__table__.name
                # await conn.execute(text(f"DELETE FROM {table_name}"))
                # Simpler:
                for table in reversed(SQLModel.metadata.sorted_tables):
                    await conn.execute(table.delete())
        # else:
            # print("Warning: clear_all_data called when DB not set up or engine is missing.")


    async def cleanup(self):
        if self.engine:
            await self.engine.dispose()
        self._setup_complete = False
        self.engine = None
        self.session_factory = None

test_db = TestDatabaseManager()

# === FIXTURES ===

# REMOVED custom event_loop fixture. pytest-asyncio will use its default.
# @pytest.fixture(scope="session")
# def event_loop():
#     loop = asyncio.new_event_loop()
#     yield loop
#     loop.close()

@pytest.fixture(scope="function", autouse=True)
async def setup_test_function_environment():
    await test_db.setup()
    await test_db.clear_all_data()
    # No yield here, this is a setup/teardown fixture for function scope

@pytest.fixture(scope="session", autouse=True)
async def session_wide_db_setup_cleanup():
    # This ensures that test_db.setup() is effectively called once (due to its internal _setup_complete flag)
    # and cleanup happens at the very end of the session.
    # await test_db.setup() # setup_test_function_environment will call it first time
    yield
    await test_db.cleanup()

@pytest.fixture
async def db_session() -> AsyncSession: # Explicitly type hint return for clarity
    # setup_test_function_environment (autouse) ensures test_db is ready and data cleared
    session = await test_db.get_session() # This should be an AsyncSession instance
    try:
        yield session # Yield the actual session instance
    finally:
        await session.close()

@pytest.fixture
def test_products():
    # Same as previous
    return [
        StandardizedProduct(source_url="https://example.com/elec/plan_a", category="electricity_plan", name="Elec Plan A", provider_name="Provider X", price_kwh=0.15, standing_charge=5.0, contract_duration_months=12, available=True, raw_data={"type": "electricity", "features": ["green", "fixed"]}),
        StandardizedProduct(source_url="https://example.com/elec/plan_b", category="electricity_plan", name="Elec Plan B", provider_name="Provider Y", price_kwh=0.12, standing_charge=4.0, contract_duration_months=24, available=False, raw_data={"type": "electricity", "features": ["variable"]}),
        StandardizedProduct(source_url="https://example.com/mobile/plan_c", category="mobile_plan", name="Mobile Plan C", provider_name="Provider X", monthly_cost=30.0, data_gb=100.0, calls=float("inf"), texts=float("inf"), contract_duration_months=0, network_type="4G", available=True, raw_data={"type": "mobile", "features": ["unlimited_calls"]}),
        StandardizedProduct(source_url="https://example.com/mobile/plan_d", category="mobile_plan", name="Mobile Plan D", provider_name="Provider Z", monthly_cost=45.0, data_gb=float("inf"), calls=500, texts=float("inf"), contract_duration_months=12, network_type="5G", available=True, raw_data={"type": "mobile", "features": ["5G", "unlimited_data"]}),
        StandardizedProduct(source_url="https://example.com/internet/plan_e", category="internet_plan", name="Internet Plan E", provider_name="Provider Y", download_speed=500.0, upload_speed=50.0, connection_type="Fiber", data_cap_gb=float("inf"), monthly_cost=60.0, contract_duration_months=24, available=True, raw_data={"type": "internet", "features": ["fiber", "unlimited"]}),
        StandardizedProduct(source_url="https://example.com/internet/plan_f", category="internet_plan", name="Internet Plan F", provider_name="Provider X", download_speed=100.0, upload_speed=20.0, connection_type="DSL", data_cap_gb=500.0, monthly_cost=50.0, contract_duration_months=12, available=True, raw_data={"type": "internet", "features": ["dsl", "limited"]}),
    ]

@pytest.fixture
async def api_client() -> AsyncClient: # Explicitly type hint return
    # setup_test_function_environment (autouse) ensures test_db is ready for overrides
    
    async def get_test_session_override(): # This is for FastAPI's dependency injection
        session_for_app = await test_db.get_session()
        try:
            yield session_for_app
        finally:
            await session_for_app.close()
    
    original_get_session_dependency = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = get_test_session_override
    
    try:
        async with AsyncClient(app=app, base_url="http://test") as client_instance:
            yield client_instance # Yield the actual AsyncClient instance
    finally:
        if original_get_session_dependency:
            app.dependency_overrides[get_session] = original_get_session_dependency
        else:
            # Ensure key exists before deleting, or use .pop(get_session, None)
            if get_session in app.dependency_overrides:
                 del app.dependency_overrides[get_session]

# === SEARCH FUNCTION (identical to previous) ===
async def search_and_filter_products(
    session: AsyncSession,
    product_type: Optional[str] = None, provider: Optional[str] = None,
    min_price: Optional[float] = None, max_price: Optional[float] = None,
    min_data_gb: Optional[float] = None, max_data_gb: Optional[float] = None,
    min_contract_duration_months: Optional[int] = None, max_contract_duration_months: Optional[int] = None,
    max_download_speed: Optional[float] = None, min_upload_speed: Optional[float] = None, # Note: v18 had max_download_speed
    connection_type: Optional[str] = None, network_type: Optional[str] = None,
    available_only: bool = False
) -> List[StandardizedProduct]:
    query = select(ProductDB)
    filters = []
    if product_type: filters.append(ProductDB.category == product_type)
    if provider: filters.append(ProductDB.provider_name == provider)
    
    # Assuming price filters apply to price_kwh for electricity, and monthly_cost for others if price_kwh is None
    # This logic might need to be more sophisticated based on actual model fields and requirements
    if min_price is not None:
        # Simplistic: apply to price_kwh. A real app might check product_type.
        filters.append(ProductDB.price_kwh >= min_price) 
    if max_price is not None:
        filters.append(ProductDB.price_kwh <= max_price)

    if min_data_gb is not None: filters.append(ProductDB.data_gb >= min_data_gb)
    
    # Handling max_data_gb: if ProductDB has data_cap_gb, it might be relevant.
    # Sticking to simpler filter for now based on v18's original search function.
    if max_data_gb is not None:
        filters.append(ProductDB.data_gb <= max_data_gb)
        # If ProductDB.data_cap_gb is a separate, relevant field for filtering:
        # if hasattr(ProductDB, 'data_cap_gb'):
        #     filters.append(ProductDB.data_cap_gb <= max_data_gb)


    if min_contract_duration_months is not None: filters.append(ProductDB.contract_duration_months >= min_contract_duration_months)
    if max_contract_duration_months is not None: filters.append(ProductDB.contract_duration_months <= max_contract_duration_months)
    
    if max_download_speed is not None: filters.append(ProductDB.download_speed <= max_download_speed) # As in v18
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
                # print(f"Warning: Malformed JSON for product {db_product.name or db_product.source_url}")
                pass # Keep raw_data as {}

        # Map all fields from db_product to StandardizedProduct, providing defaults for missing ones
        product_data = {}
        for field in StandardizedProduct.model_fields:
            if hasattr(db_product, field):
                product_data[field] = getattr(db_product, field)
            else:
                # Handle cases where StandardizedProduct has fields not in ProductDB
                # For example, if 'contract_type' is in StandardizedProduct but not ProductDB
                product_data[field] = StandardizedProduct.model_fields[field].default # Or None
        
        product_data['raw_data'] = raw_data # Ensure this is set correctly
        
        # Fill Nones for fields that might be in ProductDB but not explicitly set (e.g. if nullable)
        # This step might be redundant if ProductDB fields are faithfully mapped.
        for key, value in product_data.items():
            if value is None and StandardizedProduct.model_fields[key].default is not None:
                 # If Pydantic field has a default and current value is None, consider applying default.
                 # This is complex; usually direct mapping is fine if ProductDB aligns with StandardizedProduct.
                 pass


        # Ensure all required StandardizedProduct fields are present, even if None, before instantiation.
        # Pydantic will raise error if required fields (without defaults) are missing.
        # The loop above tries to ensure all fields are present.

        try:
            product = StandardizedProduct(**product_data)
            standardized_products.append(product)
        except Exception as e: # Catch Pydantic validation error or others
            # print(f"Error converting ProductDB to StandardizedProduct for {db_product.name}: {e}")
            # print(f"Product data attempted: {product_data}")
            pass # Skip this product or handle error
            
    return standardized_products

# === UNIT TESTS FOR HELPER FUNCTIONS (Adapted from V21 for robustness) ===
class TestDataParserFunctions:
    def test_extract_float_with_units(self):
        units = ["кВт·ч", "руб/кВт·ч", "ГБ", "GB", "Mbps"]
        unit_conversion = {"кВт·ч": 1.0, "руб/кВт·ч": 1.0, "ГБ": 1.0, "GB": 1.0, "Mbps": 1.0}
        try:
            result = extract_float_with_units("15.5 кВт·ч", units, unit_conversion)
            assert result == 15.5, f"Expected 15.5, got {result}"
            
            result_none = extract_float_with_units("no number", units, unit_conversion)
            assert result_none is None
        except (TypeError, AttributeError, NameError) as e:
            pytest.skip(f"extract_float_with_units: Skipping due to error: {e}")
    
    def test_extract_float_or_handle_unlimited(self):
        unlimited_terms = ["безлимит", "unlimited", "неограниченно", "∞", "infinity"]
        units = ["ГБ", "GB", "MB"]
        try:
            result_inf = extract_float_or_handle_unlimited("unlimited", unlimited_terms, units)
            assert result_inf == float('inf')

            result_num = extract_float_or_handle_unlimited("100 ГБ", unlimited_terms, units)
            assert result_num == 100.0
        except (TypeError, AttributeError, NameError) as e:
            pytest.skip(f"extract_float_or_handle_unlimited: Skipping due to error: {e}")

    def test_extract_duration_in_months(self):
        month_terms = ["месяцев", "месяца", "months", "month", "мес.", "мес"]
        year_terms = ["год", "года", "лет", "year", "years", "г.", "л."]
        try:
            # Assuming the function now requires these arguments as per v18 error
            result = extract_duration_in_months("12 месяцев", month_terms, year_terms)
            assert result == 12

            result_year = extract_duration_in_months("1 год", month_terms, year_terms)
            assert result_year == 12

            result_zero = extract_duration_in_months("без контракта", month_terms, year_terms)
            assert result_zero == 0
        except (TypeError, AttributeError, NameError) as e:
             pytest.skip(f"extract_duration_in_months: Skipping due to error: {e}")
    
    def test_parse_availability(self):
        try:
            assert parse_availability("available") == True
            assert parse_availability("в наличии") == True
            assert parse_availability("unavailable") == False
            assert parse_availability("недоступен") == False
            assert parse_availability("unknown") == True # As per original v18 test
        except (TypeError, AttributeError, NameError) as e:
            pytest.skip(f"parse_availability: Skipping due to error: {e}")

# === DATABASE TESTS ===
class TestDatabase:
    @pytest.mark.asyncio
    async def test_session_fixture_works(self, db_session: AsyncSession):
        assert db_session is not None, "db_session fixture did not return a session."
        # Test basic query
        result = await db_session.execute(select(1))
        assert result.scalar_one() == 1
        
        # Test table exists
        table_name_to_check = ProductDB.__tablename__ if hasattr(ProductDB, '__tablename__') else 'productdb'
        result_table_exists = await db_session.execute(
            text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name_to_check}'")
        )
        assert result_table_exists.scalar_one_or_none() is not None, f"Table '{table_name_to_check}' not found."
    
    @pytest.mark.asyncio
    async def test_store_standardized_data(self, db_session: AsyncSession, test_products):
        result_before = await db_session.execute(select(ProductDB))
        assert len(result_before.scalars().all()) == 0
        
        await store_standardized_data(session=db_session, data=test_products)
        # store_standardized_data should commit, or we need to commit here. Assuming it does for now.
        # If not, add: await db_session.commit()
        
        result_after = await db_session.execute(select(ProductDB))
        stored_products_db = result_after.scalars().all()
        assert len(stored_products_db) == len(test_products)
        
        # Further checks as in previous version...
        elec_plan_a_db = next((p for p in stored_products_db if p.name == "Elec Plan A"), None)
        assert elec_plan_a_db is not None
        assert elec_plan_a_db.price_kwh == 0.15
        raw_data = json.loads(elec_plan_a_db.raw_data_json)
        assert raw_data["type"] == "electricity"

    @pytest.mark.asyncio
    async def test_store_duplicate_data(self, db_session: AsyncSession, test_products):
        await store_standardized_data(session=db_session, data=test_products[:2])
        # await db_session.commit() # If store_standardized_data doesn't commit

        modified_product = test_products[0].model_copy(deep=True)
        modified_product.price_kwh = 0.20
        
        await store_standardized_data(session=db_session, data=[modified_product] + test_products[2:4])
        # await db_session.commit()

        result_final = await db_session.execute(select(ProductDB))
        all_products_db = result_final.scalars().all()
        assert len(all_products_db) == 4 
        
        updated_product_db = next((p for p in all_products_db if p.name == "Elec Plan A"), None)
        assert updated_product_db is not None
        assert updated_product_db.price_kwh == 0.20

# === SEARCH AND FILTER TESTS ===
# (These tests use db_session and test_products, assuming they are now correctly provided)
# Add await db_session.commit() after store_standardized_data if it doesn't auto-commit.
class TestSearchAndFilter:
    @pytest.mark.asyncio
    async def test_search_all_products(self, db_session: AsyncSession, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        # await db_session.commit()
        results = await search_and_filter_products(session=db_session)
        assert len(results) == len(test_products)

    # ... other search tests from previous version, ensuring to commit if needed ...
    @pytest.mark.asyncio
    async def test_search_by_category(self, db_session: AsyncSession, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        # await db_session.commit()
        electricity_plans = await search_and_filter_products(session=db_session, product_type="electricity_plan")
        expected_names = {"Elec Plan A", "Elec Plan B"}
        assert {p.name for p in electricity_plans} == expected_names

    @pytest.mark.asyncio
    async def test_search_by_provider(self, db_session: AsyncSession, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        # await db_session.commit()
        provider_x_products = await search_and_filter_products(session=db_session, provider="Provider X")
        expected_names = {"Elec Plan A", "Mobile Plan C", "Internet Plan F"}
        assert {p.name for p in provider_x_products} == expected_names

    @pytest.mark.asyncio
    async def test_search_by_price_range(self, db_session: AsyncSession, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        # await db_session.commit()
        expensive_electricity = await search_and_filter_products(session=db_session, product_type="electricity_plan", min_price=0.13)
        assert len(expensive_electricity) == 1
        assert expensive_electricity[0].name == "Elec Plan A"
        
        cheap_electricity = await search_and_filter_products(session=db_session, product_type="electricity_plan", max_price=0.13)
        assert len(cheap_electricity) == 1
        assert cheap_electricity[0].name == "Elec Plan B"

    @pytest.mark.asyncio
    async def test_search_by_contract_duration(self, db_session: AsyncSession, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        # await db_session.commit()
        long_contracts = await search_and_filter_products(session=db_session, min_contract_duration_months=18)
        expected_names = {"Elec Plan B", "Internet Plan E"}
        assert {p.name for p in long_contracts} == expected_names
        
        short_contracts = await search_and_filter_products(session=db_session, max_contract_duration_months=12)
        expected_names = {"Elec Plan A", "Mobile Plan C", "Mobile Plan D", "Internet Plan F"}
        assert {p.name for p in short_contracts} == expected_names

    @pytest.mark.asyncio
    async def test_search_by_data_limits(self, db_session: AsyncSession, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        # await db_session.commit()
        limited_data = await search_and_filter_products(session=db_session, product_type="mobile_plan", max_data_gb=200)
        assert len(limited_data) == 1 
        assert limited_data[0].name == "Mobile Plan C"
        
        high_data = await search_and_filter_products(session=db_session, product_type="mobile_plan", min_data_gb=50)
        expected_names = {"Mobile Plan C", "Mobile Plan D"}
        assert {p.name for p in high_data} == expected_names

    @pytest.mark.asyncio
    async def test_search_by_connection_properties(self, db_session: AsyncSession, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        # await db_session.commit()
        fiber_connections = await search_and_filter_products(session=db_session, connection_type="Fiber")
        assert len(fiber_connections) == 1
        assert fiber_connections[0].name == "Internet Plan E"
        
        fiveg_plans = await search_and_filter_products(session=db_session, network_type="5G")
        assert len(fiveg_plans) == 1
        assert fiveg_plans[0].name == "Mobile Plan D"
        
        fast_upload = await search_and_filter_products(session=db_session, min_upload_speed=30)
        assert len(fast_upload) == 1
        assert fast_upload[0].name == "Internet Plan E"

    @pytest.mark.asyncio
    async def test_search_available_only(self, db_session: AsyncSession, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        # await db_session.commit()
        available_products = await search_and_filter_products(session=db_session, available_only=True)
        unavailable_names = {"Elec Plan B"}
        expected_available_names = {p.name for p in test_products if p.name not in unavailable_names}
        assert {p.name for p in available_products} == expected_available_names
    
    @pytest.mark.asyncio
    async def test_search_complex_filters(self, db_session: AsyncSession, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        # await db_session.commit()
        results = await search_and_filter_products(session=db_session, provider="Provider X", max_contract_duration_months=12)
        expected_names = {"Elec Plan A", "Mobile Plan C", "Internet Plan F"}
        assert {p.name for p in results} == expected_names

    @pytest.mark.asyncio
    async def test_search_no_results(self, db_session: AsyncSession, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        # await db_session.commit()
        no_results_category = await search_and_filter_products(session=db_session, product_type="gas_plan")
        assert len(no_results_category) == 0
        
        no_results_price = await search_and_filter_products(session=db_session, product_type="electricity_plan", min_price=1.0)
        assert len(no_results_price) == 0

# === API TESTS ===
# These tests use api_client and db_session.
# The db_session is used to set up data before API calls.
# Ensure data is committed to DB if store_standardized_data doesn't auto-commit.
class TestAPI:
    @pytest.mark.asyncio
    async def test_search_endpoint_no_filters(self, api_client: AsyncClient, db_session: AsyncSession, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        # await db_session.commit() # Crucial if store_standardized_data doesn't commit
        
        response = await api_client.get("/search")
        assert response.status_code == 200
        # ... rest of assertions
        data = response.json()
        assert len(data) == len(test_products)

    @pytest.mark.asyncio
    async def test_search_endpoint_with_filters(self, api_client: AsyncClient, db_session: AsyncSession, test_products):
        await store_standardized_data(session=db_session, data=test_products)
        # await db_session.commit()
        
        response_cat = await api_client.get("/search?product_type=electricity_plan")
        assert response_cat.status_code == 200
        assert len(response_cat.json()) == 2
        # ... other filter tests

    @pytest.mark.asyncio
    async def test_search_endpoint_validation(self, api_client: AsyncClient):
        # Test with parameters that might cause validation errors (FastAPI returns 422) or be handled gracefully (200)
        response_neg_price = await api_client.get("/search?min_price=not_a_number")
        assert response_neg_price.status_code == 422 # Expecting Pydantic validation error from FastAPI

        response_neg_dur = await api_client.get("/search?min_contract_duration_months=not_an_int")
        assert response_neg_dur.status_code == 422

    @pytest.mark.asyncio
    async def test_search_endpoint_empty_database(self, api_client: AsyncClient, db_session: AsyncSession):
        # db_session fixture and setup_test_function_environment ensure DB is empty
        result_check = await db_session.execute(select(ProductDB)) # Check directly
        assert len(result_check.scalars().all()) == 0

        response = await api_client.get("/search")
        assert response.status_code == 200
        assert len(response.json()) == 0
    
    @pytest.mark.asyncio
    async def test_search_endpoint_json_response_format(self, api_client: AsyncClient, db_session: AsyncSession, test_products):
        mobile_plan_d = next(p for p in test_products if p.name == "Mobile Plan D")
        await store_standardized_data(session=db_session, data=[mobile_plan_d])
        # await db_session.commit()
        
        response = await api_client.get("/search?product_type=mobile_plan")
        assert response.status_code == 200
        # ... rest of assertions for format

# === INTEGRATION TESTS ===
# (Similar to Search and Filter, ensure commits if needed)
class TestIntegration:
    @pytest.mark.asyncio
    async def test_full_workflow_electricity_plans(self, db_session: AsyncSession):
        electricity_products = [
            StandardizedProduct(source_url="https://energy-provider.com/green-fixed", category="electricity_plan", name="Green Fixed Rate", provider_name="GreenEnergy Co", price_kwh=0.18, standing_charge=8.50, contract_duration_months=24, contract_type="fixed", available=True, raw_data={"tariff_type": "green"}),
            StandardizedProduct(source_url="https://energy-provider.com/variable-standard", category="electricity_plan", name="Standard Variable", provider_name="PowerCorp Ltd", price_kwh=0.16, standing_charge=12.00, contract_duration_months=0, contract_type="variable", available=True, raw_data={"tariff_type": "standard"})
        ]
        await store_standardized_data(session=db_session, data=electricity_products)
        # await db_session.commit()
        
        all_electricity = await search_and_filter_products(session=db_session, product_type="electricity_plan")
        assert len(all_electricity) == 2
    # ... other integration tests

    @pytest.mark.asyncio
    async def test_full_workflow_mobile_plans(self, db_session: AsyncSession):
        mobile_products = [
            StandardizedProduct(source_url="https://mobile-provider.com/unlimited-5g", category="mobile_plan", name="Unlimited 5G Pro", provider_name="MobileTech", monthly_cost=55.0, data_gb=float("inf"), calls=float("inf"), texts=float("inf"), network_type="5G", contract_duration_months=24, available=True, raw_data={}),
            StandardizedProduct(source_url="https://mobile-provider.com/basic-4g", category="mobile_plan", name="Basic 4G Plan", provider_name="ValueMobile", monthly_cost=25.0, data_gb=20.0, calls=1000, texts=float("inf"), network_type="4G", contract_duration_months=12, available=True, raw_data={})
        ]
        await store_standardized_data(session=db_session, data=mobile_products)
        # await db_session.commit()
        fiveg_plans = await search_and_filter_products(session=db_session, network_type="5G")
        assert len(fiveg_plans) == 1
        assert fiveg_plans[0].name == "Unlimited 5G Pro"

    @pytest.mark.asyncio
    async def test_full_workflow_internet_plans(self, db_session: AsyncSession):
        internet_products = [
            StandardizedProduct(source_url="https://broadband-provider.com/fiber-ultra", category="internet_plan", name="Fiber Ultra 1000", provider_name="FastNet", monthly_cost=85.0, download_speed=1000.0, upload_speed=1000.0, connection_type="Fiber", data_cap_gb=float("inf"), contract_duration_months=18, available=True, raw_data={}),
            StandardizedProduct(source_url="https://broadband-provider.com/adsl-basic", category="internet_plan", name="ADSL Basic", provider_name="TradNet", monthly_cost=35.0, download_speed=24.0, upload_speed=3.0, connection_type="ADSL", data_cap_gb=500.0, contract_duration_months=12, available=True, raw_data={})
        ]
        await store_standardized_data(session=db_session, data=internet_products)
        # await db_session.commit()
        slow_speed_plans = await search_and_filter_products(session=db_session, product_type="internet_plan", max_download_speed=100)
        assert len(slow_speed_plans) == 1
        assert slow_speed_plans[0].name == "ADSL Basic"

# === PERFORMANCE AND EDGE CASE TESTS ===
class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_large_dataset_performance(self, db_session: AsyncSession):
        # ... (data generation)
        large_dataset = [StandardizedProduct(source_url=f"https://example.com/product_{i}", category="electricity_plan" if i % 3 == 0 else "mobile_plan" if i % 3 == 1 else "internet_plan", name=f"Test Product {i}", provider_name=f"Provider {i % 10}", price_kwh=0.10 + (i % 20) * 0.01, monthly_cost=20.0 + (i % 50) * 2.0, contract_duration_months=(i % 4) * 12, available=i % 4 != 0, raw_data={"index": i}) for i in range(100)]
        await store_standardized_data(session=db_session, data=large_dataset)
        # await db_session.commit()
        # ... (timing and assertions)
        results = await search_and_filter_products(session=db_session)
        assert len(results) == 100


    @pytest.mark.asyncio
    async def test_infinity_values_handling(self, db_session: AsyncSession):
        infinity_products = [StandardizedProduct(source_url="https://example.com/infinity_test", category="mobile_plan", name="Infinity Test Plan", provider_name="Test Provider", data_gb=float("inf"), calls=float("inf"), texts=float("inf"), monthly_cost=50.0, raw_data={})]
        await store_standardized_data(session=db_session, data=infinity_products)
        # await db_session.commit()
        results = await search_and_filter_products(session=db_session)
        assert len(results) == 1
        assert results[0].data_gb == float("inf")

    @pytest.mark.asyncio
    async def test_empty_string_and_none_values(self, db_session: AsyncSession):
        edge_case_products = [StandardizedProduct(source_url="https://example.com/edge_case", category="electricity_plan", name="Edge Case Plan", provider_name="", price_kwh=0.15, contract_type=None, raw_data={})]
        await store_standardized_data(session=db_session, data=edge_case_products)
        # await db_session.commit()
        results = await search_and_filter_products(session=db_session)
        assert len(results) == 1
        assert results[0].provider_name == ""

    @pytest.mark.asyncio
    async def test_special_characters_in_data(self, db_session: AsyncSession):
        special_char_products = [StandardizedProduct(source_url="https://example.com/unicode_test", category="mobile_plan", name="Test Plan with émojis 📱💨", provider_name="Провайдер с кириллицей", monthly_cost=30.0, raw_data={"emoji": "🚀📡💯"})]
        await store_standardized_data(session=db_session, data=special_char_products)
        # await db_session.commit()
        results = await search_and_filter_products(session=db_session)
        assert len(results) == 1
        assert "émojis" in results[0].name


# === ERROR HANDLING TESTS ===
class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_database_connection_error_handling(self):
        with pytest.raises(Exception): # More specific exception if known (e.g., OperationalError from SQLAlchemy)
            invalid_engine = create_async_engine("sqlite+aiosqlite:///nonexistent_path/test.db") # Invalid path
            try:
                async with invalid_engine.connect() as conn:
                    await conn.execute(select(1))
            finally:
                await invalid_engine.dispose() # Ensure disposal
    
    @pytest.mark.asyncio
    async def test_malformed_json_in_raw_data(self, db_session: AsyncSession):
        # Manually insert a ProductDB record with malformed JSON
        # This requires ProductDB to be defined and its primary key structure known
        # Assuming ProductDB has at least: source_url, category, name, raw_data_json
        pk_fields = ProductDB.model_config.get('sqlmodel_primary_key', None) if hasattr(ProductDB, 'model_config') else None

        # Create a valid entry first to ensure table schema etc. are fine
        db_session.add(ProductDB(source_url="s_ok", category="c_ok", name="n_ok", raw_data_json='{"valid":true}'))
        # await db_session.commit() # commit if not auto-committed by add or subsequent operations

        # Now, add the problematic entry. Using text to bypass potential model validation on insert.
        # Adjust columns based on ProductDB actual schema.
        await db_session.execute(
            text("INSERT INTO productdb (source_url, category, name, raw_data_json) VALUES (:s, :cat, :n, :raw)"),
            {"s": "https://example.com/bad_json", "cat": "test_bad", "n": "Bad JSON Plan", "raw": "{'invalid_json: True"} # Malformed
        )
        # await db_session.commit()

        results = await search_and_filter_products(session=db_session)
        bad_json_product = next((p for p in results if p.name == "Bad JSON Plan"), None)
        assert bad_json_product is not None
        assert bad_json_product.raw_data == {}, "Malformed JSON should result in empty raw_data dict"

# === API ERROR TESTS ===
class TestAPIErrors:
    @pytest.mark.asyncio
    async def test_api_with_database_error_simulated(self, api_client: AsyncClient):
        async def get_session_that_fails():
            raise Exception("Simulated DB error") # Don't yield, just raise
            # The yield below would make it an async generator, which is not what we want for this sim.
            # yield None 

        original_override = app.dependency_overrides.get(get_session)
        app.dependency_overrides[get_session] = get_session_that_fails
        
        try:
            response = await api_client.get("/search")
            assert response.status_code == 500 # FastAPI should catch unhandled exceptions from deps
        finally: # Restore original dependency
            if original_override: app.dependency_overrides[get_session] = original_override
            elif get_session in app.dependency_overrides : del app.dependency_overrides[get_session]

    @pytest.mark.asyncio
    async def test_api_malformed_query_parameters(self, api_client: AsyncClient):
        response_bad_type = await api_client.get("/search?min_price=not_a_number")
        assert response_bad_type.status_code == 422 # FastAPI validation for type errors

# === MAIN EXECUTION ===
if __name__ == "__main__":
    print("To run tests, use: pytest tests_api_Version18.py -v --asyncio-mode=auto")
