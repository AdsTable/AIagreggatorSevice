# main.py
from fastapi import FastAPI, HTTPException, Query, Depends
from typing import List, Dict, Any, Optional
from sqlmodel import Session # Import Session from sqlmodel
from sqlalchemy.ext.asyncio import AsyncSession # Import AsyncSession
from contextlib import asynccontextmanager
# Import functions and models from your modules
from data_discoverer import discover_and_extract_data # Use the enhanced discoverer
from data_parser import parse_and_standardize
from data_storage import store_standardized_data
from data_search import search_and_filter_products
from models import StandardizedProduct, ProductDB
from database import create_db_and_tables, get_session # Import get_session

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Application startup: Creating database tables...")
    await create_db_and_tables()
    print("Database tables created.")
    yield
    # Place any shutdown logic here if needed

app = FastAPI(lifespan=lifespan)

@app.post("/ingest_data")
async def ingest_provider_data(
    source_identifier: str,
    category: str = Query(..., description="The category of products to search for (e.g., 'electricity_plan', 'mobile_plan')"), # Require category
    session: AsyncSession = Depends(get_session) # Use AsyncSession here
):
    """
    Discovers, extracts (using AI), parses, and stores product data from a source.
    Can perform web searches if the source identifier is not a direct URL or file path.

    Args:
        source_identifier: A string identifying the data source (e.g., a URL,
                           a file path, or a description for AI search).
        category: The category of products to search for (e.g., 'electricity_plan').
    """
    print("\n--- Starting Data Ingestion Process (AI-Assisted) ---")
    print(f"Received source identifier: {source_identifier}, Category: {category}")

    # --- Step 1: Discover and Extract Data (using enhanced AI discoverer) ---
    # Pass both the source identifier and the category
    raw_extracted_data = discover_and_extract_data(source_identifier=source_identifier, category=category)

    if raw_extracted_data is None: # Check for None explicitly if discovery fails
        raise HTTPException(status_code=500, detail=f"Failed to discover and extract data from source: {source_identifier}. Check logs for details.")
    if not raw_extracted_data:
         # It's possible the AI found the source but extracted no relevant data
         print("Discovery and extraction successful, but no raw product data was extracted.")
         return {"message": f"Data ingestion completed, but no raw data was extracted from source: {source_identifier}. Check AI extraction logic."}

    print(f"Raw data extracted from source: {source_identifier}.")

    # --- Step 2: Parse and Standardize (pass category to parser) ---
    # The parse_and_standardize function now uses the category for mapping and parsing logic
    standardized_data = parse_and_standardize(raw_extracted_data, category=category)

    if not standardized_data:
        print("No standardized data generated after parsing.")
        # Depending on whether no data is an error or expected, adjust response
        return {"message": "Data ingestion completed, but no standardized data was generated after parsing. Check parser logic and extracted data format."}

    print(f"{len(standardized_data)} products standardized.")

    # --- Step 3: Store Data ---
    await store_standardized_data(session=session, data=standardized_data)
    print("Standardized data stored.")

    print("--- Data Ingestion Process Completed ---")
    return {"message": f"Data ingestion process completed successfully from source: {source_identifier}. {len(standardized_data)} products stored."}


@app.get("/search", response_model=List[StandardizedProduct])
async def search_products_endpoint(
    session: AsyncSession = Depends(get_session), # Inject asynchronous database session
    product_type: Optional[str] = Query(None, description="Filter by product type (e.g., electricity_plan, mobile_plan)"),
    min_price: Optional[float] = Query(None, description="Filter by minimum price"),
    provider: Optional[str] = Query(None, description="Filter by provider name"),
    # Add other filtering parameters as needed, matching data_search.py
    max_data_gb: Optional[float] = Query(None, description="Filter by maximum data allowance in GB"),
    min_contract_duration_months: Optional[int] = Query(None, description="Filter by minimum contract duration in months")
):
    """
    Searches and filters aggregated product data stored in the database.
    """
    print("\n--- Received Search Request ---")
    # Print received parameters for debugging
    print(f"Parameters: product_type={product_type}, min_price={min_price}, provider={provider}, max_data_gb={max_data_gb}, min_contract_duration_months={min_contract_duration_months}")

    try:
        # The search_and_filter_products function filters based on the StandardizedProduct model fields.
        # Ensure data_search.py can handle these parameters.
        search_results = await search_and_filter_products(
            session=session,
            product_type=product_type,
            min_price=min_price,
            provider=provider,
            max_data_gb=max_data_gb,
            min_contract_duration_months=min_contract_duration_months
        )

        print("--- Search Request Processed ---")
        return search_results

    except Exception as e:
        print(f"An error occurred during search: {e}")
        # Return a 500 Internal Server Error with details
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {e}")


# To run this FastAPI application:
# 1. Save the code above into their respective files (models.py, data_discoverer.py, data_parser.py, data_storage.py, database.py, main.py, and data_search.py).
# 2. Install necessary libraries: pip install fastapi uvicorn pydantic requests sqlmodel aiosqlite sqlalchemy
# 3. Implement the actual web search functionality in the perform_web_search function in data_discoverer.py (replace the placeholder).
# 4. Implement the actual AI call for web extraction in the call_ai_for_web_extraction function in data_discoverer.py (replace the placeholder).
# 5. Refine the parsing logic and update the FIELD_MAPPINGS and PARSING_INSTRUCTIONS in data_parser.py based on the actual output of your AI model from web extraction.
# 6. Update data_search.py to include filtering logic for max_data_gb and min_contract_duration_months if you added those to the search endpoint.
# 7. Run from your terminal in the project directory: uvicorn main:app --reload
# 8. Access the interactive documentation at http://127.0.0.1:8000/docs to test the endpoints.
#    - Use the /ingest_data POST endpoint with a 'source_identifier' (a URL, a file path, or a search query) and a 'category' to trigger the data discovery, extraction, parsing, and storage process.
#    - Use the /search GET endpoint with query parameters (e.g., product_type, min_price, provider, max_data_gb, min_contract_duration_months) to search for data stored in the database.
