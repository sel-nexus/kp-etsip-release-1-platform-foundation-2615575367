"""Exercise identity behavior through HTTP and an isolated MongoDB."""

import pytest
from datetime import datetime, timedelta, timezone
from jose import jwt
from app.core.config import settings
from app.core.seed import seed_database

pytestmark = pytest.mark.asyncio


async def sign_in(client, password="DemoPassword123!", email="admin@ketsip.local"):
    """Submit the credentials for a seeded account."""
    return await client.post("/api/auth/login", json={"email": email, "password": password})


async def test_seed_idempotence_login_and_audit(environment):
    """Seed six roles and users once and audit known and unknown attempts."""
    client, db = environment
    await seed_database(db)
    assert await db.users.count_documents({}) == 6
    assert await db.roles.count_documents({}) == 6
    assert (await sign_in(client, "wrong")).status_code == 401
    assert (await sign_in(client, email="missing@ketsip.local")).status_code == 401
    response = await sign_in(client, email=" ADMIN@KETSIP.LOCAL ")
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["role"] == "Administrator"
    assert data["user"]["mustChangePassword"] is True
    assert "passwordHash" not in response.text
    claims = jwt.decode(data["token"], settings.JWT_SECRET, algorithms=["HS256"])
    assert claims["userId"] == data["user"]["id"] and claims["role"] == "Administrator"
    events = await db.audit_logs.find({}).sort("timestamp", 1).to_list(None)
    assert len(events) == 3
    assert events[0]["details"] == "Login failed" and events[0]["userId"]
    assert events[1]["userId"] is None and events[1]["userName"] == "missing@ketsip.local"
    assert events[2]["details"] == "Login succeeded"
    assert (await db.users.find_one({"email": "admin@ketsip.local"}))["lastLogin"] is not None


async def test_password_first_login_and_persistence(environment):
    """Require password change, reject bad changes and persist valid changes."""
    client, db = environment
    login_response = await sign_in(client)
    assert login_response.status_code == 200
    token = login_response.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert (await client.get("/api/auth/me", headers=headers)).status_code == 200
    assert (await client.put("/api/auth/profile", headers=headers, json={"defaultLandingPage": "applications"})).status_code == 403
    assert (await client.post("/api/auth/password", headers=headers, json={"currentPassword": "wrong", "newPassword": "AnewPassword123!"})).status_code == 400
    assert (await client.post("/api/auth/password", headers=headers, json={"currentPassword": "DemoPassword123!", "newPassword": "DemoPassword123!"})).status_code == 400
    assert (await client.post("/api/auth/password", headers=headers, json={"currentPassword": "DemoPassword123!", "newPassword": "short"})).status_code == 422
    assert (await client.post("/api/auth/password", headers=headers, json={"currentPassword": "DemoPassword123!", "newPassword": "AnewPassword123!"})).status_code == 200
    assert (await client.get("/api/auth/me", headers=headers)).status_code == 401
    assert (await sign_in(client)).status_code == 401
    login_response = await sign_in(client, "AnewPassword123!")
    assert login_response.status_code == 200
    token = login_response.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    result = await client.put("/api/auth/profile", headers=headers, json={"defaultLandingPage": "applications"})
    assert result.status_code == 200 and result.json()["defaultLandingPage"] == "applications"
    await seed_database(db)
    stored = await db.users.find_one({"email": "admin@ketsip.local"})
    assert stored["mustChangePassword"] is False and stored["defaultLandingPage"] == "applications"
    assert await db.audit_logs.count_documents({"action": "edit", "details": "Password changed"}) == 1
    assert await db.audit_logs.count_documents({"action": "edit", "details": "Landing preference changed"}) == 1
    checked_response_1 = await client.get("/api/auth/me", headers=headers)
    assert checked_response_1.status_code == 200, checked_response_1.text
    assert checked_response_1.json()["defaultLandingPage"] == "applications"
    assert (await client.post("/api/auth/logout", headers=headers)).status_code == 200


async def test_auth_boundaries_validation_and_inactive(environment):
    """Reject anonymous, malformed, deactivated, and invalid requests."""
    client, db = environment
    assert (await client.get("/api/health")).status_code == 200
    for method, url in [("GET", "/api/auth/me"), ("POST", "/api/auth/logout"), ("PUT", "/api/auth/profile"), ("POST", "/api/auth/password")]:
        assert (await client.request(method, url)).status_code == 401
        assert (await client.request(method, url, headers={"Authorization": "Bearer invalid"})).status_code == 401
    assert (await client.post("/api/auth/login", json={"email": {"$ne": ""}, "password": "x"})).status_code == 422
    login_response = await sign_in(client)
    assert login_response.status_code == 200
    token = login_response.json()["token"]
    await db.users.update_one({"email": "admin@ketsip.local"}, {"$set": {"status": "Inactive"}})
    assert (await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})).status_code == 401
    assert (await sign_in(client)).status_code == 401


async def test_expired_signed_token_and_login_input_validation(environment):
    client, db = environment
    user = await db.users.find_one({"role": "Administrator"})
    claims = {"sub": str(user["_id"]), "userId": str(user["_id"]), "role": user["role"],
              "ver": user.get("tokenVersion", 0), "exp": datetime.now(timezone.utc) - timedelta(minutes=1)}
    expired = jwt.encode(claims, settings.JWT_SECRET, algorithm="HS256")
    response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    for body in ({"password": "x"}, {"email": "admin@ketsip.local"},
                 {"email": "", "password": "x"}, {"email": "x" * 255, "password": "x"},
                 {"email": "admin@ketsip.local", "password": {"$ne": ""}}):
        assert (await client.post("/api/auth/login", json=body)).status_code == 422


async def test_profile_and_password_required_types_and_boundaries(environment):
    client, db = environment
    login = await sign_in(client)
    assert login.status_code == 200
    headers = {"Authorization": "Bearer " + login.json()["token"]}
    await db.users.update_one({"email": "admin@ketsip.local"}, {"$set": {"mustChangePassword": False}})
    for body in ({}, {"defaultLandingPage": None}, {"defaultLandingPage": {}},
                 {"defaultLandingPage": ""}, {"defaultLandingPage": "x" * 500},
                 {"defaultLandingPage": "settings"}):
        response = await client.put("/api/auth/profile", headers=headers, json=body)
        assert response.status_code == 422, body
    valid = {"currentPassword": "DemoPassword123!", "newPassword": "AnotherPassword123!"}
    for body in ({}, {"newPassword": valid["newPassword"]}, {"currentPassword": valid["currentPassword"]},
                 {**valid, "currentPassword": None}, {**valid, "currentPassword": {}},
                 {**valid, "currentPassword": ""}, {**valid, "currentPassword": "x" * 257},
                 {**valid, "newPassword": None}, {**valid, "newPassword": {}},
                 {**valid, "newPassword": "x" * 11}, {**valid, "newPassword": "x" * 73},
                 {**valid, "newPassword": "é" * 37}):
        response = await client.post("/api/auth/password", headers=headers, json=body)
        assert response.status_code == 422, body
    user = await db.users.find_one({"email": "admin@ketsip.local"})
    assert user["defaultLandingPage"] is None
    assert (await sign_in(client)).status_code == 200
