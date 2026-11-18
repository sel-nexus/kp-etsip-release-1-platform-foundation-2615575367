"""Persist administration records in the shared MongoDB database."""

import re
from datetime import datetime, timezone
from bson import ObjectId
from bson.errors import InvalidDocument
from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import WriteError
from app.applications.repository import ApplicationRepository


class AdminRepository:
    """Provide bounded queries and atomic document updates."""

    def __init__(self, db: AsyncDatabase) -> None:
        """Bind to the application's database."""
        self.db = db

    async def permissions(self, role: str) -> list[str]:
        """Read the persisted permissions for a role."""
        row = await self.db.roles.find_one({'name': role})
        return row.get('permissions', []) if row else []

    async def get(self, collection: str, identifier: str) -> dict | None:
        """Read a document using its external identifier."""
        if not ObjectId.is_valid(identifier):
            return None
        return await self.db[collection].find_one({'_id': ObjectId(identifier)})

    async def page(self, collection: str, query: dict, offset: int, limit: int) -> dict:
        """Fetch a stable bounded page and count."""
        sort = [('timestamp', -1), ('_id', -1)] if collection == 'audit_logs' else [('name', 1), ('_id', 1)]
        projection = {'passwordHash': 0} if collection == 'users' else None
        items = await self.db[collection].find(query, projection).sort(sort).skip(offset).limit(limit).to_list(None)
        return {'items': items, 'total': await self.db[collection].count_documents(query), 'offset': offset, 'limit': limit}

    async def insert(self, collection: str, fields: dict) -> dict:
        """Insert a timestamped document."""
        now = datetime.now(timezone.utc)
        row = {**fields, 'createdAt': now, 'updatedAt': now}
        reservations = await self.reserve_assignments(fields.get('portfolioAccess', [])) if collection == 'users' else []
        try:
            await self.db[collection].insert_one(row)
        except (WriteError, InvalidDocument):
            await self.release_assignments(reservations)
            raise
        await self.release_assignments(reservations)
        return row

    async def update(self, collection: str, identifier: str, fields: dict, invalidate: bool = False) -> dict | None:
        """Update and return an existing document."""
        if not ObjectId.is_valid(identifier):
            return None
        update = {'$set': {**fields, 'updatedAt': datetime.now(timezone.utc)}}
        if invalidate:
            update['$inc'] = {'tokenVersion': 1}
        reservations = await self.reserve_assignments(fields.get('portfolioAccess', [])) if collection == 'users' else []
        try:
            row = await self.db[collection].find_one_and_update({'_id': ObjectId(identifier)}, update, return_document=ReturnDocument.AFTER)
        except (WriteError, InvalidDocument):
            await self.release_assignments(reservations)
            raise
        await self.release_assignments(reservations)
        return row

    async def reserve_assignments(self, identifiers: list[str]) -> list[tuple[str, str]]:
        """Protect new assignments while their user document is written.

        Crashes and uncertain writes may leave reservations requiring manual
        reconciliation. Releasing them without confirming the outcome is unsafe.
        """
        repo = ApplicationRepository(self.db)
        reservations: list[tuple[str, str]] = []
        try:
            for identifier in identifiers:
                token = await repo.reserve(identifier)
                if token is None:
                    raise HTTPException(422, 'Invalid portfolio assignment')
                reservations.append((identifier, token))
        except Exception:
            await self.release_assignments(reservations)
            raise
        return reservations

    async def release_assignments(self, reservations: list[tuple[str, str]]) -> None:
        """Release known completed or aborted assignment reservations."""
        repo = ApplicationRepository(self.db)
        for identifier, token in reservations:
            await repo.release(identifier, token)

    async def valid_portfolios(self, identifiers: list[str]) -> bool:
        """Verify every assignment points to an existing portfolio."""
        if any(not ObjectId.is_valid(value) for value in identifiers):
            return False
        return await self.db.portfolios.count_documents({'_id': {'$in': [ObjectId(value) for value in identifiers]}}) == len(identifiers)

    async def audit(self, actor: dict, action: str, entity: str, identifier: str | None, details: str) -> None:
        """Record a sensitive action without credential data."""
        now = datetime.now(timezone.utc)
        await self.db.audit_logs.insert_one({'timestamp': now, 'createdAt': now, 'updatedAt': now,
            'userId': str(actor['_id']), 'userName': actor['name'], 'action': action,
            'entityType': entity, 'entityId': identifier, 'details': details})


def user_query(search: str) -> dict:
    """Build a literal case-insensitive account search."""
    if not search:
        return {}
    pattern = {'$regex': re.escape(search), '$options': 'i'}
    return {'$or': [{'name': pattern}, {'email': pattern}]}
