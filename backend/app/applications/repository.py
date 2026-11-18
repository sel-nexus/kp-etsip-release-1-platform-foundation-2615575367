"""Persist applications and atomic portfolio reference reservations."""

import re
from datetime import datetime, timezone
from uuid import uuid4
from bson import ObjectId
from bson.errors import InvalidDocument
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import WriteError


class ApplicationRepository:
    """Access application documents through the shared MongoDB pool."""

    def __init__(self, db: AsyncDatabase) -> None:
        """Bind the active database."""
        self.db = db

    async def permissions(self, role: str) -> list[str]:
        """Read editable permissions for the role."""
        role_doc = await self.db.roles.find_one({"name": role})
        return role_doc.get("permissions", []) if role_doc else []

    async def get(self, identifier: str) -> dict | None:
        """Find an application by its public identifier."""
        return await self.db.applications.find_one({"_id": ObjectId(identifier)}) if ObjectId.is_valid(identifier) else None

    async def serialize(self, document: dict) -> dict:
        """Resolve the portfolio display name without exposing reservations."""
        pid = document["portfolioId"]
        portfolio = await self.db.portfolios.find_one({"_id": ObjectId(pid)}) if ObjectId.is_valid(pid) else None
        return {**{k: v for k, v in document.items() if k not in ("_id", "reservation")},
                "id": str(document["_id"]), "portfolioName": portfolio["name"] if portfolio else "Unavailable"}

    async def page(self, query: dict, offset: int, limit: int) -> tuple[list[dict], int]:
        """Fetch a stable bounded page and count."""
        total = await self.db.applications.count_documents(query)
        rows = await self.db.applications.find(query).sort([("name", 1), ("_id", 1)]).skip(offset).limit(limit).to_list(None)
        return [await self.serialize(row) for row in rows], total

    async def reserve(self, portfolio_id: str) -> str | None:
        """Atomically reserve a portfolio against deletion; return None if missing."""
        if not ObjectId.is_valid(portfolio_id):
            return None
        token = uuid4().hex
        result = await self.db.portfolios.update_one({"_id": ObjectId(portfolio_id), "deletionLock": {"$exists": False}}, {"$addToSet": {"applicationReservations": token}})
        return token if result.matched_count else None

    async def release(self, portfolio_id: str, token: str | None) -> None:
        """Release a completed or definitively aborted reservation."""
        if token and ObjectId.is_valid(portfolio_id):
            await self.db.portfolios.update_one({"_id": ObjectId(portfolio_id)}, {"$pull": {"applicationReservations": token}})

    async def insert(self, fields: dict) -> dict | None:
        """Reserve the portfolio and persist an application.

        Crashes or ambiguous outcomes may leave reservations requiring manual
        reconciliation; do not release them when the write might have succeeded.
        """
        token = await self.reserve(fields["portfolioId"])
        if not token:
            return None
        now = datetime.now(timezone.utc)
        row = {**fields, "reservation": token, "createdAt": now, "updatedAt": now}
        try:
            await self.db.applications.insert_one(row)
        except (WriteError, InvalidDocument):
            await self.release(fields["portfolioId"], token)
            raise
        return row

    async def update(self, old: dict, fields: dict) -> dict | None:
        """Move with a new reservation and optimistic concurrency checks."""
        token = await self.reserve(fields["portfolioId"])
        if not token:
            return None
        query = {"_id": old["_id"], "portfolioId": old["portfolioId"], "reservation": old.get("reservation")}
        try:
            result = await self.db.applications.update_one(query, {"$set": {**fields, "reservation": token, "updatedAt": datetime.now(timezone.utc)}})
        except (WriteError, InvalidDocument):
            await self.release(fields["portfolioId"], token)
            raise
        if not result.matched_count:
            await self.release(fields["portfolioId"], token)
            return None
        await self.release(old["portfolioId"], old.get("reservation"))
        return await self.get(str(old["_id"]))

    async def delete(self, old: dict) -> bool:
        """Delete only the observed version and release its reservation."""
        result = await self.db.applications.delete_one({"_id": old["_id"], "portfolioId": old["portfolioId"], "reservation": old.get("reservation")})
        if result.deleted_count:
            await self.release(old["portfolioId"], old.get("reservation"))
        return bool(result.deleted_count)

    async def audit(self, user: dict, action: str, identifier: str | None, name: str) -> None:
        """Record a successful application mutation or export."""
        now = datetime.now(timezone.utc)
        await self.db.audit_logs.insert_one({"timestamp": now, "createdAt": now, "updatedAt": now,
            "userId": str(user["_id"]), "userName": user["name"], "action": action,
            "entityType": "application", "entityId": identifier, "details": f"Application {action}: {name}"})


def search_query(user: dict, search: str, portfolio_id: str | None, criticality: str | None, risk: str | None, lifecycle: str | None) -> dict:
    """Build a safe scoped filter from validated strings."""
    query: dict = {}
    if user["role"] == "Portfolio Leader":
        query["portfolioId"] = {"$in": user.get("portfolioAccess", [])}
    if portfolio_id:
        if "portfolioId" in query:
            query["portfolioId"] = {"$in": [portfolio_id] if portfolio_id in user.get("portfolioAccess", []) else []}
        else:
            query["portfolioId"] = portfolio_id
    if search:
        pattern = {"$regex": re.escape(search), "$options": "i"}
        query["$or"] = [{"name": pattern}, {"description": pattern}]
    for key, value in (("criticality", criticality), ("riskLevel", risk), ("lifecycleStatus", lifecycle)):
        if value:
            query[key] = value
    return query
