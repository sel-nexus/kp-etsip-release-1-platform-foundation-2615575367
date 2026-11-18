"""Exercise administration security and persistence using real MongoDB."""

from datetime import datetime, timedelta, timezone
import csv
import io
import pytest
from bson import ObjectId
from app.core.security import create_access_token, verify_password

pytestmark = pytest.mark.asyncio


async def credentials(db, role='Administrator', ready=True):
    """Create a bearer token for a seeded account."""
    await db.users.update_one({'role': role}, {'$set': {'mustChangePassword': not ready}})
    user = await db.users.find_one({'role': role})
    return {'Authorization': 'Bearer ' + create_access_token(user)}


def payload(**changes):
    """Build an account creation request."""
    return {'name': 'New Person', 'email': 'PERSON@example.com', 'password': 'StrongPassword123!', 'role': 'Engineer', 'portfolioAccess': [], 'status': 'Active', 'managerName': None, 'vendorIndicator': False, **changes}


async def test_user_crud_validation_and_persistence(environment):
    """Create, update, inspect and deactivate a user without erasing history."""
    client, db = environment
    headers = await credentials(db)
    portfolio = str((await db.portfolios.find_one({}))['_id'])
    created = await client.post('/api/users', headers=headers, json=payload(portfolioAccess=[portfolio]))
    assert created.status_code == 201, created.text
    user = created.json()
    assert user['email'] == 'person@example.com' and user['mustChangePassword']
    assert 'passwordHash' not in user and 'password' not in user
    stored = await db.users.find_one({'_id': ObjectId(user['id'])})
    assert verify_password('StrongPassword123!', stored['passwordHash'])
    assert (await client.post('/api/users', headers=headers, json=payload())).status_code == 409
    assert (await client.post('/api/users', headers=headers, json=payload(email='bad'))).status_code == 422
    assert (await client.post('/api/users', headers=headers, json=payload(email='other@example.com', portfolioAccess=['bad']))).status_code == 422
    assert (await client.post('/api/users', headers=headers, json=payload(email='other@example.com', password='é' * 40))).status_code == 422
    assert (await client.get('/api/users', headers=headers, params={'search': 'PERSON'})).json()['total'] == 1
    assert (await client.get('/api/users', headers=headers, params={'search': '.*'})).json()['total'] == 0
    assert (await client.get('/api/users', headers=headers, params={'limit': 101})).status_code == 422
    old_token = {'Authorization': 'Bearer ' + create_access_token(stored)}
    edit = {k: v for k, v in payload(role='Portfolio Leader', portfolioAccess=[portfolio]).items() if k != 'password'}
    updated = await client.put('/api/users/' + user['id'], headers=headers, json=edit)
    assert updated.status_code == 200 and updated.json()['role'] == 'Portfolio Leader'
    assert (await client.get('/api/auth/me', headers=old_token)).status_code == 401
    assert (await client.get('/api/users/' + user['id'], headers=headers)).json()['portfolioAccess'] == [portfolio]
    assert (await client.delete('/api/users/' + user['id'], headers=headers)).status_code == 204
    assert (await db.users.find_one({'_id': ObjectId(user['id'])}))['status'] == 'Inactive'
    assert (await client.post('/api/auth/login', json={'email': user['email'], 'password': 'StrongPassword123!'})).status_code == 401
    assert (await client.get('/api/users/not-id', headers=headers)).status_code == 404
    actions = [event['action'] async for event in db.audit_logs.find({'entityId': user['id']})]
    assert {'create', 'edit', 'roleChange', 'delete'}.issubset(actions)
    assert all('StrongPassword123!' not in str(event) for event in await db.audit_logs.find({}).to_list(None))


async def test_role_ceiling_and_access_boundaries(environment):
    """Restrict role changes and audit access to authorized ready users."""
    client, db = environment
    admin = await credentials(db)
    auditor = await credentials(db, 'Auditor')
    reader = await credentials(db, 'Read Only')
    assert (await client.get('/api/users')).status_code == 401
    gated = await credentials(db, ready=False)
    assert (await client.get('/api/users', headers=gated)).status_code == 403
    admin = await credentials(db)
    for path in ['/api/users', '/api/roles']:
        assert (await client.get(path, headers=auditor)).status_code == 403
    assert (await client.post('/api/users', headers=auditor, json=payload())).status_code == 403
    assert (await client.get('/api/audit-logs', headers=reader)).status_code == 403
    roles = (await client.get('/api/roles', headers=admin)).json()
    assert roles['total'] == 6
    role = next(item for item in roles['items'] if item['name'] == 'Auditor')
    assert (await client.put('/api/roles/' + role['id'], headers=auditor, json={'name': 'Auditor', 'description': '', 'permissions': ['view']})).status_code == 403
    assert (await client.post('/api/roles', headers=admin, json={'name': 'Auditor', 'description': '', 'permissions': ['view']})).status_code == 409
    bad = {'name': 'Auditor', 'description': '', 'permissions': ['view', 'administer']}
    assert (await client.put('/api/roles/' + role['id'], headers=admin, json=bad)).status_code == 422
    good = {'name': 'Auditor', 'description': 'Audit review', 'permissions': ['view']}
    assert (await client.put('/api/roles/' + role['id'], headers=admin, json=good)).status_code == 200
    assert (await client.get('/api/audit-logs', headers=auditor)).status_code == 200
    assert (await client.get('/api/audit-logs?format=csv', headers=auditor)).status_code == 403
    assert await db.audit_logs.count_documents({'action': 'permissionChange', 'entityId': role['id']}) == 1
    assert (await client.put('/api/roles/not-id', headers=admin, json=good)).status_code == 404


async def test_audit_filter_pagination_csv_and_export(environment):
    """Filter persisted audit events and prevent spreadsheet formula execution."""
    client, db = environment
    auditor = await credentials(db, 'Auditor')
    now = datetime.now(timezone.utc)
    await db.audit_logs.insert_one({'timestamp': now, 'userId': 'target', 'userName': '=HYPERLINK("x")', 'action': 'edit', 'entityType': 'user', 'entityId': 'a', 'details': '+formula', 'createdAt': now, 'updatedAt': now})
    params = {'userId': 'target', 'action': 'edit', 'from': (now - timedelta(minutes=1)).isoformat(), 'to': (now + timedelta(minutes=1)).isoformat(), 'limit': 1}
    result = await client.get('/api/audit-logs', headers=auditor, params=params)
    assert result.status_code == 200 and result.json()['total'] == 1
    csv_result = await client.get('/api/audit-logs', headers=auditor, params={**params, 'format': 'csv'})
    assert csv_result.status_code == 200
    rows = list(csv.DictReader(io.StringIO(csv_result.text)))
    assert rows[0]['userName'].startswith("'=") and rows[0]['details'].startswith("'+")
    assert await db.audit_logs.count_documents({'action': 'export', 'entityType': 'audit'}) == 1
    assert (await client.get('/api/audit-logs', headers=auditor, params={'from': now.isoformat(), 'to': (now - timedelta(days=1)).isoformat()})).status_code == 422
    assert (await client.get('/api/audit-logs', headers=auditor, params={'offset': -1})).status_code == 422
