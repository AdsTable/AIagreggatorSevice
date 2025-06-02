# product_schema.py
from pydantic import BaseModel, HttpUrl, RootModel, ValidationError
from typing import List, Dict, Optional, Any, AsyncGenerator

class RawData(RootModel[Dict[str, Any]]):
    """Root model for raw_data - a dictionary with arbitrary keys and values."""
    pass

class Product(BaseModel):
    """
    External product schema.
    Use ONLY for validating/importing/exporting data from/to API, JSON, or files.
    Fields that may be missing are Optional.
    Never use for internal logic, storage, or search.
    """
    category: str
    source_url: HttpUrl
    provider_name: str
    product_id: str
    name: str
    description: Optional[str] = None
    contract_duration_months: Optional[int] = None
    available: bool
    price_kwh: Optional[float] = None
    standing_charge: Optional[float] = None
    contract_type: Optional[str] = None
    monthly_cost: Optional[float] = None
    data_gb: Optional[float] = None
    calls: Optional[float] = None
    texts: Optional[float] = None
    network_type: Optional[str] = None
    download_speed: Optional[float] = None
    upload_speed: Optional[float] = None
    connection_type: Optional[str] = None
    data_cap_gb: Optional[float] = None
    internet_monthly_cost: Optional[float] = None
    raw_data: RawData

class ApiResponse(RootModel[List[Product]]):
    """Root model for API responses with a list of products."""
    pass    

# Usage example:
if __name__ == "__main__":
    import json

    raw_json = '''
    [
     {
        "category": "electricity_plan",
        "source_url": "https://example.com/plan",
        "provider_name": "Provider",
        "product_id": "prd-123",
        "name": "Best Plan",
        "description": "Great for everyone",
        "contract_duration_months": 12,
        "available": true,
        "price_kwh": 0.15,
        "standing_charge": 5.0,
        "contract_type": "fixed",
        "monthly_cost": 30.0,
        "data_gb": 100,
        "calls": 999,
        "texts": 1000,
        "network_type": "4G",
        "download_speed": 100,
        "upload_speed": 50,
        "connection_type": "fiber",
        "data_cap_gb": 500,
        "internet_monthly_cost": 0,
        "raw_data": {"additionalProp1": {"nested": "value"}}
      }
    ]
    '''
    try:
        # Note: Since ApiResponse is a RootModel[List[Product]], you can parse a JSON array directly
        response = ApiResponse.model_validate_json(raw_json)
        products = response.root
        for product in products:
            print(product.name, product.price_kwh)
    except ValidationError as e:
        print("Validation error:", e)