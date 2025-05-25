# models.py
from typing import Optional, Dict, Any
from sqlmodel import Field, SQLModel
from pydantic import BaseModel
from sqlalchemy import Column, JSON # Import Column and JSON
import math # Import math for infinity handling if needed in logic, though pydantic handles inf

# Define the StandardizedProduct Pydantic model
class StandardizedProduct(BaseModel):
    """
    Standardized data model for a product.
    This model defines the consistent structure for products from different sources.
    """
    # Core fields (applicable to most/all product types)
    category: str  # e.g., "electricity_plan", "mobile_plan", "internet_plan"
    source_url: str # URL of the product page (Adding this as it's expected in tests)
    provider_name: Optional[str] = None
    product_id: Optional[str] = None # Unique ID from the provider or generated
    name: Optional[str] = None
    description: Optional[str] = None # Optional description of the product
    contract_duration_months: Optional[int] = None # Contract duration in months
    available: bool = True # Whether the product is currently available

    # Fields for electricity plans
    price_kwh: Optional[float] = None # Price per kilowatt-hour
    standing_charge: Optional[float] = None # Daily or monthly standing charge
    contract_type: Optional[str] = None # e.g., "Fixed Price", "Variable"

    # Fields for mobile plans
    monthly_cost: Optional[float] = None # Monthly cost
    data_gb: Optional[float] = None # Data allowance in gigabytes (Use float to handle infinity)
    calls: Optional[float] = None # Call allowance (Use float to handle infinity)
    texts: Optional[float] = None # Text allowance (Use float to handle infinity)
    network_type: Optional[str] = None # e.g., "4G", "5G"

    # Fields for internet plans
    download_speed: Optional[float] = None # Download speed in Mbps
    upload_speed: Optional[float] = None # Upload speed in Mbps
    connection_type: Optional[str] = None # e.g., "Fiber", "DSL", "Cable"
    data_cap_gb: Optional[float] = None # Data cap in gigabytes (Use float to handle infinity)
    internet_monthly_cost: Optional[float] = None # Monthly cost for internet (if different from generic monthly_cost)

    # Add fields for other product types as needed
    # ...

    # Field to store the original raw data (optional, but useful for debugging)
    # Use default_factory=dict for a mutable default, although Pydantic handles it well
    raw_data: Dict[str, Any]


# Define the ProductDB SQLModel (for database storage)
class ProductDB(SQLModel, table=True):
    """
    Database model for a product. Inherits from StandardizedProduct for fields.
    """
    id: Optional[int] = Field(default=None, primary_key=True) # Auto-incrementing primary key

    # Fields from StandardizedProduct
    category: str = Field(index=True)
    source_url: str = Field(index=True) # Add to DB model
    provider_name: Optional[str] = Field(default=None, index=True)
    product_id: Optional[str] = Field(default=None, index=True)
    name: Optional[str] = None
    description: Optional[str] = None
    contract_duration_months: Optional[int] = Field(default=None, index=True)
    available: bool = Field(default=True)

    # Fields for electricity plans
    price_kwh: Optional[float] = Field(default=None, index=True)
    standing_charge: Optional[float] = Field(default=None) # Add to DB model
    contract_type: Optional[str] = Field(default=None, index=True) # Add to DB model

    # Fields for mobile plans
    monthly_cost: Optional[float] = Field(default=None, index=True)
    data_gb: Optional[float] = Field(default=None, index=True) # Add to DB model
    calls: Optional[float] = Field(default=None) # Add to DB model
    texts: Optional[float] = Field(default=None) # Add to DB model
    network_type: Optional[str] = Field(default=None, index=True) # Add to DB model

    # Fields for internet plans
    download_speed: Optional[float] = Field(default=None, index=True) # Add to DB model
    upload_speed: Optional[float] = Field(default=None) # Add to DB model
    connection_type: Optional[str] = Field(default=None, index=True) # Add to DB model
    data_cap_gb: Optional[float] = Field(default=None, index=True) # Add to DB model
    internet_monthly_cost: Optional[float] = Field(default=None, index=True) # Add to DB model if used

    # raw_data is stored as a JSON string in the database using SQLAlchemy's JSON type
    raw_data_json: Dict[str, Any] = Field(default_factory=dict, sa_column=Column("raw_data", JSON))

# Helper function to create a ProductDB instance from a StandardizedProduct instance
def create_product_db_from_standardized(product: StandardizedProduct) -> ProductDB:
    """
    Converts a StandardizedProduct Pydantic model to a ProductDB SQLModel.
    Handles the conversion of raw_data dictionary.
    """
    # SQLAlchemy's JSON type handles the dictionary directly
    return ProductDB(
        category=product.category,
        source_url=product.source_url, # Add mapping
        provider_name=product.provider_name,
        product_id=product.product_id,
        name=product.name,
        description=product.description,
        contract_duration_months=product.contract_duration_months,
        available=product.available,

        # Map category-specific fields
        price_kwh=product.price_kwh,
        standing_charge=product.standing_charge, # Add mapping
        contract_type=product.contract_type, # Add mapping

        monthly_cost=product.monthly_cost, # This field is generic, but also used for mobile
        data_gb=product.data_gb, # Add mapping
        calls=product.calls, # Add mapping
        texts=product.texts, # Add mapping
        network_type=product.network_type, # Add mapping

        download_speed=product.download_speed, # Add mapping
        upload_speed=product.upload_speed, # Add mapping
        connection_type=product.connection_type, # Add mapping
        data_cap_gb=product.data_cap_gb, # Add mapping
        internet_monthly_cost=product.internet_monthly_cost, # Add mapping if used

        raw_data_json=product.raw_data # Map raw_data from StandardizedProduct to raw_data_json in ProductDB
    )
