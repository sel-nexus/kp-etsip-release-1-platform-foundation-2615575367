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
    checked_response_1 = await client.get('/api/users', headers=headers, params={'search': 'PERSON'})
    assert checked_response_1.status_code == 200, checked_response_1.text
    assert checked_response_1.json()['total'] == 1
    checked_response_2 = await client.get('/api/users', headers=headers, params={'search': '.*'})
    assert checked_response_2.status_code == 200, checked_response_2.text
    assert checked_response_2.json()['total'] == 0
    assert (await client.get('/api/users', headers=headers, params={'limit': 101})).status_code == 422
    old_token = {'Authorization': 'Bearer ' + create_access_token(stored)}
    edit = {k: v for k, v in payload(role='Portfolio Leader', portfolioAccess=[portfolio]).items() if k != 'password'}
    updated = await client.put('/api/users/' + user['id'], headers=headers, json=edit)
    assert updated.status_code == 200 and updated.json()['role'] == 'Portfolio Leader'
    assert (await db.users.find_one({'_id': ObjectId(user['id'])}))['role'] == 'Portfolio Leader'
    assert (await client.get('/api/auth/me', headers=old_token)).status_code == 401
    checked_response_3 = await client.get('/api/users/' + user['id'], headers=headers)
    assert checked_response_3.status_code == 200, checked_response_3.text
    assert checked_response_3.json()['portfolioAccess'] == [portfolio]
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
    checked_response_4 = await client.get('/api/roles', headers=admin)
    assert checked_response_4.status_code == 200, checked_response_4.text
    roles = checked_response_4.json()
    assert roles['total'] == 6
    role = next(item for item in roles['items'] if item['name'] == 'Auditor')
    assert (await client.put('/api/roles/' + role['id'], headers=auditor, json={'name': 'Auditor', 'description': '', 'permissions': ['view']})).status_code == 403
    assert (await client.post('/api/roles', headers=admin, json={'name': 'Auditor', 'description': '', 'permissions': ['view']})).status_code == 409
    bad = {'name': 'Auditor', 'description': '', 'permissions': ['view', 'administer']}
    assert (await client.put('/api/roles/' + role['id'], headers=admin, json=bad)).status_code == 422
    good = {'name': 'Auditor', 'description': 'Audit review', 'permissions': ['view']}
    assert (await client.put('/api/roles/' + role['id'], headers=admin, json=good)).status_code == 200
    assert (await db.roles.find_one({'_id': ObjectId(role['id'])}))['permissions'] == ['view']
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


async def test_create_missing_seeded_role_and_verify_persistence(environment):
    client, db = environment
    admin = await credentials(db)
    assert (await db.roles.delete_one({'name': 'Auditor'})).deleted_count == 1
    body = {'name': 'Auditor', 'description': 'Restored', 'permissions': ['view', 'export']}
    created = await client.post('/api/roles', headers=admin, json=body)
    assert created.status_code == 201
    identifier = created.json()['id']
    stored = await db.roles.find_one({'_id': ObjectId(identifier)})
    assert stored['description'] == 'Restored' and stored['permissions'] == ['view', 'export']
    listing = await client.get('/api/roles', headers=admin)
    assert listing.status_code == 200 and any(row['id'] == identifier for row in listing.json()['items'])
    assert (await client.post('/api/roles', headers=admin, json=body)).status_code == 409
    assert await db.audit_logs.count_documents({'action': 'create', 'entityType': 'role', 'entityId': identifier}) == 1


async def test_user_and_role_create_reject_invalid_inputs_and_missing_resources_return_404(environment):
    client, db = environment
    admin = await credentials(db)
    body = payload()
    for field in ('name', 'email', 'role', 'password'):
        assert (await client.post('/api/users', headers=admin, json={k: v for k, v in body.items() if k != field})).status_code == 422
    for change in ({'name': ''}, {'name': 'x' * 201}, {'email': {'$ne': ''}},
                   {'portfolioAccess': {'$ne': []}}, {'role': 'Unknown'}, {'password': 'x' * 73}):
        assert (await client.post('/api/users', headers=admin, json={**body, **change})).status_code == 422
    for role in ({'permissions': ['view']}, {'name': 'Auditor'}, {'name': 'Auditor', 'permissions': ['view', 'view']},
                 {'name': {'$ne': ''}, 'permissions': ['view']}, {'name': 'Auditor', 'description': 'x' * 1001, 'permissions': ['view']}):
        assert (await client.post('/api/roles', headers=admin, json=role)).status_code == 422
    missing = str(ObjectId())
    for identifier in ('bad-id', missing):
        assert (await client.get('/api/users/' + identifier, headers=admin)).status_code == 404
        assert (await client.put('/api/users/' + identifier, headers=admin, json={k: v for k, v in body.items() if k != 'password'})).status_code == 404
        assert (await client.delete('/api/users/' + identifier, headers=admin)).status_code == 404
        assert (await client.put('/api/roles/' + identifier, headers=admin, json={'name': 'Auditor', 'permissions': ['view']})).status_code == 404
    assert await db.users.count_documents({'email': 'person@example.com'}) == 0


async def test_user_put_rejects_missing_invalid_and_oversized_fields_without_mutation(environment):
    client, db = environment
    admin = await credentials(db)
    portfolio = str((await db.portfolios.find_one({}))['_id'])
    created = await client.post('/api/users', headers=admin, json=payload(portfolioAccess=[portfolio]))
    assert created.status_code == 201, created.text
    identifier = created.json()['id']
    before = await db.users.find_one({'_id': ObjectId(identifier)})
    audit_before = await db.audit_logs.count_documents({'entityId': identifier})
    valid = {key: value for key, value in payload(portfolioAccess=[portfolio]).items() if key != 'password'}
    cases = [({key: value for key, value in valid.items() if key != field}, field)
             for field in ('name', 'email', 'role')]
    for field, value in (
        ('name', None), ('name', {'$ne': ''}), ('name', ''), ('name', '  '), ('name', 'x' * 201),
        ('email', None), ('email', {'$ne': ''}), ('email', ''), ('email', 'bad'), ('email', 'x' * 255),
        ('role', None), ('role', {'$ne': ''}), ('role', ''), ('role', 'Unknown'),
        ('portfolioAccess', {'$ne': []}), ('portfolioAccess', [123]), ('portfolioAccess', ['x'] * 1001),
        ('status', None), ('status', {'$ne': ''}), ('status', 'Unknown'),
        ('managerName', 123), ('managerName', 'x' * 201), ('vendorIndicator', {'$ne': False}),
    ):
        cases.append(({**valid, field: value}, field))
    for body, field in cases:
        response = await client.put('/api/users/' + identifier, headers=admin, json=body)
        assert response.status_code == 422, (field, response.text)
        assert any(error['loc'][:2] == ['body', field] for error in response.json()['detail']), (field, response.text)
        assert await db.users.find_one({'_id': ObjectId(identifier)}) == before
        assert await db.audit_logs.count_documents({'entityId': identifier}) == audit_before


async def test_duplicate_portfolio_assignments_rejected_on_create_and_update(environment):
    client, db = environment
    admin = await credentials(db)
    portfolio = str((await db.portfolios.find_one({}))['_id'])
    duplicate = payload(portfolioAccess=[portfolio, portfolio])
    assert (await client.post('/api/users', headers=admin, json=duplicate)).status_code == 422
    created = await client.post('/api/users', headers=admin, json=payload(portfolioAccess=[portfolio]))
    assert created.status_code == 201
    identifier = created.json()['id']
    edit = {key: value for key, value in duplicate.items() if key != 'password'}
    assert (await client.put('/api/users/' + identifier, headers=admin, json=edit)).status_code == 422
    reread = await client.get('/api/users/' + identifier, headers=admin)
    assert reread.status_code == 200 and reread.json()['portfolioAccess'] == [portfolio]
    assert (await db.users.find_one({'_id': ObjectId(identifier)}))['portfolioAccess'] == [portfolio]
