# conftest.py - Shared fixtures for all tests
import pytest
import pytest_asyncio
import sys
import os
import math
import json
from typing import List, Optional, AsyncGenerator

# Add the parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlmodel import SQLModel, Field, create_engine, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from models import StandardizedProduct
from models import ProductDB

TEST_DB_URL = "sqlite+aiosqlite:///./test.db"

# Mock ProductDB model for testing
class ProductDB(SQLModel, table=True):
    """Database model for storing standardized products"""
    __tablename__ = "productdb"
    __table_args__ = {'extend_existing': True}
    
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


# Database fixture
@pytest_asyncio.fixture(scope="function")
async def engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        SQLModel.metadata.clear()
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest_asyncio.fixture(scope="function")
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session_factory() as session:
        yield session

@pytest.fixture(scope="function")
async def engine():
    """Async database engine fixture"""
    # Clear metadata to avoid conflicts
    SQLModel.metadata.clear()
    
    # Create async engine
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True
    )
    
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    
    yield engine
    
    # Cleanup
    await engine.dispose()


@pytest.fixture(scope="function")
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Async database session fixture"""
    # Create session factory
    async_session_factory = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    # Create and yield session
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest.fixture
def test_products() -> List[StandardizedProduct]:
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


# Mock data storage functions
async def store_standardized_data(session: AsyncSession, data: List[StandardizedProduct]) -> None:
    """Mock function to store standardized data in database"""
    for product in data:
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
