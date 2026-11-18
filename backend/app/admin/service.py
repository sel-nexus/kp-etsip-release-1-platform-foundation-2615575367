"""Enforce administration policy and sensitive change rules."""

import asyncio
import csv
import io
from datetime import datetime, timezone
from fastapi import HTTPException
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from app.admin.repository import AdminRepository
from app.admin.schemas import RoleInput, UserCreate, UserInput
from app.core.security import hash_password
from app.core.seed import ROLE_PERMISSIONS


async def authorize(repo: AdminRepository, actor: dict, permission: str, audit: bool = False) -> None:
    """Require the appropriate role and its currently enabled permission."""
    role = actor.get('role', '')
    if role not in (('Administrator', 'Auditor') if audit else ('Administrator',)):
        raise HTTPException(403, 'Permission denied')
    if permission not in ROLE_PERMISSIONS.get(role, []) or permission not in await repo.permissions(role):
        raise HTTPException(403, 'Permission denied')


async def find(repo: AdminRepository, collection: str, identifier: str) -> dict:
    """Resolve a managed record or return not found."""
    row = await repo.get(collection, identifier)
    if row is None:
        raise HTTPException(404, 'Record not found')
    return row


async def save_user(repo: AdminRepository, actor: dict, payload: UserInput | UserCreate, identifier: str | None = None) -> dict:
    """Create or update an account while preserving audit references."""
    await authorize(repo, actor, 'administer')
    previous = await find(repo, 'users', identifier) if identifier else None
    if not await repo.valid_portfolios(payload.portfolioAccess):
        raise HTTPException(422, 'Invalid portfolio assignment')
    fields = payload.model_dump(exclude={'password'})
    fields['portfolioAccess'] = [str(ObjectId(value)) for value in fields['portfolioAccess']]
    if identifier and str(actor['_id']) == identifier and (fields['status'] != 'Active' or fields['role'] != 'Administrator'):
        raise HTTPException(409, 'Cannot deactivate or change your own administrator role')
    if identifier is None:
        assert isinstance(payload, UserCreate)
        fields.update(passwordHash=await asyncio.to_thread(hash_password, payload.password), mustChangePassword=True,
                      lastLogin=None, authSource='local', defaultLandingPage=None, tokenVersion=0)
    try:
        row = await repo.insert('users', fields) if identifier is None else await repo.update('users', identifier, fields, invalidate=(previous['role'] != fields['role'] or previous['status'] != fields['status']))
    except DuplicateKeyError as exc:
        raise HTTPException(409, 'Email already exists') from exc
    if row is None:
        raise HTTPException(404, 'Record not found')
    key = str(row['_id'])
    await repo.audit(actor, 'create' if previous is None else 'edit', 'user', key, 'User created' if previous is None else 'User updated')
    if previous and previous['role'] != row['role']:
        await repo.audit(actor, 'roleChange', 'user', key, f"Role changed from {previous['role']} to {row['role']}")
    return row


async def deactivate(repo: AdminRepository, actor: dict, identifier: str) -> None:
    """Deactivate an account without deleting its history."""
    await authorize(repo, actor, 'administer')
    await find(repo, 'users', identifier)
    if str(actor['_id']) == identifier:
        raise HTTPException(409, 'Cannot deactivate your own account')
    row = await repo.update('users', identifier, {'status': 'Inactive'}, invalidate=True)
    if row is None:
        raise HTTPException(404, 'Record not found')
    await repo.audit(actor, 'delete', 'user', identifier, 'User deactivated')


async def save_role(repo: AdminRepository, actor: dict, payload: RoleInput, identifier: str | None = None) -> dict:
    """Enforce role ceilings and persist a role or its permissions."""
    await authorize(repo, actor, 'administer')
    if not set(payload.permissions).issubset(ROLE_PERMISSIONS[payload.name]):
        raise HTTPException(422, 'Permissions exceed role ceiling')
    previous = await find(repo, 'roles', identifier) if identifier else None
    if previous and previous['name'] != payload.name:
        raise HTTPException(422, 'Role names cannot be changed')
    try:
        row = await repo.insert('roles', payload.model_dump()) if identifier is None else await repo.update('roles', identifier, payload.model_dump())
    except DuplicateKeyError as exc:
        raise HTTPException(409, 'Role already exists') from exc
    if row is None:
        raise HTTPException(404, 'Record not found')
    await repo.audit(actor, 'create' if previous is None else 'edit', 'role', str(row['_id']), f"Role {'created' if previous is None else 'updated'}: {row['name']}")
    if previous and set(previous.get('permissions', [])) != set(row['permissions']):
        await repo.audit(actor, 'permissionChange', 'role', str(row['_id']), f"Permissions changed for {row['name']}")
    return row


def audit_query(user_id: str | None, action: str | None, start: datetime | None, end: datetime | None) -> dict:
    """Build validated date and actor filters for the audit log."""
    if start and start.tzinfo is None or end and end.tzinfo is None:
        raise HTTPException(422, 'Date filters must include a timezone')
    if start and end and start > end:
        raise HTTPException(422, 'Start date must not be after end date')
    query: dict = {}
    if user_id:
        query['userId'] = user_id
    if action:
        query['action'] = action
    if start or end:
        query['timestamp'] = {}
        if start:
            query['timestamp']['$gte'] = start.astimezone(timezone.utc)
        if end:
            query['timestamp']['$lte'] = end.astimezone(timezone.utc)
    return query


def csv_value(value: object) -> str:
    """Neutralize spreadsheet formulas and retain ordinary text."""
    text = '' if value is None else str(value)
    if text.lstrip(' \t\r\n').startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')):
        return "'" + text
    return text


async def export_audit(repo: AdminRepository, actor: dict, query: dict, offset: int, limit: int) -> str:
    """Export one bounded audit page and record the export."""
    await authorize(repo, actor, 'view', audit=True)
    await authorize(repo, actor, 'export', audit=True)
    page = await repo.page('audit_logs', query, offset, limit)
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    keys = ['timestamp', 'userId', 'userName', 'action', 'entityType', 'entityId', 'details']
    writer.writerow(keys)
    for row in page['items']:
        writer.writerow([csv_value(row.get(key)) for key in keys])
    await repo.audit(actor, 'export', 'audit', None, 'Audit log exported')
    return output.getvalue()
