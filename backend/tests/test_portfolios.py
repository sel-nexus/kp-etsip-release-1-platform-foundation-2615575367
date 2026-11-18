"""Exercise portfolio authorization and persistence against real MongoDB."""

import pytest
from bson import ObjectId
from app.core.security import create_access_token

pytestmark = pytest.mark.asyncio
BASE = "/api/portfolios"


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
    assert (await client.get(BASE, headers=admin, params={"search": "pay", "status": "Active", "productArea": "Commerce"})).json()["total"] == 1
    assert (await client.get(BASE, headers=admin, params={"search": ".*"})).json()["total"] == 0
    assert (await client.get(BASE, headers=admin, params={"status": "Archived"})).json()["items"][0]["name"] == "Data"
    assert (await client.get(BASE, headers=admin, params={"limit": 1, "offset": 1})).json()["total"] == 2
    assert (await client.get(BASE, headers=admin, params={"limit": 101})).status_code == 422
    for name, score in [("One", 70), ("Two", 81)]:
        await db.applications.insert_one({"name": name, "portfolioId": identifier, "qualityScore": score, "lifecycleStatus": "Active"})
    detail = (await client.get(f"{BASE}/{identifier}", headers=admin)).json()
    assert detail["applicationCount"] == 2 and detail["qualityScore"] == 76
    assert "qualityScore" not in await db.portfolios.find_one({"_id": ObjectId(identifier)})
    apps = (await client.get(f"{BASE}/{identifier}/applications?limit=1", headers=admin)).json()
    assert apps["total"] == 2 and apps["items"][0]["name"] == "One"
    assert (await client.delete(f"{BASE}/{identifier}", headers=admin)).status_code == 409
    changed = await client.put(f"{BASE}/{identifier}", headers=admin, json=payload("Payments Revised", owner="Taylor"))
    assert changed.status_code == 200 and changed.json()["owner"] == "Taylor"
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
    first = (await client.post(BASE, headers=admin, json=payload("First"))).json()["id"]
    second = (await client.post(BASE, headers=admin, json=payload("Second"))).json()["id"]
    leader = await credentials(db, "Portfolio Leader", [first])
    listing = (await client.get(BASE, headers=leader)).json()
    assert listing["total"] == 1 and listing["items"][0]["id"] == first
    assert (await client.get(f"{BASE}/{second}", headers=leader)).status_code == 403
    assert (await client.get(f"{BASE}/{second}/applications", headers=leader)).status_code == 403
    assert (await client.put(f"{BASE}/{first}", headers=leader, json=payload("Edited"))).status_code == 200
    assert (await client.put(f"{BASE}/{second}", headers=leader, json=payload("Denied"))).status_code == 403
    assert (await client.post(BASE, headers=leader, json=payload("Denied"))).status_code == 403
    assert (await client.delete(f"{BASE}/{first}", headers=leader)).status_code == 403
    await db.users.update_one({"role": "Portfolio Leader"}, {"$set": {"portfolioAccess": []}})
    assert (await client.get(BASE, headers=leader)).json()["total"] == 0
    assert (await client.get(f"{BASE}/{first}", headers=leader)).status_code == 403
    engineer = await credentials(db, "Engineer")
    assert (await client.get(BASE, headers=engineer)).json()["total"] == 2
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
