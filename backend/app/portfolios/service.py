"""Enforce portfolio authorization and inventory rules."""

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError
from app.core.seed import ROLE_PERMISSIONS
from app.portfolios.repository import PortfolioRepository, search_query
from app.portfolios.schemas import PortfolioInput


async def authorize(repo: PortfolioRepository, user: dict, permission: str, identifier: str | None = None) -> None:
    """Apply current role permissions, ceilings, and resource-specific scope."""
    role = user.get("role", "")
    if permission not in ROLE_PERMISSIONS.get(role, []) or permission not in await repo.permissions(role):
        raise HTTPException(status_code=403, detail="Permission denied")
    if permission in ("create", "delete") and role != "Administrator":
        raise HTTPException(status_code=403, detail="Only administrators may create or delete portfolios")
    if permission == "edit" and role not in ("Administrator", "Portfolio Leader"):
        raise HTTPException(status_code=403, detail="Permission denied")
    if role == "Portfolio Leader" and identifier is not None and identifier not in user.get("portfolioAccess", []):
        raise HTTPException(status_code=403, detail="Portfolio is outside your assigned scope")


async def find(repo: PortfolioRepository, user: dict, identifier: str, permission: str = "view") -> dict:
    """Authorize access and resolve a portfolio or return not found."""
    await authorize(repo, user, permission, identifier)
    row = await repo.get(identifier)
    if not row:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return row


async def list_portfolios(repo: PortfolioRepository, user: dict, search: str, status: str | None, product_area: str | None, offset: int, limit: int) -> dict:
    """List the caller's visible portfolio summaries."""
    await authorize(repo, user, "view")
    items, total = await repo.list_portfolios(search_query(search, status, product_area, user), offset, limit)
    return {"items": items, "total": total, "offset": offset, "limit": limit}


async def save(repo: PortfolioRepository, user: dict, payload: PortfolioInput, identifier: str | None = None) -> dict:
    """Create or update a portfolio and record the successful change."""
    if identifier is None:
        await authorize(repo, user, "create")
    else:
        await find(repo, user, identifier, "edit")
    try:
        row = await repo.insert(payload.model_dump()) if identifier is None else await repo.update(identifier, payload.model_dump())
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=409, detail="Portfolio name already exists") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    await repo.audit(user, "create" if identifier is None else "edit", str(row["_id"]), row["name"])
    return await repo.serialize(row)


async def remove(repo: PortfolioRepository, user: dict, identifier: str) -> None:
    """Reject nonempty portfolios and audit a successful deletion."""
    row = await find(repo, user, identifier, "delete")
    _, total = await repo.applications(identifier, 0, 1)
    if total:
        raise HTTPException(status_code=409, detail="Cannot delete a portfolio containing applications")
    if not await repo.delete(identifier):
        raise HTTPException(status_code=404, detail="Portfolio not found")
    await repo.audit(user, "delete", identifier, row["name"])
