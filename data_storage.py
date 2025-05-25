# data_storage.py
from typing import List
from sqlmodel import Session
from sqlalchemy.ext.asyncio import AsyncSession
from database import engine # Import the engine from your database setup
from models import StandardizedProduct, ProductDB, create_product_db_from_standardized # Import models and helper

async def store_standardized_data(session: AsyncSession, data: List[StandardizedProduct]):
    """
    Stores a list of standardized product data into the database.

    Args:
        session: The database session (SQLModel AsyncSession).
        data: A list of StandardizedProduct Pydantic models.
    """
    if not data:
        print("No standardized data to store.")
        return

    print(f"Attempting to store {len(data)} standardized products...")

    try:
        product_db_objects = [create_product_db_from_standardized(product) for product in data]

        # Add all objects to the session
        session.add_all(product_db_objects)

        # Commit the transaction
        await session.commit()

        # Refresh objects (optional, but ensures they have their primary keys populated)
        # for product_db in product_db_objects:
        #     await session.refresh(product_db)

        print(f"Successfully stored {len(data)} standardized products.")

    except Exception as e:
        # Rollback the transaction in case of error
        await session.rollback()
        print(f"Error storing standardized data: {e}")
        # Depending on severity, you might want to re-raise the exception
        # raise e
