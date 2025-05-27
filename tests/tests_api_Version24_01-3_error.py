"""
ERROR :103: in <module> def enhanced_add_products(self, products: List[StandardizedProduct]):
NameError: name 'StandardizedProduct' is not defined 
ERROR tests_api_Version24_1_error.py - NameError: name 'StandardizedProduct' is not defined
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

# === JSON-SAFE UTILITY FUNCTIONS ===

def json_safe_float(value: Optional[float]) -> Optional[Union[float, str]]:
    """Convert float to JSON-safe value with advanced protection"""
    if value is None:
        return None
    if isinstance(value, float):
        if math.isinf(value):
            return 999999.0 if value > 0 else -999999.0
        if math.isnan(value):
            return None
    return value

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
    
    # Fallback serializer for any remaining edge cases
    def json_serializer(obj):
        if isinstance(obj, float):
            if math.isinf(obj):
                return 999999.0 if obj > 0 else -999999.0
            if math.isnan(obj):
                return None
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    
    return json.dumps(obj, default=json_serializer, **kwargs)

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
    """Mock database with JSON safety enhancements"""
    
    def __init__(self):
        self.products = []
        self.call_count = 0

    def enhanced_add_products(self, products: List[StandardizedProduct]):
        """Add products with complete JSON safety"""
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
                        safe_product_data[attr] = json_safe_float(value)
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
        
        self.products.extend(safe_products)
        print(f"📦 Added {len(products)} fully JSON-safe products. Total: {len(self.products)}")

    def enhanced_get_all_products(self) -> List[Dict[str, Any]]:
        """Get products with guaranteed JSON safety"""
        self.call_count += 1
        result = []
        
        for product in self.products:
            if hasattr(product, 'to_json_safe_dict'):
                # Use enhanced method
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

            # Final safety verification - ensure no inf values can slip through
            result.append(json_safe_dict(product_dict))
        
        return result

# === API ENDPOINT ENHANCED SAFETY ===

def create_enhanced_search_endpoint(app):
    """Create API endpoint with multiple layers of JSON safety"""
    @app.get("/search")
    async def search_endpoint(
        product_type: Optional[str] = None,
        provider: Optional[str] = None,
        available_only: bool = False
    ):
        try:
            # Mock search functionality for testing
            db = JsonSafeMockDatabase()
            
            # Add test products with potentially problematic values
            test_products = [
                StandardizedProduct(
                    source_url="https://example.com/product1",
                    category="electricity_plan",
                    name="Test Product 1",
                    provider_name="Test Provider",
                    price_kwh=float('inf'),  # Problematic value
                    available=True
                ),
                StandardizedProduct(
                    source_url="https://example.com/product2",
                    category="mobile_plan",
                    name="Test Product 2",
                    provider_name="Test Provider",
                    data_gb=float('nan'),  # Problematic value
                    available=True
                )
            ]
            
            db.enhanced_add_products(test_products)
            results = db.enhanced_get_all_products()
            
            # Triple JSON safety layers:
            # 1. Convert to safe dictionaries again
            safe_results = json_safe_list(results)
            
            # 2. Use enhanced safe dumps
            json_str = safe_json_dumps(safe_results)
            
            # 3. Parse and return as validated JSON
            return json.loads(json_str)
            
        except Exception as e:
            print(f"❌ API Error: {e}")
            return {"error": str(e), "results": []}
    
    return search_endpoint

# === TEST CLASS ===

class TestJsonSafetyAPI:
    """Test class for JSON safety functionality"""
    
    def test_enhanced_add_products(self):
        """Test the enhanced add products functionality"""
        db = JsonSafeMockDatabase()
        
        # Create test products with problematic float values
        products = [
            StandardizedProduct(
                source_url="https://example.com/test1",
                category="electricity_plan",
                name="Test Product with Inf",
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
        
        # Verify JSON safety
        all_products = db.enhanced_get_all_products()
        json_str = safe_json_dumps(all_products)
        
        # Should not contain 'inf' or 'nan' strings
        assert 'inf' not in json_str.lower()
        assert 'nan' not in json_str.lower()
        
        print("✅ Enhanced add products test passed")

    def test_json_safe_utilities(self):
        """Test JSON safety utility functions"""
        # Test json_safe_float
        assert json_safe_float(None) is None
        assert json_safe_float(25.5) == 25.5
        assert json_safe_float(float('inf')) == 999999.0
        assert json_safe_float(float('-inf')) == -999999.0
        assert json_safe_float(float('nan')) is None
        
        # Test json_safe_dict
        test_dict = {
            "normal": 25.5,
            "infinite": float('inf'),
            "negative_inf": float('-inf'),
            "not_a_number": float('nan'),
            "nested": {"inner_inf": float('inf')}
        }
        
        safe_dict = json_safe_dict(test_dict)
        json_str = safe_json_dumps(safe_dict)
        
        # Verify no problematic values in JSON
        assert 'inf' not in json_str.lower()
        assert 'nan' not in json_str.lower()
        
        print("✅ JSON safe utilities test passed")

    def test_standardized_product_to_json_safe_dict(self):
        """Test StandardizedProduct JSON conversion"""
        product = StandardizedProduct(
            source_url="https://example.com/test",
            category="electricity_plan",
            name="Test Product",
            provider_name="Test Provider",
            price_kwh=float('inf'),
            standing_charge=float('nan'),
            available=True,
            raw_data={"test_inf": float('inf')}
        )
        
        safe_dict = product.to_json_safe_dict()
        json_str = safe_json_dumps(safe_dict)
        
        # Verify conversion worked
        assert 'inf' not in json_str.lower()
        assert 'nan' not in json_str.lower()
        assert safe_dict['price_kwh'] == 999999.0
        assert safe_dict['standing_charge'] is None
        
        print("✅ StandardizedProduct JSON conversion test passed")

# === PYTEST CONFIGURATION ===

# Configure pytest for async mode
pytest_plugins = ['pytest_asyncio']

# === INTEGRATION INSTRUCTIONS ===
"""
To integrate this solution:

1. The file now includes a complete StandardizedProduct definition
2. All utility functions are enhanced with proper JSON safety
3. Mock database class is included for testing
4. Test class provides comprehensive testing functionality
5. Pytest configuration is properly set up

Run with: pytest tests_api_Version24-1_error.py -v --asyncio-mode=auto

All tests should now pass without NameError.
"""