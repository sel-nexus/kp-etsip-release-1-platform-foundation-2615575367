"""Exercise service branches against the real isolated MongoDB fixture."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId
from fastapi import HTTPException

from app.admin import service as admin_service
from app.admin.repository import AdminRepository
from app.admin.schemas import RoleInput
from app.applications import service as application_service
from app.applications.repository import ApplicationRepository
from app.auth import service as auth_service
from app.auth.repository import AuthRepository
from app.insights import service as insights_service
from app.insights.repository import InsightsRepository
from app.portfolios import service as portfolio_service
from app.portfolios.repository import PortfolioRepository
from app.portfolios.schemas import PortfolioInput

pytestmark = pytest.mark.asyncio


async def test_auth_service_login_and_stale_password_update(environment):
    _, db = environment
    repo = AuthRepository(db)
    login = await auth_service.login(repo, ' ADMIN@KETSIP.LOCAL ', 'DemoPassword123!')
    user = login['user']
    assert login['token'] and (await repo.by_id(str(user['_id'])))['lastLogin'] is not None
    with pytest.raises(HTTPException) as error:
        await auth_service.login(repo, 'missing@example.com', 'wrong')
    assert error.value.status_code == 401
    await db.users.update_one({'_id': user['_id']}, {'$set': {'status': 'Inactive'}})
    with pytest.raises(HTTPException) as error:
        await auth_service.change_password(repo, user, 'DemoPassword123!', 'AnotherPassword123!')
    assert error.value.status_code == 409
    assert (await repo.by_id(str(user['_id'])))['passwordHash'] == user['passwordHash']


async def test_portfolio_service_create_duplicate_find_and_remove(environment):
    _, db = environment
    repo = PortfolioRepository(db)
    actor = await db.users.find_one({'role': 'Administrator'})
    body = PortfolioInput(name='Service portfolio')
    created = await portfolio_service.save(repo, actor, body)
    assert (await portfolio_service.find(repo, actor, created['id']))['name'] == 'Service portfolio'
    with pytest.raises(HTTPException) as error:
        await portfolio_service.save(repo, actor, body)
    assert error.value.status_code == 409
    await portfolio_service.remove(repo, actor, created['id'])
    assert await repo.get(created['id']) is None
    with pytest.raises(HTTPException) as error:
        await portfolio_service.find(repo, actor, created['id'])
    assert error.value.status_code == 404


async def test_application_service_scope_and_not_found(environment):
    _, db = environment
    repo = ApplicationRepository(db)
    leader = await db.users.find_one({'role': 'Portfolio Leader'})
    first, second = [str(row['_id']) for row in await db.portfolios.find().limit(2).to_list(None)]
    leader['portfolioAccess'] = [first]
    await application_service.authorize(repo, leader, 'view', first)
    with pytest.raises(HTTPException) as error:
        await application_service.authorize(repo, leader, 'view', second)
    assert error.value.status_code == 403
    with pytest.raises(HTTPException) as error:
        await application_service.find(repo, leader, str(ObjectId()))
    assert error.value.status_code == 404


async def test_admin_service_role_ceiling_name_and_live_authorization(environment):
    _, db = environment
    repo = AdminRepository(db)
    actor = await db.users.find_one({'role': 'Administrator'})
    auditor = await db.roles.find_one({'name': 'Auditor'})
    identifier = str(auditor['_id'])
    updated = await admin_service.save_role(repo, actor, RoleInput(name='Auditor', description='Reviewed', permissions=['view']), identifier)
    assert updated['description'] == 'Reviewed'
    assert (await db.roles.find_one({'_id': auditor['_id']}))['permissions'] == ['view']
    with pytest.raises(HTTPException) as error:
        await admin_service.save_role(repo, actor, RoleInput(name='Auditor', permissions=['administer']), identifier)
    assert error.value.status_code == 422
    with pytest.raises(HTTPException) as error:
        await admin_service.save_role(repo, actor, RoleInput(name='Engineer', permissions=['view']), identifier)
    assert error.value.status_code == 422
    await db.roles.update_one({'name': 'Administrator'}, {'$set': {'permissions': []}})
    with pytest.raises(HTTPException) as error:
        await admin_service.authorize(repo, actor, 'administer')
    assert error.value.status_code == 403


async def test_insights_service_empty_average_scope_and_permission(environment):
    _, db = environment
    repo = InsightsRepository(db)
    actor = await db.users.find_one({'role': 'Administrator'})
    assert insights_service.average([], 'qualityScore') is None
    assert insights_service.average([{'qualityScore': 80}, {'qualityScore': 81}, {}], 'qualityScore') == 81
    metrics, portfolios, applications = await insights_service.read_inventory(repo, actor, 'invalid-id', None, None)
    assert metrics['totalPortfolios'] == 0 and metrics['totalApplications'] == 0
    assert portfolios == [] and applications == []
    await db.roles.update_one({'name': 'Administrator'}, {'$set': {'permissions': []}})
    with pytest.raises(HTTPException) as error:
        await insights_service.read_inventory(repo, actor, None, None, None)
    assert error.value.status_code == 403


async def test_audit_query_and_csv_value_branches():
    now = datetime.now(timezone.utc)
    assert admin_service.audit_query(None, None, None, None) == {}
    query = admin_service.audit_query('u', 'edit', now - timedelta(days=1), now)
    assert query['userId'] == 'u' and query['action'] == 'edit'
    assert query['timestamp']['$lte'] == now
    with pytest.raises(HTTPException) as error:
        admin_service.audit_query(None, None, datetime(2024, 1, 1), None)
    assert error.value.status_code == 422
    with pytest.raises(HTTPException) as error:
        admin_service.audit_query(None, None, now, now - timedelta(days=1))
    assert error.value.status_code == 422
    assert admin_service.csv_value(None) == ''
    assert admin_service.csv_value('  =1+1') == "'  =1+1"
    assert admin_service.csv_value('normal') == 'normal'


async def test_application_service_create_update_duplicate_missing_portfolio_and_delete(environment):
    from app.applications.schemas import ApplicationInput
    _, db = environment
    repo = ApplicationRepository(db)
    actor = await db.users.find_one({'role': 'Administrator'})
    pid = str((await db.portfolios.find_one({}))['_id'])
    body = ApplicationInput(name='Service app', portfolioId=pid, criticality='High', tier=1,
        lifecycleStatus='Active', applicationHealthScore=80, qualityScore=70, automationCoverage=60,
        unitTestCoverage=50, openDefects=1, openCriticalDefects=0, riskLevel='Low')
    created = await application_service.save(repo, actor, body)
    identifier = created['id']
    listing = await application_service.listing(repo, actor, 'Service app', None, None, None, None, 0, 10)
    assert listing['total'] == 1 and listing['items'][0]['id'] == identifier
    with pytest.raises(HTTPException) as error:
        await application_service.save(repo, actor, body)
    assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        await application_service.save(repo, actor, body.model_copy(update={'name': 'Missing', 'portfolioId': str(ObjectId())}))
    assert error.value.status_code == 409
    updated = await application_service.save(repo, actor, body.model_copy(update={'qualityScore': 42}), identifier)
    assert updated['qualityScore'] == 42
    assert (await repo.get(identifier))['qualityScore'] == 42
    await application_service.remove(repo, actor, identifier)
    assert await repo.get(identifier) is None
    with pytest.raises(HTTPException) as error:
        await application_service.remove(repo, actor, identifier)
    assert error.value.status_code == 404


async def test_portfolio_service_update_listing_and_nonempty_delete(environment):
    _, db = environment
    repo = PortfolioRepository(db)
    actor = await db.users.find_one({'role': 'Administrator'})
    portfolio = await portfolio_service.save(repo, actor, PortfolioInput(name='Service update'))
    identifier = portfolio['id']
    updated = await portfolio_service.save(repo, actor, PortfolioInput(name='Updated service'), identifier)
    assert updated['name'] == 'Updated service'
    page = await portfolio_service.list_portfolios(repo, actor, 'Updated service', None, None, 0, 10)
    assert page['total'] == 1 and page['items'][0]['id'] == identifier
    await db.applications.insert_one({'name': 'Linked service', 'portfolioId': identifier, 'qualityScore': 80})
    with pytest.raises(HTTPException) as error:
        await portfolio_service.remove(repo, actor, identifier)
    assert error.value.status_code == 409
    assert await repo.get(identifier) is not None


async def test_application_delete_reports_conflict_when_observed_version_moves(environment, monkeypatch):
    _, db = environment
    repo = ApplicationRepository(db)
    actor = await db.users.find_one({'role': 'Administrator'})
    old_pid = str((await db.portfolios.insert_one({'name': 'Delete race old'})).inserted_id)
    new_pid = str((await db.portfolios.insert_one({'name': 'Delete race new'})).inserted_id)
    original_row = await repo.insert({'name': 'Delete race application', 'portfolioId': old_pid})
    identifier = str(original_row['_id'])
    reached_delete, proceed = asyncio.Event(), asyncio.Event()
    delete_observed = repo.delete

    async def paused_delete(row):
        reached_delete.set()
        await asyncio.wait_for(proceed.wait(), 5)
        return await delete_observed(row)

    monkeypatch.setattr(repo, 'delete', paused_delete)
    operation = asyncio.create_task(application_service.remove(repo, actor, identifier))
    try:
        await asyncio.wait_for(reached_delete.wait(), 5)
        moved = await repo.update(original_row, {'name': 'Delete race application', 'portfolioId': new_pid})
        assert moved is not None
    finally:
        proceed.set()
    with pytest.raises(HTTPException) as error:
        await operation
    assert error.value.status_code == 409
    assert error.value.detail == 'Application changed concurrently'
    stored = await db.applications.find_one({'_id': original_row['_id']})
    assert stored['portfolioId'] == new_pid and stored['reservation'] == moved['reservation']
    assert stored['reservation'] in (await db.portfolios.find_one({'_id': ObjectId(new_pid)}))['applicationReservations']
    assert original_row['reservation'] not in (await db.portfolios.find_one({'_id': ObjectId(old_pid)}))['applicationReservations']
    assert await db.audit_logs.count_documents({'entityType': 'application', 'entityId': identifier, 'action': 'delete'}) == 0


async def test_application_update_loses_optimistic_match_and_cleans_reservation(environment, monkeypatch):
    """A stale update cannot overwrite a winner or leave its own reservation or audit."""
    from app.applications.schemas import ApplicationInput

    _, db = environment
    loser_repo = ApplicationRepository(db)
    winner_repo = ApplicationRepository(db)
    actor = await db.users.find_one({'role': 'Administrator'})
    old_pid = str((await db.portfolios.insert_one({'name': 'Update race old'})).inserted_id)
    loser_pid = str((await db.portfolios.insert_one({'name': 'Update race loser'})).inserted_id)
    winner_pid = str((await db.portfolios.insert_one({'name': 'Update race winner'})).inserted_id)
    body = ApplicationInput(name='Update race application', portfolioId=old_pid, criticality='High', tier=1,
        lifecycleStatus='Active', applicationHealthScore=80, qualityScore=70, automationCoverage=60,
        unitTestCoverage=50, openDefects=1, openCriticalDefects=0, riskLevel='Low')
    created = await application_service.save(winner_repo, actor, body)
    identifier = created['id']
    original = await winner_repo.get(identifier)
    reserved, proceed = asyncio.Event(), asyncio.Event()
    reserve = loser_repo.reserve
    loser_token = None

    async def paused_reserve(portfolio_id):
        nonlocal loser_token
        loser_token = await reserve(portfolio_id)
        reserved.set()
        await asyncio.wait_for(proceed.wait(), 5)
        return loser_token

    monkeypatch.setattr(loser_repo, 'reserve', paused_reserve)
    operation = asyncio.create_task(application_service.save(
        loser_repo, actor, body.model_copy(update={'portfolioId': loser_pid, 'qualityScore': 10}), identifier))
    try:
        await asyncio.wait_for(reserved.wait(), 5)
        assert loser_token is not None
        assert loser_token in (await db.portfolios.find_one({'_id': ObjectId(loser_pid)}))['applicationReservations']
        winner = await application_service.save(
            winner_repo, actor, body.model_copy(update={'portfolioId': winner_pid, 'qualityScore': 99}), identifier)
        winning_row = await winner_repo.get(identifier)
        assert winner['qualityScore'] == 99 and winning_row['reservation'] != original['reservation']
    finally:
        proceed.set()
    with pytest.raises(HTTPException) as error:
        await operation
    assert error.value.status_code == 409
    assert error.value.detail == 'Portfolio unavailable or application changed concurrently'
    assert await loser_repo.get(identifier) == winning_row
    assert (await db.portfolios.find_one({'_id': ObjectId(old_pid)}))['applicationReservations'] == []
    assert (await db.portfolios.find_one({'_id': ObjectId(loser_pid)}))['applicationReservations'] == []
    assert (await db.portfolios.find_one({'_id': ObjectId(winner_pid)}))['applicationReservations'] == [winning_row['reservation']]
    audits = await db.audit_logs.find({'entityType': 'application', 'entityId': identifier}).to_list(None)
    assert [event['action'] for event in audits].count('create') == 1
    assert [event['action'] for event in audits].count('edit') == 1
    assert len(audits) == 2


@pytest.mark.parametrize('interleaving', ['reservation', 'disappearance'])
async def test_portfolio_delete_distinguishes_pending_reservation_from_disappearance(environment, monkeypatch, interleaving):
    _, db = environment
    repo = PortfolioRepository(db)
    actor = await db.users.find_one({'role': 'Administrator'})
    identifier = str((await db.portfolios.insert_one({'name': 'Portfolio delete ' + interleaving})).inserted_id)
    reached_delete, proceed = asyncio.Event(), asyncio.Event()
    delete_observed = repo.delete

    async def paused_delete(pid):
        reached_delete.set()
        await asyncio.wait_for(proceed.wait(), 5)
        return await delete_observed(pid)

    monkeypatch.setattr(repo, 'delete', paused_delete)
    operation = asyncio.create_task(portfolio_service.remove(repo, actor, identifier))
    token = None
    try:
        await asyncio.wait_for(reached_delete.wait(), 5)
        if interleaving == 'reservation':
            token = await ApplicationRepository(db).reserve(identifier)
            assert token is not None
        else:
            assert await PortfolioRepository(db).delete(identifier) is True
    finally:
        proceed.set()
    with pytest.raises(HTTPException) as error:
        await operation
    assert error.value.status_code == (409 if token else 404)
    assert error.value.detail == ('Portfolio has references or pending changes' if token else 'Portfolio not found')
    stored = await db.portfolios.find_one({'_id': ObjectId(identifier)})
    if token:
        assert token in stored['applicationReservations'] and 'deletionLock' not in stored
        await ApplicationRepository(db).release(identifier, token)
        assert (await repo.get(identifier))['applicationReservations'] == []
    else:
        assert stored is None
    assert await db.audit_logs.count_documents({'entityType': 'portfolio', 'entityId': identifier, 'action': 'delete'}) == 0


async def test_portfolio_update_returns_404_if_deleted_after_lookup(environment, monkeypatch):
    _, db = environment
    repo = PortfolioRepository(db)
    actor = await db.users.find_one({'role': 'Administrator'})
    identifier = str((await db.portfolios.insert_one({'name': 'Portfolio update disappearance'})).inserted_id)
    reached_update, proceed = asyncio.Event(), asyncio.Event()
    update_observed = repo.update

    async def paused_update(pid, fields):
        reached_update.set()
        await asyncio.wait_for(proceed.wait(), 5)
        return await update_observed(pid, fields)

    monkeypatch.setattr(repo, 'update', paused_update)
    operation = asyncio.create_task(portfolio_service.save(repo, actor, PortfolioInput(name='Never written'), identifier))
    try:
        await asyncio.wait_for(reached_update.wait(), 5)
        assert await PortfolioRepository(db).delete(identifier) is True
    finally:
        proceed.set()
    with pytest.raises(HTTPException) as error:
        await operation
    assert error.value.status_code == 404 and error.value.detail == 'Portfolio not found'
    assert await repo.get(identifier) is None
    assert not await db.portfolios.find_one({'name': 'Never written'})
    assert await db.audit_logs.count_documents({'entityType': 'portfolio', 'entityId': identifier, 'action': 'edit'}) == 0


async def test_admin_service_user_create_edit_deactivate_and_self_protection(environment):
    from app.admin.schemas import UserCreate, UserInput
    _, db = environment
    repo = AdminRepository(db)
    actor = await db.users.find_one({'role': 'Administrator'})
    data = {'name': 'Service User', 'email': 'service@example.com', 'role': 'Engineer'}
    created = await admin_service.save_user(repo, actor, UserCreate(**data, password='StrongPassword123!'))
    identifier = str(created['_id'])
    assert (await admin_service.find(repo, 'users', identifier))['email'] == data['email']
    changed = await admin_service.save_user(repo, actor, UserInput(**{**data, 'role': 'Auditor'}), identifier)
    assert changed['role'] == 'Auditor'
    with pytest.raises(HTTPException) as error:
        await admin_service.deactivate(repo, actor, str(actor['_id']))
    assert error.value.status_code == 409
    await admin_service.deactivate(repo, actor, identifier)
    assert (await db.users.find_one({'_id': created['_id']}))['status'] == 'Inactive'
    with pytest.raises(HTTPException) as error:
        await admin_service.find(repo, 'users', str(ObjectId()))
    assert error.value.status_code == 404


async def test_insights_service_export_branches_and_revoked_export(environment):
    import csv
    import io
    _, db = environment
    repo = InsightsRepository(db)
    actor = await db.users.find_one({'role': 'Executive'})
    for kind in ('application', 'portfolio'):
        rows = list(csv.DictReader(io.StringIO(await insights_service.export(repo, actor, kind, None, None, None))))
        assert rows and all(row['name'] for row in rows)
    assert await db.audit_logs.count_documents({'action': 'export'}) == 2
    await db.roles.update_one({'name': 'Executive'}, {'$set': {'permissions': ['view']}})
    with pytest.raises(HTTPException) as error:
        await insights_service.export(repo, actor, 'application', None, None, None)
    assert error.value.status_code == 403
    assert await db.audit_logs.count_documents({'action': 'export'}) == 2
