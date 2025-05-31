"""
Basic Pydantic 2.x API tests with complete migration
"""

import pytest
import math
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

# Import updated models
from models import StandardizedProduct, ProductDB, create_product_db_from_standardized


class TestPydantic2Migration:
    """Test Pydantic 2.x migration and validation."""
    
    def test_basic_model_creation(self):
        """Test basic StandardizedProduct creation with Pydantic 2.x."""
        product = StandardizedProduct(
            category="electricity_plan",
            source_url="https://test.com/product1",
            name="Test Electricity Plan",
            provider_name="Test Provider",
            price_kwh=0.15,
            available=True
        )
        
        assert product.category == "electricity_plan"
        assert product.source_url == "https://test.com/product1"
        assert product.name == "Test Electricity Plan"
        assert product.provider_name == "Test Provider"
        assert product.price_kwh == 0.15
        assert product.available is True

    def test_field_validators(self):
        """Test Pydantic 2.x field validators."""
        # Test category validator
        with pytest.raises(ValueError, match="Category must be one of"):
            StandardizedProduct(
                category="invalid_category",
                source_url="https://test.com"
            )
        
        # Test source_url validator
        with pytest.raises(ValueError, match="source_url must be a non-empty string"):
            StandardizedProduct(
                category="electricity_plan",
                source_url=""
            )
        
        # Test valid creation
        product = StandardizedProduct(
            category="mobile_plan",
            source_url="https://test.com/valid"
        )
        assert product.category == "mobile_plan"
        assert product.source_url == "https://test.com/valid"

    def test_json_safe_serialization(self):
        """Test JSON-safe serialization with infinity/NaN handling."""
        product = StandardizedProduct(
            category="electricity_plan",
            source_url="https://test.com/test1",
            name="Test Product with Special Values",
            provider_name="Test Provider",
            price_kwh=float("inf"),
            standing_charge=float("nan"),
            data_gb=-float("inf"),
            monthly_cost=25.99,
            raw_data={"test_inf": float("inf"), "test_nan": float("nan"), "normal": 42.0}
        )
        
        # Test to_json_safe_dict method
        safe_dict = product.to_json_safe_dict()
        
        # Verify infinity/NaN handling
        assert safe_dict["price_kwh"] == 999999.0  # positive inf -> 999999.0
        assert safe_dict["standing_charge"] is None  # NaN -> None
        assert safe_dict["data_gb"] == -999999.0  # negative inf -> -999999.0
        assert safe_dict["monthly_cost"] == 25.99  # normal value preserved
        
        # Check raw_data handling
        assert safe_dict["raw_data"]["test_inf"] == 999999.0
        assert safe_dict["raw_data"]["test_nan"] is None
        assert safe_dict["raw_data"]["normal"] == 42.0
        
        # Verify JSON serialization works
        json_str = json.dumps(safe_dict)
        assert json_str is not None
        assert "999999.0" in json_str
        assert "null" in json_str  # NaN becomes null
        
        # Verify can be parsed back
        parsed = json.loads(json_str)
        assert parsed["price_kwh"] == 999999.0
        assert parsed["standing_charge"] is None

    def test_model_dump_vs_dict(self):
        """Test that model_dump() is used instead of deprecated dict()."""
        product = StandardizedProduct(
            category="mobile_plan",
            source_url="https://test.com/mobile1",
            name="Mobile Plan",
            monthly_cost=30.0,
            data_gb=50.0
        )
        
        # Verify model_dump() method exists and works
        data = product.model_dump()
        assert isinstance(data, dict)
        assert data["category"] == "mobile_plan"
        assert data["source_url"] == "https://test.com/mobile1"
        assert data["monthly_cost"] == 30.0
        
        # Verify model_dump(mode="json") works with serializers
        json_data = product.model_dump(mode="json")
        assert isinstance(json_data, dict)
        assert json_data["category"] == "mobile_plan"

    def test_config_dict_usage(self):
        """Test that ConfigDict is properly used instead of Config class."""
        # Verify the model has model_config attribute
        assert hasattr(StandardizedProduct, 'model_config')
        
        # Test validation behavior from ConfigDict
        product = StandardizedProduct(
            category="electricity_plan",
            source_url="  https://test.com/trimmed  ",  # Should be trimmed
            provider_name="  Provider Name  "  # Should be trimmed
        )
        
        # ConfigDict should trim whitespace
        assert product.source_url == "https://test.com/trimmed"
        assert product.provider_name == "Provider Name"

    def test_db_model_conversion(self):
        """Test conversion between Pydantic and SQLModel using Pydantic 2.x methods."""
        # Create StandardizedProduct
        product = StandardizedProduct(
            category="internet_plan",
            source_url="https://test.com/internet1",
            name="High Speed Internet",
            provider_name="Internet Provider",
            download_speed=1000.0,
            upload_speed=100.0,
            monthly_cost=75.0,
            raw_data={"speed_test": "passed", "fiber": True}
        )
        
        # Convert to ProductDB
        product_db = create_product_db_from_standardized(product)
        assert isinstance(product_db, ProductDB)
        assert product_db.category == "internet_plan"
        assert product_db.source_url == "https://test.com/internet1"
        assert product_db.download_speed == 1000.0
        assert product_db.raw_data_json == {"speed_test": "passed", "fiber": True}
        
        # Convert back to StandardizedProduct
        converted_back = product_db.to_standardized_product()
        assert isinstance(converted_back, StandardizedProduct)
        assert converted_back.category == "internet_plan"
        assert converted_back.source_url == "https://test.com/internet1"
        assert converted_back.download_speed == 1000.0
        assert converted_back.raw_data == {"speed_test": "passed", "fiber": True}

    def test_validation_assignment(self):
        """Test validate_assignment=True from ConfigDict."""
        product = StandardizedProduct(
            category="electricity_plan",
            source_url="https://test.com/validation"
        )
        
        # Should allow valid assignment
        product.name = "Updated Name"
        assert product.name == "Updated Name"
        
        # Should validate on assignment (if validation rules exist)
        with pytest.raises(ValueError):
            product.category = "invalid_category"

    def test_field_descriptions(self):
        """Test that field descriptions are properly set."""
        # Get field info from model
        fields = StandardizedProduct.model_fields
        
        # Check some key fields have descriptions
        assert "description" in str(fields["category"])
        assert "description" in str(fields["source_url"])
        assert "Product category" in str(fields["category"])
        assert "URL of the product page" in str(fields["source_url"])

    def test_comprehensive_serialization(self):
        """Test comprehensive serialization with all field types."""
        product = StandardizedProduct(
            category="mobile_plan",
            source_url="https://test.com/comprehensive",
            name="Comprehensive Test Plan",
            provider_name="Test Provider",
            product_id="TEST-001",
            description="A test plan with all fields",
            contract_duration_months=12,
            available=True,
            
            # Electricity fields
            price_kwh=0.18,
            standing_charge=10.0,
            contract_type="Fixed",
            
            # Mobile fields
            monthly_cost=45.0,
            data_gb=100.0,
            calls=float("inf"),  # Unlimited calls
            texts=1000.0,
            network_type="5G",
            
            # Internet fields
            download_speed=500.0,
            upload_speed=50.0,
            connection_type="Fiber",
            data_cap_gb=float("inf"),  # Unlimited data
            internet_monthly_cost=60.0,
            
            raw_data={
                "original_price": "45 USD/month",
                "features": ["5G", "unlimited calls"],
                "test_inf": float("inf"),
                "test_nan": float("nan")
            }
        )
        
        # Test JSON-safe serialization
        safe_dict = product.to_json_safe_dict()
        
        # Verify all fields are present and properly serialized
        assert safe_dict["category"] == "mobile_plan"
        assert safe_dict["calls"] == 999999.0  # inf -> 999999.0
        assert safe_dict["data_cap_gb"] == 999999.0  # inf -> 999999.0
        assert safe_dict["raw_data"]["test_inf"] == 999999.0
        assert safe_dict["raw_data"]["test_nan"] is None
        assert safe_dict["raw_data"]["features"] == ["5G", "unlimited calls"]
        
        # Verify JSON serialization
        json_str = json.dumps(safe_dict)
        parsed = json.loads(json_str)
        assert parsed["category"] == "mobile_plan"
        assert parsed["calls"] == 999999.0


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])