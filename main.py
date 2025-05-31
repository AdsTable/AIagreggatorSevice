# main.py
from fastapi import FastAPI, HTTPException, Query, Depends
from typing import List, Dict, Any, Optional
from sqlmodel import Session
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager
from pydantic import BaseModel, ConfigDict, field_validator

# Import functions and models from your modules
from data_discoverer import discover_and_extract_data
from data_parser import parse_and_standardize
from data_storage import store_standardized_data
from data_search import search_and_filter_products
from models import StandardizedProduct, ProductDB
from product_schema import Product, ApiResponse
from database import create_db_and_tables, get_session


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
    min_price: Optional[float] = Query(None, ge=0, description="Filter by minimum price"),
    provider: Optional[str] = Query(None, description="Filter by provider name"),
    max_data_gb: Optional[float] = Query(None, ge=0, description="Filter by maximum data allowance in GB"),
    min_contract_duration_months: Optional[int] = Query(None, ge=0, description="Filter by minimum contract duration in months")
):
    """
    Searches and filters aggregated product data stored in the database.
    Returns JSON-safe serialized products using Pydantic 2.x.
    """
    print("\n--- Received Search Request ---")
    print(f"Parameters: product_type={product_type}, min_price={min_price}, provider={provider}, max_data_gb={max_data_gb}, min_contract_duration_months={min_contract_duration_months}")

    try:
        search_results = await search_and_filter_products(
            session=session,
            product_type=product_type,
            min_price=min_price,
            provider=provider,
            max_data_gb=max_data_gb,
            min_contract_duration_months=min_contract_duration_months
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
    min_price: Optional[float] = Query(None, ge=0, description="Filter by minimum price"),
    provider: Optional[str] = Query(None, description="Filter by provider name"),
    max_data_gb: Optional[float] = Query(None, ge=0, description="Filter by maximum data allowance in GB"),
    min_contract_duration_months: Optional[int] = Query(None, ge=0, description="Filter by minimum contract duration in months")
):
    """
    Enhanced search endpoint with detailed response including metadata.
    """
    filters_applied = {
        "product_type": product_type,
        "min_price": min_price,
        "provider": provider,
        "max_data_gb": max_data_gb,
        "min_contract_duration_months": min_contract_duration_months
    }
    
    search_results = await search_and_filter_products(
        session=session,
        product_type=product_type,
        min_price=min_price,
        provider=provider,
        max_data_gb=max_data_gb,
        min_contract_duration_months=min_contract_duration_months
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
    return ApiResponse(__root__=fake_db)

@app.post("/products", response_model=Product)
def add_product(product: Product):
    # Automatic validation of input data via Pedantic
    fake_db.append(product)
    return product

# For example: manual validation of a JSON string (for example, downloaded from a file)
@app.post("/products/import", response_model=ApiResponse)
def import_products(raw_json: str):
    try:
        response = ApiResponse.parse_raw(raw_json)
        for prod in response.__root__:
            fake_db.append(prod)
        return response
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


# For documentation/testing:
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