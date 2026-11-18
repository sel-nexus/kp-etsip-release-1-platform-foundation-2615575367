"""Provide isolated real-MongoDB fixtures for identity tests."""

import os
import uuid
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pymongo import AsyncMongoClient
from app.core.config import settings
from app.core.database import create_indexes
from app.core.seed import seed_database
from app.main import app


@pytest_asyncio.fixture
async def environment():
    """Create and later drop a uniquely named database, never the configured app DB."""
    settings.JWT_SECRET = "test-only-secret-with-adequate-entropy-12345"
    settings.SEED_PASSWORD = "DemoPassword123!"
    client = AsyncMongoClient(os.getenv("TEST_MONGODB_URI", "mongodb://localhost:27017"), serverSelectionTimeoutMS=3000, tz_aware=True)
    db_name = "ketsip_test_" + uuid.uuid4().hex
    db = client[db_name]
    await client.admin.command("ping")
    await create_indexes(db)
    await seed_database(db)
    app.state.db = db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            yield http, db
    finally:
        await client.drop_database(db_name)
        await client.close()
