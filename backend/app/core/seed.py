"""Seed local roles and demonstration accounts without overwriting changes."""

import asyncio
from datetime import datetime, timezone
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
