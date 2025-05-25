# tests/test_ingest_and_search.py

import pytest
from httpx import AsyncClient
from main import app
from models import ProductDB

@pytest.mark.asyncio
async def test_ingest_and_search_endpoint(session, mocker):
    mock_data = [
        {"type": "mobile_plan", "provider_name": "Ice", "name": "Plan 5GB", "monthly_cost": 199, "data_gb": 5, "contract_duration_months": 12}
    ]
    from models import StandardizedProduct
    from sqlmodel import Field
    mock_result = [
        ProductDB(
            type="mobile_plan",
            provider_name="Ice",
            name="Plan 5GB",
            monthly_cost=199,
            data_gb=5,
            contract_duration_months=12,
            raw_data={"k": "v"}
        )
    ]

    mocker.patch("data_fetcher.fetch_product_data_from_api", return_value=mock_data)
    mocker.patch("data_parser.parse_and_standardize", return_value=mock_result)

    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.post("/ingest_data")
        assert r.status_code == 200
        r2 = await ac.get("/search", params={"product_type": "mobile_plan"})
        assert r2.status_code == 200
        assert any("Plan 5GB" in r["name"] for r in r2.json())
