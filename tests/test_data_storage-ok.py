import pytest
import logging
from unittest.mock import AsyncMock, MagicMock
from models import StandardizedProduct, ProductDB
from data_storage import store_standardized_data

# Setup a dummy StandardizedProduct for testing
def example_standardized_product(**kwargs):
    data = {
        "category": "mobile_plan",
        "source_url": "https://example.com/product",
        "provider_name": "Test Provider",
        "product_id": "int-001",
        "name": "Internal Product Example",
        "description": "Internal use only",
        "contract_duration_months": 24,
        "available": True,
        "price_kwh": 0.11,
        "standing_charge": 1.8,
        "contract_type": "fixed",
        "monthly_cost": 34.99,
        "data_gb": 150.0,
        "calls": 2000,
        "texts": 1000,
        "network_type": "4G",
        "download_speed": 100,
        "upload_speed": 40,
        "connection_type": "dsl",
        "data_cap_gb": 500.0,
        "internet_monthly_cost": 1.0,
        "raw_data": {"test": 1}
    }
    data.update(kwargs)
    return StandardizedProduct(**data)

@pytest.mark.asyncio
async def test_store_standardized_data_success(monkeypatch):
    # Prepare dummy session
    session = AsyncMock()
    session.add_all = MagicMock()
    session.commit = AsyncMock()
    # No exception
    products = [example_standardized_product(), example_standardized_product(product_id="int-002")]
    await store_standardized_data(session, products)
    session.add_all.assert_called_once()
    session.commit.assert_awaited_once()

@pytest.mark.asyncio
async def test_store_standardized_data_empty(monkeypatch, caplog):
    session = AsyncMock()
    # No commit, no error
    products = []
    with caplog.at_level(logging.INFO):
        await store_standardized_data(session, products)
    assert "No standardized data to store." in caplog.text

@pytest.mark.asyncio
async def test_store_standardized_data_type_error():
    session = AsyncMock()
    # Pass an invalid object
    products = ["not a product"]
    with pytest.raises(TypeError):
        await store_standardized_data(session, products)

@pytest.mark.asyncio
async def test_store_standardized_data_validation_error():
    session = AsyncMock()
    # Pass an invalid StandardizedProduct (missing required field)
    invalid = example_standardized_product()
    object.__setattr__(invalid, "category", None)  # force invalid
    products = [invalid]
    with pytest.raises(Exception):
        await store_standardized_data(session, products)

@pytest.mark.asyncio
async def test_store_standardized_data_db_error(monkeypatch):
    session = AsyncMock()
    session.add_all = MagicMock()
    session.commit = AsyncMock(side_effect=Exception("DB error"))
    session.rollback = AsyncMock()
    products = [example_standardized_product()]
    with pytest.raises(Exception):
        await store_standardized_data(session, products)
    session.rollback.assert_awaited_once()