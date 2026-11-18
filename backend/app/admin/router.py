"""Expose account, role and separately authorized audit endpoints."""

from datetime import datetime
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, Query, Request, Response
from app.admin import service
from app.admin.repository import AdminRepository, user_query
from app.admin.schemas import AdminUser, AuditPage, Role, RoleInput, RolePage, UserCreate, UserInput, UserPage
from app.auth.router import ready_user
from app.core.database import get_database

router = APIRouter(prefix='/api', tags=['administration'])


def get_repo(request: Request) -> AdminRepository:
    """Bind a repository to the shared application database."""
    return AdminRepository(get_database(request))


@router.get('/users', response_model=UserPage)
async def users(actor: Annotated[dict, Depends(ready_user)], repo: Annotated[AdminRepository, Depends(get_repo)], search: str = Query('', max_length=200), offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)) -> dict:
    """List accounts for an administrator."""
    await service.authorize(repo, actor, 'administer')
    return await repo.page('users', user_query(search), offset, limit)


@router.post('/users', response_model=AdminUser, status_code=201)
async def create_user(payload: UserCreate, actor: Annotated[dict, Depends(ready_user)], repo: Annotated[AdminRepository, Depends(get_repo)]) -> dict:
    """Create an account with a one-time initial password."""
    return await service.save_user(repo, actor, payload)


@router.get('/users/{identifier}', response_model=AdminUser)
async def user_detail(identifier: str, actor: Annotated[dict, Depends(ready_user)], repo: Annotated[AdminRepository, Depends(get_repo)]) -> dict:
    """Read one account without returning its credential."""
    await service.authorize(repo, actor, 'administer')
    return await service.find(repo, 'users', identifier)


@router.put('/users/{identifier}', response_model=AdminUser)
async def update_user(identifier: str, payload: UserInput, actor: Annotated[dict, Depends(ready_user)], repo: Annotated[AdminRepository, Depends(get_repo)]) -> dict:
    """Update an account and its portfolio assignments."""
    return await service.save_user(repo, actor, payload, identifier)


@router.delete('/users/{identifier}', status_code=204)
async def delete_user(identifier: str, actor: Annotated[dict, Depends(ready_user)], repo: Annotated[AdminRepository, Depends(get_repo)]) -> Response:
    """Deactivate rather than erase an account."""
    await service.deactivate(repo, actor, identifier)
    return Response(status_code=204)


@router.get('/roles', response_model=RolePage)
async def roles(actor: Annotated[dict, Depends(ready_user)], repo: Annotated[AdminRepository, Depends(get_repo)], offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)) -> dict:
    """List the six role policies."""
    await service.authorize(repo, actor, 'administer')
    return await repo.page('roles', {}, offset, limit)


@router.post('/roles', response_model=Role, status_code=201)
async def create_role(payload: RoleInput, actor: Annotated[dict, Depends(ready_user)], repo: Annotated[AdminRepository, Depends(get_repo)]) -> dict:
    """Create a supported role if it does not exist."""
    return await service.save_role(repo, actor, payload)


@router.put('/roles/{identifier}', response_model=Role)
async def update_role(identifier: str, payload: RoleInput, actor: Annotated[dict, Depends(ready_user)], repo: Annotated[AdminRepository, Depends(get_repo)]) -> dict:
    """Change a role's permitted policy within its ceiling."""
    return await service.save_role(repo, actor, payload, identifier)


@router.get('/audit-logs', response_model=AuditPage)
async def audit_logs(actor: Annotated[dict, Depends(ready_user)], repo: Annotated[AdminRepository, Depends(get_repo)],
                     userId: str | None = Query(None, max_length=100), action: Literal['login', 'create', 'edit', 'delete', 'roleChange', 'permissionChange', 'export'] | None = None,
                     start: datetime | None = Query(None, alias='from'), end: datetime | None = Query(None, alias='to'),
                     offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100), format: Literal['json', 'csv'] = 'json') -> dict | Response:
    """Read or export a filtered, bounded page of audit records."""
    await service.authorize(repo, actor, 'view', audit=True)
    query = service.audit_query(userId, action, start, end)
    if format == 'csv':
        content = await service.export_audit(repo, actor, query, offset, limit)
        return Response(content, media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="audit-log.csv"'})
    return await repo.page('audit_logs', query, offset, limit)
