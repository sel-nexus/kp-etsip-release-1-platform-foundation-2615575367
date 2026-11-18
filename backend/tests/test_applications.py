"""Exercise application inventory against an isolated real MongoDB."""

import asyncio
import pytest
from bson import ObjectId
from app.core.security import create_access_token
from app.core.seed import seed_database

pytestmark = pytest.mark.asyncio
BASE = "/api/applications"


async def credentials(db, role="Administrator", access=None, ready=True):
    """Issue a token for the requested seeded role."""
    await db.users.update_one({"role": role}, {"$set": {"mustChangePassword": not ready, "portfolioAccess": access or []}})
    return {"Authorization": "Bearer " + create_access_token(await db.users.find_one({"role": role}))}


def payload(portfolio, name="Test Application", **changes):
    """Provide valid application fields for a test."""
    return {"name": name, "description": "Example", "portfolioId": portfolio, "productArea": "Commerce",
            "businessOwner": "Business", "technologyOwner": "Tech", "etsOwner": "ETS",
            "criticality": "High", "tier": 2, "lifecycleStatus": "Active", "technologyStack": "Python",
            "repositoryLink": "https://example.com/repo", "pipelineLink": None, "applicationHealthScore": 80,
            "qualityScore": 90, "automationCoverage": 70, "unitTestCoverage": 60,
            "openDefects": 3, "openCriticalDefects": 1, "riskLevel": "High", **changes}


async def test_crud_filter_validation_and_audit(environment):
    """Persist valid edits, reject invalid records, and record changes."""
    client, db = environment
    admin = await credentials(db)
    portfolio = str((await db.portfolios.find_one({"name": "Payments"}))["_id"])
    created = await client.post(BASE, headers=admin, json=payload(portfolio))
    assert created.status_code == 201, created.text
    identifier = created.json()["id"]
    assert (await db.applications.find_one({"_id": ObjectId(identifier)}))["qualityScore"] == 90
    assert (await client.post(BASE, headers=admin, json=payload(portfolio))).status_code == 409
    for bad in ({"name": "  "}, {"tier": 0}, {"qualityScore": 101}, {"openDefects": -1}, {"criticality": "Wrong"}, {"repositoryLink": "javascript:alert(1)"}):
        assert (await client.post(BASE, headers=admin, json=payload(portfolio, **bad))).status_code == 422
    assert (await client.post(BASE, headers=admin, json=payload(str(ObjectId()), name="Missing"))).status_code == 409
    assert (await client.get(BASE, headers=admin, params={"search": "Test Application", "riskLevel": "High", "criticality": "High", "lifecycleStatus": "Active", "portfolioId": portfolio})).json()["total"] == 1
    assert (await client.get(BASE, headers=admin, params={"limit": 101})).status_code == 422
    assert (await client.get(BASE, headers=admin, params={"search": ".*"})).json()["total"] == 0
    assert (await client.get(f"{BASE}/{identifier}", headers=admin)).json()["portfolioName"] == "Payments"
    edited = await client.put(f"{BASE}/{identifier}", headers=admin, json=payload(portfolio, qualityScore=42))
    assert edited.status_code == 200 and (await db.applications.find_one({"_id": ObjectId(identifier)}))["qualityScore"] == 42
    export = await client.get(BASE + "/export?search=Test", headers=admin)
    assert export.status_code == 200 and "Test Application" in export.text
    assert (await client.delete(f"{BASE}/{identifier}", headers=admin)).status_code == 204
    assert not await db.applications.find_one({"_id": ObjectId(identifier)})
    assert (await client.get(f"{BASE}/{identifier}", headers=admin)).status_code == 404
    events = await db.audit_logs.find({"entityType": "application"}).to_list(None)
    assert {e["action"] for e in events} == {"create", "edit", "delete", "export"}


async def test_scope_permissions_password_guard_and_seed(environment):
    """Enforce role ceilings, live permissions, and both sides of a move."""
    client, db = environment
    assert (await client.get(BASE)).status_code == 401
    gated = await credentials(db, ready=False)
    assert (await client.get(BASE, headers=gated)).status_code == 403
    admin = await credentials(db)
    portfolios = await db.portfolios.find().sort("name", 1).to_list(None)
    first, second = [str(p["_id"]) for p in portfolios[:2]]
    leader = await credentials(db, "Portfolio Leader", [first])
    created = await client.post(BASE, headers=leader, json=payload(first, name="Leader Application"))
    assert created.status_code == 201
    identifier = created.json()["id"]
    assert (await client.put(f"{BASE}/{identifier}", headers=leader, json=payload(second, name="Move"))).status_code == 403
    other = await client.post(BASE, headers=admin, json=payload(second, name="Other Application"))
    assert (await client.put(f"{BASE}/{other.json()['id']}", headers=leader, json=payload(first, name="Steal"))).status_code == 403
    assert all(a["portfolioId"] == first for a in (await client.get(BASE, headers=leader)).json()["items"])
    assert (await client.get(BASE, headers=leader, params={"portfolioId": second})).json()["total"] == 0
    assert (await client.delete(f"{BASE}/{identifier}", headers=leader)).status_code == 403
    readonly = await credentials(db, "Read Only")
    assert (await client.get(BASE + "/export", headers=readonly)).status_code == 403
    assert (await client.post(BASE, headers=readonly, json=payload(first, name="No"))).status_code == 403
    await db.roles.update_one({"name": "Portfolio Leader"}, {"$set": {"permissions": ["view"]}})
    assert (await client.post(BASE, headers=leader, json=payload(first, name="Denied"))).status_code == 403
    seeded = await db.applications.find_one({"name": "Payment Gateway"})
    await db.applications.update_one({"_id": seeded["_id"]}, {"$set": {"name": "Edited Seed"}})
    await seed_database(db)
    assert (await db.applications.find_one({"_id": seeded["_id"]}))["name"] == "Edited Seed"


async def test_concurrent_create_and_portfolio_delete_cannot_orphan(environment):
    """Race separate HTTP operations and check the persisted invariant."""
    client, db = environment
    admin = await credentials(db)
    for index in range(12):
        portfolio = await client.post('/api/portfolios', headers=admin, json={"name": f"Race {index}"})
        pid = portfolio.json()["id"]
        create, delete = await asyncio.gather(client.post(BASE, headers=admin, json=payload(pid, name=f"Race app {index}")), client.delete(f"/api/portfolios/{pid}", headers=admin))
        assert create.status_code in (201, 409) and delete.status_code in (204, 409)
        if await db.applications.find_one({"portfolioId": pid}):
            assert await db.portfolios.find_one({"_id": ObjectId(pid)})
