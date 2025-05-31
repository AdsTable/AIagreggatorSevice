# data_search.py
from typing import List, Optional
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_
from models import ProductDB, StandardizedProduct


async def search_and_filter_products(
    session: AsyncSession,
    product_type: Optional[str] = None,
    min_price: Optional[float] = None,
    provider: Optional[str] = None,
    max_data_gb: Optional[float] = None,
    min_contract_duration_months: Optional[int] = None
) -> List[StandardizedProduct]:
    """
    Search and filter products using Pydantic 2.x serialization.
    """
    print("\n--- Received Search Request ---")
    print("Parameters:",
          f"product_type={product_type}, min_price={min_price}, provider={provider},",
          f"max_data_gb={max_data_gb}, min_contract_duration_months={min_contract_duration_months}")

    query = select(ProductDB)
    filters = []

    if product_type:
        filters.append(ProductDB.category == product_type)
        print(f"Applying filter: category = '{product_type}'")

    if provider:
        filters.append(ProductDB.provider_name.ilike(f"%{provider}%"))
        print(f"Applying filter: provider LIKE '%{provider}%'")

    if min_price is not None:
        if product_type == "electricity_plan":
            filters.append(ProductDB.price_kwh >= min_price)
            print(f"Applying filter: price_kwh >= {min_price}")
        elif product_type == "mobile_plan":
            filters.append(ProductDB.monthly_cost >= min_price)
            print(f"Applying filter: monthly_cost >= {min_price}")
        else:
            filters.append(
                (ProductDB.price_kwh >= min_price) | (ProductDB.monthly_cost >= min_price)
            )
            print(f"Applying fallback filter: price_kwh >= {min_price} OR monthly_cost >= {min_price}")

    if max_data_gb is not None:
        filters.append(
            (ProductDB.data_gb.is_(None)) | (ProductDB.data_gb <= max_data_gb)
        )
        print(f"Applying filter: data_gb <= {max_data_gb} OR data_gb IS NULL")

    if min_contract_duration_months is not None:
        filters.append(
            (ProductDB.contract_duration_months.is_(None)) |
            (ProductDB.contract_duration_months >= min_contract_duration_months)
        )
        print(f"Applying filter: contract_duration_months >= {min_contract_duration_months} OR IS NULL")

    if filters:
        query = query.where(and_(*filters))

    result = await session.exec(query)
    product_db_results = result.all()
    print(f"Found {len(product_db_results)} matching products in the database.")

    # Convert ProductDB to StandardizedProduct using Pydantic 2.x method
    return [product_db.to_standardized_product() for product_db in product_db_results]