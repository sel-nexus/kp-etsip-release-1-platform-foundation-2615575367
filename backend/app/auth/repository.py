"""Persist identity and authentication audit records in MongoDB."""

from datetime import datetime, timezone
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase


class AuthRepository:
    """Perform identity reads and atomic single-document updates."""

    def __init__(self, db: AsyncDatabase) -> None:
        """Bind the repository to the application's pooled database."""
        self.db = db

    async def by_email(self, email: str) -> dict | None:
        """Find an account by normalized email."""
        return await self.db.users.find_one({"email": email})

    async def by_id(self, user_id: str) -> dict | None:
        """Find an account by its external identifier."""
        if not ObjectId.is_valid(user_id):
            return None
        return await self.db.users.find_one({"_id": ObjectId(user_id)})

    async def audit_login(self, email: str, user: dict | None, success: bool) -> None:
        """Record a login outcome without storing a password."""
        now = datetime.now(timezone.utc)
        await self.db.audit_logs.insert_one({"timestamp": now, "createdAt": now, "updatedAt": now,
            "userId": str(user["_id"]) if user else None, "userName": user["name"] if user else email,
            "action": "login", "entityType": "user", "entityId": str(user["_id"]) if user else None,
            "details": "Login succeeded" if success else "Login failed"})

    async def audit_account_change(self, user: dict, details: str) -> None:
        """Record a successful account change without including secret values."""
        now = datetime.now(timezone.utc)
        await self.db.audit_logs.insert_one({"timestamp": now, "createdAt": now, "updatedAt": now,
            "userId": str(user["_id"]), "userName": user["name"], "action": "edit",
            "entityType": "user", "entityId": str(user["_id"]), "details": details})

    async def update(self, user: dict, fields: dict, *, old_hash: str | None = None) -> bool:
        """Update an account, optionally only if its credential is unchanged."""
        query = {"_id": user["_id"], "status": "Active"}
        if old_hash is not None:
            query["passwordHash"] = old_hash
        fields["updatedAt"] = datetime.now(timezone.utc)
        update = {"$set": fields}
        if old_hash is not None:
            update["$inc"] = {"tokenVersion": 1}
        result = await self.db.users.update_one(query, update)
        return result.matched_count == 1
