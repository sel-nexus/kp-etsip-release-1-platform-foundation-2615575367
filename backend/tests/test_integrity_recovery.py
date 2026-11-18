"""Exercise reference protection and reservation recovery with real MongoDB."""

import asyncio
import pytest
from bson import ObjectId
from bson.errors import InvalidDocument
from pymongo.errors import AutoReconnect, WriteError
from pymongo.asynchronous.collection import AsyncCollection
from app.applications.repository import ApplicationRepository
from app.admin.repository import AdminRepository
from app.core.security import create_access_token
from app.portfolios.repository import PortfolioRepository
from fastapi import HTTPException

pytestmark = pytest.mark.asyncio


async def admin_headers(db):
    """Make the seeded administrator ready for API calls."""
    await db.users.update_one({'role': 'Administrator'}, {'$set': {'mustChangePassword': False}})
    user = await db.users.find_one({'role': 'Administrator'})
    return {'Authorization': 'Bearer ' + create_access_token(user)}


async def test_delete_rejects_user_references_including_inactive_accounts(environment):
    client, db = environment
    headers = await admin_headers(db)
    created = await client.post('/api/portfolios', headers=headers, json={'name': 'Assigned only'})
    assert created.status_code == 201, created.text
    identifier = created.json()['id']
    await db.users.update_one({'role': 'Engineer'}, {'$set': {'portfolioAccess': [identifier], 'status': 'Inactive'}})
    response = await client.delete('/api/portfolios/' + identifier, headers=headers)
    assert response.status_code == 409
    assert await db.portfolios.find_one({'_id': ObjectId(identifier)})
    assert (await db.users.find_one({'role': 'Engineer'}))['portfolioAccess'] == [identifier]
    await db.users.update_one({'role': 'Engineer'}, {'$set': {'portfolioAccess': []}})
    assert (await client.delete('/api/portfolios/' + identifier, headers=headers)).status_code == 204


async def test_definite_insert_validation_failure_releases_reservation(environment):
    _, db = environment
    pid = str((await db.portfolios.insert_one({'name': 'Validation target'})).inserted_id)
    await db.command({'collMod': 'applications', 'validator': {'$jsonSchema': {'required': ['requiredByTest']}}})
    with pytest.raises(WriteError):
        await ApplicationRepository(db).insert({'name': 'Invalid', 'portfolioId': pid})
    portfolio = await db.portfolios.find_one({'_id': ObjectId(pid)})
    assert portfolio.get('applicationReservations', []) == []
    assert not await db.applications.find_one({'name': 'Invalid'})


async def test_invalid_bson_releases_reservation(environment):
    _, db = environment
    pid = str((await db.portfolios.insert_one({'name': 'Invalid BSON target'})).inserted_id)
    with pytest.raises(InvalidDocument):
        await ApplicationRepository(db).insert({'name': 'Invalid BSON', 'portfolioId': pid, 'invalid': object()})
    assert (await db.portfolios.find_one({'_id': ObjectId(pid)})).get('applicationReservations', []) == []
    assert not await db.applications.find_one({'name': 'Invalid BSON'})


async def test_definite_update_validation_failure_releases_new_reservation(environment):
    _, db = environment
    old_pid = str((await db.portfolios.insert_one({'name': 'Old target'})).inserted_id)
    new_pid = str((await db.portfolios.insert_one({'name': 'New target'})).inserted_id)
    repo = ApplicationRepository(db)
    old = await repo.insert({'name': 'Moving', 'portfolioId': old_pid, 'valid': True})
    await db.command({'collMod': 'applications', 'validator': {'valid': True}})
    with pytest.raises(WriteError):
        await repo.update(old, {'name': 'Moving', 'portfolioId': new_pid, 'valid': False})
    assert (await db.applications.find_one({'_id': old['_id']}))['portfolioId'] == old_pid
    assert (await db.portfolios.find_one({'_id': ObjectId(new_pid)})).get('applicationReservations', []) == []
    assert old['reservation'] in (await db.portfolios.find_one({'_id': ObjectId(old_pid)}))['applicationReservations']


async def test_ambiguous_insert_after_write_retains_reservation(environment, monkeypatch):
    _, db = environment
    pid = str((await db.portfolios.insert_one({'name': 'Ambiguous target'})).inserted_id)
    original = AsyncCollection.insert_one

    async def written_then_disconnected(collection, document, *args, **kwargs):
        result = await original(collection, document, *args, **kwargs)
        if collection.name == 'applications':
            raise AutoReconnect('lost acknowledgement')
        return result

    monkeypatch.setattr(AsyncCollection, 'insert_one', written_then_disconnected)
    with pytest.raises(AutoReconnect):
        await ApplicationRepository(db).insert({'name': 'Ambiguous', 'portfolioId': pid})
    row = await db.applications.find_one({'name': 'Ambiguous'})
    assert row and row['reservation'] in (await db.portfolios.find_one({'_id': ObjectId(pid)}))['applicationReservations']


async def test_case_variant_user_reference_is_protected(environment):
    client, db = environment
    headers = await admin_headers(db)
    created = await client.post('/api/portfolios', headers=headers, json={'name': 'Case reference'})
    assert created.status_code == 201, created.text
    identifier = created.json()['id']
    await db.users.update_one({'role': 'Engineer'}, {'$set': {'portfolioAccess': [identifier.upper()]}})
    assert (await client.delete('/api/portfolios/' + identifier, headers=headers)).status_code == 409
    assert await db.portfolios.find_one({'_id': ObjectId(identifier)})


async def test_ambiguous_move_after_write_preserves_both_reservations(environment, monkeypatch):
    _, db = environment
    old_pid = str((await db.portfolios.insert_one({'name': 'Ambiguous old'})).inserted_id)
    new_pid = str((await db.portfolios.insert_one({'name': 'Ambiguous new'})).inserted_id)
    repo = ApplicationRepository(db)
    old = await repo.insert({'name': 'Ambiguous move', 'portfolioId': old_pid})
    original = AsyncCollection.update_one

    async def written_then_disconnected(collection, query, update, *args, **kwargs):
        result = await original(collection, query, update, *args, **kwargs)
        if collection.name == 'applications':
            raise AutoReconnect('lost acknowledgement')
        return result

    monkeypatch.setattr(AsyncCollection, 'update_one', written_then_disconnected)
    with pytest.raises(AutoReconnect):
        await repo.update(old, {'name': 'Ambiguous move', 'portfolioId': new_pid})
    row = await db.applications.find_one({'_id': old['_id']})
    assert row['portfolioId'] == new_pid
    assert row['reservation'] in (await db.portfolios.find_one({'_id': ObjectId(new_pid)}))['applicationReservations']
    assert old['reservation'] in (await db.portfolios.find_one({'_id': ObjectId(old_pid)}))['applicationReservations']


async def test_ambiguous_delete_keeps_lock_and_blocks_assignments(environment, monkeypatch):
    _, db = environment
    pid = str((await db.portfolios.insert_one({'name': 'Uncertain deletion'})).inserted_id)
    original = AsyncCollection.delete_one

    async def uncertain_delete(collection, query, *args, **kwargs):
        if collection.name == 'portfolios':
            raise AutoReconnect('unknown deletion outcome')
        return await original(collection, query, *args, **kwargs)

    monkeypatch.setattr(AsyncCollection, 'delete_one', uncertain_delete)
    with pytest.raises(AutoReconnect):
        await PortfolioRepository(db).delete(pid)
    assert (await db.portfolios.find_one({'_id': ObjectId(pid)}))['deletionLock']
    assert await ApplicationRepository(db).reserve(pid) is None


async def test_user_write_failure_and_partial_reservations_are_released(environment):
    _, db = environment
    pid = str((await db.portfolios.insert_one({'name': 'User validation target'})).inserted_id)
    repo = AdminRepository(db)
    with pytest.raises(HTTPException) as error:
        await repo.insert('users', {'email': 'new@example.com', 'portfolioAccess': [pid, str(ObjectId())]})
    assert error.value.status_code == 422
    assert (await db.portfolios.find_one({'_id': ObjectId(pid)})).get('applicationReservations', []) == []
    await db.command({'collMod': 'users', 'validator': {'$jsonSchema': {'required': ['requiredByTest']}}})
    with pytest.raises(WriteError):
        await repo.insert('users', {'email': 'new@example.com', 'portfolioAccess': [pid]})
    assert (await db.portfolios.find_one({'_id': ObjectId(pid)})).get('applicationReservations', []) == []


async def test_assignment_and_delete_race_cannot_leave_orphan(environment):
    client, db = environment
    headers = await admin_headers(db)
    for index in range(8):
        created = await client.post('/api/portfolios', headers=headers, json={'name': f'Assignment race {index}'})
        assert created.status_code == 201, created.text
        pid = created.json()['id']
        body = {'name': 'Race Person', 'email': f'race-{index}@example.com', 'password': 'StrongPassword123!',
                'role': 'Engineer', 'portfolioAccess': [pid], 'status': 'Active'}
        assignment, deletion = await asyncio.gather(client.post('/api/users', headers=headers, json=body),
                                                     client.delete('/api/portfolios/' + pid, headers=headers))
        assert assignment.status_code in (201, 422)
        assert deletion.status_code in (204, 409)
        if await db.users.find_one({'portfolioAccess': pid}):
            assert await db.portfolios.find_one({'_id': ObjectId(pid)})
