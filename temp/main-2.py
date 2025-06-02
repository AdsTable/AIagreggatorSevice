# main.py - exist code
from fastapi import FastAPI, HTTPException, Query, Body
from dotenv import load_dotenv
from fastapi.responses import StreamingResponse
import os, yaml, asyncio
from services.ai_async_client import AIAsyncClient

load_dotenv()

def load_ai_config(config_path="ai_integrations.yaml"):
    with open(config_path, "r") as f:
        cfg = yaml.safe_load(f)
    for provider, settings in cfg.items():
        for key, value in settings.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                env_key = value[2:-1]
                cfg[provider][key] = os.getenv(env_key)
    return cfg

ai_config = load_ai_config()
ai_client = AIAsyncClient(ai_config)

from fastapi import FastAPI, HTTPException, Query, Depends, Body
from fastapi.responses import JSONResponse
from typing import List, Dict, Any, Optional, Union
from sqlmodel import Session
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager
from pydantic import BaseModel, ConfigDict, field_validator, ValidationError

# Import functions and models from your modules
from product_schema import Product, ApiResponse
from models import StandardizedProduct, ProductDB
from database import create_db_and_tables, get_session

# Importing business logic and helpers functions
from data_discoverer import discover_and_extract_data
from data_export import export_products
from data_fetcher import fetch_product_data_from_api
from data_import import import_products as import_products_func  # alias to avoid conflict
from data_parser import parse_and_standardize
from data_search import search_and_filter_products
from data_storage import store_standardized_data
from flexible_api import safe_float_parse, safe_int_parse, search_endpoint

app = FastAPI()
fake_db: List[Product] = []

@app.post("/ai/ask")
async def ai_ask(
    prompt: str = Body(..., embed=True),
    provider: str = Query("openai", description="Provider: openai, moonshot, together, huggingface, ollama, tibber, wenxin"),
    stream: bool = Query(False, description="Enable streaming")
):
    try:
        if stream:
            async def gen():
                async for chunk in ai_client.stream(prompt, provider=provider):
                    # Пример: фильтруем только текстовые дельты (OpenAI/Moonshot - нужен json-парсинг!)
                    import json
                    try:
                        data = json.loads(chunk)
                        if 'choices' in data and 'delta' in data['choices'][0]:
                            yield data['choices'][0]['delta'].get('content', '')
                    except Exception:
                        continue
            return StreamingResponse(gen(), media_type="text/plain")
        answer = await ai_client.ask(prompt, provider=provider)
        return {"provider": provider, "prompt": prompt, "answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ai/batch")
async def ai_batch(
    prompts: list = Body(..., embed=True),
    provider: str = Query("openai", description="Provider for batch")
):
    try:
        results = await ai_client.batch(prompts, provider=provider)
        return {"provider": provider, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("shutdown")
async def shutdown_event():
    await ai_client.aclose()

def safe_float_parse(value: Optional[str]) -> Optional[float]:
    """Safely parse a string to float with error handling."""
    if value is None or value.strip() == '':
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid number format: '{value}'. Expected a valid number."
        )

def safe_int_parse(value: Optional[str]) -> Optional[int]:
    """Safely parse a string to int with error handling."""
    if value is None or value.strip() == '':
        return None
    try:
        return int(float(value))  # Allows "12.0" -> 12
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid integer format: '{value}'. Expected a valid integer."
        )

class IngestionRequest(BaseModel):
    """Request model for data ingestion using Pydantic 2.x."""
    source_identifier: str
    category: str

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True
    )

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        allowed = ["electricity_plan", "mobile_plan", "internet_plan"]
        if v not in allowed:
            raise ValueError(f"Category must be one of: {allowed}")
        return v

    @field_validator("source_identifier")
    @classmethod
    def validate_source_identifier(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("source_identifier cannot be empty")
        return v.strip()

class IngestionResponse(BaseModel):
    """Response model for data ingestion."""
    message: str
    products_stored: int = 0
    source: str

    model_config = ConfigDict(
        validate_assignment=True
    )

class SearchResponse(BaseModel):
    """Response model for search results."""
    products: List[StandardizedProduct]
    total_count: int
    filters_applied: Dict[str, Any]

    model_config = ConfigDict(
        validate_assignment=True
    )

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Application startup: Creating database tables...")
    await create_db_and_tables()
    print("Database tables created.")
    yield
    # Place any shutdown logic here if needed

app = FastAPI(
    title="AI Aggregator Service",
    description="AI-powered data aggregation service for product comparison",
    version="2.0.0",
    lifespan=lifespan
)

@app.post("/ingest_data", response_model=IngestionResponse)
async def ingest_provider_data(
    request: IngestionRequest,
    session: AsyncSession = Depends(get_session)
):
    """
    Discovers, extracts (using AI), parses, and stores product data from a source.
    Can perform web searches if the source identifier is not a direct URL or file path.
    """
    print("\n--- Starting Data Ingestion Process (AI-Assisted) ---")
    print(f"Received source identifier: {request.source_identifier}, Category: {request.category}")
    try:
        # --- Step 1: Discover and Extract Data (using enhanced AI discoverer) ---
        raw_extracted_data = discover_and_extract_data(
            source_identifier=request.source_identifier,
            category=request.category
        )
        if raw_extracted_data is None:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to discover and extract data from source: {request.source_identifier}. Check logs for details."
            )
        if not raw_extracted_data:
            print("Discovery and extraction successful, but no raw product data was extracted.")
            return IngestionResponse(
                message=f"Data ingestion completed, but no raw data was extracted from source: {request.source_identifier}. Check AI extraction logic.",
                products_stored=0,
                source=request.source_identifier
            )
        print(f"Raw data extracted from source: {request.source_identifier}.")
        # --- Step 2: Parse and Standardize ---
        standardized_data = parse_and_standardize(raw_extracted_data, category=request.category)
        if not standardized_data:
            print("No standardized data generated after parsing.")
            return IngestionResponse(
                message="Data ingestion completed, but no standardized data was generated after parsing. Check parser logic and extracted data format.",
                products_stored=0,
                source=request.source_identifier
            )
        print(f"{len(standardized_data)} products standardized.")
        # --- Step 3: Store Data ---
        await store_standardized_data(session=session, data=standardized_data)
        print("Standardized data stored.")
        print("--- Data Ingestion Process Completed ---")
        return IngestionResponse(
            message=f"Data ingestion process completed successfully from source: {request.source_identifier}. {len(standardized_data)} products stored.",
            products_stored=len(standardized_data),
            source=request.source_identifier
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Unexpected error during data ingestion: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred during data ingestion: {str(e)}"
        )

@app.get("/search", response_model=List[StandardizedProduct])
async def search_products_endpoint(
    session: AsyncSession = Depends(get_session),
    product_type: Optional[str] = Query(None, description="Filter by product type (e.g., electricity_plan, mobile_plan)"),
    min_price: Optional[str] = Query(None, description="Filter by minimum price"),
    provider: Optional[str] = Query(None, description="Filter by provider name"),
    max_data_gb: Optional[str] = Query(None, description="Filter by maximum data allowance in GB"),
    min_contract_duration_months: Optional[str] = Query(None, description="Filter by minimum contract duration in months")
):
    """
    Searches and filters aggregated product data stored in the database.
    Returns JSON-safe serialized products using Pydantic 2.x.
    """
    print("\n--- Received Search Request ---")
    # Safe type parsing
    try:
        parsed_min_price = safe_float_parse(min_price)
        parsed_max_data_gb = safe_float_parse(max_data_gb)
        parsed_min_contract_duration = safe_int_parse(min_contract_duration_months)
    except HTTPException as he:
        raise he

    print(f"Parameters: product_type={product_type}, min_price={parsed_min_price}, provider={provider}, max_data_gb={parsed_max_data_gb}, min_contract_duration_months={parsed_min_contract_duration}")

    try:
        search_results = await search_and_filter_products(
            session=session,
            product_type=product_type,
            min_price=parsed_min_price,
            provider=provider,
            max_data_gb=parsed_max_data_gb,
            min_contract_duration_months=parsed_min_contract_duration
        )
        print(f"--- Search Request Processed - Found {len(search_results)} products ---")
        return search_results
    except Exception as e:
        print(f"An error occurred during search: {e}")
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {e}")

@app.get("/search/detailed", response_model=SearchResponse)
async def search_products_detailed_endpoint(
    session: AsyncSession = Depends(get_session),
    product_type: Optional[str] = Query(None, description="Filter by product type"),
    min_price: Optional[str] = Query(None, description="Filter by minimum price"),
    provider: Optional[str] = Query(None, description="Filter by provider name"),
    max_data_gb: Optional[str] = Query(None, description="Filter by maximum data allowance in GB"),
    min_contract_duration_months: Optional[str] = Query(None, description="Filter by minimum contract duration in months")
):
    """Enhanced search endpoint with detailed response including metadata."""
    try:
        parsed_min_price = safe_float_parse(min_price)
        parsed_max_data_gb = safe_float_parse(max_data_gb)
        parsed_min_contract_duration = safe_int_parse(min_contract_duration_months)
    except HTTPException as he:
        raise he

    filters_applied = {
        "product_type": product_type,
        "min_price": parsed_min_price,
        "provider": provider,
        "max_data_gb": parsed_max_data_gb,
        "min_contract_duration_months": parsed_min_contract_duration
    }
    search_results = await search_and_filter_products(
        session=session,
        product_type=product_type,
        min_price=parsed_min_price,
        provider=provider,
        max_data_gb=parsed_max_data_gb,
        min_contract_duration_months=parsed_min_contract_duration
    )
    return SearchResponse(
        products=search_results,
        total_count=len(search_results),
        filters_applied=filters_applied
    )

# Example: storage of products in memory
fake_db: List[Product] = []

@app.get("/products", response_model=ApiResponse)
def get_products():
    # Forming the response in the form of an Api Response (Product list)
    return ApiResponse(root=fake_db)

@app.post("/products", response_model=Product)
def add_product(product: Product):
    # Automatic validation of input data via Pydantic
    fake_db.append(product)
    return product

@app.post("/products/import", response_model=ApiResponse, summary="Import products (array or single object)",
    description=(
        "Imports products from an external data source. "
        "Accepts either a JSON array of Product objects or a single Product object in the request body. "
        "Returns validated and stored products."
    ),
)
async def import_products(
    products_data: Union[List[Product], Product] = Body(
        ...,
        examples={
            "array": {
                "summary": "Array of products",
                "value": [
                    {
                        "category": "electricity_plan",
                        "source_url": "https://example.com/plan",
                        "provider_name": "ProviderX",
                        "product_id": "prd-001",
                        "name": "Plan X",
                        "available": True,
                        "raw_data": {},
                    }
                ],
            },
            "object": {
                "summary": "Single product",
                "value": {
                    "category": "electricity_plan",
                    "source_url": "https://example.com/plan",
                    "provider_name": "ProviderX",
                    "product_id": "prd-001",
                    "name": "Plan X",
                    "available": True,
                    "raw_data": {},
                },
            },
        },
        description="JSON array of Product objects or a single Product object."
    ),
):
    """
    Import products from external data source. Accepts JSON array or single product object in request body.
    Returns validated and stored products.
    """
    try:
        if isinstance(products_data, Product):
            products = [products_data]
            request_type = "single_object"
        else:
            products = products_data
            request_type = "array"

        print(f"[INFO] /products/import received {request_type} with {len(products)} products.")

        for product in products:
            fake_db.append(product)
        return ApiResponse(root=products)
    except ValidationError as ve:
        print(f"Validation error during import: {ve}")
        raise HTTPException(
            status_code=422,
            detail=f"Product validation failed: {ve.errors()}"
        )
    except Exception as e:
        print(f"Unexpected error during import: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error during import: {str(e)}"
        )

# Legacy endpoint for backward compatibility (optional)
@app.post("/products/import_legacy", response_model=ApiResponse)
async def import_products_legacy(raw_json: str = Body(..., media_type="text/plain")):
    """
    Legacy import endpoint for backward compatibility. Accepts raw JSON string in request body.
    """
    try:
        import json
        json_data = json.loads(raw_json)
        api_response = ApiResponse.model_validate(json_data)
        for product in api_response.root:
            fake_db.append(product)
        return api_response
    except json.JSONDecodeError as je:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid JSON format: {str(je)}"
        )
    except ValidationError as ve:
        raise HTTPException(
            status_code=422,
            detail=f"Product validation failed: {ve.errors()}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

@app.get("/")
def docs_redirect():
    return {"docs": "/docs", "openapi": "/openapi.json"}

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "2.0.0", "pydantic_version": "2.x"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)