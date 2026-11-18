"""Cross-feature HTTP journeys against the isolated real MongoDB fixture."""

import csv
import io
import os

import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient
from pymongo import AsyncMongoClient

from app.main import app

pytestmark = pytest.mark.asyncio

INITIAL_PASSWORD = "DemoPassword123!"
NEW_PASSWORD = "ChangedPassword123!"


async def sign_in_and_change_password(client, email, password=INITIAL_PASSWORD):
    """Complete the first-login password change through the public API."""
    login = await client.post('/api/auth/login', json={'email': email, 'password': password})
    assert login.status_code == 200, login.text
    body = login.json()
    assert body['user']['mustChangePassword'] is True
    initial = {'Authorization': 'Bearer ' + body['token']}
    assert (await client.get('/api/dashboard/executive', headers=initial)).status_code == 403
    changed = await client.post('/api/auth/password', headers=initial, json={
        'currentPassword': password, 'newPassword': NEW_PASSWORD,
    })
    assert changed.status_code == 200, changed.text
    assert (await client.get('/api/auth/me', headers=initial)).status_code == 401
    assert (await client.post('/api/auth/login', json={'email': email, 'password': password})).status_code == 401
    renewed = await client.post('/api/auth/login', json={'email': email, 'password': NEW_PASSWORD})
    assert renewed.status_code == 200, renewed.text
    assert renewed.json()['user']['mustChangePassword'] is False
    return {'Authorization': 'Bearer ' + renewed.json()['token']}, renewed.json()['user']['id']


def application_payload(portfolio_id, name, **changes):
    """Build a valid application with known values for derived metrics."""
    return {
        'name': name, 'portfolioId': portfolio_id, 'productArea': 'Integration Area',
        'criticality': 'High', 'tier': 2, 'lifecycleStatus': 'Active',
        'applicationHealthScore': 60, 'qualityScore': 80, 'automationCoverage': 40,
        'unitTestCoverage': 50, 'openDefects': 4, 'openCriticalDefects': 2,
        'riskLevel': 'High', **changes,
    }


def csv_rows(response):
    """Decode exported CSV into dictionaries for content assertions."""
    assert response.status_code == 200, response.text
    assert response.headers['content-type'].startswith('text/csv')
    return list(csv.DictReader(io.StringIO(response.text)))


async def test_login_inventory_insights_reports_audit_and_persistence(environment):
    """Carry HTTP-created and edited data through summaries, exports and audit."""
    client, db = environment
    admin, admin_id = await sign_in_and_change_password(client, 'admin@ketsip.local')
    profile = await client.put('/api/auth/profile', headers=admin, json={'defaultLandingPage': 'applications'})
    assert profile.status_code == 200 and profile.json()['defaultLandingPage'] == 'applications'

    created = await client.post('/api/portfolios', headers=admin, json={
        'name': 'Integration Portfolio', 'owner': 'Integration Owner', 'productArea': 'Integration Area',
    })
    assert created.status_code == 201, created.text
    pid = created.json()['id']
    assert created.json()['applicationCount'] == 0 and created.json()['qualityScore'] is None
    first_payload = application_payload(pid, 'Integration App One')
    first = await client.post('/api/applications', headers=admin, json=first_payload)
    second = await client.post('/api/applications', headers=admin, json=application_payload(
        pid, 'Integration App Two', qualityScore=81, applicationHealthScore=61,
        automationCoverage=41, openCriticalDefects=3, riskLevel='Low'))
    assert first.status_code == second.status_code == 201, (first.text, second.text)
    app_id = first.json()['id']
    assert first.json()['portfolioName'] == 'Integration Portfolio'

    params = {'portfolioId': pid}
    dashboard = await client.get('/api/dashboard/executive', headers=admin, params=params)
    assert dashboard.status_code == 200, dashboard.text
    assert {key: dashboard.json()[key] for key in (
        'enterpriseQualityScore', 'applicationHealthScore', 'automationMaturityScore',
        'openCriticalDefects', 'applicationsAtRisk', 'totalApplications', 'totalPortfolios',
    )} == {'enterpriseQualityScore': 81, 'applicationHealthScore': 61,
           'automationMaturityScore': 41, 'openCriticalDefects': 5,
           'applicationsAtRisk': 1, 'totalApplications': 2, 'totalPortfolios': 1}
    edited_payload = {**first_payload, 'qualityScore': 40, 'applicationHealthScore': 70,
                      'automationCoverage': 60, 'openCriticalDefects': 1, 'riskLevel': 'Low'}
    edited = await client.put(f'/api/applications/{app_id}', headers=admin, json=edited_payload)
    assert edited.status_code == 200, edited.text
    summary = await client.get(f'/api/portfolios/{pid}', headers=admin)
    assert summary.status_code == 200
    assert summary.json()['applicationCount'] == 2 and summary.json()['qualityScore'] == 61
    linked = await client.get(f'/api/portfolios/{pid}/applications', headers=admin)
    assert linked.status_code == 200 and linked.json()['total'] == 2
    assert {item['id'] for item in linked.json()['items']} == {app_id, second.json()['id']}
    dashboard = await client.get('/api/dashboard/executive', headers=admin, params=params)
    assert dashboard.status_code == 200
    assert {key: dashboard.json()[key] for key in (
        'enterpriseQualityScore', 'applicationHealthScore', 'automationMaturityScore',
        'openCriticalDefects', 'applicationsAtRisk', 'totalApplications',
    )} == {'enterpriseQualityScore': 61, 'applicationHealthScore': 66,
           'automationMaturityScore': 51, 'openCriticalDefects': 4,
           'applicationsAtRisk': 0, 'totalApplications': 2}
    assert dashboard.json()['portfolios'][0]['qualityScore'] == 61
    high = await client.get('/api/dashboard/executive', headers=admin, params={**params, 'riskLevel': 'High'})
    assert high.status_code == 200 and high.json()['totalApplications'] == 0 and high.json()['totalPortfolios'] == 0

    apps = await client.get('/api/reports/applications', headers=admin, params=params)
    portfolios = await client.get('/api/reports/portfolios', headers=admin, params=params)
    assert apps.status_code == portfolios.status_code == 200
    assert {row['id'] for row in apps.json()['items']} == {app_id, second.json()['id']}
    assert portfolios.json()['items'][0]['qualityScore'] == 61
    app_csv = csv_rows(await client.get('/api/reports/applications', headers=admin, params={**params, 'format': 'csv'}))
    portfolio_csv = csv_rows(await client.get('/api/reports/portfolios', headers=admin, params={**params, 'format': 'csv'}))
    assert {row['name'] for row in app_csv} == {'Integration App One', 'Integration App Two'}
    assert next(row for row in app_csv if row['name'] == 'Integration App One')['qualityScore'] == '40'
    assert len(portfolio_csv) == 1 and portfolio_csv[0]['qualityScore'] == '61'
    inventory_csv = csv_rows(await client.get('/api/applications/export', headers=admin, params=params))
    assert {row['name'] for row in inventory_csv} == {'Integration App One', 'Integration App Two'}

    audit = await client.get('/api/audit-logs', headers=admin, params={'userId': admin_id, 'limit': 100})
    assert audit.status_code == 200, audit.text
    events = audit.json()['items']
    assert any(e['action'] == 'login' and e['details'] == 'Login failed' for e in events)
    assert any(e['action'] == 'login' and e['details'] == 'Login succeeded' for e in events)
    assert any(e['action'] == 'create' and e['entityId'] == pid for e in events)
    assert any(e['action'] == 'create' and e['entityId'] == app_id for e in events)
    assert any(e['action'] == 'edit' and e['entityId'] == app_id for e in events)
    assert {'application', 'portfolio'} <= {e['entityType'] for e in events if e['action'] == 'export'}
    assert all(INITIAL_PASSWORD not in str(e) and NEW_PASSWORD not in str(e) for e in events)
    exported_audit = csv_rows(await client.get('/api/audit-logs', headers=admin, params={
        'userId': admin_id, 'action': 'edit', 'format': 'csv', 'limit': 100,
    }))
    assert any(row['entityId'] == app_id for row in exported_audit)

    # A fresh driver connection and HTTP client read the same database, not process-local state.
    mongo = AsyncMongoClient(os.getenv('TEST_MONGODB_URI', 'mongodb://localhost:27017'), tz_aware=True)
    try:
        persisted = await mongo[db.name].applications.find_one({'_id': ObjectId(app_id)})
        assert persisted['portfolioId'] == pid and persisted['qualityScore'] == 40
        assert (await mongo[db.name].portfolios.find_one({'_id': ObjectId(pid)}))['name'] == 'Integration Portfolio'
        assert (await mongo[db.name].users.find_one({'_id': ObjectId(admin_id)}))['defaultLandingPage'] == 'applications'
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as fresh:
            reread = await fresh.get(f'/api/applications/{app_id}', headers=admin)
            assert reread.status_code == 200 and reread.json()['qualityScore'] == 40
            checked_response_1 = await fresh.get('/api/auth/me', headers=admin)
            assert checked_response_1.status_code == 200, checked_response_1.text
            assert checked_response_1.json()['defaultLandingPage'] == 'applications'
    finally:
        await mongo.close()


async def test_scope_roles_and_invalid_changes_do_not_leak_or_mutate(environment):
    """Scope applies across inventory, derived data, exports and failed writes."""
    client, db = environment
    admin, _ = await sign_in_and_change_password(client, 'admin@ketsip.local')
    p1 = await client.post('/api/portfolios', headers=admin, json={'name': 'Allowed Portfolio'})
    p2 = await client.post('/api/portfolios', headers=admin, json={'name': 'Restricted Portfolio'})
    assert p1.status_code == p2.status_code == 201
    allowed, restricted = p1.json()['id'], p2.json()['id']
    a1 = await client.post('/api/applications', headers=admin, json=application_payload(allowed, 'Allowed App'))
    a2 = await client.post('/api/applications', headers=admin, json=application_payload(restricted, 'Restricted App'))
    assert a1.status_code == a2.status_code == 201
    allowed_id, restricted_id = a1.json()['id'], a2.json()['id']
    leader_account = {'name': 'Scoped Leader', 'email': 'scoped@example.com', 'password': INITIAL_PASSWORD,
                      'role': 'Portfolio Leader', 'portfolioAccess': [allowed], 'status': 'Active'}
    created = await client.post('/api/users', headers=admin, json=leader_account)
    assert created.status_code == 201, created.text
    leader, _ = await sign_in_and_change_password(client, leader_account['email'])
    reader, _ = await sign_in_and_change_password(client, 'readonly@ketsip.local')
    auditor, _ = await sign_in_and_change_password(client, 'auditor@ketsip.local')

    assert (await client.get(f'/api/portfolios/{restricted}', headers=leader)).status_code == 403
    assert (await client.get(f'/api/applications/{restricted_id}', headers=leader)).status_code == 403
    visible = await client.get('/api/applications', headers=leader)
    assert visible.status_code == 200 and {row['id'] for row in visible.json()['items']} == {allowed_id}
    dash = await client.get('/api/dashboard/executive', headers=leader)
    assert dash.status_code == 200 and dash.json()['totalApplications'] == 1
    assert [p['id'] for p in dash.json()['portfolios']] == [allowed]
    for kind in ('applications', 'portfolios'):
        rows = csv_rows(await client.get(f'/api/reports/{kind}', headers=leader, params={'format': 'csv'}))
        assert {row['name'] for row in rows} == ({'Allowed App'} if kind == 'applications' else {'Allowed Portfolio'})
        blocked = await client.get(f'/api/reports/{kind}', headers=leader, params={'portfolioId': restricted})
        assert blocked.status_code == 200 and blocked.json()['total'] == 0
    assert (await client.get('/api/users', headers=auditor)).status_code == 403
    assert (await client.get('/api/roles', headers=auditor)).status_code == 403
    assert (await client.get('/api/audit-logs', headers=auditor)).status_code == 200
    assert (await client.get('/api/audit-logs?format=csv', headers=auditor)).status_code == 200
    assert (await client.get('/api/audit-logs', headers=reader)).status_code == 403
    assert (await client.get('/api/reports/applications?format=csv', headers=reader)).status_code == 403
    assert (await client.post('/api/applications', headers=reader, json=application_payload(allowed, 'Denied App'))).status_code == 403
    assert (await client.delete(f'/api/applications/{allowed_id}', headers=leader)).status_code == 403

    before_doc = await db.applications.find_one({'_id': ObjectId(allowed_id)})
    checked_response_2 = await client.get('/api/dashboard/executive', headers=admin, params={'portfolioId': allowed})
    assert checked_response_2.status_code == 200, checked_response_2.text
    before_dashboard = checked_response_2.json()
    checked_response_3 = await client.get(f'/api/portfolios/{allowed}', headers=admin)
    assert checked_response_3.status_code == 200, checked_response_3.text
    before_summary = checked_response_3.json()
    checked_response_4 = await client.get('/api/reports/applications', headers=admin, params={'portfolioId': allowed})
    assert checked_response_4.status_code == 200, checked_response_4.text
    before_report = checked_response_4.json()
    edit_events = await db.audit_logs.count_documents({'action': 'edit', 'entityId': allowed_id})
    assert (await client.put(f'/api/applications/{allowed_id}', headers=leader, json=application_payload(restricted, 'Allowed App'))).status_code == 403
    assert (await client.put(f'/api/applications/{restricted_id}', headers=leader, json=application_payload(allowed, 'Restricted App'))).status_code == 403
    assert (await client.put(f'/api/applications/{allowed_id}', headers=admin, json=application_payload(allowed, 'Allowed App', qualityScore=101))).status_code == 422
    assert (await client.put(f'/api/applications/{allowed_id}', headers=admin, json=application_payload(str(ObjectId()), 'Allowed App'))).status_code == 409
    assert await db.applications.find_one({'_id': ObjectId(allowed_id)}) == before_doc
    checked_response_5 = await client.get('/api/dashboard/executive', headers=admin, params={'portfolioId': allowed})
    assert checked_response_5.status_code == 200, checked_response_5.text
    assert checked_response_5.json() == before_dashboard
    checked_response_6 = await client.get(f'/api/portfolios/{allowed}', headers=admin)
    assert checked_response_6.status_code == 200, checked_response_6.text
    assert checked_response_6.json() == before_summary
    checked_response_7 = await client.get('/api/reports/applications', headers=admin, params={'portfolioId': allowed})
    assert checked_response_7.status_code == 200, checked_response_7.text
    assert checked_response_7.json() == before_report
    assert await db.audit_logs.count_documents({'action': 'edit', 'entityId': allowed_id}) == edit_events


async def test_move_delete_and_reference_integrity_across_read_models(environment):
    """Reject deletion of referenced portfolios, then verify move and deletion propagation."""
    client, db = environment
    admin, admin_id = await sign_in_and_change_password(client, 'admin@ketsip.local')
    first = await client.post('/api/portfolios', headers=admin, json={'name': 'Move Source'})
    second = await client.post('/api/portfolios', headers=admin, json={'name': 'Move Destination'})
    assert first.status_code == second.status_code == 201
    source, destination = first.json()['id'], second.json()['id']
    payload = application_payload(source, 'Moving Application')
    created = await client.post('/api/applications', headers=admin, json=payload)
    assert created.status_code == 201, created.text
    app_id = created.json()['id']
    assert (await client.delete(f'/api/portfolios/{source}', headers=admin)).status_code == 409
    assert await db.portfolios.find_one({'_id': ObjectId(source)})
    assert (await db.applications.find_one({'_id': ObjectId(app_id)}))['portfolioId'] == source
    moved = await client.put(f'/api/applications/{app_id}', headers=admin, json={**payload, 'portfolioId': destination})
    assert moved.status_code == 200 and moved.json()['portfolioName'] == 'Move Destination'
    checked_response_8 = await client.get(f'/api/portfolios/{source}', headers=admin)
    assert checked_response_8.status_code == 200, checked_response_8.text
    old_summary = checked_response_8.json()
    checked_response_9 = await client.get(f'/api/portfolios/{destination}', headers=admin)
    assert checked_response_9.status_code == 200, checked_response_9.text
    new_summary = checked_response_9.json()
    assert old_summary['applicationCount'] == 0 and old_summary['qualityScore'] is None
    assert new_summary['applicationCount'] == 1 and new_summary['qualityScore'] == 80
    checked_response_10 = await client.get(f'/api/portfolios/{source}/applications', headers=admin)
    assert checked_response_10.status_code == 200, checked_response_10.text
    assert checked_response_10.json()['total'] == 0
    checked_response_11 = await client.get(f'/api/portfolios/{destination}/applications', headers=admin)
    assert checked_response_11.status_code == 200, checked_response_11.text
    assert checked_response_11.json()['items'][0]['id'] == app_id
    assert (await client.delete(f'/api/portfolios/{source}', headers=admin)).status_code == 204
    assert (await client.delete(f'/api/portfolios/{destination}', headers=admin)).status_code == 409
    assert (await client.delete(f'/api/applications/{app_id}', headers=admin)).status_code == 204
    assert (await client.get(f'/api/applications/{app_id}', headers=admin)).status_code == 404
    checked_response_12 = await client.get(f'/api/portfolios/{destination}', headers=admin)
    assert checked_response_12.status_code == 200, checked_response_12.text
    assert checked_response_12.json()['applicationCount'] == 0
    empty = await client.get('/api/dashboard/executive', headers=admin, params={'portfolioId': destination})
    assert empty.status_code == 200 and empty.json()['totalApplications'] == 0 and empty.json()['enterpriseQualityScore'] is None
    report = await client.get('/api/reports/applications', headers=admin, params={'portfolioId': destination})
    assert report.status_code == 200 and report.json()['total'] == 0
    assert (await client.delete(f'/api/portfolios/{destination}', headers=admin)).status_code == 204
    assert await db.applications.find_one({'_id': ObjectId(app_id)}) is None
    assert await db.applications.count_documents({'portfolioId': {'$in': [source, destination]}}) == 0
    assert await db.portfolios.count_documents({'_id': {'$in': [ObjectId(source), ObjectId(destination)]}}) == 0
    audit = await client.get('/api/audit-logs', headers=admin, params={'userId': admin_id, 'action': 'delete', 'limit': 100})
    assert audit.status_code == 200
    assert {source, destination, app_id} <= {event['entityId'] for event in audit.json()['items']}


async def test_role_permission_revocation_and_restoration_propagates_to_existing_sessions(environment):
    client, db = environment
    admin, _ = await sign_in_and_change_password(client, 'admin@ketsip.local')
    executive, _ = await sign_in_and_change_password(client, 'executive@ketsip.local')
    roles = await client.get('/api/roles', headers=admin)
    assert roles.status_code == 200
    role = next(row for row in roles.json()['items'] if row['name'] == 'Executive')
    original = role['permissions']
    assert set(original) == {'view', 'export'}
    views = ['/api/dashboard/executive', '/api/applications', '/api/portfolios',
             '/api/reports/applications', '/api/reports/portfolios']
    exports = ['/api/applications/export', '/api/reports/applications?format=csv',
               '/api/reports/portfolios?format=csv']
    for path in views + exports:
        response = await client.get(path, headers=executive)
        assert response.status_code == 200, (path, response.text)
    revoked = await client.put('/api/roles/' + role['id'], headers=admin,
                               json={'name': 'Executive', 'description': role['description'], 'permissions': []})
    assert revoked.status_code == 200 and revoked.json()['permissions'] == []
    for path in views + exports:
        response = await client.get(path, headers=executive)
        assert response.status_code == 403, (path, response.text)
    restored = await client.put('/api/roles/' + role['id'], headers=admin,
                                json={'name': 'Executive', 'description': role['description'], 'permissions': original})
    assert restored.status_code == 200 and restored.json()['permissions'] == original
    for path in views + exports:
        response = await client.get(path, headers=executive)
        assert response.status_code == 200, (path, response.text)
    assert (await db.roles.find_one({'_id': ObjectId(role['id'])}))['permissions'] == original
    assert await db.audit_logs.count_documents({'action': 'permissionChange', 'entityId': role['id']}) == 2
