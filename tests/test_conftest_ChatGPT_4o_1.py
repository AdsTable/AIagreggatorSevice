# ✅ conftest.py — shared fixtures for async testing https://chatgpt.com/share/6830d70a-0870-800d-bc5d-5728de21fa76

import pytest_asyncio
from typing import AsyncIterator
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, AsyncEngine
from sqlalchemy.orm import sessionmaker
from database import get_session
from main import app
from httpx import AsyncClient

# In-memory SQLite for test isolation
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture(scope="session")
def engine() -> AsyncEngine:
    engine = create_async_engine(TEST_DB_URL, echo=False)
    return engine

@pytest_asyncio.fixture(scope="function")
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    async with async_session_factory() as session:
        yield session

@pytest_asyncio.fixture()
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session

    async with AsyncClient(app=app, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()
