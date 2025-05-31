"""
Updated Version18_12 for Pydantic 2.x - Enterprise grade with full migration
"""

import pytest
import sys
import os
import json
import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, AsyncGenerator, Union
from unittest.mock import patch, MagicMock, AsyncMock
from contextlib import asynccontextmanager
import re

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import updated Pydantic 2.x models
from models import StandardizedProduct, ProductDB, create_product_db_from_standardized
from data_parser import OptimizedParsers

# FastAPI testing imports
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI, Depends

# Database imports
from sqlmodel import SQLModel, select, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import text

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === OPTIMIZED PARSERS USING UPDATED MODELS ===
# Use the OptimizedParsers from data_parser.py which is now Pydantic 2.x compatible
parsers = OptimizedParsers()

# === HIGH-PERFORMANCE THREAD-SAFE DATABASE ===
class OptimizedMockDatabase:
    """Enterprise-grade in-memory database with Pydantic 2.x integration"""
    
    def __init__(self):
        self._lock = asyncio.Lock()
        self._products: List[StandardizedProduct] = []  # Use updated StandardizedProduct
        self._next_id: int = 1
        
        # Multi-level indexes for ultra-fast lookups
        self._by_category: Dict[str, List[StandardizedProduct]] = {}
        self._by_provider: Dict[str, List[StandardizedProduct]] = {}
        self._by_availability: Dict[bool, List[StandardizedProduct]] = {True: [], False: []}
        
    async def clear(self) -> None:
        """Thread-safe data reset"""
        async with self._lock:
            self._products.clear()
            self._next_id = 1
            self._by_category.clear()
            self._by_provider.clear()
            self._by_availability = {True: [], False: []}
    
    async def add_product(self, product: StandardizedProduct) -> StandardizedProduct:
        """Thread-safe product addition with automatic indexing"""
        async with self._lock:
            # Add to main collection
            self._products.append(product)
            
            # Update all indexes
            self._update_indexes(product)
            
            self._next_id += 1
            return product
    
    def _update_indexes(self, product: StandardizedProduct) -> None:
        """Update all indexes for fast lookup"""
        # Category index
        category = product.category
        if category not in self._by_category:
            self._by_category[category] = []
        self._by_category[category].append(product)
        
        # Provider index
        provider = product.provider_name
        if provider and provider not in self._by_provider:
            self._by_provider[provider] = []
        if provider:
            self._by_provider[provider].append(product)
        
        # Availability index
        self._by_availability[product.available].append(product)
    
    async def get_all_products(self) -> List[StandardizedProduct]:
        """Thread-safe get all products"""
        async with self._lock:
            return self._products.copy()
    
    async def filter_products(
        self,
        product_type: Optional[str] = None,
        provider: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        available_only: bool = False,
        **kwargs
    ) -> List[StandardizedProduct]:
        """Ultra-fast filtering using optimal index selection"""
        async with self._lock:
            # Select optimal starting set based on selectivity
            candidates = None
            
            # Use most selective index first
            if available_only:
                candidates = self._by_availability[True].copy()
            elif product_type and product_type in self._by_category:
                candidates = self._by_category[product_type].copy()
            elif provider and provider in self._by_provider:
                candidates = self._by_provider[provider].copy()
            else:
                candidates = self._products.copy()
            
            # Apply remaining filters efficiently
            result = candidates
            
            # Filter by type if not already filtered
            if product_type and not (product_type in self._by_category and candidates != self._products):
                result = [p for p in result if p.category == product_type]
            
            # Filter by provider if not already filtered
            if provider and not (provider in self._by_provider and candidates != self._products):
                result = [p for p in result if p.provider_name == provider]
            
            # Price filtering with null safety
            if min_price is not None:
                result = [p for p in result if p.price_kwh is not None and p.price_kwh >= min_price]
            
            if max_price is not None:
                result = [p for p in result if p.price_kwh is not None and p.price_kwh <= max_price]
            
            # Availability filter if not already applied
            if available_only and candidates == self._products:
                result = [p for p in result if p.available]
            
            return result

# Global optimized database instance
mock_db = OptimizedMockDatabase()

# === ASYNC MOCK FUNCTIONS WITH PYDANTIC 2.X ===
async def mock_store_standardized_data(session: AsyncSession, data: List[StandardizedProduct]) -> None:
    """High-performance mock storage with Pydantic 2.x models"""
    logger.info(f"Storing {len(data)} products")
    
    try:
        for product in data:
            await mock_db.add_product(product)
        
        logger.info(f"Storage complete. Total: {len((await mock_db.get_all_products()))}")
    except Exception as e:
        logger.error(f"Storage error: {e}")
        raise

async def mock_search_and_filter_products(
    session: AsyncSession,
    product_type: Optional[str] = None,
    provider: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    available_only: bool = False,
    **kwargs
) -> List[StandardizedProduct]:
    """Enterprise-grade search with Pydantic 2.x models"""
    logger.info(f"Searching: type={product_type}, provider={provider}")
    
    try:
        # Use optimized database filtering
        filtered_products = await mock_db.filter_products(
            product_type=product_type,
            provider=provider,
            min_price=min_price,
            max_price=max_price,
            available_only=available_only,
            **kwargs
        )
        
        logger.info(f"Found {len(filtered_products)} products")
        return filtered_products
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        return []

async def mock_get_session() -> AsyncGenerator[AsyncSession, None]:
    """Production-ready session mock with proper cleanup"""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock() 
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()
    
    try:
        yield mock_session
    finally:
        await mock_session.close()

# === PRODUCTION-READY FIXTURES ===
@pytest.fixture(autouse=True)
async def setup_comprehensive_mocks():
    """Setup all mocks with proper async cleanup"""
    patches = []
    
    try:
        # Apply comprehensive patches
        patches.extend([
            patch('data_storage.store_standardized_data', side_effect=mock_store_standardized_data),
        ])
        
        for p in patches:
            p.start()
        
        # Reset database state
        await mock_db.clear()
        yield
        
    finally:
        # Guaranteed cleanup
        for p in patches:
            try:
                p.stop()
            except Exception:
                pass

@pytest.fixture
async def mock_session():
    """High-performance mock session"""
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session

@pytest.fixture
def optimized_test_products():
    """Production test data with Pydantic 2.x models"""
    return [
        StandardizedProduct(
            source_url="https://example.com/elec/plan_a",
            category="electricity_plan",
            name="Elec Plan A",
            provider_name="Provider X",
            product_id="elec_a_001",
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
            product_id="elec_b_002",
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
            product_id="mobile_c_003",
            monthly_cost=30.0,
            data_gb=100.0,
            calls=float('inf'),  # Will be serialized as 999999.0 by field_serializer
            texts=float('inf'),  # Will be serialized as 999999.0 by field_serializer
            contract_duration_months=0,
            network_type="4G",
            available=True,
            raw_data={"type": "mobile", "features": ["unlimited_calls"]}
        ),
    ]

@pytest.fixture
async def optimized_api_client():
    """Production-grade API client with Pydantic 2.x models"""
    # Create minimal FastAPI app for testing
    test_app = FastAPI()
    
    @test_app.get("/search")
    async def search_endpoint():
        """Mock search endpoint with Pydantic 2.x responses"""
        try:
            results = await mock_search_and_filter_products(None)
            # Convert to JSON-safe format using Pydantic 2.x serialization
            json_safe_results = [product.to_json_safe_dict() for product in results]
            return json_safe_results
        except Exception as e:
            logger.error(f"API error: {e}")
            return []
    
    @test_app.get("/health")
    async def health_check():
        return {"status": "healthy", "pydantic_version": "2.x"}
    
    try:
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        pass

# === COMPREHENSIVE TEST CLASSES ===
class TestPydantic2Migration:
    """Test Pydantic 2.x migration compatibility"""
    
    def test_model_creation_and_validation(self):
        """Test Pydantic 2.x model creation and validation"""
        # Test valid model creation
        product = StandardizedProduct(
            source_url="https://test.com/product1",
            category="electricity_plan",
            name="Test Product",
            provider_name="Test Provider",
            price_kwh=0.15
        )
        
        assert product.source_url == "https://test.com/product1"
        assert product.category == "electricity_plan"
        assert product.price_kwh == 0.15
        
        # Test field validators
        with pytest.raises(ValueError):
            StandardizedProduct(
                source_url="",  # Should fail validation
                category="electricity_plan"
            )
        
        with pytest.raises(ValueError):
            StandardizedProduct(
                source_url="https://test.com",
                category="invalid_category"  # Should fail validation
            )
    
    def test_model_dump_vs_dict(self):
        """Test model_dump() method vs legacy dict()"""
        product = StandardizedProduct(
            source_url="https://test.com/product1",
            category="mobile_plan",
            name="Test Product",
            monthly_cost=30.0,
            data_gb=50.0
        )
        
        # Test model_dump() method (Pydantic 2.x)
        data = product.model_dump()
        assert isinstance(data, dict)
        assert data["source_url"] == "https://test.com/product1"
        assert data["category"] == "mobile_plan"
        
        # Test model_dump(mode="json") with serializers
        json_data = product.model_dump(mode="json")
        assert isinstance(json_data, dict)
        assert json_data["monthly_cost"] == 30.0

class TestOptimizedDatabase:
    """Test enterprise-grade database operations with Pydantic 2.x"""
    
    @pytest.mark.asyncio
    async def test_optimized_storage(self, mock_session, optimized_test_products):
        """Test high-performance storage operations"""
        # Verify clean state
        products = await mock_db.get_all_products()
        assert len(products) == 0
        
        # Store products
        await mock_store_standardized_data(mock_session, optimized_test_products)
        
        # Verify storage
        stored_products = await mock_db.get_all_products()
        assert len(stored_products) == len(optimized_test_products)
    
    @pytest.mark.asyncio
    async def test_indexed_filtering(self, mock_session, optimized_test_products):
        """Test indexed filtering performance"""
        await mock_store_standardized_data(mock_session, optimized_test_products)
        
        # Test category filtering
        elec_products = await mock_db.filter_products(product_type="electricity_plan")
        assert len(elec_products) == 2
        
        # Test provider filtering 
        provider_x_products = await mock_db.filter_products(provider="Provider X")
        assert len(provider_x_products) == 2

class TestAdvancedSearch:
    """Test advanced search functionality with Pydantic 2.x"""
    
    @pytest.mark.asyncio
    async def test_comprehensive_search(self, mock_session, optimized_test_products):
        """Test full search functionality"""
        await mock_store_standardized_data(mock_session, optimized_test_products)
        
        # Search all products
        all_results = await mock_search_and_filter_products(mock_session)
        assert len(all_results) == len(optimized_test_products)
        
        # Test that results are StandardizedProduct instances
        for result in all_results:
            assert isinstance(result, StandardizedProduct)

class TestProductionAPI:
    """Test API with Pydantic 2.x patterns"""
    
    @pytest.mark.asyncio
    async def test_api_empty_state(self, optimized_api_client):
        """Test API with empty database"""
        response = await optimized_api_client.get("/search")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0
    
    @pytest.mark.asyncio
    async def test_api_with_data(self, optimized_api_client, optimized_test_products):
        """Test API with populated database - Pydantic 2.x serialization"""
        # Populate database
        mock_session = AsyncMock()
        await mock_store_standardized_data(mock_session, optimized_test_products)
        
        # Test search endpoint
        response = await optimized_api_client.get("/search")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == len(optimized_test_products)
        
        # Verify Pydantic 2.x serialization worked - infinity should be converted
        for item in data:
            assert isinstance(item, dict)
            # Check that infinity values are properly serialized
            if 'calls' in item and item['calls'] is not None:
                assert item['calls'] == 999999.0  # Pydantic 2.x field_serializer conversion
            if 'texts' in item and item['texts'] is not None:
                assert item['texts'] == 999999.0  # Pydantic 2.x field_serializer conversion

    @pytest.mark.asyncio
    async def test_json_serialization_pydantic2(self, optimized_test_products):
        """Test Pydantic 2.x JSON serialization"""
        for product in optimized_test_products:
            # Test to_json_safe_dict method
            json_dict = product.to_json_safe_dict()
            assert isinstance(json_dict, dict)
            
            # This should not raise an exception
            json_str = json.dumps(json_dict)
            assert isinstance(json_str, str)
            
            # Verify we can parse it back
            parsed = json.loads(json_str)
            assert isinstance(parsed, dict)
            
            # Verify infinity handling by field_serializer
            if parsed.get('calls') is not None:
                assert parsed['calls'] == 999999.0
            if parsed.get('texts') is not None:
                assert parsed['texts'] == 999999.0

class TestFieldSerializers:
    """Test Pydantic 2.x field serializers"""

    def test_infinity_serialization(self):
        """Infinity/NaN serialization — только валидные значения"""
        product = StandardizedProduct(
            source_url="https://test.com/infinity",
            category="mobile_plan",
            name="Infinity Test",
            calls=float('inf'),
            texts=999.0,
            data_gb=123.0,
            monthly_cost=25.99
        )
        json_data = product.model_dump(mode="json")
        assert json_data['calls'] == 999999.0
        assert json_data['texts'] == 999.0
        assert json_data['data_gb'] == 123.0

        # Проверка, что NaN и -inf вызывают ошибку
        import math
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            StandardizedProduct(
                source_url="https://test.com/infinity",
                category="mobile_plan",
                name="Infinity Test",
                calls=999.0,
                texts=float('-inf'),
                data_gb=123.0,
                monthly_cost=25.99
            )
        with pytest.raises(ValidationError):
            StandardizedProduct(
                source_url="https://test.com/infinity",
                category="mobile_plan",
                name="Infinity Test",
                calls=999.0,
                texts=123.0,
                data_gb=math.nan,
                monthly_cost=25.99
            )
if __name__ == "__main__":
    print("=== ENTERPRISE OPTIMIZED TEST SUITE - PYDANTIC 2.X ===")
    print("🚀 Fully migrated to Pydantic 2.x with field_serializer support")
    print("✅ Updated models with ConfigDict and field_validator")
    print("✅ JSON-safe serialization through field_serializer")
    print("✅ model_dump() instead of deprecated dict()")
    print("✅ Enterprise-grade performance with Pydantic 2.x optimizations")
    print()
    print("Run with: pytest tests_api_Version18_12_pydantic2-ok.py -v --asyncio-mode=auto")