# models.py
from typing import Optional, Dict, Any
from sqlmodel import Field, SQLModel
from pydantic import BaseModel, ConfigDict, Field as PydanticField, field_validator, field_serializer
from sqlalchemy import Column, JSON
import math


class StandardizedProduct(BaseModel):
    """
    Standardized data model for a product using Pydantic 2.x.
    This model defines the consistent structure for products from different sources.
    """
    # Core fields (applicable to most/all product types)
    category: str = PydanticField(..., description="Product category (e.g., 'electricity_plan', 'mobile_plan')")
    source_url: str = PydanticField(..., description="URL of the product page")
    provider_name: Optional[str] = PydanticField(None, description="Provider or company name")
    product_id: Optional[str] = PydanticField(None, description="Unique ID from the provider or generated")
    name: Optional[str] = PydanticField(None, description="Product name")
    description: Optional[str] = PydanticField(None, description="Product description")
    contract_duration_months: Optional[int] = PydanticField(None, ge=0, description="Contract duration in months")
    available: bool = PydanticField(True, description="Whether the product is currently available")

    # Fields for electricity plans
    price_kwh: Optional[float] = PydanticField(None, ge=0, description="Price per kilowatt-hour")
    standing_charge: Optional[float] = PydanticField(None, ge=0, description="Daily or monthly standing charge")
    contract_type: Optional[str] = PydanticField(None, description="Contract type (e.g., 'Fixed Price', 'Variable')")

    # Fields for mobile plans
    monthly_cost: Optional[float] = PydanticField(None, ge=0, description="Monthly cost")
    data_gb: Optional[float] = PydanticField(None, ge=0, description="Data allowance in gigabytes")
    calls: Optional[float] = PydanticField(None, ge=0, description="Call allowance (use float for infinity)")
    texts: Optional[float] = PydanticField(None, ge=0, description="Text allowance (use float for infinity)")
    network_type: Optional[str] = PydanticField(None, description="Network type (e.g., '4G', '5G')")

    # Fields for internet plans
    download_speed: Optional[float] = PydanticField(None, ge=0, description="Download speed in Mbps")
    upload_speed: Optional[float] = PydanticField(None, ge=0, description="Upload speed in Mbps")
    connection_type: Optional[str] = PydanticField(None, description="Connection type (e.g., 'Fiber', 'DSL', 'Cable')")
    data_cap_gb: Optional[float] = PydanticField(None, ge=0, description="Data cap in gigabytes")
    internet_monthly_cost: Optional[float] = PydanticField(None, ge=0, description="Monthly cost for internet")

    # Field to store the original raw data
    raw_data: Dict[str, Any] = PydanticField(default_factory=dict, description="Original raw data for debugging")

    # Pydantic 2.x configuration
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        validate_default=True,
        frozen=False
    )

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        """Validate that category is one of allowed values."""
        allowed_categories = ["electricity_plan", "mobile_plan", "internet_plan"]
        if v not in allowed_categories:
            raise ValueError(f"Category must be one of: {allowed_categories}")
        return v

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, v: str) -> str:
        """Validate that source_url is a non-empty string."""
        if not isinstance(v, str) or not v.strip():
            raise ValueError("source_url must be a non-empty string")
        return v.strip()

    @field_validator("provider_name")
    @classmethod
    def validate_provider_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate and clean provider name."""
        if v is not None and isinstance(v, str):
            return v.strip() or None
        return v

    @field_validator("contract_duration_months")
    @classmethod
    def validate_contract_duration(cls, v: Optional[int]) -> Optional[int]:
        """Validate contract duration is non-negative."""
        if v is not None and v < 0:
            raise ValueError("contract_duration_months must be non-negative")
        return v

    @field_serializer("price_kwh", "standing_charge", "monthly_cost", "data_gb", "calls", "texts", 
                     "download_speed", "upload_speed", "data_cap_gb", "internet_monthly_cost",
                     when_used="json")
    def serialize_float_fields(self, v: Optional[float]) -> Optional[float]:
        """Serialize float fields with infinity/NaN handling for JSON safety."""
        if v is None:
            return None
        if isinstance(v, float):
            if math.isinf(v):
                return 999999.0 if v > 0 else -999999.0
            if math.isnan(v):
                return None
        return v

    @field_serializer("raw_data", when_used="json")
    def serialize_raw_data(self, v: Dict[str, Any]) -> Dict[str, Any]:
        """Serialize raw_data with infinity/NaN handling for nested values."""
        def clean_value(value):
            if isinstance(value, float):
                if math.isinf(value):
                    return 999999.0 if value > 0 else -999999.0
                if math.isnan(value):
                    return None
            elif isinstance(value, dict):
                return {k: clean_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [clean_value(item) for item in value]
            return value
        
        return clean_value(v)

    def to_json_safe_dict(self) -> Dict[str, Any]:
        """
        Convert to JSON-safe dictionary using Pydantic 2.x serialization.
        Uses the field_serializer methods to handle infinity/NaN values.
        """
        return self.model_dump(mode="json")


class ProductDB(SQLModel, table=True):
    """
    Database model for a product using SQLModel with Pydantic 2.x.
    """
    id: Optional[int] = Field(default=None, primary_key=True)

    # Fields from StandardizedProduct
    category: str = Field(index=True)
    source_url: str = Field(index=True)
    provider_name: Optional[str] = Field(default=None, index=True)
    product_id: Optional[str] = Field(default=None, index=True)
    name: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None)
    contract_duration_months: Optional[int] = Field(default=None, index=True)
    available: bool = Field(default=True, index=True)

    # Fields for electricity plans
    price_kwh: Optional[float] = Field(default=None, index=True)
    standing_charge: Optional[float] = Field(default=None)
    contract_type: Optional[str] = Field(default=None, index=True)

    # Fields for mobile plans
    monthly_cost: Optional[float] = Field(default=None, index=True)
    data_gb: Optional[float] = Field(default=None, index=True)
    calls: Optional[float] = Field(default=None)
    texts: Optional[float] = Field(default=None)
    network_type: Optional[str] = Field(default=None, index=True)

    # Fields for internet plans
    download_speed: Optional[float] = Field(default=None, index=True)
    upload_speed: Optional[float] = Field(default=None)
    connection_type: Optional[str] = Field(default=None, index=True)
    data_cap_gb: Optional[float] = Field(default=None, index=True)
    internet_monthly_cost: Optional[float] = Field(default=None, index=True)

    # raw_data is stored as a JSON string in the database
    raw_data_json: Dict[str, Any] = Field(default_factory=dict, sa_column=Column("raw_data", JSON))

    def to_standardized_product(self) -> StandardizedProduct:
        """
        Converts DB model to Pydantic model using Pydantic 2.x methods.
        """
        data = self.model_dump()
        data["raw_data"] = self.raw_data_json or {}
        # Remove the DB-specific field
        data.pop("raw_data_json", None)
        data.pop("id", None)
        return StandardizedProduct(**data)


def create_product_db_from_standardized(product: StandardizedProduct) -> ProductDB:
    """
    Converts a StandardizedProduct Pydantic model to a ProductDB SQLModel.
    Uses Pydantic 2.x serialization methods.
    """
    data = product.model_dump(exclude={"raw_data"})
    return ProductDB(
        **data,
        raw_data_json=product.raw_data
    )