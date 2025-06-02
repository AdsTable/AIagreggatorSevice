"""
Production-ready test suite updated for Pydantic 2.x
Migrated from dataclass models to full Pydantic 2.x integration
"""

import pytest
import pytest_asyncio
import sys
import os
import json
import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, AsyncGenerator, Union
from unittest.mock import patch, MagicMock, AsyncMock
from copy import deepcopy

# Используем существующий conftest.py infrastructure
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import updated Pydantic 2.x models
from models import StandardizedProduct, ProductDB, create_product_db_from_standardized

# FastAPI testing imports
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

# Database imports
from sqlmodel import SQLModel, select, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import text

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === PYTEST ASYNCIO CONFIGURATION ===
pytest_plugins = ('pytest_asyncio',)

# === ENHANCED ERROR MONITORING ===
class ProductionErrorCapture:
    """Production-ready error capture with Pydantic 2.x compatibility"""
    
    def __init__(self):
        self.errors = []
        self.request_count = 0
        self.performance_metrics = {}
        
    def log_error(self, error: str, context: str = ""):
        self.errors.append({"error": error, "context": context, "timestamp": time.time()})
        logger.error(f"Production error captured: {error} | Context: {context}")
        
    def log_request(self, endpoint: str = ""):
        self.request_count += 1
        if endpoint not in self.performance_metrics:
            self.performance_metrics[endpoint] = {"count": 0, "total_time": 0}
        self.performance_metrics[endpoint]["count"] += 1
        
    def get_comprehensive_stats(self):
        return {
            "total_requests": self.request_count,
            "total_errors": len(self.errors),
            "error_rate": len(self.errors) / max(self.request_count, 1),
            "performance_metrics": self.performance_metrics,
            "recent_errors": self.errors[-5:] if self.errors else []
        }
        
    def clear(self):
        self.errors.clear()
        self.request_count = 0
        self.performance_metrics.clear()

# Global production error capture
production_error_capture = ProductionErrorCapture()

# === PRODUCTION DATABASE WITH PYDANTIC 2.X ===
class ProductionMockDatabase:
    """Production database using Pydantic 2.x models"""
    
    def __init__(self):
        self._products: List[StandardizedProduct] = []
        self._lock = None
        self._performance_cache = {}
        
    def _ensure_lock(self):
        """Safe lock initialization"""
        try:
            if self._lock is None:
                self._lock = asyncio.Lock()
        except RuntimeError:
            self._lock = None
    
    async def clear_async(self):
        """Async clear with performance tracking"""
        start_time = time.time()
        self._ensure_lock()
        
        if self._lock:
            async with self._lock:
                self._products.clear()
        else:
            self._products.clear()
            
        self._performance_cache.clear()
        logger.info(f"Database cleared in {time.time() - start_time:.3f}s")
    
    def clear_sync(self):
        """Sync clear for compatibility"""
        self._products.clear()
        self._performance_cache.clear()
        logger.info("Database cleared synchronously")
    
    async def add_products_async(self, products: List[StandardizedProduct]):
        """High-performance async add with Pydantic 2.x validation"""
        start_time = time.time()
        self._ensure_lock()
        
        # Validate products using Pydantic 2.x
        validated_products = []
        for product in products:
            if isinstance(product, StandardizedProduct):
                validated_products.append(product)
            else:
                # Convert dict to StandardizedProduct if needed
                if isinstance(product, dict):
                    validated_product = StandardizedProduct.model_validate(product)
                    validated_products.append(validated_product)
        
        if self._lock:
            async with self._lock:
                self._products.extend(validated_products)
        else:
            self._products.extend(validated_products)
            
        # Update performance cache
        self._performance_cache['last_add'] = {
            'count': len(validated_products),
            'time': time.time() - start_time,
            'total_products': len(self._products)
        }
        
        logger.info(f"Added {len(validated_products)} products in {time.time() - start_time:.3f}s")
    
    def add_products_sync(self, products: List[StandardizedProduct]):
        """Sync add for compatibility"""
        validated_products = []
        for product in products:
            if isinstance(product, StandardizedProduct):
                validated_products.append(product)
            else:
                if isinstance(product, dict):
                    validated_product = StandardizedProduct.model_validate(product)
                    validated_products.append(validated_product)
        
        self._products.extend(validated_products)
        logger.info(f"Added {len(validated_products)} products synchronously")
    
    async def get_products_async(self, **filters) -> List[Dict[str, Any]]:
        """High-performance filtered search with Pydantic 2.x serialization"""
        start_time = time.time()
        self._ensure_lock()
        
        if self._lock:
            async with self._lock:
                result = await self._apply_filters(self._products, filters)
        else:
            result = await self._apply_filters(self._products, filters)
        
        # Performance tracking
        search_time = time.time() - start_time
        logger.info(f"Search completed in {search_time:.3f}s, returned {len(result)} products")
        
        # Use Pydantic 2.x serialization
        return [product.to_json_safe_dict() for product in result]
    
    def get_products_sync(self, **filters) -> List[Dict[str, Any]]:
        """Sync get for compatibility"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(self._apply_filters(self._products, filters))
            return [product.to_json_safe_dict() for product in result]
        finally:
            loop.close()
    
    async def _apply_filters(self, products: List[StandardizedProduct], filters: Dict[str, Any]) -> List[StandardizedProduct]:
        """Optimized filtering logic"""
        result = products.copy()
        
        # Category filter
        if filters.get('category') or filters.get('product_type'):
            category = filters.get('category') or filters.get('product_type')
            result = [p for p in result if p.category == category]
        
        # Provider filter
        if filters.get('provider'):
            result = [p for p in result if p.provider_name == filters['provider']]
        
        # Availability filter
        if filters.get('available_only'):
            result = [p for p in result if p.available]
        
        # Price filters
        if filters.get('min_price') is not None:
            result = [p for p in result if p.price_kwh is not None and p.price_kwh >= filters['min_price']]
        
        if filters.get('max_price') is not None:
            result = [p for p in result if p.price_kwh is not None and p.price_kwh <= filters['max_price']]
        
        return result

# Global production database
production_db = ProductionMockDatabase()

# === PRODUCTION MOCK FUNCTIONS WITH PYDANTIC 2.X ===
async def production_mock_search(*args, **kwargs) -> List[Dict[str, Any]]:
    """Production search function using Pydantic 2.x models"""
    start_time = time.time()
    
    try:
        production_error_capture.log_request("search")
        
        # Extract filters
        filters = {}
        
        # Handle positional arguments
        if args and len(args) > 1:
            filters['product_type'] = args[1]
        
        # Handle keyword arguments
        filters.update({k: v for k, v in kwargs.items() if v is not None})
        
        logger.info(f"Production search with filters: {filters}")
        result = await production_db.get_products_async(**filters)
        
        search_time = time.time() - start_time
        logger.info(f"Production search completed in {search_time:.3f}s, returned {len(result)} products")
        
        return result
        
    except Exception as e:
        production_error_capture.log_error(f"Search error: {str(e)}", "production_mock_search")
        logger.error(f"Production search error: {e}")
        return []

def production_mock_search_sync(*args, **kwargs) -> List[Dict[str, Any]]:
    """Sync version for compatibility"""
    try:
        production_error_capture.log_request("search_sync")
        
        filters = {}
        if args and len(args) > 1:
            filters['product_type'] = args[1]
        filters.update({k: v for k, v in kwargs.items() if v is not None})
        
        result = production_db.get_products_sync(**filters)
        logger.info(f"Sync search returned {len(result)} products")
        return result
        
    except Exception as e:
        production_error_capture.log_error(f"Sync search error: {str(e)}", "production_mock_search_sync")
        return []

# === PRODUCTION TEST DATA WITH PYDANTIC 2.X ===
def create_production_test_products() -> List[StandardizedProduct]:
    """Production test data using Pydantic 2.x models"""
    return [
        # Electricity plans
        StandardizedProduct(
            source_url="https://production.energy.com/plan_a",
            category="electricity_plan",
            name="Production Green Energy Plan",
            provider_name="GreenEnergy Corp",
            product_id="prod_green_001",
            price_kwh=0.15,
            standing_charge=5.0,
            contract_duration_months=12,
            available=True,
            contract_type="fixed",
            raw_data={"type": "electricity", "features": ["green", "renewable"], "tier": "premium"}
        ),
        StandardizedProduct(
            source_url="https://production.energy.com/plan_b",
            category="electricity_plan",
            name="Production Standard Energy Plan",
            provider_name="Standard Energy Ltd",
            product_id="prod_standard_002",
            price_kwh=0.12,
            standing_charge=4.0,
            contract_duration_months=24,
            available=False,  # Test unavailable products
            contract_type="variable",
            raw_data={"type": "electricity", "features": ["standard"], "tier": "basic"}
        ),
        
        # Mobile plans with infinity values for serialization testing
        StandardizedProduct(
            source_url="https://production.mobile.com/unlimited",
            category="mobile_plan",
            name="Production Unlimited Mobile",
            provider_name="MegaMobile Corp",
            product_id="prod_mobile_003",
            monthly_cost=35.0,
            data_gb=float('inf'),  # Will be serialized as 999999.0
            calls=float('inf'),    # Will be serialized as 999999.0
            texts=float('inf'),    # Will be serialized as 999999.0
            contract_duration_months=0,  # No contract
            network_type="5G",
            available=True,
            raw_data={"type": "mobile", "features": ["unlimited", "5g"], "tier": "premium"}
        ),
        
        # Internet plans
        StandardizedProduct(
            source_url="https://production.internet.com/fiber",
            category="internet_plan",
            name="Production Fiber Internet",
            provider_name="FiberNet Solutions",
            product_id="prod_fiber_004",
            internet_monthly_cost=45.0,
            download_speed=1000.0,
            upload_speed=500.0,
            connection_type="fiber",
            data_cap_gb=None,  # Truly unlimited
            contract_duration_months=12,
            available=True,
            raw_data={"type": "internet", "features": ["fiber", "gigabit"], "tier": "enterprise"}
        ),
    ]

# === PRODUCTION TEST CLASSES ===
class TestProductionPydantic2Compatibility:
    """Test Pydantic 2.x specific features"""
    
    @pytest.fixture(autouse=True)
    async def setup_production_test(self):
        """Setup using Pydantic 2.x patterns"""
        await production_db.clear_async()
        production_error_capture.clear()
        yield
        await production_db.clear_async()
    
    def test_pydantic2_model_validation(self):
        """Test Pydantic 2.x model validation features"""
        # Test successful validation
        product = StandardizedProduct(
            source_url="https://test.com/valid",
            category="electricity_plan",
            name="Valid Product"
        )
        assert product.source_url == "https://test.com/valid"
        assert product.category == "electricity_plan"
        
        # Test field validators
        with pytest.raises(ValueError):
            StandardizedProduct(
                source_url="",  # Should fail source_url validator
                category="electricity_plan"
            )
        
        with pytest.raises(ValueError):
            StandardizedProduct(
                source_url="https://test.com",
                category="invalid_category"  # Should fail category validator
            )
    
    def test_pydantic2_serialization_methods(self):
        """Test Pydantic 2.x serialization methods"""
        product = StandardizedProduct(
            source_url="https://test.com/serialize",
            category="mobile_plan",
            name="Serialization Test",
            calls=float('inf'),
            texts=123.0,
            monthly_cost=30.0
        )
        
        # Test model_dump() method
        data = product.model_dump()
        assert isinstance(data, dict)
        assert data["source_url"] == "https://test.com/serialize"
        
        # Test model_dump(mode="json") with field_serializer
        json_data = product.model_dump(mode="json")
        assert json_data["calls"] == 999999.0  # infinity -> 999999.0
        assert json_data["texts"] == 123.0
        assert json_data["monthly_cost"] == 30.0  # normal value preserved
        
        # Test to_json_safe_dict method
        safe_dict = product.to_json_safe_dict()
        assert safe_dict["calls"] == 999999.0
        assert safe_dict["texts"] == 123.0

        import math
        from pydantic import ValidationError

        # Проверяем, что NaN вызывает ошибку
        with pytest.raises(ValidationError):
            StandardizedProduct(
                source_url="https://test.com/serialize",
                category="mobile_plan",
                name="Serialization Test",
                calls=999.0,
                texts=math.nan,
                monthly_cost=30.0
            )
        # Verify JSON serialization works
        json_str = json.dumps(safe_dict)
        assert isinstance(json_str, str)

class TestProductionBasicFunctionality:
    """Production-ready basic functionality tests with Pydantic 2.x"""
    
    @pytest.fixture(autouse=True)
    async def setup_production_test(self):
        """Setup using Pydantic 2.x patterns"""
        await production_db.clear_async()
        production_error_capture.clear()
        yield
        await production_db.clear_async()
    
    def test_production_empty_database_sync(self):
        """Test empty database with production error capture"""
        results = production_mock_search_sync()
        assert isinstance(results, list)
        assert len(results) == 0
        
        # Verify error capture worked
        stats = production_error_capture.get_comprehensive_stats()
        assert stats["total_requests"] >= 1
        assert stats["error_rate"] <= 0.1  # Allow for some errors
    
    @pytest.mark.asyncio
    async def test_production_empty_database_async(self):
        """Test empty database async"""
        results = await production_mock_search()
        assert isinstance(results, list)
        assert len(results) == 0
    
    def test_production_storage_and_retrieval_sync(self):
        """Test storage and retrieval with Pydantic 2.x models"""
        test_products = create_production_test_products()
        
        # Store products
        production_db.add_products_sync(test_products)
        
        # Retrieve all products
        all_products = production_db.get_products_sync()
        assert len(all_products) == len(test_products)
        assert len(all_products) == 4
        
        # Verify Pydantic 2.x serialization
        for product_dict in all_products:
            json_str = json.dumps(product_dict)
            assert isinstance(json_str, str)
            
            # Verify infinity values are properly handled
            if 'calls' in product_dict and product_dict['calls'] is not None:
                assert product_dict['calls'] == 999999.0
    
    @pytest.mark.asyncio
    async def test_production_filtered_search(self):
        """Test filtered search with Pydantic 2.x models"""
        test_products = create_production_test_products()
        await production_db.add_products_async(test_products)
        
        # Category filter
        electricity_products = await production_mock_search(product_type="electricity_plan")
        assert len(electricity_products) == 2
        
        # Availability filter
        available_products = await production_mock_search(available_only=True)
        assert len(available_products) == 3  # 1 electricity + 1 mobile + 1 internet
        
        # Provider filter
        green_products = await production_mock_search(provider="GreenEnergy Corp")
        assert len(green_products) == 1

class TestProductionAPIEndpoints:
    """Production API tests with Pydantic 2.x integration"""
    
    def setup_method(self):
        """Setup using Pydantic 2.x patterns"""
        self.test_app = FastAPI()
        
        @self.test_app.get("/search")
        async def production_search_endpoint(
            product_type: Optional[str] = None,
            provider: Optional[str] = None,
            available_only: bool = False,
            min_price: Optional[float] = None,
            max_price: Optional[float] = None
        ):
            """Production search endpoint with Pydantic 2.x serialization"""
            try:
                results = await production_mock_search(
                    product_type=product_type,
                    provider=provider,
                    available_only=available_only,
                    min_price=min_price,
                    max_price=max_price
                )
                return results
            except Exception as e:
                production_error_capture.log_error(f"API error: {str(e)}", "search_endpoint")
                return []
        
        @self.test_app.get("/health")
        async def production_health():
            """Production health check with Pydantic version info"""
            stats = production_error_capture.get_comprehensive_stats()
            return {
                "status": "healthy",
                "pydantic_version": "2.x",
                "timestamp": time.time(),
                "metrics": stats
            }
    
    @pytest.mark.asyncio
    async def test_production_api_with_pydantic2_serialization(self):
        """Test API with Pydantic 2.x serialization"""
        test_products = create_production_test_products()
        await production_db.clear_async()
        await production_db.add_products_async(test_products)
        
        transport = ASGITransport(app=self.test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Test basic search
            response = await client.get("/search")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 4
            
            # Verify Pydantic 2.x field_serializer worked
            mobile_plan = next((p for p in data if p["category"] == "mobile_plan"), None)
            assert mobile_plan is not None
            assert mobile_plan["calls"] == 999999.0   # infinity serialized correctly
            assert mobile_plan["texts"] == 999999.0   # infinity serialized correctly
            assert mobile_plan["data_gb"] == 999999.0 # infinity serialized correctly
            
            # Test health endpoint shows Pydantic version
            response = await client.get("/health")
            assert response.status_code == 200
            health_data = response.json()
            assert health_data["pydantic_version"] == "2.x"

if __name__ == "__main__":
    print("=== PRODUCTION-READY TEST SUITE - PYDANTIC 2.X ===")
    print("🚀 Fully migrated to Pydantic 2.x from dataclass models")
    print("✅ Using StandardizedProduct with field_validator and field_serializer")
    print("✅ model_dump() instead of deprecated dict()")
    print("✅ ConfigDict instead of Config class")
    print("✅ JSON-safe serialization through Pydantic 2.x features")
    print("✅ Production error capture and metrics")
    print("✅ High-performance async operations")
    print()
    print("Run with: pytest tests_api_Version19_pydantic2-ok.py -v --asyncio-mode=auto")