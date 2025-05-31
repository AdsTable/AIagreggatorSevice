from fastapi import FastAPI, Query, HTTPException
from typing import Optional, Union

def safe_float_parse(value: Optional[str]) -> Optional[float]:
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
    if value is None or value.strip() == '':
        return None
    try:
        return int(float(value))  # Позволяет "12.0" -> 12
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=422, 
            detail=f"Invalid integer format: '{value}'. Expected a valid integer."
        )

app = FastAPI()

@app.get("/search")
async def search_endpoint(
    min_price: Optional[str] = Query(None, description="Minimum price (number)"),
    max_data_gb: Optional[str] = Query(None, description="Maximum data in GB (number)"),
    min_contract_duration_months: Optional[str] = Query(None, description="Minimum contract duration in months (integer)")
):
    # Безопасное приведение типов
    parsed_min_price = safe_float_parse(min_price)
    parsed_max_data_gb = safe_float_parse(max_data_gb)
    parsed_min_contract_duration = safe_int_parse(min_contract_duration_months)
    
    # Ваша бизнес-логика
    results = perform_search(
        min_price=parsed_min_price,
        max_data_gb=parsed_max_data_gb,
        min_contract_duration_months=parsed_min_contract_duration
    )
    return results