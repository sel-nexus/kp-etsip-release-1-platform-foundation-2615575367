"""Expose the pooled MongoDB database from the application lifespan."""

from fastapi import Request
from pymongo.asynchronous.database import AsyncDatabase


def get_database(request: Request) -> AsyncDatabase:
    """Return the database associated with the running application."""
    return request.app.state.db


async def create_indexes(db: AsyncDatabase) -> None:
    """Create the natural-key and audit query indexes."""
    await db.users.create_index("email", unique=True)
    await db.roles.create_index("name", unique=True)
    await db.portfolios.create_index("name", unique=True)
    await db.portfolios.create_index([("status", 1), ("productArea", 1)])
    await db.applications.create_index("portfolioId")
    await db.applications.create_index("name", unique=True)
    await db.applications.create_index([("criticality", 1), ("riskLevel", 1), ("lifecycleStatus", 1)])
    await db.audit_logs.create_index([("timestamp", -1)])
    await db.audit_logs.create_index([("userId", 1), ("timestamp", -1)])
