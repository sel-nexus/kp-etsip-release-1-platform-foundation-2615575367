"""Query visible inventory for dashboard and reporting."""

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase


class InsightsRepository:
    """Use the shared database to read scoped inventory and write audits."""

    def __init__(self, db: AsyncDatabase) -> None:
        """Bind the active database."""
        self.db = db

    async def permissions(self, role: str) -> list[str]:
        """Return currently enabled role permissions."""
        role_doc = await self.db.roles.find_one({"name": role})
        return role_doc.get("permissions", []) if role_doc else []

    async def inventory(self, user: dict, portfolio_id: str | None, product_area: str | None, risk: str | None) -> tuple[list[dict], list[dict]]:
        """Read visible portfolios and matching applications in stable order."""
        ids = None
        if user.get("role") == "Portfolio Leader":
            ids = [ObjectId(i) for i in user.get("portfolioAccess", []) if ObjectId.is_valid(i)]
        if portfolio_id:
            selected = ObjectId(portfolio_id) if ObjectId.is_valid(portfolio_id) else None
            ids = [selected] if selected and (ids is None or selected in ids) else []
        query = {"_id": {"$in": ids}} if ids is not None else {}
        portfolios = await self.db.portfolios.find(query, {"applicationReservations": 0}).sort([("name", 1), ("_id", 1)]).to_list(None)
        app_query: dict = {"portfolioId": {"$in": [str(p["_id"]) for p in portfolios]}}
        if product_area:
            app_query["productArea"] = product_area
        if risk:
            app_query["riskLevel"] = risk
        applications = await self.db.applications.find(app_query, {"reservation": 0}).sort([("name", 1), ("_id", 1)]).to_list(None)
        if product_area or risk:
            matching = {a["portfolioId"] for a in applications}
            portfolios = [p for p in portfolios if str(p["_id"]) in matching]
        return portfolios, applications

    async def audit_export(self, user: dict, kind: str) -> None:
        """Record a successful report export without including sensitive data."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        await self.db.audit_logs.insert_one({"timestamp": now, "createdAt": now, "updatedAt": now,
            "userId": str(user["_id"]), "userName": user["name"], "action": "export",
            "entityType": kind, "entityId": None, "details": f"{kind.capitalize()} report exported"})
