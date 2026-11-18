"""Expose scoped application CRUD and CSV export."""

import csv
import io
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Query, Request, Response
from app.auth.router import ready_user
from app.core.database import get_database
from app.applications import service
from app.applications.repository import ApplicationRepository, search_query
from app.applications.schemas import Application, ApplicationInput, ApplicationPage

router = APIRouter(prefix="/api/applications", tags=["applications"])


def get_repo(request: Request) -> ApplicationRepository:
    """Bind application operations to the active database."""
    return ApplicationRepository(get_database(request))


@router.get("", response_model=ApplicationPage)
async def list_route(user: Annotated[dict, Depends(ready_user)], repo: Annotated[ApplicationRepository, Depends(get_repo)],
                     search: str = Query(default="", max_length=200), portfolioId: str | None = Query(default=None, max_length=24),
                     criticality: Literal["Low", "Medium", "High", "Critical"] | None = None,
                     riskLevel: Literal["Low", "Medium", "High"] | None = None,
                     lifecycleStatus: Literal["Active", "Deprecated", "Retired"] | None = None,
                     offset: int = Query(default=0, ge=0), limit: int = Query(default=25, ge=1, le=100)) -> dict:
    """List a bounded page of visible applications."""
    return await service.listing(repo, user, search, portfolioId, criticality, riskLevel, lifecycleStatus, offset, limit)


@router.get("/export")
async def export_route(user: Annotated[dict, Depends(ready_user)], repo: Annotated[ApplicationRepository, Depends(get_repo)],
                       search: str = Query(default="", max_length=200), portfolioId: str | None = Query(default=None, max_length=24),
                       criticality: Literal["Low", "Medium", "High", "Critical"] | None = None,
                       riskLevel: Literal["Low", "Medium", "High"] | None = None,
                       lifecycleStatus: Literal["Active", "Deprecated", "Retired"] | None = None) -> Response:
    """Export the filtered visible inventory without spreadsheet formula injection."""
    await service.authorize(repo, user, "view")
    await service.authorize(repo, user, "export")
    query = search_query(user, search, portfolioId, criticality, riskLevel, lifecycleStatus)
    output = io.StringIO(newline="")
    fields = ["name", "portfolioName", "criticality", "tier", "lifecycleStatus", "applicationHealthScore", "automationCoverage", "openCriticalDefects", "riskLevel"]
    writer = csv.writer(output)
    writer.writerow(fields)
    cursor = repo.db.applications.find(query).sort([("name", 1), ("_id", 1)])
    async for row in cursor:
        item = await repo.serialize(row)
        writer.writerow([("'" + str(item[f]) if isinstance(item[f], str) and item[f].lstrip().startswith(("=", "+", "-", "@")) else item[f]) for f in fields])
    await repo.audit(user, "export", None, "filtered inventory")
    return Response(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="applications.csv"'})


@router.post("", response_model=Application, status_code=201)
async def create_route(payload: ApplicationInput, user: Annotated[dict, Depends(ready_user)], repo: Annotated[ApplicationRepository, Depends(get_repo)]) -> dict:
    """Create an authorized application."""
    return await service.save(repo, user, payload)


@router.get("/{identifier}", response_model=Application)
async def detail_route(identifier: str, user: Annotated[dict, Depends(ready_user)], repo: Annotated[ApplicationRepository, Depends(get_repo)]) -> dict:
    """Read an authorized application."""
    return await repo.serialize(await service.find(repo, user, identifier))


@router.put("/{identifier}", response_model=Application)
async def update_route(identifier: str, payload: ApplicationInput, user: Annotated[dict, Depends(ready_user)], repo: Annotated[ApplicationRepository, Depends(get_repo)]) -> dict:
    """Edit an authorized application."""
    return await service.save(repo, user, payload, identifier)


@router.delete("/{identifier}", status_code=204)
async def delete_route(identifier: str, user: Annotated[dict, Depends(ready_user)], repo: Annotated[ApplicationRepository, Depends(get_repo)]) -> Response:
    """Delete an application as an administrator."""
    await service.remove(repo, user, identifier)
    return Response(status_code=204)
