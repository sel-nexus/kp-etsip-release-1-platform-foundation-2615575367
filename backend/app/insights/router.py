"""Expose scoped executive insight and inventory report endpoints."""

from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Query, Request, Response
from app.auth.router import ready_user
from app.core.database import get_database
from app.insights import service
from app.insights.repository import InsightsRepository

router = APIRouter(prefix="/api", tags=["insights"])


def get_repo(request: Request) -> InsightsRepository:
    """Bind insights to the current database."""
    return InsightsRepository(get_database(request))


@router.get("/dashboard/executive")
async def dashboard(user: Annotated[dict, Depends(ready_user)], repo: Annotated[InsightsRepository, Depends(get_repo)],
                    portfolioId: str | None = Query(default=None, max_length=24), productArea: str | None = Query(default=None, max_length=200),
                    riskLevel: Literal["Low", "Medium", "High"] | None = None) -> dict:
    """Return computed executive metrics for the visible selection."""
    metrics, _, _ = await service.read_inventory(repo, user, portfolioId, productArea, riskLevel)
    return metrics


@router.get("/reports/{kind}", response_model=None)
async def report(kind: Literal["applications", "portfolios"], user: Annotated[dict, Depends(ready_user)],
                 repo: Annotated[InsightsRepository, Depends(get_repo)], format: Literal["json", "csv"] = "json",
                 portfolioId: str | None = Query(default=None, max_length=24), productArea: str | None = Query(default=None, max_length=200),
                 riskLevel: Literal["Low", "Medium", "High"] | None = None, offset: int = Query(default=0, ge=0),
                 limit: int = Query(default=25, ge=1, le=100)) -> dict | Response:
    """Return a bounded table page or a complete filtered CSV export."""
    if format == "csv":
        data = await service.export(repo, user, kind[:-1], portfolioId, productArea, riskLevel)
        return Response(data, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{kind}.csv"'})
    _, portfolios, applications = await service.read_inventory(repo, user, portfolioId, productArea, riskLevel)
    rows = applications if kind == "applications" else portfolios
    return {"items": rows[offset:offset + limit], "total": len(rows), "offset": offset, "limit": limit}
