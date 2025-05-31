# data_import.py

from product_schema import ApiResponse
from models import StandardizedProduct
from converters import product_to_standardized

def import_products(raw_json: str) -> list[StandardizedProduct]:
    """
    Import products from external JSON (API or file).
    1. Validate with external schema (ApiResponse).
    2. Convert to internal StandardizedProduct.
    """
    api_response = ApiResponse.parse_raw(raw_json)
    standardized = [product_to_standardized(p) for p in api_response.__root__]
    return standardized