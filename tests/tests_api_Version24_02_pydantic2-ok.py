"""
Enhanced JSON-safe testing updated for Pydantic 2.x
Migrated from standalone dataclass to full Pydantic 2.x integration
"""

import math
import json
import pytest
from pydantic import ValidationError
from typing import List, Optional, Dict, Any, Union

# Import Pydantic 2.x models
from models import StandardizedProduct

# === ENHANCED JSON-SAFE UTILITY FUNCTIONS FOR PYDANTIC 2.X ===

class SafeNumericValue:
    """Wrapper for tracking replaced infinity/NaN values"""
    def __init__(self, original_type: str, safe_value: Any):
        self.original_type = original_type  # 'inf', '-inf', 'nan'
        self.safe_value = safe_value
    
    def __str__(self):
        return str(self.safe_value)
    
    def __repr__(self):
        return f"SafeNumericValue({self.original_type}, {self.safe_value})"

def validate_json_safety(json_str: str) -> Dict[str, Any]:
    """
    Comprehensive validation of JSON safety for Pydantic 2.x output
    """
    analysis = {
        "is_safe": True,
        "issues": [],
        "has_infinity": False,
        "has_nan": False,
        "can_parse": True
    }
    
    try:
        # Test parsing
        parsed = json.loads(json_str)
        
        # Check for actual infinity values in parsed data
        def check_recursive(obj, path="root"):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    check_recursive(value, f"{path}.{key}")
            elif isinstance(obj, list):
                for i, value in enumerate(obj):
                    check_recursive(value, f"{path}[{i}]")
            elif isinstance(obj, float):
                if math.isinf(obj):
                    analysis["has_infinity"] = True
                    analysis["is_safe"] = False
                    analysis["issues"].append(f"Infinity value at {path}")
                elif math.isnan(obj):
                    analysis["has_nan"] = True
                    analysis["is_safe"] = False
                    analysis["issues"].append(f"NaN value at {path}")
        
        check_recursive(parsed)
        
    except json.JSONDecodeError as e:
        analysis["can_parse"] = False
        analysis["is_safe"] = False
        analysis["issues"].append(f"JSON parse error: {e}")
    
    return analysis

def json_safe_float_with_metadata(value: Optional[float]) -> Dict[str, Any]:
    """
    Enhanced version that preserves metadata about replacements for Pydantic 2.x
    """
    if value is None:
        return {"value": None, "original": None}
    
    if isinstance(value, float):
        if math.isinf(value):
            return {
                "value": None,
                "original": "positive_infinity" if value > 0 else "negative_infinity",
                "replaced": True
            }
        if math.isnan(value):
            return {
                "value": None,
                "original": "not_a_number",
                "replaced": True
            }
    
    return {"value": value, "original": value}

# === MOCK DATABASE CLASS WITH PYDANTIC 2.X ===

class JsonSafeMockDatabase:
    """Mock database with Pydantic 2.x integration and enhanced JSON safety"""
    
    def __init__(self):
        self.products = []
        self.call_count = 0
        self.replacement_stats = {
            "infinity_replaced": 0,
            "nan_replaced": 0,
            "total_processed": 0
        }

    def enhanced_add_products(self, products: List[StandardizedProduct]):
        """Add products with Pydantic 2.x validation and JSON safety tracking"""
        safe_products = []
        
        for product in products:
            # Validate using Pydantic 2.x
            if not isinstance(product, StandardizedProduct):
                if isinstance(product, dict):
                    # Convert dict to StandardizedProduct using model_validate
                    product = StandardizedProduct.model_validate(product)
                else:
                    continue
            
            # The field_serializer in StandardizedProduct handles infinity/NaN conversion
            # We just need to track what was converted
            json_data = product.model_dump(mode="json")
            
            # Count replacements by comparing original values
            for field_name in ['price_kwh', 'standing_charge', 'monthly_cost', 'data_gb', 
                              'calls', 'texts', 'download_speed', 'upload_speed', 'data_cap_gb']:
                original_value = getattr(product, field_name, None)
                json_value = json_data.get(field_name)
                
                if isinstance(original_value, float):
                    if math.isinf(original_value) and json_value == 999999.0:
                        self.replacement_stats["infinity_replaced"] += 1
                    elif math.isnan(original_value) and json_value is None:
                        self.replacement_stats["nan_replaced"] += 1
            
            safe_products.append(product)
            self.replacement_stats["total_processed"] += 1
        
        self.products.extend(safe_products)
        print(f"📦 Added {len(products)} Pydantic 2.x products. "
              f"Field serializers handled: {self.replacement_stats['infinity_replaced']} inf, "
              f"{self.replacement_stats['nan_replaced']} NaN values")

    def enhanced_get_all_products(self) -> List[Dict[str, Any]]:
        """Get products with Pydantic 2.x serialization and guaranteed JSON safety"""
        self.call_count += 1
        result = []
        
        for product in self.products:
            # Use Pydantic 2.x to_json_safe_dict method
            product_dict = product.to_json_safe_dict()
            result.append(product_dict)
        
        return result

# === TEST CLASS WITH PYDANTIC 2.X ===

class TestPydantic2JsonSafetyAPI:
    """Enhanced test class for Pydantic 2.x JSON safety validation"""
    
    def test_pydantic2_field_serializers(self):
        """Test Pydantic 2.x field_serializer functionality"""
        
        # Create products with problematic float values
        products = [
            StandardizedProduct(
                source_url="https://example.com/test1",
                category="electricity_plan",
                name="Test Product with Infinity",
                provider_name="Test Provider",
                price_kwh=float('inf'),
                standing_charge=10.0,  # valid
                available=True
            ),
            StandardizedProduct(
                source_url="https://example.com/test2",
                category="mobile_plan",
                name="Test Product",
                provider_name="Test Provider",
                data_gb=123.0,
                calls=float('inf'),
                monthly_cost=25.99,
                available=True
            )
        ]
        
        # Test field_serializer conversion using model_dump(mode="json")
        for product in products:
            json_data = product.model_dump(mode="json")
            
            # Verify field_serializer conversions
            if hasattr(product, "calls") and getattr(product, "calls", 0) == float('inf'):
                assert json_data['calls'] == 999999.0
            if hasattr(product, "price_kwh") and getattr(product, "price_kwh", 0) == float('inf'):
               assert json_data['price_kwh'] == 999999.0
            # Проверяем сериализуемость и безопасность JSON
            json_str = json.dumps(json_data)
            safety_analysis = validate_json_safety(json_str)
            assert safety_analysis["is_safe"], f"Field serializer output not JSON safe: {safety_analysis['issues']}"
        # Проверяем, что -inf и nan дают ошибку
        with pytest.raises(ValidationError):
            StandardizedProduct(
                source_url="https://example.com/test1",
                category="electricity_plan",
                name="Test Product with -inf",
                provider_name="Test Provider",
                price_kwh=float('-inf'),
                standing_charge=10.0,
                available=True
            )
        with pytest.raises(ValidationError):
            StandardizedProduct(
                source_url="https://example.com/test2",
                category="mobile_plan",
                name="Test Product with NaN",
                provider_name="Test Provider",
                data_gb=math.nan,
                calls=100.0,
                monthly_cost=25.99,
                available=True
            )
            
            # Test JSON serialization works
            json_str = json.dumps(json_data)
            safety_analysis = validate_json_safety(json_str)
            assert safety_analysis["is_safe"], f"Field serializer output not JSON safe: {safety_analysis['issues']}"
        
        print("✅ Pydantic 2.x field_serializer test passed")
    
    def test_enhanced_add_products_pydantic2(self):
        """Test the enhanced add products functionality with Pydantic 2.x validation"""
        db = JsonSafeMockDatabase()
        
        # Create test products with problematic float values
        products = [
            StandardizedProduct(
                source_url="https://example.com/test1",
                category="electricity_plan",
                name="Test Product with Infinity",
                provider_name="Test Provider",
                price_kwh=float('inf'),
                standing_charge=10.0,
                available=True
            ),
            StandardizedProduct(
                source_url="https://example.com/test2",
                category="mobile_plan",
                name="Test Product",
                provider_name="Test Provider",
                data_gb=123.0,
                monthly_cost=25.99,
                available=True
            )
        ]
        
        # Add products using enhanced method
        db.enhanced_add_products(products)
        
        # Verify products were added
        assert len(db.products) == 2
        for product in db.products:
            assert isinstance(product, StandardizedProduct)
        all_products = db.enhanced_get_all_products()
        for product_dict in all_products:
            json_str = json.dumps(product_dict)
            safety_analysis = validate_json_safety(json_str)
            assert safety_analysis["is_safe"], f"JSON safety issues: {safety_analysis['issues']}"
            assert not safety_analysis["has_infinity"], "JSON contains infinity values"
            assert not safety_analysis["has_nan"], "JSON contains NaN values"
        # Проверяем ошибки для недопустимых значений
        with pytest.raises(ValidationError):
            StandardizedProduct(
                source_url="https://example.com/test3",
                category="electricity_plan",
                name="Test Product with -inf",
                provider_name="Test Provider",
                price_kwh=float('-inf'),
                standing_charge=10.0,
                available=True
            )
        with pytest.raises(ValidationError):
            StandardizedProduct(
                source_url="https://example.com/test4",
                category="mobile_plan",
                name="Test Product with NaN",
                provider_name="Test Provider",
                data_gb=math.nan,
                monthly_cost=25.99,
                available=True
            )

        for product in db.products:
            assert isinstance(product, StandardizedProduct)
        
        # Get products and validate JSON safety using Pydantic 2.x serialization
        all_products = db.enhanced_get_all_products()
        
        for product_dict in all_products:
            json_str = json.dumps(product_dict)
            safety_analysis = validate_json_safety(json_str)
            
            assert safety_analysis["is_safe"], f"JSON safety issues: {safety_analysis['issues']}"
            assert not safety_analysis["has_infinity"], "JSON contains infinity values"
            assert not safety_analysis["has_nan"], "JSON contains NaN values"
        
        print(f"✅ Enhanced add products with Pydantic 2.x test passed")

    def test_pydantic2_to_json_safe_dict(self):
        """Test StandardizedProduct.to_json_safe_dict() method"""
        product = StandardizedProduct(
            source_url="https://example.com/test",
            category="electricity_plan",
            name="Test Product",
            provider_name="Test Provider",
            price_kwh=float('inf'),
            standing_charge=10.0,
            available=True,
            raw_data={"test_infinity": float('inf'), "normal_value": 42.0}
        )
        
        safe_dict = product.to_json_safe_dict()
        json_str = json.dumps(safe_dict)
        
        # Use enhanced validation
        safety_analysis = validate_json_safety(json_str)
        
        assert safety_analysis["is_safe"]
        assert not safety_analysis["has_infinity"]
        assert not safety_analysis["has_nan"]
        
        # Verify specific conversions using Pydantic 2.x field_serializer
        assert safe_dict['price_kwh'] == 999999.0  # inf -> 999999.0 by field_serializer
        assert safe_dict['standing_charge']  == 10.0  
        assert safe_dict['raw_data']['test_infinity'] == 999999.0  # nested inf handled
        assert safe_dict['raw_data']['normal_value'] == 42.0  # normal value preserved        
        
        with pytest.raises(ValidationError):
            StandardizedProduct(
                source_url="https://example.com/test",
                category="electricity_plan",
                name="Test Product",
                provider_name="Test Provider",
                price_kwh=10.0,
                standing_charge=math.nan,  # invalid
                available=True,
                raw_data={"test_infinity": float('inf'), "normal_value": 42.0}
            )
        print(f"✅ Pydantic 2.x to_json_safe_dict test passed")

    def test_pydantic2_model_validation(self):
        """Test Pydantic 2.x model validation features"""
        # Test successful validation
        product = StandardizedProduct(
            source_url="https://valid.example.com/test",
            category="electricity_plan",
            name="Valid Product"
        )
        assert product.source_url == "https://valid.example.com/test"
        
        # Test field_validator for source_url
        with pytest.raises(ValidationError):
            StandardizedProduct(
                source_url="",  # Should fail validation
                category="electricity_plan",
                name="Invalid Product"
            )
        
        # Test field_validator for category
        with pytest.raises(ValidationError):
            StandardizedProduct(
                source_url="https://test.com",
                category="invalid_category",  # Should fail validation
                name="Invalid Category Product"
            )
        
        print("✅ Pydantic 2.x model validation test passed")

    def test_pydantic2_serialization_modes(self):
        """Test different Pydantic 2.x serialization modes"""
        product = StandardizedProduct(
            source_url="https://test.com/modes",
            category="mobile_plan",
            name="Serialization Test",
            calls=float('inf'),
            texts=123.0,
            monthly_cost=30.0
        )
        
        # Test regular model_dump()
        regular_dump = product.model_dump()
        assert regular_dump['calls'] == float('inf')  # Original values preserved
        assert regular_dump['texts'] == 123.0
        
        # Test model_dump(mode="json") - uses field_serializer
        json_dump = product.model_dump(mode="json")
        assert json_dump['calls'] == 999999.0  # field_serializer applied
        assert json_dump['texts'] == 123.0     # field_serializer applied
        
        # Test to_json_safe_dict() method
        safe_dict = product.to_json_safe_dict()
        assert safe_dict['calls'] == 999999.0
        assert safe_dict['texts'] == 123.0
        
        # All JSON modes should be serializable
        for data in [json_dump, safe_dict]:
            json_str = json.dumps(data)
            safety_analysis = validate_json_safety(json_str)
            assert safety_analysis["is_safe"]

        import math
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            StandardizedProduct(
                source_url="https://test.com/modes",
                category="mobile_plan",
                name="Serialization Test",
                calls=100.0,
                texts=math.nan,
                monthly_cost=30.0
            )
        
        print("✅ Pydantic 2.x serialization modes test passed")

    def test_metadata_preservation_pydantic2(self):
        """Test enhanced float processing with metadata for Pydantic 2.x"""
        test_values = [
            float('inf'),
            float('-inf'), 
            float('nan'),
            42.5,
            None
        ]
        
        for value in test_values:
            metadata = json_safe_float_with_metadata(value)
            
            if value is None:
                assert metadata["value"] is None
                assert metadata["original"] is None
            elif math.isinf(value):
                assert metadata["value"] is None
                assert metadata["replaced"] is True
                assert "infinity" in metadata["original"]
            elif math.isnan(value):
                assert metadata["value"] is None
                assert metadata["replaced"] is True
                assert metadata["original"] == "not_a_number"
            else:
                assert metadata["value"] == value
                assert metadata["original"] == value
        
        print("✅ Metadata preservation with Pydantic 2.x test passed")

    def test_pydantic2_complex_nested_data(self):
        """Test complex nested data with Pydantic 2.x"""
        complex_raw_data = {
            "measurements": [{"value": float('inf')}, {"value": 42.0}],
            "analytics": {
                "stats": [1.0, float('nan'), 3.0],
                "summary": {
                    "max": float('inf'),
                    "min": -10.0,
                    "avg": float('nan')
                }
            }
        }
        
        product = StandardizedProduct(
            source_url="https://complex.test.com/data",
            category="internet_plan",
            name="Complex Data Product",
            provider_name="Complex Provider",
            raw_data=complex_raw_data
        )
        
        # Test Pydantic 2.x serialization handles nested infinity/NaN
        safe_dict = product.to_json_safe_dict()
        json_str = json.dumps(safe_dict)
        
        safety_analysis = validate_json_safety(json_str)
        assert safety_analysis["is_safe"], f"Complex nested data not JSON safe: {safety_analysis['issues']}"
        
        # Verify nested conversions
        raw_data = safe_dict['raw_data']
        assert raw_data['measurements'][0]['value'] == 999999.0  # inf converted
        assert raw_data['measurements'][1]['value'] == 42.0      # normal preserved
        assert raw_data['analytics']['stats'][1] is None         # NaN converted
        assert raw_data['analytics']['summary']['max'] == 999999.0  # inf converted
        assert raw_data['analytics']['summary']['avg'] is None   # NaN converted
        
        print("✅ Complex nested data with Pydantic 2.x test passed")

# === PYTEST CONFIGURATION ===
pytest_plugins = ['pytest_asyncio']

if __name__ == "__main__":
    # Run tests directly with Pydantic 2.x
    print("=== PYDANTIC 2.X JSON SAFETY TEST SUITE ===")
    print("🚀 Fully migrated to Pydantic 2.x with field_serializer")
    print("✅ Using StandardizedProduct with ConfigDict")
    print("✅ field_validator for input validation")
    print("✅ field_serializer for JSON-safe output")
    print("✅ model_dump(mode='json') for serialization")
    print("✅ Enhanced error handling and validation")
    print()
    
    test_instance = TestPydantic2JsonSafetyAPI()
    test_instance.test_pydantic2_field_serializers()
    test_instance.test_enhanced_add_products_pydantic2()
    test_instance.test_pydantic2_to_json_safe_dict()
    test_instance.test_pydantic2_model_validation()
    test_instance.test_pydantic2_serialization_modes()
    test_instance.test_metadata_preservation_pydantic2()
    test_instance.test_pydantic2_complex_nested_data()
    
    print("🎉 All Pydantic 2.x tests completed successfully!")
    print()
    print("Run with pytest:")
    print("pytest tests/tests_api_Version24_02_pydantic2-ok.py -v --tb=short")