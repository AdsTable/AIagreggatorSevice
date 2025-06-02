# AI Aggregator Service – Data Model Integration Guide

## Overview

This project is designed to **aggregate, standardize, and compare various product offers** (e.g., electricity, mobile, internet plans) collected from diverse sources (AI-powered extraction, API, file import, manual entry).

**Key principle:**  
- Internal operations use a single canonical model (`StandardizedProduct`).
- API/data import/export uses a dedicated schema (`Product`/`ApiResponse` from `product_schema.py`).

---

## 1. Models and Their Zones of Application

### Internal Model (`models.py`)

#### `StandardizedProduct`
- **Usage:**  
  - All core business logic (parsing, search, analytics, storage, DB ORM).
  - Results of data parsing (AI, scraping, manual entry).
  - All FastAPI endpoints for search, internal manipulation, and business features.
- **Do NOT use** for: direct API import, raw JSON upload, or export to third-party clients.

#### Example:
```python
class StandardizedProduct(BaseModel):
    """
    Canonical internal product model.
    Used for parsing, storage, search, analytics, and all business logic.
    Never use for direct API import/export; convert external data first.
    """
    # fields...
```

---

### External API Model (`product_schema.py`)

#### `Product`, `ApiResponse`
- **Usage:**  
  - Validation and parsing of external data from APIs, JSON, bulk file uploads.
  - Exporting data to external consumers (API clients, partners, etc).
- **All fields that can be missing in external data MUST be Optional.**
- **Never use for internal logic or as DB models.**

#### Example:
```python
class Product(BaseModel):
    """
    External product schema.
    Use ONLY for validating/importing/exporting data from/to API, JSON, or files.
    Fields that may be missing are Optional.
    Never use for internal logic, storage, or search.
    """
    # fields...
```

---

## 2. Typical Data Flow

1. **Import from API/JSON/file:**
   - Validate with `ApiResponse` (`product_schema.py`)
   - Convert each `Product` to `StandardizedProduct`
   - Store/process as internal product

2. **Parsing (AI, scraping, manual):**
   - Directly create `StandardizedProduct`

3. **Export to external clients:**
   - Convert `StandardizedProduct` → `Product`
   - Use `ApiResponse` to serialize list for output

---

## 3. Explicit Conversion Functions

```python name=converters.py
from product_schema import Product
from models import StandardizedProduct

def product_to_standardized(p: Product) -> StandardizedProduct:
    """
    Convert external Product (API/file) to canonical internal StandardizedProduct.
    Only call after API validation.
    """
    raw_data = p.raw_data.__root__ if hasattr(p.raw_data, "__root__") else {}
    return StandardizedProduct(
        category=p.category,
        source_url=str(p.source_url),
        provider_name=p.provider_name,
        product_id=p.product_id,
        name=p.name,
        description=p.description,
        contract_duration_months=p.contract_duration_months,
        available=p.available,
        price_kwh=p.price_kwh,
        standing_charge=p.standing_charge,
        contract_type=p.contract_type,
        monthly_cost=p.monthly_cost,
        data_gb=p.data_gb,
        calls=p.calls,
        texts=p.texts,
        network_type=p.network_type,
        download_speed=p.download_speed,
        upload_speed=p.upload_speed,
        connection_type=p.connection_type,
        data_cap_gb=p.data_cap_gb,
        internet_monthly_cost=getattr(p, "internet_monthly_cost", None),
        raw_data=raw_data
    )

def standardized_to_product(sp: StandardizedProduct) -> Product:
    """
    Convert internal StandardizedProduct to external Product for export.
    """
    from product_schema import RawData
    return Product(
        category=sp.category,
        source_url=sp.source_url,
        provider_name=sp.provider_name,
        product_id=sp.product_id,
        name=sp.name,
        description=sp.description,
        contract_duration_months=sp.contract_duration_months,
        available=sp.available,
        price_kwh=sp.price_kwh,
        standing_charge=sp.standing_charge,
        contract_type=sp.contract_type,
        monthly_cost=sp.monthly_cost,
        data_gb=sp.data_gb,
        calls=sp.calls,
        texts=sp.texts,
        network_type=sp.network_type,
        download_speed=sp.download_speed,
        upload_speed=sp.upload_speed,
        connection_type=sp.connection_type,
        data_cap_gb=sp.data_cap_gb,
        internet_monthly_cost=getattr(sp, "internet_monthly_cost", None),
        raw_data=RawData(__root__=sp.raw_data if sp.raw_data else {})
    )
```

---

## 4. Sample Endpoint Usage

```python name=main.py
from fastapi import FastAPI, HTTPException
from typing import List
from product_schema import Product, ApiResponse
from models import StandardizedProduct
from converters import product_to_standardized, standardized_to_product

app = FastAPI()
internal_db: List[StandardizedProduct] = []

@app.post("/products/import", response_model=ApiResponse)
async def import_products(raw_json: str):
    """
    Import products from external API/file.
    1. Validate using external API schema.
    2. Convert to internal product.
    3. Store in internal DB.
    """
    try:
        api_response = ApiResponse.parse_raw(raw_json)
        for p in api_response.__root__:
            internal_db.append(product_to_standardized(p))
        return api_response
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

@app.get("/products", response_model=List[StandardizedProduct])
async def list_products():
    """
    Return products in internal canonical format.
    """
    return internal_db

@app.get("/products/export", response_model=ApiResponse)
async def export_products():
    """
    Export all internal products as API response.
    """
    products = [standardized_to_product(p) for p in internal_db]
    return ApiResponse(__root__=products)
```

---

## 5. Example: product_schema.py (all Optionals for possibly missing fields)

```python name=product_schema.py
from pydantic import BaseModel, HttpUrl
from typing import List, Dict, Optional, Any

class RawData(BaseModel):
    __root__: Dict[str, Any]

class Product(BaseModel):
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

class ApiResponse(BaseModel):
    __root__: List[Product]
```

---

## 6. Best Practices

- **Document model use in code via docstrings and comments.**
- **Convert data explicitly between external and internal models at system boundaries.**
- **Mark all potentially missing fields as Optional in external schema.**
- **Keep all internal operations (search, storage, analytics) on StandardizedProduct.**
- **Never use external models for business logic or DB storage.**
- **Validate all incoming data via external schema before converting.**

---

## Summary Table

| Scenario                        | Model Used           | File                | Notes                                  |
|----------------------------------|----------------------|---------------------|----------------------------------------|
| Parsing (AI, file, manual)       | StandardizedProduct  | models.py           | Internal canonical model               |
| Internal search/storage          | StandardizedProduct  | models.py           | Only one model in business logic       |
| API/file import                  | Product, ApiResponse | product_schema.py   | For validation, then convert           |
| API/file export                  | Product, ApiResponse | product_schema.py   | Convert from internal model            |
| Conversion logic                 | -                    | converters.py       | Functions for both directions          |

---