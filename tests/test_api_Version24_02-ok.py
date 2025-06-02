"""
Enhanced JSON-safe testing with improved infinity/NaN handling
Fixed: NameError for StandardizedProduct and improved test logic
"""

import math
import json
import pytest
from typing import List, Optional, Dict, Any, Union
from dataclasses import dataclass, field

# === STANDARDIZED PRODUCT MODEL ===

@dataclass
class StandardizedProduct:
    """JSON-safe StandardizedProduct for standalone testing"""
    source_url: str
    category: str
    name: str
    provider_name: str = ""
    product_id: Optional[str] = None
    description: Optional[str] = None
    
    # Electricity fields
    price_kwh: Optional[float] = None
    standing_charge: Optional[float] = None
    contract_type: Optional[str] = None
    
    # Mobile/Internet fields
    monthly_cost: Optional[float] = None
    contract_duration_months: Optional[int] = None
    data_gb: Optional[float] = None
    calls: Optional[float] = None
    texts: Optional[float] = None
    network_type: Optional[str] = None
    
    # Internet specific
    download_speed: Optional[float] = None
    upload_speed: Optional[float] = None
    connection_type: Optional[str] = None
    data_cap_gb: Optional[float] = None
    
    # Common fields
    available: bool = True
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def to_json_safe_dict(self) -> Dict[str, Any]:
        """Convert to JSON-safe dictionary"""
        return enhanced_to_json_safe_dict(self)

# === ENHANCED JSON-SAFE UTILITY FUNCTIONS ===

class SafeNumericValue:
    """Wrapper for tracking replaced infinity/NaN values"""
    def __init__(self, original_type: str, safe_value: Any):
        self.original_type = original_type  # 'inf', '-inf', 'nan'
        self.safe_value = safe_value
    
    def __str__(self):
        return str(self.safe_value)
    
    def __repr__(self):
        return f"SafeNumericValue({self.original_type}, {self.safe_value})"

def json_safe_float(value: Optional[float]) -> Optional[Union[float, None]]:
    """
    Convert float to JSON-safe value with enhanced protection
    Returns None for all problematic values to avoid string conflicts
    """
    if value is None:
        return None
    if isinstance(value, float):
        if math.isinf(value):
            # Return None instead of numeric replacement to avoid 'inf' in strings
            return None
        if math.isnan(value):
            return None
    return value

def json_safe_float_with_metadata(value: Optional[float]) -> Dict[str, Any]:
    """
    Enhanced version that preserves metadata about replacements
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

def json_safe_list(data: List[Any]) -> List[Any]:
    """Convert list to JSON-safe format with recursive protection"""
    if not isinstance(data, list):
        return []
    
    result = []
    for item in data:
        if isinstance(item, float):
            result.append(json_safe_float(item))
        elif isinstance(item, dict):
            result.append(json_safe_dict(item))
        elif isinstance(item, list):
            result.append(json_safe_list(item))
        else:
            result.append(item)
    return result

def json_safe_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert dictionary to JSON-safe format with recursive protection"""
    if not isinstance(data, dict):
        return {}
    
    result = {}
    for key, value in data.items():
        if isinstance(value, float):
            result[key] = json_safe_float(value)
        elif isinstance(value, dict):
            result[key] = json_safe_dict(value)
        elif isinstance(value, list):
            result[key] = json_safe_list(value)
        else:
            result[key] = value
    return result

def safe_json_dumps(obj: Any, **kwargs) -> str:
    """Enhanced JSON dumps with complete protection"""
    # Apply recursive safety conversion first
    if isinstance(obj, dict):
        obj = json_safe_dict(obj)
    elif isinstance(obj, list):
        obj = json_safe_list(obj)
    
    # Enhanced fallback serializer
    def json_serializer(obj):
        if isinstance(obj, float):
            if math.isinf(obj) or math.isnan(obj):
                return None  # Convert to null instead of string
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    
    return json.dumps(obj, default=json_serializer, **kwargs)

def validate_json_safety(json_str: str) -> Dict[str, Any]:
    """
    Comprehensive validation of JSON safety
    Returns analysis instead of simple boolean check
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

# === ENHANCED StandardizedProduct METHODS ===

def enhanced_to_json_safe_dict(product) -> Dict[str, Any]:
    """JSON-safe dictionary conversion for StandardizedProduct"""
    data = {}
    
    # Process all relevant fields with JSON safety
    for field_name in ['source_url', 'category', 'name', 'provider_name', 'product_id', 
                      'description', 'price_kwh', 'standing_charge', 'contract_type',
                      'monthly_cost', 'contract_duration_months', 'data_gb', 'calls',
                      'texts', 'network_type', 'download_speed', 'upload_speed',
                      'connection_type', 'data_cap_gb', 'available', 'raw_data']:
        if hasattr(product, field_name):
            value = getattr(product, field_name)
            if isinstance(value, float):
                data[field_name] = json_safe_float(value)
            elif isinstance(value, dict):
                data[field_name] = json_safe_dict(value)
            elif isinstance(value, list):
                data[field_name] = json_safe_list(value)
            else:
                data[field_name] = value
    return data

# === MOCK DATABASE CLASS ===

class JsonSafeMockDatabase:
    """Mock database with enhanced JSON safety"""
    
    def __init__(self):
        self.products = []
        self.call_count = 0
        self.replacement_stats = {
            "infinity_replaced": 0,
            "nan_replaced": 0,
            "total_processed": 0
        }

    def enhanced_add_products(self, products: List[StandardizedProduct]):
        """Add products with complete JSON safety and statistics tracking"""
        safe_products = []
        
        for product in products:
            # Create completely safe product data
            safe_product_data = {}
            
            for attr in ['source_url', 'category', 'name', 'provider_name', 
                         'product_id', 'description', 'price_kwh', 'standing_charge', 
                         'contract_type', 'monthly_cost', 'contract_duration_months', 
                         'data_gb', 'calls', 'texts', 'network_type', 'download_speed', 
                         'upload_speed', 'connection_type', 'data_cap_gb', 'available']:
                if hasattr(product, attr):
                    value = getattr(product, attr)
                    if isinstance(value, float):
                        original_value = value
                        safe_value = json_safe_float(value)
                        
                        # Track replacements
                        if original_value != safe_value:
                            if math.isinf(original_value):
                                self.replacement_stats["infinity_replaced"] += 1
                            elif math.isnan(original_value):
                                self.replacement_stats["nan_replaced"] += 1
                        
                        safe_product_data[attr] = safe_value
                    else:
                        safe_product_data[attr] = value
            
            # Handle raw_data separately with deep safety
            if hasattr(product, 'raw_data'):
                safe_product_data['raw_data'] = json_safe_dict(product.raw_data)
            else:
                safe_product_data['raw_data'] = {}
            
            # Create new safe product
            safe_product = StandardizedProduct(**safe_product_data)
            safe_products.append(safe_product)
            self.replacement_stats["total_processed"] += 1
        
        self.products.extend(safe_products)
        print(f"📦 Added {len(products)} JSON-safe products. "
              f"Replaced: {self.replacement_stats['infinity_replaced']} inf, "
              f"{self.replacement_stats['nan_replaced']} NaN values")

    def enhanced_get_all_products(self) -> List[Dict[str, Any]]:
        """Get products with guaranteed JSON safety"""
        self.call_count += 1
        result = []
        
        for product in self.products:
            if hasattr(product, 'to_json_safe_dict'):
                product_dict = product.to_json_safe_dict()
            else:
                # Fallback manual safe conversion
                product_dict = {
                    'source_url': product.source_url,
                    'category': product.category,
                    'name': product.name,
                    'provider_name': product.provider_name,
                    'available': getattr(product, 'available', True)
                }
                for attr in ['price_kwh', 'data_gb', 'calls', 'texts', 'monthly_cost']:
                    value = getattr(product, attr, None)
                    product_dict[attr] = json_safe_float(value) if isinstance(value, float) else value

            # Final safety verification
            result.append(json_safe_dict(product_dict))
        
        return result

# === TEST CLASS ===

class TestJsonSafetyAPI:
    """Enhanced test class with proper validation logic"""
    
    def test_enhanced_add_products(self):
        """Test the enhanced add products functionality with proper validation"""
        db = JsonSafeMockDatabase()
        
        # Create test products with problematic float values
        products = [
            StandardizedProduct(
                source_url="https://example.com/test1",
                category="electricity_plan",
                name="Test Product with Infinity",
                provider_name="Test Provider",
                price_kwh=float('inf'),
                standing_charge=float('-inf'),
                available=True
            ),
            StandardizedProduct(
                source_url="https://example.com/test2",
                category="mobile_plan",
                name="Test Product with NaN",
                provider_name="Test Provider",
                data_gb=float('nan'),
                monthly_cost=25.99,
                available=True
            )
        ]
        
        # Add products using enhanced method
        db.enhanced_add_products(products)
        
        # Verify products were added
        assert len(db.products) == 2
        
        # Verify replacement statistics
        assert db.replacement_stats["infinity_replaced"] == 2  # +inf and -inf
        assert db.replacement_stats["nan_replaced"] == 1
        assert db.replacement_stats["total_processed"] == 2
        
        # Get products and validate JSON safety
        all_products = db.enhanced_get_all_products()
        json_str = safe_json_dumps(all_products)
        
        # Use enhanced validation instead of simple string check
        safety_analysis = validate_json_safety(json_str)
        
        assert safety_analysis["is_safe"], f"JSON safety issues: {safety_analysis['issues']}"
        assert not safety_analysis["has_infinity"], "JSON contains infinity values"
        assert not safety_analysis["has_nan"], "JSON contains NaN values"
        assert safety_analysis["can_parse"], "JSON cannot be parsed"
        
        print(f"✅ Enhanced add products test passed. Safety analysis: {safety_analysis}")

    def test_json_safe_utilities(self):
        """Test JSON safety utility functions with enhanced validation"""
        # Test json_safe_float
        assert json_safe_float(None) is None
        assert json_safe_float(25.5) == 25.5
        assert json_safe_float(float('inf')) is None  # Now returns None
        assert json_safe_float(float('-inf')) is None  # Now returns None
        assert json_safe_float(float('nan')) is None
        
        # Test json_safe_dict with problematic values
        test_dict = {
            "normal": 25.5,
            "infinite": float('inf'),
            "negative_inf": float('-inf'),
            "not_a_number": float('nan'),
            "nested": {"inner_inf": float('inf')},
            "text": "This contains the word infinity but should be fine"
        }
        
        safe_dict = json_safe_dict(test_dict)
        json_str = safe_json_dumps(safe_dict)
        
        # Use enhanced validation
        safety_analysis = validate_json_safety(json_str)
        
        assert safety_analysis["is_safe"], f"JSON safety issues: {safety_analysis['issues']}"
        assert not safety_analysis["has_infinity"], "Processed dict contains infinity values"
        assert not safety_analysis["has_nan"], "Processed dict contains NaN values"
        
        # Verify specific replacements
        assert safe_dict["infinite"] is None
        assert safe_dict["negative_inf"] is None
        assert safe_dict["not_a_number"] is None
        assert safe_dict["nested"]["inner_inf"] is None
        assert safe_dict["text"] == "This contains the word infinity but should be fine"  # Text should be preserved
        
        print(f"✅ JSON safe utilities test passed. Analysis: {safety_analysis}")

    def test_standardized_product_to_json_safe_dict(self):
        """Test StandardizedProduct JSON conversion with enhanced validation"""
        product = StandardizedProduct(
            source_url="https://example.com/test",
            category="electricity_plan",
            name="Test Product",
            provider_name="Test Provider",
            price_kwh=float('inf'),
            standing_charge=float('nan'),
            available=True,
            raw_data={"test_infinity": float('inf'), "normal_value": 42.0}
        )
        
        safe_dict = product.to_json_safe_dict()
        json_str = safe_json_dumps(safe_dict)
        
        # Use enhanced validation
        safety_analysis = validate_json_safety(json_str)
        
        assert safety_analysis["is_safe"], f"JSON safety issues: {safety_analysis['issues']}"
        assert not safety_analysis["has_infinity"], "Product dict contains infinity values"
        assert not safety_analysis["has_nan"], "Product dict contains NaN values"
        
        # Verify specific conversions
        assert safe_dict['price_kwh'] is None  # inf -> None
        assert safe_dict['standing_charge'] is None  # nan -> None
        assert safe_dict['raw_data']['test_infinity'] is None  # nested inf -> None
        assert safe_dict['raw_data']['normal_value'] == 42.0  # normal value preserved
        
        print(f"✅ StandardizedProduct JSON conversion test passed. Analysis: {safety_analysis}")

    def test_metadata_preservation(self):
        """Test enhanced float processing with metadata"""
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
        
        print("✅ Metadata preservation test passed")

# === PYTEST CONFIGURATION ===
pytest_plugins = ['pytest_asyncio']

if __name__ == "__main__":
    # Run tests directly if needed
    test_instance = TestJsonSafetyAPI()
    test_instance.test_enhanced_add_products()
    test_instance.test_json_safe_utilities()
    test_instance.test_standardized_product_to_json_safe_dict()
    test_instance.test_metadata_preservation()
    print("🎉 All tests completed successfully!")