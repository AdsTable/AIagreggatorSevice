# database.py
import os
from typing import AsyncGenerator
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine

# Define the database URL - Using SQLite for simplicity in this example
# Replace with your actual database URL for production (e.g., PostgreSQL, MySQL)
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./database.db")

# Create an asynchronous engine
engine = create_async_engine(DATABASE_URL, echo=True)

# Function to create database tables
async def create_db_and_tables():
    """
    Creates the database tables based on the SQLModel metadata.
    """
    async with engine.begin() as conn:
        # This line will create tables for all models that inherit from SQLModel
        await conn.run_sync(SQLModel.metadata.create_all)
    print("Database tables created or already exist.")

# Dependency to get an asynchronous database session
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Provides an asynchronous database session to be used as a FastAPI dependency.
    """
    async_session = AsyncSession(engine)
    try:
        yield async_session
    finally:
        await async_session.close()

# Example of how you might run the table creation independently
# async def main():
#      await create_db_and_tables()

# if __name__ == "__main__":
#      import asyncio
#      asyncio.run(main())
