# test_data_parser.py
import pytest
import sys
import os
import math # Import math for infinity

# Add the parent directory of the test file (typically project root)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from data_parser import (
    extract_float_with_units,
    extract_float_or_handle_unlimited, # Use the new helper functions
    extract_duration_in_months,      # Use the new helper functions
    parse_availability,
    standardize_extracted_product,
    parse_and_standardize,
)
from models import StandardizedProduct, ProductDB
from data_storage import store_standardized_data # Assuming this function exists
from typing import Dict, Any, AsyncIterator, List

# Import necessary components for database testing with SQLModel and AsyncIO
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
import json # Import json for comparing raw_data


# --- Pytest Fixtures for Database ---

@pytest.fixture(name="engine")
async def engine_fixture():
    """Fixture for creating and disposing of the async database engine."""
    # Use an in-memory SQLite database for testing
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    # Create tables before tests
    async with engine.begin() as conn:
        # Use drop_all to ensure a clean state for each test run
        # await conn.run_sync(SQLModel.metadata.drop_all) # Optional: uncomment if you want drop_all before each test run within the engine fixture
        await conn.run_sync(SQLModel.metadata.create_all)

    yield engine

    # Dispose of the engine after all tests using this fixture are done
    await engine.dispose()

@pytest.fixture(name="session")
async def session_fixture(engine) -> AsyncIterator[AsyncSession]:
    """
    Async database session fixture with transaction management for tests.
    Provides a session with an active transaction for each test.
    Rolls back on error, commits on success, and closes the session.
    """
    # Create a test session factory
    async_session_factory = sessionmaker(
        # Renamed for clarity, was async_session
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Use a new session for each test function
    # Explicit transaction management
    async with async_session_factory() as session:
        await session.begin()  # Begin a transaction for the test
        try:
            yield session  # Provide the session to the test
            await session.commit()  # Commit the transaction if the test passes
        except Exception:
            await session.rollback()  # Rollback the transaction if an error occurs
            raise  # Re-raise the exception
        finally:
            await session.close()  # Close the session

# --- Tests for Helper Parsing Functions ---

def test_extract_float_with_units():
    # Define units and conversions for these tests (can match PARSING_INSTRUCTIONS in data_parser)
    price_units = ["kwh", "usd", "$", "kr"]
    price_conversion = {"usd": 1.0}
    data_units = ["gb", "gigabyte"]
    speed_units = ["mbps", "mbit/s"]

    assert extract_float_with_units("15.5 USD/kWh", price_units, price_conversion) == 15.5
    assert extract_float_with_units("20 GB", data_units, {}) == 20.0
    assert extract_float_with_units("5", [], {}) == 5.0 # Test with just a number
    assert extract_float_with_units(" 10.2 ", [], {}) == 10.2 # Test with leading/trailing spaces
    assert extract_float_with_units("invalid", [], {}) is None # Test with invalid string
    assert extract_float_with_units(None, [], {}) is None # Test with None
    assert extract_float_with_units("", [], {}) is None # Test with empty string
    assert extract_float_with_units("1000 Mbps", speed_units, {}) == 1000.0
    assert extract_float_with_units("75,5 kr", price_units, price_conversion) == 75.5 # Test with comma

    # Test with numeric input
    assert extract_float_with_units(10, [], {}) == 10.0
    assert extract_float_with_units(50.5, [], {}) == 50.5


def test_extract_float_or_handle_unlimited():
    unlimited_terms = ["unlimited", "ubegrenset", "безлимит", "no data cap"]
    data_units = ["gb", "gigabyte"]
    calls_units = ["minutes", "мин"]

    # Test cases for unlimited values (should return infinity)
    assert math.isinf(extract_float_or_handle_unlimited("unlimited data", unlimited_terms, data_units))
    assert math.isinf(extract_float_or_handle_unlimited("Ubegrenset data", unlimited_terms, data_units))
    assert math.isinf(extract_float_or_handle_unlimited("Unlimited", unlimited_terms, data_units))
    assert math.isinf(extract_float_or_handle_unlimited("No Data Cap", unlimited_terms, data_units))
    assert math.isinf(extract_float_or_handle_unlimited("Безлимитные минуты", unlimited_terms, calls_units))

    # Test cases for numeric values with units
    assert extract_float_or_handle_unlimited("50 GB", unlimited_terms, data_units) == 50.0
    assert extract_float_or_handle_unlimited("100 gigabyte", unlimited_terms, data_units) == 100.0
    assert extract_float_or_handle_unlimited("120 minutes", unlimited_terms, calls_units) == 120.0

    # Test cases for numeric input
    assert extract_float_or_handle_unlimited(300, unlimited_terms, calls_units) == 300.0
    assert extract_float_or_handle_unlimited(100.5, unlimited_terms, data_units) == 100.5

    # Test cases for invalid/non-matching strings
    assert extract_float_or_handle_unlimited("Not relevant string", unlimited_terms, data_units) is None
    assert extract_float_or_handle_unlimited("abc", unlimited_terms, data_units) is None
    assert extract_float_or_handle_unlimited(None, unlimited_terms, data_units) is None
    assert extract_float_or_handle_unlimited("", unlimited_terms, data_units) is None


def test_extract_duration_in_months():
    month_terms = ["month", "mo", "месяц"]
    year_terms = ["year", "yr", "год"]

    # Test cases for months
    assert extract_duration_in_months("12 months", month_terms, year_terms) == 12
    assert extract_duration_in_months("6 mo", month_terms, year_terms) == 6
    assert extract_duration_in_months("1 month", month_terms, year_terms) == 1
    assert extract_duration_in_months("36months", month_terms, year_terms) == 36 # Test without space
    assert extract_duration_in_months("1 месяц", month_terms, year_terms) == 1

    # Test cases for years
    assert extract_duration_in_months("2 year", month_terms, year_terms) == 24
    assert extract_duration_in_months("3 yr", month_terms, year_terms) == 36
    assert extract_duration_in_months("1 year", month_terms, year_terms) == 12
    assert extract_duration_in_months("1 год", month_terms, year_terms) == 12

    # Test cases for no contract
    assert extract_duration_in_months("no contract", month_terms, year_terms) == 0
    assert extract_duration_in_months("cancel anytime", month_terms, year_terms) == 0
    assert extract_duration_in_months("без контракта", month_terms, year_terms) == 0

    # Test with integer input (assuming integer means months)
    assert extract_duration_in_months(12, month_terms, year_terms) == 12
    assert extract_duration_in_months(0, month_terms, year_terms) == 0


    # Test cases for invalid/unparsable strings
    assert extract_duration_in_months("invalid duration", month_terms, year_terms) is None
    assert extract_duration_in_months("abc", month_terms, year_terms) is None
    assert extract_duration_in_months(None, month_terms, year_terms) is None
    assert extract_duration_in_months("", month_terms, year_terms) is None
    # Test just a number without a unit - should return None
    assert extract_duration_in_months("100", month_terms, year_terms) is None


def test_parse_availability():
    assert parse_availability("Available") is True
    assert parse_availability("In Stock") is True
    assert parse_availability("active") is True
    assert parse_availability("Some text about status") is True # Default to True
    assert parse_availability(None) is True # Default to True
    assert parse_availability("") is True # Default to True

    assert parse_availability("Expired") is False
    assert parse_availability("Sold Out") is False
    assert parse_availability("inactive") is False
    assert parse_availability("unavailable") is False
    assert parse_availability("недоступен") is False
    assert parse_availability("нет в наличии") is False


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
    assert standardized.raw_data == raw_data # Check raw_data is stored


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
        "plan_title": "Basic Plan" # Missing many fields
    }
    category = "mobile_plan"
    standardized = standardize_extracted_product(raw_data, category)

    assert isinstance(standardized, StandardizedProduct)
    assert standardized.source_url == "https://example.com/incomplete"
    assert standardized.name == "Basic Plan"
    # Assert missing optional fields are None (as they are Optional in the model)
    assert standardized.monthly_cost is None
    assert standardized.data_gb is None
    assert standardized.calls is None
    assert standardized.texts is None
    assert standardized.contract_duration_months is None
    assert standardized.provider_name is None
    assert standardized.network_type is None
    assert standardized.category == category
    assert standardized.raw_data == raw_data


# --- Tests for parse_and_standardize ---

def test_parse_and_standardize():
    # Example list of raw data
    raw_data_list = [
        {
            "source_url": "https://example.com/elec1",
            "product_name_on_page": "Elec Plan A",
            "price_info": "0.15", # Should be parsed as 0.15
            "contract_details": "12mo", # Should be parsed as 12
            "validity_info": "Available" # Should be parsed as True
        },
        {
            "source_url": "https://example.com/mobile1",
            "plan_title": "Mobile Plan B",
            "monthly_price_text": "30", # Should be parsed as 30.0
            "data_allowance_text": "10 GB", # Should be parsed as 10.0
            "contract_term_text": "No Contract" # Should be parsed as 0
        },
        {
            "source_url": "https://example.com/elec2",
            "product_name_on_page": "Elec Plan C",
            "price_info": "0.18", # Should be parsed as 0.18
            "contract_details": "24 months", # Should be parsed as 24
            "validity_info": "Expired" # Should be parsed as False
        },
         {
            "source_url": "https://example.com/internet1",
            "plan_title": "Internet Plan D",
            "provider_name_on_page": "Net Provider",
            "monthly_price_text": "60.50$", # Should be parsed as 60.50
            "download_speed_info": "500 Mbps", # Should be parsed as 500.0
            "data_cap_info": "Unlimited", # Should be parsed as infinity
            "contract_term_text": "1 year" # Should be parsed as 12
         }
    ]

    # Note: parse_and_standardize currently assumes all items in the list are of the SAME category
    # based on how it's called in main.py. We'll test it with lists for each category.

    # Test with electricity plan list
    electricity_list = [raw_data_list[0], raw_data_list[2]]
    standardized_elec_list = parse_and_standardize(electricity_list, "electricity_plan")
    assert len(standardized_elec_list) == 2
    assert isinstance(standardized_elec_list[0], StandardizedProduct)
    assert standardized_elec_list[0].name == "Elec Plan A"
    assert standardized_elec_list[0].price_kwh == 0.15
    assert standardized_elec_list[0].contract_duration_months == 12
    assert standardized_elec_list[0].available is True
    assert standardized_elec_list[0].raw_data == raw_data_list[0] # Check raw_data
    assert isinstance(standardized_elec_list[1], StandardizedProduct)
    assert standardized_elec_list[1].name == "Elec Plan C"
    assert standardized_elec_list[1].price_kwh == 0.18
    assert standardized_elec_list[1].contract_duration_months == 24
    assert standardized_elec_list[1].available is False
    assert standardized_elec_list[1].raw_data == raw_data_list[2] # Check raw_data


    # Test with mobile plan list
    mobile_list = [raw_data_list[1]]
    standardized_mobile_list = parse_and_standardize(mobile_list, "mobile_plan")
    assert len(standardized_mobile_list) == 1
    assert isinstance(standardized_mobile_list[0], StandardizedProduct)
    assert standardized_mobile_list[0].name == "Mobile Plan B"
    assert standardized_mobile_list[0].monthly_cost == 30.0
    assert standardized_mobile_list[0].data_gb == 10.0
    assert standardized_mobile_list[0].contract_duration_months == 0 # No contract
    assert standardized_mobile_list[0].raw_data == raw_data_list[1] # Check raw_data


    # Test with internet plan list
    internet_list = [raw_data_list[3]]
    standardized_internet_list = parse_and_standardize(internet_list, "internet_plan")
    assert len(standardized_internet_list) == 1
    assert isinstance(standardized_internet_list[0], StandardizedProduct)
    assert standardized_internet_list[0].name == "Internet Plan D"
    assert standardized_internet_list[0].provider_name == "Net Provider"
    assert standardized_internet_list[0].monthly_cost == 60.50
    assert standardized_internet_list[0].download_speed == 500.0
    assert math.isinf(standardized_internet_list[0].data_cap_gb)
    assert standardized_internet_list[0].contract_duration_months == 12 # 1 year
    assert standardized_internet_list[0].raw_data == raw_data_list[3] # Check raw_data

    # Test with empty list
    standardized_empty_list = parse_and_standardize([], "electricity_plan")
    assert len(standardized_empty_list) == 0

    # Test with invalid input (not a list)
    standardized_invalid_input = parse_and_standardize({"key": "value"}, "electricity_plan")
    assert len(standardized_invalid_input) == 0

    # Test with list containing invalid items
    invalid_items_list = [raw_data_list[0], "not a dict", None, raw_data_list[2]]
    standardized_with_invalid = parse_and_standardize(invalid_items_list, "electricity_plan")
    assert len(standardized_with_invalid) == 2 # Only the valid items should be processed


# Add this fixture after the existing database fixtures
@pytest.fixture(name="test_products")
def test_products_fixture() -> List[StandardizedProduct]:
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
            data_gb=math.inf, # Use math.inf directly in tests
            calls=math.inf,
            texts=math.inf,
            contract_duration_months=0,
            raw_data={"k": "v3"}
        ),
        StandardizedProduct(
            source_url="https://example.com/mobile/plan_d",
            category="mobile_plan",
            name="Mobile Plan D",
            provider_name="Provider Z",
            monthly_cost=45.0,
            data_gb=math.inf,
            calls=500,
            texts=math.inf,
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
            data_cap_gb=math.inf,
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

# --- Tests for store_standardized_data ---

@pytest.mark.asyncio # Mark as async test
async def test_store_standardized_data(session: AsyncSession):
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
    # The conversion logic is in create_product_db_from_standardized (presumably),
    # which we trust is correct. We'll check key fields and raw_data_json.

    # Find stored product corresponding to product1
    stored_p1 = next((p for p in stored_products_list if p.source_url == product1.source_url and p.name == product1.name), None)
    assert stored_p1 is not None
    assert stored_p1.category == product1.category
    assert stored_p1.price_kwh == product1.price_kwh
    assert stored_p1.contract_duration_months == product1.contract_duration_months
    # For raw_data, compare the JSON strings as it's stored as JSON in ProductDB
    assert json.loads(stored_p1.raw_data_json) == product1.raw_data

    # Find stored product corresponding to product2
    stored_p2 = next((p for p in stored_products_list if p.source_url == product2.source_url and p.name == product2.name), None)
    assert stored_p2 is not None
    assert stored_p2.category == product2.category
    assert stored_p2.monthly_cost == product2.monthly_cost
    assert stored_p2.data_gb == product2.data_gb
    assert json.loads(stored_p2.raw_data_json) == product2.raw_data

    # Add more tests for store_standardized_data, e.g., handling empty list, duplicate data (if applicable)


# --- Tests for search_and_filter_products ---

# Assuming search_and_filter_products function is in data_search.py and imported
from data_search import search_and_filter_products # Import the search function

@pytest.mark.asyncio # Mark as async test
async def test_search_and_filter_products(session: AsyncSession, test_products: List[StandardizedProduct]):
    # Store the test data first
    await store_standardized_data(session=session, data=test_products)

    # Test search without parameters (should return all products)
    all_products = await search_and_filter_products(session=session)
    assert len(all_products) == len(test_products)
    # Check if the returned products are StandardizedProduct instances (search function should return these)
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
    assert elec_min_price[0].name == "Elec Plan A" # Price 0.15 > 0.13

    # Test filtering by provider
    provider_x_products = await search_and_filter_products(session=session, provider="Provider X")
    assert len(provider_x_products) == 3 # Elec A, Mobile C, Internet F
    assert all(p.provider_name == "Provider X" for p in provider_x_products)

    # Test filtering by maximum data allowance (mobile)
    # Note: max_data_gb applies to data_gb field.
    mobile_max_data = await search_and_filter_products(session=session, product_type="mobile_plan", max_data_gb=150.0)
    # Mobile Plan C has data_gb = infinity, Mobile Plan D has data_gb = infinity.
    # If max_data_gb filters out infinity, then maybe 0 results.
    # If max_data_gb allows infinity if no finite value is less than max_data_gb, then 2 results.
    # Assuming max_data_gb filters out infinity:
    assert len(mobile_max_data) == 0 # Both Mobile C and D have infinite data.

    # Let's adjust the test products or the expected outcome based on the actual search logic for infinity.
    # If the search logic in data_search.py for max_data_gb filters out infinity, this test is correct.
    # If it includes infinity when max_data_gb is large, adjust the assertion.
    # For now, assuming infinity is filtered out by a finite max_data_gb.

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

    # Test combined filtering: Internet plans from Provider Y with max download speed
    internet_provider_y_max_speed = await search_and_filter_products(
        session=session,
        product_type="internet_plan",
        provider="Provider Y",
        max_download_speed=600.0 # Internet Plan E has 500 Mbps download speed
    )
    assert len(internet_provider_y_max_speed) == 1
    assert internet_provider_y_max_speed[0].name == "Internet Plan E"
    assert internet_provider_y_max_speed[0].provider_name == "Provider Y"
    assert internet_provider_y_max_speed[0].download_speed == 500.0


    # Test scenario with no matching results
    no_results = await search_and_filter_products(session=session, product_type="gas_plan")
    assert len(no_results) == 0

    no_results_filtered = await search_and_filter_products(session=session, product_type="electricity_plan", min_price=1.0)
    assert len(no_results_filtered) == 0

    # Add more complex combined filtering tests as needed.

