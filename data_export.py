# data_export.py

from product_schema import Product, ApiResponse
from models import StandardizedProduct
from converters import standardized_to_product

def export_products(products: list[StandardizedProduct]) -> ApiResponse:
    """
    Export standardized products to external API schema.
    1. Convert to Product.
    2. Package as ApiResponse for output.
    """
    products_external = [standardized_to_product(p) for p in products]
    return ApiResponse(__root__=products_external)