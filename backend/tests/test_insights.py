"""Verify insight formulas, report scope and exports against real MongoDB."""

import csv
import io
import pytest
from bson import ObjectId
from app.core.security import create_access_token

pytestmark = pytest.mark.asyncio


async def credentials(db, role="Administrator", access=None, ready=True):
    """Create a token with the selected scope and password state."""
    await db.users.update_one({"role": role}, {"$set": {"portfolioAccess": access or [], "mustChangePassword": not ready}})
    return {"Authorization": "Bearer " + create_access_token(await db.users.find_one({"role": role}))}


async def test_dashboard_formulas_rounding_filters_and_empty(environment):
    """Calculate the exact metrics and include empty visible portfolios only without application filters."""
    client, db = environment
    admin = await credentials(db)
    await db.applications.delete_many({})
    portfolios = await db.portfolios.find().sort("name", 1).to_list(None)
    first, second = [str(p["_id"]) for p in portfolios[:2]]
    await db.applications.insert_many([
        {"name": "A", "portfolioId": first, "productArea": "Commerce", "qualityScore": 80, "applicationHealthScore": 61, "automationCoverage": 70, "openCriticalDefects": 2, "riskLevel": "High"},
        {"name": "B", "portfolioId": first, "productArea": "Commerce", "qualityScore": 81, "applicationHealthScore": 62, "automationCoverage": 71, "openCriticalDefects": 3, "riskLevel": "Low"},
        {"name": "C", "portfolioId": second, "productArea": "Other", "qualityScore": 40, "applicationHealthScore": 20, "automationCoverage": 50, "openCriticalDefects": 1, "riskLevel": "High"},
    ])
    response = await client.get('/api/dashboard/executive', headers=admin, params={"portfolioId": first})
    assert response.status_code == 200
    data = response.json()
    assert {k: data[k] for k in ('enterpriseQualityScore', 'applicationHealthScore', 'automationMaturityScore', 'openCriticalDefects', 'applicationsAtRisk', 'totalApplications', 'totalPortfolios')} == {
        'enterpriseQualityScore': 81, 'applicationHealthScore': 62, 'automationMaturityScore': 71, 'openCriticalDefects': 5, 'applicationsAtRisk': 1, 'totalApplications': 2, 'totalPortfolios': 1}
    assert data['portfolios'][0]['qualityScore'] == 81
    filtered = (await client.get('/api/dashboard/executive', headers=admin, params={'productArea': 'Commerce', 'riskLevel': 'High'})).json()
    assert filtered['totalPortfolios'] == 1 and filtered['totalApplications'] == 1 and filtered['enterpriseQualityScore'] == 80
    empty = (await client.get('/api/dashboard/executive', headers=admin, params={'productArea': 'missing'})).json()
    assert empty['enterpriseQualityScore'] is None and empty['applicationHealthScore'] is None and empty['automationMaturityScore'] is None
    assert empty['totalPortfolios'] == empty['totalApplications'] == 0
    await db.applications.delete_many({})
    empty = (await client.get('/api/dashboard/executive', headers=admin)).json()
    assert empty['totalPortfolios'] == 3 and empty['enterpriseQualityScore'] is None
    assert all(p['qualityScore'] is None and p['applicationCount'] == 0 for p in empty['portfolios'])


async def test_permissions_scope_password_gate_and_filter_validation(environment):
    """Enforce token, password, role ceilings, current permissions and Leader scope."""
    client, db = environment
    assert (await client.get('/api/dashboard/executive')).status_code == 401
    gated = await credentials(db, ready=False)
    assert (await client.get('/api/reports/applications?format=csv', headers=gated)).status_code == 403
    first, second = [str(p['_id']) for p in await db.portfolios.find().sort('name', 1).limit(2).to_list(None)]
    leader = await credentials(db, 'Portfolio Leader', [first])
    data = (await client.get('/api/dashboard/executive', headers=leader)).json()
    assert data['totalPortfolios'] == 1 and data['portfolios'][0]['id'] == first
    visible_export = await client.get('/api/reports/applications', headers=leader, params={'format': 'csv'})
    visible_rows = list(csv.DictReader(io.StringIO(visible_export.text)))
    assert visible_rows and all(row['portfolioName'] == data['portfolios'][0]['name'] for row in visible_rows)
    assert (await client.get('/api/reports/applications', headers=leader, params={'portfolioId': second})).json()['total'] == 0
    assert (await client.get('/api/reports/portfolios', headers=leader, params={'portfolioId': second, 'format': 'csv'})).text.count('\n') == 1
    leader = await credentials(db, 'Portfolio Leader', [])
    assert (await client.get('/api/dashboard/executive', headers=leader)).json()['totalPortfolios'] == 0
    readonly = await credentials(db, 'Read Only')
    count_before_denials = await db.audit_logs.count_documents({'action': 'export'})
    assert (await client.get('/api/reports/applications?format=csv', headers=readonly)).status_code == 403
    assert (await client.get('/api/reports/portfolios?format=csv', headers=readonly)).status_code == 403
    assert await db.audit_logs.count_documents({'action': 'export'}) == count_before_denials
    assert (await client.get('/api/dashboard/executive?riskLevel=Wrong', headers=readonly)).status_code == 422
    await db.roles.update_one({'name': 'Read Only'}, {'$set': {'permissions': ['view', 'export']}})
    assert (await client.get('/api/reports/applications?format=csv', headers=readonly)).status_code == 403
    await db.roles.update_one({'name': 'Read Only'}, {'$set': {'permissions': []}})
    assert (await client.get('/api/dashboard/executive', headers=readonly)).status_code == 403
    assert (await client.get('/api/reports/portfolios', headers=readonly)).status_code == 403


async def test_complete_csv_safe_cells_audit_and_pagination(environment):
    """Export every matching record, neutralize formulas, and audit only successful requests."""
    client, db = environment
    admin = await credentials(db)
    await db.applications.delete_many({})
    p = await db.portfolios.find_one({})
    pid = str(p['_id'])
    await db.portfolios.update_one({'_id': p['_id']}, {'$set': {'owner': '  =SUM(1,1)'}})
    await db.applications.insert_many([{'_id': ObjectId(), 'name': f'App {i:03}', 'portfolioId': pid, 'productArea': 'Bulk',
        'qualityScore': 75, 'applicationHealthScore': 80, 'automationCoverage': 60, 'openCriticalDefects': 0, 'riskLevel': 'High'} for i in range(105)] + [
        {'name': '\t@danger', 'portfolioId': pid, 'productArea': 'Bulk', 'qualityScore': 80, 'applicationHealthScore': 80, 'automationCoverage': 60, 'openCriticalDefects': 1, 'riskLevel': 'High'},
        {'name': 'Excluded', 'portfolioId': pid, 'productArea': 'Other', 'qualityScore': 80, 'applicationHealthScore': 80, 'automationCoverage': 60, 'openCriticalDefects': 1, 'riskLevel': 'Low'}])
    params = {'productArea': 'Bulk', 'riskLevel': 'High', 'portfolioId': pid}
    page = await client.get('/api/reports/applications', headers=admin, params={**params, 'limit': 100})
    assert page.status_code == 200 and page.json()['total'] == 106 and len(page.json()['items']) == 100
    response = await client.get('/api/reports/applications', headers=admin, params={**params, 'format': 'csv', 'limit': 1})
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert response.status_code == 200 and len(rows) == 106
    assert any(r['name'] == "'\t@danger" for r in rows) and all(r['name'] != 'Excluded' for r in rows)
    response = await client.get('/api/reports/portfolios', headers=admin, params={**params, 'format': 'csv'})
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 1 and rows[0]['owner'] == "'  =SUM(1,1)" and rows[0]['applicationCount'] == '106'
    events = await db.audit_logs.find({'action': 'export'}).to_list(None)
    assert len(events) == 2 and {event['entityType'] for event in events} == {'application', 'portfolio'}
