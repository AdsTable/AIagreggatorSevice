import pytest
import sys
import os
import json
import asyncio
from typing import Dict, Any, List, Optional
from unittest.mock import patch, MagicMock, AsyncMock
import tempfile

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# FastAPI testing imports
from httpx import AsyncClient
from fastapi.testclient import TestClient

# Database imports
from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import text

# Application imports
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

# === TEST DATABASE SETUP ===
class TestDatabaseManager:
    """Manages test database lifecycle"""
    
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self._setup_complete = False
        
    async def setup(self):
        """Setup test database with proper cleanup"""
        if self._setup_complete:
            return
            
        # Use in-memory database for testing
        db_url = "sqlite+aiosqlite:///:memory:"
        
        self.engine = create_async_engine(
            db_url,
            echo=False,
            future=True,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False}
        )
        
        # Drop all tables before creating new ones
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
            await conn.run_sync(SQLModel.metadata.create_all)
        
        self.session_factory = async_sessionmaker(
            self.engine, 
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        self._setup_complete = True

    async def get_session(self) -> AsyncSession:
        """Get a new database session"""
        if not self._setup_complete:
            await self.setup()
        return self.session_factory()

    async def clear_all_data(self):
        """Clear all data from database"""
        if self.engine and self._setup_complete:
            async with self.engine.begin() as conn:
                await conn.execute(text("DELETE FROM productdb"))

    async def cleanup(self):
        """Cleanup database resources"""
        if self.engine:
            await self.engine.dispose()
            self._setup_complete = False

# Global test database manager
test_db = TestDatabaseManager()

# === FIXTURES ===
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(autouse=True)
async def setup_test_db():
    """Setup and teardown the test database for each test"""
    await test_db.setup()
    yield
    await test_db.cleanup()

@pytest.fixture
async def db_session():
    """Provide a database session for each test"""
    async with test_db.session_factory() as session:
        yield session

@pytest.fixture
def test_products():
    """Sample test data"""
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
        # ... [Previous test product definitions remain the same]
    ]

@pytest.fixture
async def api_client(db_session):
    """Create API client with test database"""
    async def override_get_session():
        yield db_session
    
    app.dependency_overrides[get_session] = override_get_session
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    
    app.dependency_overrides.clear()

# === HELPER FUNCTIONS TESTS ===
class TestDataParserFunctions:
    """Test data parsing helper functions"""
    
    def test_extract_float_with_units(self):
        """Test float extraction with units"""
        input_text = "15.5 кВт·ч"
        units = ["кВт·ч", "руб/кВт·ч", "ГБ", "GB", "Mbps"]
        unit_conversion = {"кВт·ч": 1.0}
        
        result = extract_float_with_units(input_text, units, unit_conversion)
        assert result == 15.5
    
    def test_extract_duration_in_months(self):
        """Test duration extraction"""
        input_text = "12 месяцев"
        month_terms = ["месяцев", "месяца", "months", "month"]
        year_terms = ["год", "года", "лет", "year", "years"]
        
        result = extract_duration_in_months(input_text, month_terms, year_terms)
        assert result == 12
    
    def test_parse_availability(self):
        """Test availability parsing"""
        assert parse_availability("available") is True
        assert parse_availability("unavailable") is False
        assert parse_availability("unknown") is True  # Default case

# === DATABASE TESTS ===
class TestDatabase:
    """Test database operations"""
    
    @pytest.mark.asyncio
    async def test_session_fixture_works(self, db_session):
        """Test that database session works correctly"""
        result = await db_session.execute(select(1))
        assert result.scalar() == 1
        
        result = await db_session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='productdb'")
        )
        assert result.scalar() is not None

    @pytest.mark.asyncio
    async def test_store_standardized_data(self, db_session, test_products):
        """Test storing standardized data"""
        await store_standardized_data(db_session, test_products)
        
        result = await db_session.execute(select(ProductDB))
        stored_products = result.scalars().all()
        assert len(stored_products) == len(test_products)

# === API TESTS ===
class TestAPI:
    """Test FastAPI endpoints"""
    
    @pytest.mark.asyncio
    async def test_search_endpoint_no_filters(self, api_client, test_products):
        """Test search endpoint without filters"""
        # First store test data
        session = await test_db.get_session()
        async with session.begin():
            await store_standardized_data(session, test_products)
        
        response = await api_client.get("/search")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == len(test_products)

    @pytest.mark.asyncio
    async def test_search_endpoint_with_filters(self, api_client, test_products):
        """Test search endpoint with filters"""
        session = await test_db.get_session()
        async with session.begin():
            await store_standardized_data(session, test_products)
        
        response = await api_client.get("/search?provider=Provider X")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3  # Number of Provider X products

# === INTEGRATION TESTS ===
class TestIntegration:
    """Integration tests combining multiple components"""
    
    @pytest.mark.asyncio
    async def test_full_workflow(self, db_session, test_products):
        """Test complete workflow"""
        # Store data
        await store_standardized_data(db_session, test_products)
        
        # Test search with filters
        results = await search_and_filter_products(
            db_session,
            product_type="electricity_plan",
            provider="Provider X"
        )
        
        assert len(results) == 1
        assert results[0].name == "Elec Plan A"

# === EDGE CASES TESTS ===
class TestEdgeCases:
    """Test edge cases and error conditions"""
    
    @pytest.mark.asyncio
    async def test_infinity_values(self, db_session):
        """Test handling of infinity values"""
        product = StandardizedProduct(
            source_url="test://infinity",
            category="test",
            name="Infinity Test",
            data_gb=float("inf"),
            raw_data={}
        )
        
        await store_standardized_data(db_session, [product])
        
        result = await search_and_filter_products(db_session)
        assert len(result) == 1
        assert result[0].data_gb == float("inf")

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])