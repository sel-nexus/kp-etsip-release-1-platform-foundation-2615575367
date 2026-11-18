"""Exercise portfolio authorization and persistence against real MongoDB."""

import pytest
import pytest_asyncio
from bson import ObjectId
from app.core.security import create_access_token

pytestmark = pytest.mark.asyncio
BASE = "/api/portfolios"


@pytest_asyncio.fixture(autouse=True)
async def empty_inventory(environment):
    """Isolate portfolio tests from the demonstration inventory."""
    _, db = environment
    await db.applications.delete_many({})
    await db.portfolios.delete_many({})


async def credentials(db, role="Administrator", access=None, ready=True):
    """Issue a token for a seeded account with selected scope."""
    await db.users.update_one({"role": role}, {"$set": {"mustChangePassword": not ready, "portfolioAccess": access or []}})
    user = await db.users.find_one({"role": role})
    return {"Authorization": "Bearer " + create_access_token(user)}


def payload(name="Payments", **changes):
    """Build a complete editable portfolio."""
    return {"name": name, "owner": "Alex", "description": "Card services", "productArea": "Commerce", "status": "Active", **changes}


async def test_crud_metrics_filters_and_audit(environment):
    """Create, search, update, inspect linked metrics, and delete an empty portfolio."""
    client, db = environment
    admin = await credentials(db)
    first = await client.post(BASE, headers=admin, json=payload())
    assert first.status_code == 201
    portfolio = first.json()
    identifier = portfolio["id"]
    assert portfolio["applicationCount"] == 0 and portfolio["qualityScore"] is None
    second = await client.post(BASE, headers=admin, json=payload("Data", productArea="Insights", status="Archived"))
    assert second.status_code == 201
    assert (await client.post(BASE, headers=admin, json=payload())).status_code == 409
    assert (await client.post(BASE, headers=admin, json=payload("  "))).status_code == 422
    assert (await client.post(BASE, headers=admin, json=payload("Bad", status="Other"))).status_code == 422
    checked_response_1 = await client.get(BASE, headers=admin, params={"search": "pay", "status": "Active", "productArea": "Commerce"})
    assert checked_response_1.status_code == 200, checked_response_1.text
    assert checked_response_1.json()["total"] == 1
    checked_response_2 = await client.get(BASE, headers=admin, params={"search": ".*"})
    assert checked_response_2.status_code == 200, checked_response_2.text
    assert checked_response_2.json()["total"] == 0
    checked_response_3 = await client.get(BASE, headers=admin, params={"status": "Archived"})
    assert checked_response_3.status_code == 200, checked_response_3.text
    assert checked_response_3.json()["items"][0]["name"] == "Data"
    checked_response_4 = await client.get(BASE, headers=admin, params={"limit": 1, "offset": 1})
    assert checked_response_4.status_code == 200, checked_response_4.text
    assert checked_response_4.json()["total"] == 2
    assert (await client.get(BASE, headers=admin, params={"limit": 101})).status_code == 422
    for name, score in [("One", 70), ("Two", 81)]:
        await db.applications.insert_one({"name": name, "portfolioId": identifier, "qualityScore": score, "lifecycleStatus": "Active"})
    checked_response_5 = await client.get(f"{BASE}/{identifier}", headers=admin)
    assert checked_response_5.status_code == 200, checked_response_5.text
    detail = checked_response_5.json()
    assert detail["applicationCount"] == 2 and detail["qualityScore"] == 76
    assert "qualityScore" not in await db.portfolios.find_one({"_id": ObjectId(identifier)})
    checked_response_6 = await client.get(f"{BASE}/{identifier}/applications?limit=1", headers=admin)
    assert checked_response_6.status_code == 200, checked_response_6.text
    apps = checked_response_6.json()
    assert apps["total"] == 2 and apps["items"][0]["name"] == "One"
    assert (await client.delete(f"{BASE}/{identifier}", headers=admin)).status_code == 409
    changed = await client.put(f"{BASE}/{identifier}", headers=admin, json=payload("Payments Revised", owner="Taylor"))
    assert changed.status_code == 200 and changed.json()["owner"] == "Taylor"
    reread = await client.get(f"{BASE}/{identifier}", headers=admin)
    assert reread.status_code == 200 and reread.json()["name"] == "Payments Revised" and reread.json()["owner"] == "Taylor"
    assert (await client.put(f"{BASE}/{identifier}", headers=admin, json=payload("Data"))).status_code == 409
    assert (await client.delete(f"{BASE}/{second.json()['id']}", headers=admin)).status_code == 204
    assert (await client.get(f"{BASE}/{second.json()['id']}", headers=admin)).status_code == 404
    assert (await client.get(f"{BASE}/not-an-id", headers=admin)).status_code == 404
    assert (await client.put(f"{BASE}/not-an-id", headers=admin, json=payload())).status_code == 404
    assert (await client.delete(f"{BASE}/not-an-id", headers=admin)).status_code == 404
    assert (await client.get(f"{BASE}/not-an-id/applications", headers=admin)).status_code == 404
    events = await db.audit_logs.find({"entityType": "portfolio"}).to_list(None)
    assert sorted(event["action"] for event in events) == ["create", "create", "delete", "edit"]


async def test_scope_role_ceilings_live_permissions_and_password_gate(environment):
    """Reject unauthorized operations, empty leader scope, and revoked permissions."""
    client, db = environment
    assert (await client.get(BASE)).status_code == 401
    gated = await credentials(db, ready=False)
    assert (await client.get(BASE, headers=gated)).status_code == 403
    admin = await credentials(db)
    first_response = await client.post(BASE, headers=admin, json=payload("First"))
    second_response = await client.post(BASE, headers=admin, json=payload("Second"))
    assert first_response.status_code == second_response.status_code == 201
    first = first_response.json()["id"]
    second = second_response.json()["id"]
    leader = await credentials(db, "Portfolio Leader", [first])
    checked_response_7 = await client.get(BASE, headers=leader)
    assert checked_response_7.status_code == 200, checked_response_7.text
    listing = checked_response_7.json()
    assert listing["total"] == 1 and listing["items"][0]["id"] == first
    assert (await client.get(f"{BASE}/{second}", headers=leader)).status_code == 403
    assert (await client.get(f"{BASE}/{second}/applications", headers=leader)).status_code == 403
    assert (await client.put(f"{BASE}/{first}", headers=leader, json=payload("Edited"))).status_code == 200
    reread = await client.get(f"{BASE}/{first}", headers=leader)
    assert reread.status_code == 200 and reread.json()["name"] == "Edited"
    assert (await db.portfolios.find_one({"_id": ObjectId(first)}))["name"] == "Edited"
    assert (await client.put(f"{BASE}/{second}", headers=leader, json=payload("Denied"))).status_code == 403
    assert (await client.post(BASE, headers=leader, json=payload("Denied"))).status_code == 403
    assert (await client.delete(f"{BASE}/{first}", headers=leader)).status_code == 403
    await db.users.update_one({"role": "Portfolio Leader"}, {"$set": {"portfolioAccess": []}})
    checked_response_8 = await client.get(BASE, headers=leader)
    assert checked_response_8.status_code == 200, checked_response_8.text
    assert checked_response_8.json()["total"] == 0
    assert (await client.get(f"{BASE}/{first}", headers=leader)).status_code == 403
    engineer = await credentials(db, "Engineer")
    checked_response_9 = await client.get(BASE, headers=engineer)
    assert checked_response_9.status_code == 200, checked_response_9.text
    assert checked_response_9.json()["total"] == 2
    assert (await client.put(f"{BASE}/{first}", headers=engineer, json=payload())).status_code == 403
    assert (await client.post(BASE, headers=engineer, json=payload())).status_code == 403
    readonly = await credentials(db, "Read Only")
    await db.roles.update_one({"name": "Read Only"}, {"$set": {"permissions": ["view", "create", "edit", "delete"]}})
    assert (await client.delete(f"{BASE}/{first}", headers=readonly)).status_code == 403
    assert (await client.post(BASE, headers=readonly, json=payload())).status_code == 403
    await db.roles.update_one({"name": "Administrator"}, {"$set": {"permissions": ["view"]}})
    assert (await client.post(BASE, headers=admin, json=payload("Denied"))).status_code == 403
    assert (await client.put(f"{BASE}/{first}", headers=admin, json=payload())).status_code == 403
    assert (await client.delete(f"{BASE}/{first}", headers=admin)).status_code == 403
    await db.roles.update_one({"name": "Administrator"}, {"$set": {"permissions": []}})
    assert (await client.get(BASE, headers=admin)).status_code == 403


async def test_role_view_revocation_blocks_detail(environment):
    """Revoke view permission and deny even an existing portfolio detail."""
    client, db = environment
    admin = await credentials(db)
    created = await client.post(BASE, headers=admin, json=payload("Restricted"))
    assert created.status_code == 201
    identifier = created.json()["id"]
    readonly = await credentials(db, "Read Only")
    assert (await client.get(f"{BASE}/{identifier}", headers=readonly)).status_code == 200
    await db.roles.update_one({"name": "Read Only"}, {"$set": {"permissions": []}})
    assert (await client.get(f"{BASE}/{identifier}", headers=readonly)).status_code == 403


async def test_validation_and_missing_valid_ids(environment):
    client, db = environment
    admin = await credentials(db)
    for body in ({}, {"name": ""}, {"name": {"$ne": ""}}, {"name": "x" * 201},
                 {"name": "Large", "description": "x" * 5001}, {"name": "Invalid", "status": 4}):
        assert (await client.post(BASE, headers=admin, json=body)).status_code == 422
    identifier = str(ObjectId())
    assert (await client.get(f'{BASE}/{identifier}', headers=admin)).status_code == 404
    assert (await client.put(f'{BASE}/{identifier}', headers=admin, json=payload())).status_code == 404
    assert (await client.delete(f'{BASE}/{identifier}', headers=admin)).status_code == 404
    assert (await client.get(f'{BASE}/{identifier}/applications', headers=admin)).status_code == 404
    assert await db.portfolios.count_documents({}) == 0
