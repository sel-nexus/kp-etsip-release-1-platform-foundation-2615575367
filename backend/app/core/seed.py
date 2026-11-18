"""Seed local roles and demonstration accounts without overwriting changes."""

import asyncio
from datetime import datetime, timezone
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from pymongo.asynchronous.database import AsyncDatabase
from app.core.config import settings
from app.core.security import hash_password

ROLE_PERMISSIONS = {
    "Administrator": ["view", "create", "edit", "delete", "export", "administer"],
    "Executive": ["view", "export"],
    "Portfolio Leader": ["view", "create", "edit", "export"],
    "Engineer": ["view", "create", "edit", "export"],
    "Auditor": ["view", "export"],
    "Read Only": ["view"],
}


async def seed_database(db: AsyncDatabase) -> None:
    """Insert missing seed records; never reset existing credentials or roles."""
    now = datetime.now(timezone.utc)
    password_hash = await asyncio.to_thread(hash_password, settings.SEED_PASSWORD)
    accounts = [("admin", "Administrator"), ("executive", "Executive"),
                ("leader", "Portfolio Leader"), ("engineer", "Engineer"),
                ("auditor", "Auditor"), ("readonly", "Read Only")]
    for name, permissions in ROLE_PERMISSIONS.items():
        await db.roles.update_one({"name": name}, {"$setOnInsert": {
            "name": name, "description": name, "permissions": permissions,
            "createdAt": now, "updatedAt": now}}, upsert=True)
    for local, role in accounts:
        email = f"{local}@ketsip.local"
        await db.users.update_one({"email": email}, {"$setOnInsert": {
            "email": email, "name": f"Demo {role}", "passwordHash": password_hash,
            "role": role, "portfolioAccess": [], "status": "Active", "lastLogin": None,
            "authSource": "local", "managerName": None, "vendorIndicator": False,
            "mustChangePassword": True, "defaultLandingPage": None, "tokenVersion": 0,
            "createdAt": now, "updatedAt": now}}, upsert=True)
    # Fixed IDs keep reruns independent of user-edited names.
    portfolios = [("64a000000000000000000001", "Payments", "Commerce"),
                  ("64a000000000000000000002", "Customer Platform", "Customer"),
                  ("64a000000000000000000003", "Data & Analytics", "Insights")]
    for identifier, name, area in portfolios:
        try:
            await db.portfolios.update_one({"_id": ObjectId(identifier)}, {"$setOnInsert": {
                "name": name, "owner": "Demo owner", "description": "Demonstration portfolio",
                "productArea": area, "status": "Active", "createdAt": now, "updatedAt": now}}, upsert=True)
        except DuplicateKeyError:
            continue
    from app.applications.repository import ApplicationRepository
    repo = ApplicationRepository(db)
    names = ["Payment Gateway", "Settlement", "Billing", "Customer Profile", "Customer Support",
             "Identity Portal", "Analytics Warehouse", "Reporting Hub", "Data Pipeline", "Risk Insights"]
    for index, name in enumerate(names):
        identifier = ObjectId(f"64b0000000000000000000{index + 1:02x}")
        if await db.applications.find_one({"_id": identifier}):
            continue
        portfolio_id, _, area = portfolios[index % len(portfolios)]
        token = await repo.reserve(portfolio_id)
        if not token:
            continue
        fields = {"_id": identifier, "name": name, "description": "Demonstration application",
                  "portfolioId": portfolio_id, "productArea": area, "businessOwner": "Demo business owner",
                  "technologyOwner": "Demo technology owner", "etsOwner": "Demo ETS owner",
                  "criticality": ["Low", "Medium", "High", "Critical"][index % 4], "tier": index % 4 + 1,
                  "lifecycleStatus": "Active", "technologyStack": "Managed services", "repositoryLink": None,
                  "pipelineLink": None, "applicationHealthScore": 70 + index, "qualityScore": 75 + index,
                  "automationCoverage": 55 + index * 2, "unitTestCoverage": 60 + index * 2,
                  "openDefects": index, "openCriticalDefects": index % 3,
                  "riskLevel": ["Low", "Medium", "High"][index % 3], "reservation": token,
                  "createdAt": now, "updatedAt": now}
        try:
            await db.applications.insert_one(fields)
        except DuplicateKeyError:
            await repo.release(portfolio_id, token)
