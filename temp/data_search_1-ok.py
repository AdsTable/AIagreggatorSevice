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
    print("\n--- Received Search Request ---")
    print("Parameters:",
          f"product_type={product_type}, min_price={min_price}, provider={provider},",
          f"max_data_gb={max_data_gb}, min_contract_duration_months={min_contract_duration_months}")

    query = select(ProductDB)
    filters = []

    if product_type:
        filters.append(ProductDB.type == product_type)  # or `.category`, match to your schema
        print(f"Applying filter: type = '{product_type}'")

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

    return [StandardizedProduct.model_validate(product) for product in product_db_results]


# Example Usage (for testing the searcher independently):
# async def main():
#     from database import get_session as get_async_session # Use the async session getter
#     from models import ProductDB # Import ProductDB

#     # You would need to populate the database with some test data first
#     # using the ingestion process or by creating ProductDB objects directly

#     async with get_async_session() as session:
#         print("\n--- Testing Search ---")
#         # Example search: mobile plans with monthly cost >= 40
#         search_results = await search_and_filter_products(
#             session=session,
#             product_type="mobile_plan",
#             min_price=40.0
#         )

#         print("\nSearch Results:")
#         if search_results:
#             for product in search_results:
#                 print(product.model_dump_json(indent=2))
#         else:
#             print("No products found matching the search criteria.")

# if __name__ == "__main__":
#      import asyncio
#      asyncio.run(main())
