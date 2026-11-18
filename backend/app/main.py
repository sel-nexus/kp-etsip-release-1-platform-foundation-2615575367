"""Create the API and manage the pooled MongoDB connection."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import AsyncMongoClient
from app.auth.router import router
from app.core.config import settings
from app.core.database import create_indexes
from app.core.seed import seed_database
from app.portfolios.router import router as portfolios_router
from app.applications.router import router as applications_router
from app.admin.router import router as admin_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize required indexes and seeds before serving requests."""
    settings.validate_security()
    client = AsyncMongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=5000, tz_aware=True)
    try:
        await client.admin.command("ping")
        app.state.db = client.get_database(settings.MONGODB_DB)
        await create_indexes(app.state.db)
        if settings.SEED_ON_STARTUP:
            await seed_database(app.state.db)
        yield
    finally:
        await client.close()


app = FastAPI(title="KP ETSIP API", version="1.0.0", description="Identity and platform foundation", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[v.strip() for v in settings.CORS_ORIGINS.split(",") if v.strip()],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
app.include_router(portfolios_router)
app.include_router(applications_router)
app.include_router(admin_router)


@app.get("/api/health", tags=["health"])
async def health() -> dict[str, str]:
    """Report process liveness without accessing external services."""
    return {"status": "ok"}
