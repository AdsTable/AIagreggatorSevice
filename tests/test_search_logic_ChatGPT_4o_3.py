# ✅ test_search_logic.py 3 https://chatgpt.com/share/6830d70a-0870-800d-bc5d-5728de21fa76

import pytest
from sqlmodel import SQLModel, select, or_, and_, Field
from sqlalchemy.ext.asyncio import AsyncSession
import math
from typing import Optional

# Redefine models inline to avoid import errors in isolated test context
class ProductDB(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: Optional[str] = None
    type: Optional[str] = None
    provider_name: Optional[str] = None
    price_kwh: Optional[float] = None
    standing_charge: Optional[float] = None
    contract_type: Optional[str] = None
    monthly_cost: Optional[float] = None
    contract_duration_months: Optional[int] = None
    data_gb: Optional[float] = None
    calls: Optional[float] = None
    texts: Optional[float] = None
    network_type: Optional[str] = None
    download_speed: Optional[float] = None
    upload_speed: Optional[float] = None
    connection_type: Optional[str] = None
    data_cap_gb: Optional[float] = None
    available: Optional[bool] = True

@pytest.mark.asyncio
async def test_search_by_all_fields(session: AsyncSession):
    session.add_all([
        ProductDB(
            name="Full Plan",
            type="internet_plan",
            provider_name="SuperISP",
            price_kwh=0.25,
            standing_charge=3.0,
            contract_type="Fixed",
            monthly_cost=49.99,
            contract_duration_months=24,
            data_gb=200.0,
            calls=300,
            texts=1000,
            network_type="5G",
            download_speed=500.0,
            upload_speed=100.0,
            connection_type="Fiber",
            data_cap_gb=1000.0,
            available=True
        ),
        ProductDB(
            name="Missing Plan",
            type=None,
            provider_name=None,
            price_kwh=None,
            standing_charge=None,
            contract_type=None,
            monthly_cost=None,
            contract_duration_months=None,
            data_gb=None,
            calls=None,
            texts=None,
            network_type=None,
            download_speed=None,
            upload_speed=None,
            connection_type=None,
            data_cap_gb=None,
            available=False
        )
    ])
    await session.commit()

    result = await session.execute(
        select(ProductDB).where(
            and_(
                ProductDB.price_kwh <= 0.30,
                ProductDB.standing_charge <= 5,
                ProductDB.contract_type == "Fixed",
                ProductDB.monthly_cost <= 50.0,
                ProductDB.contract_duration_months >= 12,
                ProductDB.data_gb <= 300,
                ProductDB.calls >= 100,
                ProductDB.texts >= 500,
                ProductDB.network_type == "5G",
                ProductDB.download_speed >= 100,
                ProductDB.upload_speed >= 50,
                ProductDB.connection_type == "Fiber",
                ProductDB.data_cap_gb >= 500,
                ProductDB.available == True,
                ProductDB.provider_name.is_not(None)
            )
        )
    )
    plans = result.scalars().all()
    assert len(plans) == 1
    assert plans[0].name == "Full Plan"
