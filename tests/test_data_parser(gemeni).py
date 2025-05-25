# test_data_parser.py - вариант со студии.
import pytest
from data_parser import (
    parse_float_with_units,
    parse_unlimited,
    parse_contract_duration,
    parse_availability,
    parse_data_allowance,
    parse_unlimited_or_minutes,
    parse_unlimited_or_count,
    standardize_extracted_product, # Import for later use
 parse_and_standardize,
)
import math
from models import StandardizedProduct, ProductDB
from data_storage import store_standardized_data
from typing import Dict, Any, AsyncIterator

# Import necessary components for database testing with SQLModel and AsyncIO
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker

# --- Pytest Fixtures for Database ---
@pytest.fixture(name="engine")
async def engine_fixture():
    assert parse_float_with_units("15.5 USD/kWh") == 15.5
    assert parse_float_with_units("20 GB") == 20.0
    assert parse_float_with_units("5") == 5.0 # Test with just a number
    assert parse_float_with_units("invalid") is None # Test with invalid string
    assert parse_float_with_units(None) is None # Test with None
    assert parse_float_with_units("") is None # Test with empty string
    assert parse_float_with_units(" 10.2 ") == 10.2 # Test with leading/trailing spaces
    # Use an in-memory SQLite database for testing
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=True)

    async with engine.begin() as conn:
        # Drop and create tables for each test to ensure a clean state
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)

    yield engine

    # Dispose the engine after tests
    await engine.dispose()

@pytest.fixture(name="session")
async def session_fixture(engine) -> AsyncIterator[AsyncSession]:
    # Create a test session factory
    async_session = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Yield a new session for each test
    async with async_session() as session:
        yield session

# Basic tests for parse_float_with_units

# Basic tests for parse_unlimited
def test_parse_unlimited():
    assert parse_unlimited("unlimited") == float("inf")
    assert parse_unlimited("Unlimited") == float("inf")
    assert parse_unlimited("not unlimited") is None
    assert parse_unlimited(None) is None
    assert parse_unlimited("") is None
    assert parse_unlimited(123) is None

# Basic tests for parse_contract_duration
def test_parse_contract_duration():
    assert parse_contract_duration("12-month contract") == 12
    assert parse_contract_duration("24mo") == 24
    assert parse_contract_duration("no contract") == 0
    assert parse_contract_duration("cancel anytime") == 0
    assert parse_contract_duration("1 year") == 12
    assert parse_contract_duration("2 yr") == 24
    assert parse_contract_duration("invalid") is None
    assert parse_contract_duration(None) is None
    assert parse_contract_duration("") is None
    assert parse_contract_duration("36months") == 36 # Test without hyphen

# Basic tests for parse_availability
def test_parse_availability():
    assert parse_availability("Available") is True
    assert parse_availability("In Stock") is True
    assert parse_availability("active") is True
    assert parse_availability("Expired") is False
    assert parse_availability("Sold Out") is False
    assert parse_availability("inactive") is False
    assert parse_availability("Some text about status") is True # Default to True
    assert parse_availability(None) is True # Default to True
    assert parse_availability("") is True # Default to True

# Basic tests for parse_data_allowance
def test_parse_data_allowance():
    assert parse_data_allowance("50 GB") == 50.0
    assert parse_data_allowance("Unlimited data") == float("inf")
    assert parse_data_allowance("invalid") is None
    assert parse_data_allowance(None) is None

# Basic tests for parse_unlimited_or_minutes
def test_parse_unlimited_or_minutes():
    assert parse_unlimited_or_minutes("120 minutes") == 120
    assert parse_unlimited_or_minutes("Unlimited calls") == float("inf")
    assert parse_unlimited_or_minutes(300) == 300 # Test with integer input
    assert parse_unlimited_or_minutes("invalid") is None
    assert parse_unlimited_or_minutes(None) is None

# Basic tests for parse_unlimited_or_count
def test_parse_unlimited_or_count():
    assert parse_unlimited_or_count("500 texts") == 500
    assert parse_unlimited_or_count("Unlimited texts") == float("inf")
    assert parse_unlimited_or_count(1000) == 1000 # Test with integer input
    assert parse_unlimited_or_count("invalid") is None
    assert parse_unlimited_or_count(None) is None

# --- Tests for standardize_extracted_product ---
def test_standardize_extracted_product_electricity():
 raw_data = {
 "source_url": "https://example.com/elec",
 "product_name_on_page": "Green Energy Plan",
 "provider_name_on_page": "EcoPower",
 "price_info": "0.20 USD/kWh",
 "standing_charge_info": "5.00 USD/month",
 "contract_details": "24-month term",
 "contract_type_info": "Fixed Price",
 "validity_info": "Available now"
 }
 category = "electricity_plan"
 standardized = standardize_extracted_product(raw_data, category)

 assert isinstance(standardized, StandardizedProduct)
 assert standardized.source_url == "https://example.com/elec"
 assert standardized.name == "Green Energy Plan"
 assert standardized.provider_name == "EcoPower"
 assert standardized.price_kwh == 0.20
 assert standardized.standing_charge == 5.00
 assert standardized.contract_duration_months == 24
 assert standardized.contract_type == "Fixed Price"
 assert standardized.available is True
 assert standardized.category == category
 assert standardized.raw_data == raw_data

def test_standardize_extracted_product_mobile():
 raw_data = {
 "source_url": "https://example.com/mobile",
 "plan_title": "Mega Mobile Plan",
 "provider_name_on_page": "TalkMore",
 "monthly_price_text": "$49.99",
 "data_allowance_text": "Unlimited Data",
 "calls_info": "Unlimited calls",
 "texts_info": "Unlimited texts",
 "network_type_info": "5G",
 "contract_term_text": "12 mo"
 }
 category = "mobile_plan"
 standardized = standardize_extracted_product(raw_data, category)

 assert isinstance(standardized, StandardizedProduct)
 assert standardized.source_url == "https://example.com/mobile"
 assert standardized.name == "Mega Mobile Plan"
 assert standardized.provider_name == "TalkMore"
 assert standardized.monthly_cost == 49.99
 assert math.isinf(standardized.data_gb) # Check for infinity
 assert math.isinf(standardized.calls) # Check for infinity
 assert math.isinf(standardized.texts) # Check for infinity
 assert standardized.network_type == "5G"
 assert standardized.contract_duration_months == 12
 assert standardized.category == category
 assert standardized.raw_data == raw_data

def test_standardize_extracted_product_internet():
 raw_data = {
 "source_url": "https://example.com/internet",
 "plan_title": "Fast Home Internet",
 "provider_name_on_page": "NetConnect",
 "download_speed_info": "500 Mbps",
 "upload_speed_info": "50 Mbps",
 "connection_type_info": "Fiber",
 "data_cap_info": "No Data Cap", # Test parsing unlimited data cap
 "monthly_price_text": "75", # Test price without currency symbol
 "contract_term_text": "2 years"
 }
 category = "internet_plan"
 standardized = standardize_extracted_product(raw_data, category)

 assert isinstance(standardized, StandardizedProduct)
 assert standardized.source_url == "https://example.com/internet"
 assert standardized.name == "Fast Home Internet"
 assert standardized.provider_name == "NetConnect"
 assert standardized.download_speed == 500.0
 assert standardized.upload_speed == 50.0
 assert standardized.connection_type == "Fiber"
 assert math.isinf(standardized.data_cap_gb) # Check for infinity
 assert standardized.monthly_cost == 75.0
 assert standardized.contract_duration_months == 24 # 2 years converted to months
 assert standardized.category == category
 assert standardized.raw_data == raw_data

# Test handling of missing raw data fields
def test_standardize_extracted_product_missing_fields():
 raw_data = {
 "source_url": "https://example.com/incomplete",
 "plan_title": "Basic Plan"
 # Missing many fields
 }
 category = "mobile_plan"
 standardized = standardize_extracted_product(raw_data, category)

 assert isinstance(standardized, StandardizedProduct)
 assert standardized.source_url == "https://example.com/incomplete"
 assert standardized.name == "Basic Plan"
 # Assert missing optional fields are None
 assert standardized.monthly_cost is None
 assert standardized.data_gb is None
 # ... check other expected None fields

# --- Tests for parse_and_standardize ---
def test_parse_and_standardize():
 # Example list of raw data
 raw_data_list = [
         {
            "source_url": "https://example.com/elec1",
            "product_name_on_page": "Elec Plan A",
            "price_info": "0.15",
            "contract_details": "12mo",
            "validity_info": "Available"
         },
         {
            "source_url": "https://example.com/mobile1",
            "plan_title": "Mobile Plan B",
            "monthly_price_text": "30",
            "data_allowance_text": "10 GB",
            "contract_term_text": "No Contract"
         },
          {
            "source_url": "https://example.com/elec2",
            "product_name_on_page": "Elec Plan C",
            "price_info": "0.18",
            "contract_details": "24 months",
             "validity_info": "Expired"
         }
 ]
 # Note: parse_and_standardize currently assumes all items in the list are of the SAME category
 # based on how it's called in main.py. We'll test it with a single category list.

 # Test with electricity plan list
 electricity_list = [raw_data_list[0], raw_data_list[2]]
 standardized_elec_list = parse_and_standardize(electricity_list, "electricity_plan")

 assert len(standardized_elec_list) == 2
 assert isinstance(standardized_elec_list[0], StandardizedProduct)
 assert standardized_elec_list[0].name == "Elec Plan A"
 assert standardized_elec_list[0].price_kwh == 0.15
 assert standardized_elec_list[0].contract_duration_months == 12
 assert standardized_elec_list[0].available is True

 assert isinstance(standardized_elec_list[1], StandardizedProduct)
 assert standardized_elec_list[1].name == "Elec Plan C"
 assert standardized_elec_list[1].price_kwh == 0.18
 assert standardized_elec_list[1].contract_duration_months == 24
 assert standardized_elec_list[1].available is False

 # Test with mobile plan list
 mobile_list = [raw_data_list[1]]
 standardized_mobile_list = parse_and_standardize(mobile_list, "mobile_plan")

 assert len(standardized_mobile_list) == 1
 assert isinstance(standardized_mobile_list[0], StandardizedProduct)
 assert standardized_mobile_list[0].name == "Mobile Plan B"
 assert standardized_mobile_list[0].monthly_cost == 30.0
 assert standardized_mobile_list[0].data_gb == 10.0
 assert standardized_mobile_list[0].contract_duration_months == 0 # No contract

 # Test with empty list
 standardized_empty_list = parse_and_standardize([], "electricity_plan")
 assert len(standardized_empty_list) == 0

# Add more tests for edge cases in standardization and parsing lists

# --- Tests for store_standardized_data ---
@pytest.mark.asyncio # Mark as async test
async def test_store_standardized_data(session: AsyncSession):
    async with session:
        # Create some dummy standardized data
        product1 = StandardizedProduct(
            source_url="https://example.com/p1",
            category="electricity_plan",
            name="Plan 1",
            price_kwh=0.1,
            contract_duration_months=12,
            raw_data={"key": "value1"}
        )
        product2 = StandardizedProduct(
            source_url="https://example.com/p2",
            category="mobile_plan",
            name="Plan 2",
            monthly_cost=25.0,
            data_gb=100.0,
            raw_data={"key": "value2"}
        )
        standardized_products = [product1, product2]

        # Store the data
        await store_standardized_data(session=session, data=standardized_products)

        # Verify the data is stored in the database
        stored_products = await session.execute(select(ProductDB))
        stored_products_list = stored_products.scalars().all()

        assert len(stored_products_list) == 2

        # Check if the stored data matches the original standardized data
        # Note: We need to compare against ProductDB instances as they are stored
        # The conversion logic is in create_product_db_from_standardized, which we trust is correct

        # Find stored product corresponding to product1
        stored_p1 = next((p for p in stored_products_list if p.source_url == product1.source_url and p.name == product1.name), None)
        assert stored_p1 is not None
        assert stored_p1.category == product1.category
        assert stored_p1.price_kwh == product1.price_kwh
        assert stored_p1.contract_duration_months == product1.contract_duration_months
        # For raw_data, compare the JSON strings as it's stored as JSON in ProductDB
        import json
        assert json.loads(stored_p1.raw_data_json) == product1.raw_data

        # Find stored product corresponding to product2
        stored_p2 = next((p for p in stored_products_list if p.source_url == product2.source_url and p.name == product2.name), None)
        assert stored_p2 is not None
        assert stored_p2.category == product2.category
        assert stored_p2.monthly_cost == product2.monthly_cost
        assert stored_p2.data_gb == product2.data_gb
        assert json.loads(stored_p2.raw_data_json) == product2.raw_data

# Add more tests for store_standardized_data, e.g., handling empty list, duplicate data (if applicable)

# Add this fixture after the existing database fixtures
@pytest.fixture(name="test_products")
def test_products_fixture() -> List[StandardizedProduct]:
    from typing import List # Ensure List is imported here if not already
    # Fixture to provide a list of standardized products for testing
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

# Add these tests at the end of the file
# --- Tests for search_and_filter_products ---
@pytest.mark.asyncio # Mark as async test
async def test_search_and_filter_products(session: AsyncSession, test_products: List[StandardizedProduct]):
    from data_storage import search_and_filter_products # Ensure this is imported
    async with session:
        # Store the test data first
        await store_standardized_data(session=session, data=test_products)

        # Test search without parameters (should return all products)
        all_products = await search_and_filter_products(session=session)
        assert len(all_products) == len(test_products)
        # Check if the returned products are StandardizedProduct instances
        assert all(isinstance(p, StandardizedProduct) for p in all_products)

        # Test filtering by product type (electricity)
        elec_plans = await search_and_filter_products(session=session, product_type="electricity_plan")
        assert len(elec_plans) == 2
        assert all(p.category == "electricity_plan" for p in elec_plans)

        # Test filtering by product type (mobile)
        mobile_plans = await search_and_filter_products(session=session, product_type="mobile_plan")
        assert len(mobile_plans) == 2
        assert all(p.category == "mobile_plan" for p in mobile_plans)

        # Test filtering by minimum price (electricity)
        elec_min_price = await search_and_filter_products(session=session, product_type="electricity_plan", min_price=0.13)
        assert len(elec_min_price) == 1
        assert elec_min_price[0].name == "Elec Plan A"

        # Test filtering by provider
        provider_x_products = await search_and_filter_products(session=session, provider="Provider X")
        assert len(provider_x_products) == 3 # Elec A, Mobile C, Internet F
        assert all(p.provider_name == "Provider X" for p in provider_x_products)

        # Test filtering by maximum data allowance (mobile)
        mobile_max_data = await search_and_filter_products(session=session, product_type="mobile_plan", max_data_gb=150.0)
        assert len(mobile_max_data) == 1 # Mobile Plan C (100 GB)
        assert mobile_max_data[0].name == "Mobile Plan C"

        # Test filtering by minimum contract duration (electricity)
        elec_min_contract = await search_and_filter_products(session=session, product_type="electricity_plan", min_contract_duration_months=18)
        assert len(elec_min_contract) == 1 # Elec Plan B (24 months)
        assert elec_min_contract[0].name == "Elec Plan B"

        # Test combined filtering: Internet plans from Provider X with max data cap
        internet_provider_x_max_datacap = await search_and_filter_products(
            session=session,
            product_type="internet_plan",
            provider="Provider X",
            max_data_gb=600.0 # Internet Plan F has 500 GB data cap
        )
        assert len(internet_provider_x_max_datacap) == 1
        assert internet_provider_x_max_datacap[0].name == "Internet Plan F"
        assert internet_provider_x_max_datacap[0].provider_name == "Provider X"
        assert internet_provider_x_max_datacap[0].data_cap_gb == 500.0

        # Test scenario with no matching results
        no_results = await search_and_filter_products(session=session, product_type="gas_plan")
        assert len(no_results) == 0

        no_results_filtered = await search_and_filter_products(session=session, product_type="electricity_plan", min_price=1.0)
        assert len(no_results_filtered) == 0

# Add more complex combined filtering tests as needed.