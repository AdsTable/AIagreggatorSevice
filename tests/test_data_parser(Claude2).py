# test_api.py - Claude-2 с исправлениями
import pytest
import sys
import os
import math
import json
from typing import Dict, Any, List, Optional

# Add the parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from data_parser import (
    extract_float_with_units,
    extract_float_or_handle_unlimited,
    extract_duration_in_months,
    parse_availability,
    standardize_extracted_product,
    parse_and_standardize,
)
from models import StandardizedProduct

# Mock ProductDB model for testing
from sqlmodel import SQLModel, Field
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.orm import sessionmaker
from typing import AsyncIterator

class ProductDB(SQLModel, table=True):
    """Database model for storing standardized products"""
    __tablename__ = "productdb"  # Explicitly specify the name of the table
    __table_args__ = {'extend_existing': True}  # Allowing redefinition of the table
    
    id: Optional[int] = Field(default=None, primary_key=True)
    source_url: str = Field(index=True)
    category: str = Field(index=True)
    name: Optional[str] = None
    provider_name: Optional[str] = Field(default=None, index=True)
    
    # Electricity-specific fields
    price_kwh: Optional[float] = None
    standing_charge: Optional[float] = None
    contract_type: Optional[str] = None
    
    # Mobile/Internet common fields
    monthly_cost: Optional[float] = None
    contract_duration_months: Optional[int] = None
    
    # Mobile-specific fields
    data_gb: Optional[float] = None
    calls: Optional[float] = None
    texts: Optional[float] = None
    network_type: Optional[str] = None
    
    # Internet-specific fields
    download_speed: Optional[float] = None
    upload_speed: Optional[float] = None
    connection_type: Optional[str] = None
    data_cap_gb: Optional[float] = None
    
    # Common fields
    available: Optional[bool] = Field(default=True)
    raw_data_json: Optional[str] = None

# Mock data_storage functions
async def store_standardized_data(session: AsyncSession, data: List[StandardizedProduct]) -> None:
    """Mock function to store standardized data in database"""
    for product in data:
        # Convert StandardizedProduct to ProductDB
        db_product = ProductDB(
            source_url=product.source_url,
            category=product.category,
            name=product.name,
            provider_name=product.provider_name,
            price_kwh=product.price_kwh,
            standing_charge=product.standing_charge,
            contract_type=product.contract_type,
            monthly_cost=product.monthly_cost,
            contract_duration_months=product.contract_duration_months,
            data_gb=product.data_gb,
            calls=product.calls,
            texts=product.texts,
            network_type=product.network_type,
            download_speed=product.download_speed,
            upload_speed=product.upload_speed,
            connection_type=product.connection_type,
            data_cap_gb=product.data_cap_gb,
            available=product.available,
            raw_data_json=json.dumps(product.raw_data) if product.raw_data else None
        )
        session.add(db_product)
    await session.commit()

# Mock search function
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
    """Mock search and filter function"""
    from sqlmodel import select
    
    query = select(ProductDB)
    
    # Apply filters
    if product_type:
        query = query.where(ProductDB.category == product_type)
    if provider:
        query = query.where(ProductDB.provider_name == provider)
    if min_price is not None:
        query = query.where(ProductDB.price_kwh >= min_price)
    if min_contract_duration_months is not None:
        query = query.where(ProductDB.contract_duration_months >= min_contract_duration_months)
    if max_download_speed is not None:
        query = query.where(ProductDB.download_speed <= max_download_speed)
    
    # Handle infinity filtering for data fields
    if max_data_gb is not None:
        # Filter out infinity values when max limit is specified
        query = query.where(ProductDB.data_gb <= max_data_gb)
        query = query.where(ProductDB.data_cap_gb <= max_data_gb)
    
    result = await session.execute(query)
    db_products = result.scalars().all()
    
    # Convert back to StandardizedProduct
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

# --- Pytest Fixtures ---

@pytest.fixture(name="engine")
async def engine_fixture():
    """Async database engine fixture"""
    # Сlear the metadata at the beginning of each test.
    SQLModel.metadata.clear()
    
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest.fixture(name="session")
async def session_fixture(engine) -> AsyncIterator[AsyncSession]:
    """Async database session fixture"""
    async_session_factory = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()

@pytest.fixture(name="test_products")
def test_products_fixture() -> List[StandardizedProduct]:
    """Test products fixture"""
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
            data_gb=math.inf,
            calls=math.inf,
            texts=math.inf,
            contract_duration_months=0,
            raw_data={"k": "v3"}
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

# --- Tests for Helper Functions ---

def test_extract_float_with_units():
    """Test float extraction with units"""
    price_units = ["kwh", "usd", "$", "kr"]
    price_conversion = {"usd": 1.0}
    data_units = ["gb", "gigabyte"]
    speed_units = ["mbps", "mbit/s"]

    assert extract_float_with_units("15.5 USD/kWh", price_units, price_conversion) == 15.5
    assert extract_float_with_units("20 GB", data_units, {}) == 20.0
    assert extract_float_with_units("5", [], {}) == 5.0
    assert extract_float_with_units(" 10.2 ", [], {}) == 10.2
    assert extract_float_with_units("invalid", [], {}) is None
    assert extract_float_with_units(None, [], {}) is None
    assert extract_float_with_units("", [], {}) is None
    assert extract_float_with_units("1000 Mbps", speed_units, {}) == 1000.0
    assert extract_float_with_units("75,5 kr", price_units, price_conversion) == 75.5
    assert extract_float_with_units(10, [], {}) == 10.0
    assert extract_float_with_units(50.5, [], {}) == 50.5

def test_extract_float_or_handle_unlimited():
    """Test unlimited value handling"""
    unlimited_terms = ["unlimited", "ubegrenset", "безлимит", "no data cap"]
    data_units = ["gb", "gigabyte"]
    calls_units = ["minutes", "мин"]

    # Test unlimited values
    assert math.isinf(extract_float_or_handle_unlimited("unlimited data", unlimited_terms, data_units))
    assert math.isinf(extract_float_or_handle_unlimited("Ubegrenset data", unlimited_terms, data_units))
    assert math.isinf(extract_float_or_handle_unlimited("No Data Cap", unlimited_terms, data_units))
    
    # Test numeric values
    assert extract_float_or_handle_unlimited("50 GB", unlimited_terms, data_units) == 50.0
    assert extract_float_or_handle_unlimited("120 minutes", unlimited_terms, calls_units) == 120.0
    assert extract_float_or_handle_unlimited(300, unlimited_terms, calls_units) == 300.0
    
    # Test invalid values
    assert extract_float_or_handle_unlimited("Not relevant", unlimited_terms, data_units) is None
    assert extract_float_or_handle_unlimited(None, unlimited_terms, data_units) is None

def test_extract_duration_in_months():
    """Test duration extraction and conversion"""
    month_terms = ["month", "mo", "месяц"]
    year_terms = ["year", "yr", "год"]

    # Test months
    assert extract_duration_in_months("12 months", month_terms, year_terms) == 12
    assert extract_duration_in_months("6 mo", month_terms, year_terms) == 6
    
    # Test years
    assert extract_duration_in_months("2 year", month_terms, year_terms) == 24
    assert extract_duration_in_months("1 год", month_terms, year_terms) == 12
    
    # Test no contract
    assert extract_duration_in_months("no contract", month_terms, year_terms) == 0
    assert extract_duration_in_months("cancel anytime", month_terms, year_terms) == 0
    
    # Test integer input
    assert extract_duration_in_months(12, month_terms, year_terms) == 12
    
    # Test invalid
    assert extract_duration_in_months("invalid", month_terms, year_terms) is None
    assert extract_duration_in_months("100", month_terms, year_terms) is None

def test_parse_availability():
    """Test availability parsing"""
    assert parse_availability("Available") is True
    assert parse_availability("In Stock") is True
    assert parse_availability("active") is True
    assert parse_availability(None) is True
    assert parse_availability("") is True
    
    assert parse_availability("Expired") is False
    assert parse_availability("Sold Out") is False
    assert parse_availability("inactive") is False
    assert parse_availability("unavailable") is False

def test_standardize_extracted_product_electricity():
    """Test electricity plan standardization"""
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
    
    standardized = standardize_extracted_product(raw_data, "electricity_plan")
    
    assert isinstance(standardized, StandardizedProduct)
    assert standardized.source_url == "https://example.com/elec"
    assert standardized.name == "Green Energy Plan"
    assert standardized.provider_name == "EcoPower"
    assert standardized.price_kwh == 0.20
    assert standardized.standing_charge == 5.00
    assert standardized.contract_duration_months == 24
    assert standardized.contract_type == "Fixed Price"
    assert standardized.available is True
    assert standardized.category == "electricity_plan"
    assert standardized.raw_data == raw_data

def test_standardize_extracted_product_mobile():
    """Test mobile plan standardization"""
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
    
    standardized = standardize_extracted_product(raw_data, "mobile_plan")
    
    assert isinstance(standardized, StandardizedProduct)
    assert standardized.name == "Mega Mobile Plan"
    assert standardized.monthly_cost == 49.99
    assert math.isinf(standardized.data_gb)
    assert math.isinf(standardized.calls)
    assert math.isinf(standardized.texts)
    assert standardized.network_type == "5G"
    assert standardized.contract_duration_months == 12

def test_parse_and_standardize():
    """Test batch parsing and standardization"""
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
        }
    ]
    
    # Test electricity plans
    elec_list = [raw_data_list[0]]
    standardized_elec = parse_and_standardize(elec_list, "electricity_plan")
    assert len(standardized_elec) == 1
    assert standardized_elec[0].name == "Elec Plan A"
    assert standardized_elec[0].price_kwh == 0.15
    
    # Test mobile plans
    mobile_list = [raw_data_list[1]]
    standardized_mobile = parse_and_standardize(mobile_list, "mobile_plan")
    assert len(standardized_mobile) == 1
    assert standardized_mobile[0].name == "Mobile Plan B"
    assert standardized_mobile[0].monthly_cost == 30.0
    
    # Test empty list
    assert len(parse_and_standardize([], "electricity_plan")) == 0
    
    # Test invalid input
    assert len(parse_and_standardize({"key": "value"}, "electricity_plan")) == 0

# --- Database Tests ---

@pytest.mark.asyncio
async def test_store_standardized_data(session: AsyncSession):
    """Test data storage functionality"""
    products = [
        StandardizedProduct(
            source_url="https://example.com/p1",
            category="electricity_plan",
            name="Plan 1",
            price_kwh=0.1,
            contract_duration_months=12,
            raw_data={"key": "value1"}
        ),
        StandardizedProduct(
            source_url="https://example.com/p2",
            category="mobile_plan",
            name="Plan 2",
            monthly_cost=25.0,
            data_gb=100.0,
            raw_data={"key": "value2"}
        )
    ]
    
    # Store data
    await store_standardized_data(session=session, data=products)
    
    # Verify storage
    from sqlmodel import select
    result = await session.execute(select(ProductDB))
    stored_products = result.scalars().all()
    
    assert len(stored_products) == 2
    
    # Verify first product
    stored_p1 = next(p for p in stored_products if p.name == "Plan 1")
    assert stored_p1.category == "electricity_plan"
    assert stored_p1.price_kwh == 0.1
    assert json.loads(stored_p1.raw_data_json) == {"key": "value1"}

@pytest.mark.asyncio
async def test_search_and_filter_products(session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test search and filtering functionality"""
    # Store test data
    await store_standardized_data(session=session, data=test_products)
    
    # Test search all
    all_products = await search_and_filter_products(session=session)
    assert len(all_products) == len(test_products)
    
    # Test filter by category
    elec_plans = await search_and_filter_products(session=session, product_type="electricity_plan")
    assert len(elec_plans) == 2
    assert all(p.category == "electricity_plan" for p in elec_plans)
    
    # Test filter by provider
    provider_x = await search_and_filter_products(session=session, provider="Provider X")
    assert len(provider_x) == 3  # Elec A, Mobile C, Internet F
    
    # Test minimum price filter
    min_price_results = await search_and_filter_products(
        session=session, 
        product_type="electricity_plan", 
        min_price=0.13
    )
    assert len(min_price_results) == 1
    assert min_price_results[0].name == "Elec Plan A"
    
    # Test contract duration filter
    long_contract = await search_and_filter_products(
        session=session,
        product_type="electricity_plan",
        min_contract_duration_months=18
    )
    assert len(long_contract) == 1
    assert long_contract[0].name == "Elec Plan B"
    
    # Test no results
    no_results = await search_and_filter_products(session=session, product_type="gas_plan")
    assert len(no_results) == 0