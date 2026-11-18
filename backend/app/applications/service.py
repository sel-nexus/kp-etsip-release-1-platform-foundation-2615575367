"""Enforce role ceilings, portfolio scope, and application rules."""

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError
from app.core.seed import ROLE_PERMISSIONS
from app.applications.repository import ApplicationRepository, search_query
from app.applications.schemas import ApplicationInput


async def authorize(repo: ApplicationRepository, user: dict, permission: str, portfolio: str | None = None) -> None:
    """Check current permissions, role ceiling and assigned portfolio."""
    role = user.get("role", "")
    if permission not in ROLE_PERMISSIONS.get(role, []) or permission not in await repo.permissions(role):
        raise HTTPException(403, "Permission denied")
    if permission == "delete" and role != "Administrator":
        raise HTTPException(403, "Only administrators may delete applications")
    if role == "Portfolio Leader" and portfolio is not None and portfolio not in user.get("portfolioAccess", []):
        raise HTTPException(403, "Portfolio is outside your assigned scope")


async def find(repo: ApplicationRepository, user: dict, identifier: str, permission: str = "view") -> dict:
    """Resolve and authorize the requested application."""
    await authorize(repo, user, permission)
    row = await repo.get(identifier)
    if not row:
        raise HTTPException(404, "Application not found")
    await authorize(repo, user, permission, row["portfolioId"])
    return row


async def listing(repo: ApplicationRepository, user: dict, search: str, portfolio: str | None, criticality: str | None, risk: str | None, lifecycle: str | None, offset: int, limit: int) -> dict:
    """Return a scoped page of matching records."""
    await authorize(repo, user, "view")
    items, total = await repo.page(search_query(user, search, portfolio, criticality, risk, lifecycle), offset, limit)
    return {"items": items, "total": total, "offset": offset, "limit": limit}


async def save(repo: ApplicationRepository, user: dict, payload: ApplicationInput, identifier: str | None = None) -> dict:
    """Create or edit an application, checking both old and new scope."""
    old = await find(repo, user, identifier, "edit") if identifier else None
    action = "edit" if identifier else "create"
    await authorize(repo, user, action, payload.portfolioId)
    fields = payload.model_dump(mode="json")
    try:
        row = await repo.update(old, fields) if old else await repo.insert(fields)
    except DuplicateKeyError as exc:
        raise HTTPException(409, "Application name already exists") from exc
    if not row:
        raise HTTPException(409, "Portfolio unavailable or application changed concurrently")
    await repo.audit(user, action, str(row["_id"]), row["name"])
    return await repo.serialize(row)


async def remove(repo: ApplicationRepository, user: dict, identifier: str) -> None:
    """Delete an observed application and audit the change."""
    row = await find(repo, user, identifier, "delete")
    if not await repo.delete(row):
        raise HTTPException(409, "Application changed concurrently")
    await repo.audit(user, "delete", identifier, row["name"])
