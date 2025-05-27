# ✅ test_search_logic.py 1 https://chatgpt.com/share/6830d70a-0870-800d-bc5d-5728de21fa76

import pytest
from sqlmodel import select
from models import ProductDB, StandardizedProduct
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.mark.asyncio
async def test_search_by_type(session: AsyncSession):
    # Insert electricity and mobile plans
    session.add_all([
        ProductDB(type="electricity_plan", name="Elec A"),
        ProductDB(type="mobile_plan", name="Mobile B"),
    ])
    await session.commit()

    # Search for electricity plans only
    result = await session.execute(select(ProductDB).where(ProductDB.type == "electricity_plan"))
    plans = result.scalars().all()
    assert len(plans) == 1
    assert plans[0].name == "Elec A"

@pytest.mark.asyncio
async def test_search_by_provider(session: AsyncSession):
    session.add_all([
        ProductDB(provider_name="Provider X", name="X1"),
        ProductDB(provider_name="Provider Y", name="Y1"),
    ])
    await session.commit()

    result = await session.execute(select(ProductDB).where(ProductDB.provider_name == "Provider X"))
    plans = result.scalars().all()
    assert len(plans) == 1
    assert plans[0].name == "X1"
