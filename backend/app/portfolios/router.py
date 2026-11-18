"""Expose scoped portfolio inventory endpoints."""

from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Query, Request, Response
from app.auth.router import ready_user
from app.core.database import get_database
from app.portfolios.repository import PortfolioRepository
from app.portfolios.schemas import ApplicationPage, Portfolio, PortfolioInput, PortfolioPage
from app.portfolios import service

router = APIRouter(prefix="/api/portfolios", tags=["portfolios"])


def get_repo(request: Request) -> PortfolioRepository:
    """Use the application's active database."""
    return PortfolioRepository(get_database(request))


@router.get("", response_model=PortfolioPage)
async def list_route(user: Annotated[dict, Depends(ready_user)], repo: Annotated[PortfolioRepository, Depends(get_repo)],
                     search: str = Query(default="", max_length=200), status: Literal["Active", "Archived"] | None = None,
                     productArea: str | None = Query(default=None, max_length=200), offset: int = Query(default=0, ge=0),
                     limit: int = Query(default=25, ge=1, le=100)) -> dict:
    """List visible portfolios with search and filters."""
    return await service.list_portfolios(repo, user, search, status, productArea, offset, limit)


@router.post("", response_model=Portfolio, status_code=201)
async def create_route(payload: PortfolioInput, user: Annotated[dict, Depends(ready_user)], repo: Annotated[PortfolioRepository, Depends(get_repo)]) -> dict:
    """Create a portfolio as an authorized administrator."""
    return await service.save(repo, user, payload)


@router.get("/{identifier}", response_model=Portfolio)
async def detail_route(identifier: str, user: Annotated[dict, Depends(ready_user)], repo: Annotated[PortfolioRepository, Depends(get_repo)]) -> dict:
    """Retrieve a visible portfolio and its current metrics."""
    return await repo.serialize(await service.find(repo, user, identifier))


@router.put("/{identifier}", response_model=Portfolio)
async def update_route(identifier: str, payload: PortfolioInput, user: Annotated[dict, Depends(ready_user)], repo: Annotated[PortfolioRepository, Depends(get_repo)]) -> dict:
    """Edit an authorized portfolio."""
    return await service.save(repo, user, payload, identifier)


@router.delete("/{identifier}", status_code=204)
async def delete_route(identifier: str, user: Annotated[dict, Depends(ready_user)], repo: Annotated[PortfolioRepository, Depends(get_repo)]) -> Response:
    """Delete an empty portfolio as an authorized administrator."""
    await service.remove(repo, user, identifier)
    return Response(status_code=204)


@router.get("/{identifier}/applications", response_model=ApplicationPage)
async def applications_route(identifier: str, user: Annotated[dict, Depends(ready_user)], repo: Annotated[PortfolioRepository, Depends(get_repo)],
                             offset: int = Query(default=0, ge=0), limit: int = Query(default=25, ge=1, le=100)) -> dict:
    """List linked applications within the caller's portfolio scope."""
    await service.find(repo, user, identifier)
    items, total = await repo.applications(identifier, offset, limit)
    return {"items": items, "total": total, "offset": offset, "limit": limit}
