# data_storage.py
import logging
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from models import StandardizedProduct, ProductDB, create_product_db_from_standardized
from pydantic import ValidationError

logger = logging.getLogger("data_storage")
logger.setLevel(logging.INFO)
async def store_standardized_data(session: AsyncSession, data: List[StandardizedProduct]):
    """
    Store standardized product data.
    Accepts ONLY StandardizedProduct (internal canonical model).
    Never call this with external Product or ApiResponse.
    Performs extra validation before storing.
    """
    if not data:
        logger.info("No standardized data to store.")
        return

    logger.info(f"Attempting to store {len(data)} standardized products...")
    # Validate incoming data
    for idx, product in enumerate(data):
        if not isinstance(product, StandardizedProduct):
            logger.error(f"Item at index {idx} is not StandardizedProduct: {product!r}")
            raise TypeError(f"Item at index {idx} is not StandardizedProduct: {product!r}")
        try:
            # This will raise if the object is not valid
            product.model_validate(product.model_dump())
        except ValidationError as ve:
            logger.error(f"Validation error for product at index {idx}: {ve}")
            raise ve
    try:
        product_db_objects = [create_product_db_from_standardized(product) for product in data]

        # Add all objects to the session
        session.add_all(product_db_objects)

        # Commit the transaction
        await session.commit()

        logger.info(f"Successfully stored {len(data)} standardized products.")

    except Exception as e:
        # Rollback the transaction in case of error
        await session.rollback()
        logger.error(f"Error storing standardized data: {e}")
        raise e
        

# If we had a method like this, we must convert before storing:
#
# def store_external_data(session, data: list[Product]):
#     standardized = [product_to_standardized(p) for p in data]
#     store_standardized_data(session, standardized)    