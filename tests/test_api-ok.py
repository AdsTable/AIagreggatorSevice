# test_api.py - ok (11 errors)
import pytest
import sys
import os

# Add the parent directory of the test file (typically project root)
# Adjust the path as needed if your project structure is different
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import necessary components from your application
from fastapi.testclient import TestClient # Kept TestClient import, though AsyncClient is used for async tests
from httpx import AsyncClient
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker

# Import your application's main FastAPI app, database session getter, models, and data storage function
from main import app
from database import get_session
from models import StandardizedProduct, ProductDB # Assuming these models are defined in models.py
from data_storage import store_standardized_data # Assuming this function is in data_storage.py

from typing import AsyncIterator, List
import asyncio
import json
import math
import unittest.mock

# --- Pytest Fixtures for Database ---

@pytest.fixture(name="engine")
async def engine_fixture():
    """Fixture for creating and disposing of the async database engine."""
    # Use an in-memory SQLite database for testing for speed and isolation
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    # Create tables defined in your SQLModel metadata before tests run
    async with engine.begin() as conn:
        # Optional: await conn.run_sync(SQLModel.metadata.drop_all) # Uncomment if you need to drop tables before each test run using this fixture
        await conn.run_sync(SQLModel.metadata.create_all)

    yield engine # Provide the engine to tests that need it

    # Dispose of the engine after all tests using this fixture are completed
    await engine.dispose()


@pytest.fixture(name="session")
async def session_fixture(engine) -> AsyncIterator[AsyncSession]:
    """
    Async database session fixture with transaction management for tests.
    Provides a session with an active transaction for each test function.
    Rolls back changes on error, commits on success, and closes the session.
    """
    # Create a factory for producing new async sessions
    async_session_factory = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False, # Prevents SQLAlchemy from expiring objects after commit
    )

    # Use a new session for each test function for isolation
    # Explicit transaction management
    async with async_session_factory() as session:
        await session.begin()  # Begin a transaction for the test's database operations
        try:
            yield session  # Provide the active session with open transaction to the test
            await session.commit()  # Commit the transaction if the test function completes successfully
        except Exception:
            await session.rollback()  # Rollback the transaction if any exception occurs during the test
            raise  # Re-raise the exception so pytest knows the test failed
        finally:
            await session.close()  # Always close the session at the end of the test

# --- Fixture for overriding get_session in FastAPI app and providing an AsyncClient ---
@pytest.fixture(name="client")
async def client_fixture(session: AsyncSession):
    """
    Fixture for creating an AsyncClient instance to test FastAPI endpoints
    and overriding the get_session dependency to use the test session.
    """
    # Redefining the get_session dependency
    # Define an async function that will replace the application's get_session dependency.
    # This function must return an awaitable (like a session object) because FastAPI expects awaitable dependencies.
    async def override_get_session():
        return session # <-- Return the Syncsession object itself, not the asynchronous generator (yield)

    # Apply the dependency override for the get_session dependency in the FastAPI app.
    # This ensures that when an endpoint requiring get_session is called via this client,
    # it receives the test session provided by the session fixture.
    app.dependency_overrides[get_session] = override_get_session

    # Create an asynchronous test client instance.
    # The app=app argument tells httpx to make requests against your FastAPI application instance.
    # base_url="http://test" is a convention for testing local apps without a real server.
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client # Yield the AsyncClient instance to the test function. The 'async with' handles its async context.
        # After the test function completes (and the client context manager exits),
        # clear the dependency override to restore the original get_session for subsequent tests (if any).
        app.dependency_overrides.clear()


# --- Fixture for dummy test products ---

@pytest.fixture(name="test_products")
def test_products_fixture() -> List[StandardizedProduct]:
    """Provides a list of dummy StandardizedProduct objects for testing various scenarios."""
    # Define a list of sample products covering different categories and data structures.
    return [
        StandardizedProduct(
            source_url="https://example.com/elec/plan_a",
            category="electricity_plan", # Use corrected category name
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
            category="electricity_plan", # Use corrected category name
            name="Elec Plan B",
            provider_name="Provider Y",
            price_kwh=0.12,
            standing_charge=4.0,
            contract_duration_months=24,
            available=False, # Example of unavailable product
            raw_data={"k": "v2"}
        ),
        StandardizedProduct(
            source_url="https://example.com/mobile/plan_c",
            category="mobile_plan", # Use corrected category name
            name="Mobile Plan C",
            provider_name="Provider X",
            monthly_cost=30.0,
            data_gb=100.0, # Finite data
            calls=float("inf"), # Unlimited calls
            texts=float("inf"), # Unlimited texts
            contract_duration_months=0, # No contract
            raw_data={"k": "v3"}
        ),
        StandardizedProduct(
            source_url="https://example.com/mobile/plan_d",
            category="mobile_plan", # Use corrected category name
            name="Mobile Plan D",
            provider_name="Provider Z",
            monthly_cost=45.0,
            data_gb=float("inf"), # Unlimited data
            calls=500, # Limited calls
            texts=float("inf"), # Unlimited texts
            contract_duration_months=12,
            raw_data={"k": "v4"}
        ),
        StandardizedProduct(
            source_url="https://example.com/internet/plan_e",
            category="internet_plan", # Use corrected category name
            name="Internet Plan E",
            provider_name="Provider Y",
            download_speed=500.0,
            upload_speed=50.0,
            connection_type="Fiber",
            data_cap_gb=float("inf"), # Unlimited data cap
            monthly_cost=60.0,
            contract_duration_months=24,
            raw_data={"k": "v5"}
        ),
        StandardizedProduct(
            source_url="https://example.com/internet/plan_f",
            category="internet_plan", # Use corrected category name
            name="Internet Plan F",
            provider_name="Provider X",
            download_speed=100.0,
            upload_speed=20.0,
            connection_type="DSL",
            data_cap_gb=500.0, # Finite data cap
            monthly_cost=50.0,
            contract_duration_months=12,
            raw_data={"k": "v6"}
        ),
    ]


# --- Tests for /search endpoint ---
# These tests verify the functionality of your search endpoint with various filters.

@pytest.mark.asyncio
async def test_search_endpoint_filter_by_type(client: AsyncClient, session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test filtering search results by product type."""
    async with session() as db_session:
        await store_standardized_data(session=db_session, data=test_products)
        response = await client.get("/search", params={"product_type": "mobile_plan"})
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2  # There are 2 mobile plans in test_products
        assert all(p["category"] == "mobile_plan" for p in data)  # Check if all results are mobile plans
        assert any(p["name"] == "Mobile Plan C" for p in data)  # Check if specific plans are included
        assert any(p["name"] == "Mobile Plan D" for p in data)


@pytest.mark.asyncio
async def test_search_endpoint_no_filters(client: AsyncClient, session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test searching with no filters returns all products stored in the database."""
    async with session() as db_session:  # Capture db_session correctly
        await store_standardized_data(session=db_session, data=test_products)  # Store products using the db_session
        response = await client.get("/search")  # Fetch all products
        assert response.status_code == 200  # Check HTTP status code
        data = response.json()  # Parse the JSON response body
        assert len(data) == len(test_products)  # Verify the number of results
        if data:  # Check if results are returned
            sample_product = data[0]
            assert "source_url" in sample_product
            assert "category" in sample_product
            assert "name" in sample_product


@pytest.mark.asyncio
async def test_search_endpoint_filter_by_min_price(client: AsyncClient, session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test filtering search results by minimum price."""
    await store_standardized_data(session=session, data=test_products)

    # Filtering electricity plans by min_price (uses price_kwh field in DB)
    response_elec = await client.get("/search", params={"product_type": "electricity_plan", "min_price": 0.13})
    assert response_elec.status_code == 200
    data_elec = response_elec.json()
    assert len(data_elec) == 1 # Only Elec Plan A (0.15) is > 0.13
    assert data_elec[0]["name"] == "Elec Plan A"


    # Filtering internet plans by min_price (uses monthly_cost field in DB)
    response_internet = await client.get("/search", params={"product_type": "internet_plan", "min_price": 55.0})
    assert response_internet.status_code == 200
    data_internet = response_internet.json()
    assert len(data_internet) == 1 # Only Internet Plan E (60.0) is > 55.0
    assert data_internet[0]["name"] == "Internet Plan E"


@pytest.mark.asyncio
async def test_search_endpoint_filter_by_provider(client: AsyncClient, session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test filtering search results by provider name."""
    await store_standardized_data(session=session, data=test_products)
    response = await client.get("/search", params={"provider": "Provider X"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3 # Elec A, Mobile C, Internet F are from Provider X
    assert all(p["provider_name"] == "Provider X" for p in data)
    assert any(p["name"] == "Elec Plan A" for p in data)
    assert any(p["name"] == "Mobile Plan C" for p in data)
    assert any(p["name"] == "Internet Plan F" for p in data)


@pytest.mark.asyncio
async def test_search_endpoint_filter_by_max_data_gb(client: AsyncClient, session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test filtering search results by maximum data allowance in GB."""
    await store_standardized_data(session=session, data=test_products)

    # Filtering mobile plans by max_data_gb
    # Assuming your search logic correctly handles float('inf') and filters it out when max_data_gb is finite.
    response_mobile = await client.get("/search", params={"product_type": "mobile_plan", "max_data_gb": 200.0})
    assert response_mobile.status_code == 200
    data_mobile = response_mobile.json()
    assert len(data_mobile) == 1 # Mobile Plan C (100 GB) should be included, Mobile Plan D (inf) should not.
    assert data_mobile[0]["name"] == "Mobile Plan C"
    assert data_mobile[0]["data_gb"] == 100.0


    # Filtering internet plans by max_data_gb
    # Assuming your search logic correctly handles float('inf') for data_cap_gb.
    response_internet = await client.get("/search", params={"product_type": "internet_plan", "max_data_gb": 600.0})
    assert response_internet.status_code == 200
    data_internet = response_internet.json()
    assert len(data_internet) == 1 # Internet Plan F (500 GB) should be included, Internet Plan E (inf) should not.
    assert data_internet[0]["name"] == "Internet Plan F"
    assert data_internet[0]["data_cap_gb"] == 500.0


@pytest.mark.asyncio
async def test_search_endpoint_filter_by_min_contract_duration(client: AsyncClient, session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test filtering search results by minimum contract duration in months."""
    await store_standardized_data(session=session, data=test_products)
    response = await client.get("/search", params={"min_contract_duration_months": 18})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2 # Elec Plan B (24mo), Internet Plan E (24mo) meet this criterion
    assert any(p["name"] == "Elec Plan B" for p in data)
    assert any(p["name"] == "Internet Plan E" for p in data)


@pytest.mark.asyncio
async def test_search_endpoint_combined_filters(client: AsyncClient, session: AsyncSession, test_products: List[StandardizedProduct]):
    """Test filtering search results with multiple combined criteria."""
    await store_standardized_data(session=session, data=test_products)

    # Filter for internet plans from Provider X with max data cap
    response = await client.get(
        "/search",
        params={
            "product_type": "internet_plan",
            "provider": "Provider X",
            "max_data_gb": 600.0 # Internet Plan F has 500 GB data cap
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Internet Plan F"
    assert data[0]["provider_name"] == "Provider X"
    assert data[0]["data_cap_gb"] == 500.0

    # Test combined filtering: Internet plans from Provider Y with max download speed
    response_speed = await client.get(
         "/search",
         params={
             "product_type": "internet_plan",
             "provider": "Provider Y",
             "max_download_speed": 600.0 # Internet Plan E has 500 Mbps download speed
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
    """Test searching with criteria that yield no results."""
    await store_standardized_data(session=session, data=test_products)

    # Search for a non-existent product type
    response_type = await client.get("/search", params={"product_type": "gas_plan"})
    assert response_type.status_code == 200
    assert len(response_type.json()) == 0 # Expect an empty list

    # Search with filters that yield no results for an existing product type
    response_filtered = await client.get("/search", params={"product_type": "electricity_plan", "min_price": 1.0})
    assert response_filtered.status_code == 200
    assert len(response_filtered.json()) == 0 # Expect an empty list


# --- Tests for /ingest_data endpoint ---
# This test verifies the /ingest_data endpoint, typically involves mocking external data sources.

@pytest.mark.asyncio
# Patch the discover_and_extract_data function in main.py which is called by the endpoint
@unittest.mock.patch("main.discover_and_extract_data")
async def test_ingest_data_endpoint(mock_discover_and_extract_data, client: AsyncClient, session: AsyncSession, test_products: List[StandardizedProduct]):
    """
    Test the /ingest_data endpoint by mocking the data discovery/extraction process.
    """
    # Configure the mock to return test raw data that your data_parser can process.
    # The structure here must match what your discover_and_extract_data function
    # would return and what your data_parser expects as input.
    # --- Updated mock_raw_data to match assumed structure for data_parser ---
    mock_raw_data = [
        {
            "source_url": "https://example.com/elec/plan_a", # Assuming source_url is part of raw data
            "category": "electricity_plan", # Assuming category is part of raw data
            "plan_title": "Elec Plan A Raw", # Example raw field name
            "provider_name_on_page": "Provider X", # Example raw field name
            "kwh_price_text": "0.15 £/kWh", # Example raw field name (text format)
            "standing_charge_daily_text": "5.0 £/day", # Example raw field name (text format)
            "contract_term_text": "12 months", # Example raw field name (text format)
            "availability_status": "Available", # Example raw field name
            # Add other raw fields that are relevant for standardization
        },
        {
            "source_url": "https://example.com/mobile/plan_c",
            "category": "mobile_plan",
            "plan_title": "Mobile Plan C Raw",
            "provider_name_on_page": "Provider X",
            "monthly_price_text": "30.0 $/month",
            "data_allowance_text": "Unlimited Data",
            "calls_info": "Unlimited Calls",
            "texts_info": "Unlimited Texts",
            "contract_term_text": "No contract",
            # Add other raw fields
        },
        # Add mock raw data for other categories or scenarios if needed for this test
    ]
    # --- End Updated mock_raw_data ---

    # Set the return value of the mocked function
    mock_discover_and_extract_data.return_value = mock_raw_data

    # Make the POST request to the /ingest_data endpoint.
    # If your endpoint requires a specific request body (e.g., source_identifier, category),
    # you need to include that in the client.post call. Example:
    # request_body = {"source_identifier": "mock_source", "category": "mock_category"}
    # response = await client.post("/ingest_data", json=request_body)

    # Assuming the endpoint triggers ingestion without a specific body for this test setup:
    response = await client.post("/ingest_data")

    # Check the response
    assert response.status_code == 200
    # Check the expected response body (adjust the message if your API returns something different)
    assert response.json() == {"message": "Data ingestion initiated"}


    # Verify that the mocked function was called as expected
    # You can optionally check the arguments it was called with:
    # mock_discover_and_extract_data.assert_called_once_with(source_identifier="mock_source", category="mock_category")
    mock_discover_and_extract_data.assert_called_once()


    # Verify that the data was processed and stored in the database by checking the test session.
    stored_products = await session.execute(select(ProductDB))
    stored_products_list = stored_products.scalars().all()

    # Check the number of products stored. This should match the number of successfully
    # standardized products from your mock_raw_data.
    # This assertion might need adjustment based on how many items in mock_raw_data
    # your data_parser successfully converts to StandardizedProduct.
    # For this mock data, assuming both items are standardized:
    assert len(stored_products_list) >= len(mock_raw_data) # Use >= in case other data was somehow present

    # Add more specific assertions to check the content of the stored data.
    # Example: Check if a specific product was stored and has the expected category and name.
    stored_elec_plan = next((p for p in stored_products_list if p.name == "Elec Plan A Raw"), None)
    assert stored_elec_plan is not None # Check if the product exists
    assert stored_elec_plan.category == "electricity_plan" # Check a specific field

    # Add checks for the other mocked product
    stored_mobile_plan = next((p for p in stored_products_list if p.name == "Mobile Plan C Raw"), None)
    assert stored_mobile_plan is not None
    assert stored_mobile_plan.category == "mobile_plan"

    # Add more assertions for other fields or products as needed to thoroughly test storage.

# Add more API tests as needed for other endpoints or scenarios.

