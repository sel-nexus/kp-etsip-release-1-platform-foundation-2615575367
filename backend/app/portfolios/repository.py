"""Persist portfolio inventory and derive linked application summaries."""

import re
from datetime import datetime, timezone
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase


class PortfolioRepository:
    """Read and write inventory using the shared MongoDB pool."""

    def __init__(self, db: AsyncDatabase) -> None:
        """Bind the repository to the active database."""
        self.db = db

    async def permissions(self, role: str) -> list[str]:
        """Read the current editable role permissions."""
        document = await self.db.roles.find_one({"name": role})
        return document.get("permissions", []) if document else []

    async def list_portfolios(self, query: dict, offset: int, limit: int) -> tuple[list[dict], int]:
        """Fetch a stable bounded page and its total."""
        total = await self.db.portfolios.count_documents(query)
        rows = await self.db.portfolios.find(query).sort([("name", 1), ("_id", 1)]).skip(offset).limit(limit).to_list(None)
        return [await self.serialize(row) for row in rows], total

    async def get(self, identifier: str) -> dict | None:
        """Find a portfolio by public identifier."""
        if not ObjectId.is_valid(identifier):
            return None
        return await self.db.portfolios.find_one({"_id": ObjectId(identifier)})

    async def serialize(self, document: dict) -> dict:
        """Compute count and rounded average from linked applications."""
        identifier = str(document["_id"])
        cursor = await self.db.applications.aggregate([
            {"$match": {"portfolioId": identifier}},
            {"$group": {"_id": None, "count": {"$sum": 1}, "average": {"$avg": "$qualityScore"}}},
        ])
        result = await cursor.to_list(None)
        metrics = result[0] if result else {"count": 0, "average": None}
        average = metrics["average"]
        return {**{key: value for key, value in document.items() if key != "_id"}, "id": identifier, "applicationCount": metrics["count"],
                "qualityScore": int(average + 0.5) if average is not None else None}

    async def insert(self, fields: dict) -> dict:
        """Create a timestamped portfolio and return its document."""
        now = datetime.now(timezone.utc)
        document = {**fields, "createdAt": now, "updatedAt": now}
        await self.db.portfolios.insert_one(document)
        return document

    async def update(self, identifier: str, fields: dict) -> dict | None:
        """Update a portfolio if it still exists."""
        fields = {**fields, "updatedAt": datetime.now(timezone.utc)}
        await self.db.portfolios.update_one({"_id": ObjectId(identifier)}, {"$set": fields})
        return await self.get(identifier)

    async def delete(self, identifier: str) -> bool:
        """Delete an existing portfolio document."""
        result = await self.db.portfolios.delete_one({"_id": ObjectId(identifier)})
        return result.deleted_count == 1

    async def applications(self, identifier: str, offset: int, limit: int) -> tuple[list[dict], int]:
        """Return a bounded list of linked applications."""
        query = {"portfolioId": identifier}
        total = await self.db.applications.count_documents(query)
        rows = await self.db.applications.find(query).sort([("name", 1), ("_id", 1)]).skip(offset).limit(limit).to_list(None)
        return [{**row, "id": str(row["_id"])} for row in rows], total

    async def audit(self, user: dict, action: str, identifier: str, name: str) -> None:
        """Record a successful portfolio mutation."""
        now = datetime.now(timezone.utc)
        await self.db.audit_logs.insert_one({"timestamp": now, "createdAt": now, "updatedAt": now,
            "userId": str(user["_id"]), "userName": user["name"], "action": action,
            "entityType": "portfolio", "entityId": identifier, "details": f"Portfolio {action}: {name}"})


def search_query(search: str, status: str | None, product_area: str | None, user: dict) -> dict:
    """Build a safe scoped filter with literal case-insensitive search."""
    query: dict = {}
    if user["role"] == "Portfolio Leader":
        query["_id"] = {"$in": [ObjectId(value) for value in user.get("portfolioAccess", []) if ObjectId.is_valid(value)]}
    if search:
        pattern = {"$regex": re.escape(search), "$options": "i"}
        query["$or"] = [{"name": pattern}, {"owner": pattern}, {"description": pattern}, {"productArea": pattern}]
    if status:
        query["status"] = status
    if product_area:
        query["productArea"] = product_area
    return query
