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
    checked_response_1 = await client.get(BASE, headers=admin, params={"search": "Test Application", "riskLevel": "High", "criticality": "High", "lifecycleStatus": "Active", "portfolioId": portfolio})
    assert checked_response_1.status_code == 200, checked_response_1.text
    assert checked_response_1.json()["total"] == 1
    assert (await client.get(BASE, headers=admin, params={"limit": 101})).status_code == 422
    checked_response_2 = await client.get(BASE, headers=admin, params={"search": ".*"})
    assert checked_response_2.status_code == 200, checked_response_2.text
    assert checked_response_2.json()["total"] == 0
    checked_response_3 = await client.get(f"{BASE}/{identifier}", headers=admin)
    assert checked_response_3.status_code == 200, checked_response_3.text
    assert checked_response_3.json()["portfolioName"] == "Payments"
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
    assert other.status_code == 201
    assert (await client.put(f"{BASE}/{other.json()['id']}", headers=leader, json=payload(first, name="Steal"))).status_code == 403
    checked_response_4 = await client.get(BASE, headers=leader)
    assert checked_response_4.status_code == 200, checked_response_4.text
    assert all(a["portfolioId"] == first for a in checked_response_4.json()["items"])
    checked_response_5 = await client.get(BASE, headers=leader, params={"portfolioId": second})
    assert checked_response_5.status_code == 200, checked_response_5.text
    assert checked_response_5.json()["total"] == 0
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
        assert portfolio.status_code == 201
        pid = portfolio.json()["id"]
        create, delete = await asyncio.gather(client.post(BASE, headers=admin, json=payload(pid, name=f"Race app {index}")), client.delete(f"/api/portfolios/{pid}", headers=admin))
        assert create.status_code in (201, 409) and delete.status_code in (204, 409)
        if await db.applications.find_one({"portfolioId": pid}):
            assert await db.portfolios.find_one({"_id": ObjectId(pid)})


async def test_application_create_rejects_invalid_inputs_and_missing_crud_returns_404(environment):
    client, db = environment
    admin = await credentials(db)
    portfolio = str((await db.portfolios.find_one({}))["_id"])
    valid = payload(portfolio, name="Input validation")
    for field in ("name", "portfolioId", "criticality", "tier", "lifecycleStatus", "applicationHealthScore",
                  "qualityScore", "automationCoverage", "unitTestCoverage", "openDefects", "openCriticalDefects", "riskLevel"):
        assert (await client.post(BASE, headers=admin, json={k: v for k, v in valid.items() if k != field})).status_code == 422, field
    for changes in ({"name": {"$ne": ""}}, {"portfolioId": {"$ne": ""}}, {"tier": "2"},
                    {"qualityScore": None}, {"name": "x" * 201}, {"description": "x" * 5001},
                    {"pipelineLink": "javascript:alert(1)"}):
        assert (await client.post(BASE, headers=admin, json={**valid, **changes})).status_code == 422, changes
    for identifier in ("not-an-id", str(ObjectId())):
        assert (await client.get(f"{BASE}/{identifier}", headers=admin)).status_code == 404
        assert (await client.put(f"{BASE}/{identifier}", headers=admin, json=valid)).status_code == 404
        assert (await client.delete(f"{BASE}/{identifier}", headers=admin)).status_code == 404
    assert await db.applications.count_documents({"name": "Input validation"}) == 0


async def test_existing_application_put_rejects_missing_invalid_and_out_of_range_fields(environment):
    """Invalid replacements cannot mutate the existing document or create an edit audit."""
    client, db = environment
    admin = await credentials(db)
    portfolio = str((await db.portfolios.find_one({}))["_id"])
    valid = payload(portfolio, name="PUT validation")
    created = await client.post(BASE, headers=admin, json=valid)
    assert created.status_code == 201, created.text
    identifier = created.json()["id"]
    original = await db.applications.find_one({"_id": ObjectId(identifier)})
    audits = await db.audit_logs.find({"entityType": "application", "entityId": identifier}).to_list(None)

    required = ("name", "portfolioId", "criticality", "tier", "lifecycleStatus", "applicationHealthScore",
                "qualityScore", "automationCoverage", "unitTestCoverage", "openDefects", "openCriticalDefects", "riskLevel")
    invalid = [(field, {k: v for k, v in valid.items() if k != field}) for field in required]
    invalid += [(field, {**valid, field: value}) for field, value in (
        ("name", {"$ne": ""}), ("portfolioId", [portfolio]), ("description", False),
        ("criticality", 1), ("lifecycleStatus", None), ("riskLevel", []),
        ("tier", "2"), ("tier", True), ("qualityScore", 1.5),
        ("applicationHealthScore", None), ("automationCoverage", "70"),
        ("unitTestCoverage", False), ("openDefects", "3"), ("openCriticalDefects", True),
        ("name", " "), ("name", "x" * 201), ("description", "x" * 5001),
        ("portfolioId", "x" * 25), ("productArea", "x" * 201),
        ("businessOwner", "x" * 201), ("technologyOwner", "x" * 201),
        ("etsOwner", "x" * 201), ("technologyStack", "x" * 5001),
        ("repositoryLink", "javascript:alert(1)"), ("pipelineLink", "not a url"),
        ("tier", 0), ("tier", 5), ("applicationHealthScore", -1),
        ("qualityScore", 101), ("automationCoverage", -1), ("unitTestCoverage", 101),
        ("openDefects", -1), ("openCriticalDefects", -1),
        ("criticality", "Wrong"), ("lifecycleStatus", "Wrong"), ("riskLevel", "Wrong"),
        ("unexpected", "field"),
    )]
    for field, body in invalid:
        response = await client.put(f"{BASE}/{identifier}", headers=admin, json=body)
        assert response.status_code == 422, (field, response.status_code, response.text)
        assert any(error["loc"][-1] == field for error in response.json()["detail"]), (field, response.text)
        assert await db.applications.find_one({"_id": ObjectId(identifier)}) == original, field
        assert await db.audit_logs.find({"entityType": "application", "entityId": identifier}).to_list(None) == audits, field


async def test_script_input_round_trips_as_json_data(environment):
    client, db = environment
    admin = await credentials(db)
    portfolio = str((await db.portfolios.find_one({}))["_id"])
    attack = '<script>alert("xss")</script>'
    created = await client.post(BASE, headers=admin, json=payload(portfolio, name=attack, description=attack))
    assert created.status_code == 201
    assert created.headers['content-type'].startswith('application/json')
    identifier = created.json()['id']
    result = await client.get(f'{BASE}/{identifier}', headers=admin)
    assert result.status_code == 200
    assert result.json()['name'] == attack and result.json()['description'] == attack
    assert (await db.applications.find_one({'_id': ObjectId(identifier)}))['description'] == attack
