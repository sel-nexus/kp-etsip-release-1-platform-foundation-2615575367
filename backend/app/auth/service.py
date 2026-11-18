"""Implement credential verification and profile operations."""

import asyncio
from datetime import datetime, timezone
from fastapi import HTTPException, status
from app.auth.repository import AuthRepository
from app.core.security import create_access_token, hash_password, verify_password

# A fixed bcrypt hash only equalizes work for unknown users; it is not a credential.
DUMMY_HASH = "$2b$12$C6UzMDM.H6dfI/f/IKcEe.2G2ZlV4G7/uBzB4NqGQnE/JRFMZ2k0K"


async def login(repo: AuthRepository, email: str, password: str) -> dict:
    """Authenticate an active account and persist the outcome before replying."""
    email = email.strip().lower()
    user = await repo.by_email(email)
    valid = await asyncio.to_thread(verify_password, password, user["passwordHash"] if user else DUMMY_HASH)
    success = bool(user and user.get("status") == "Active" and valid)
    await repo.audit_login(email, user, success)
    if not success:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    await repo.update(user, {"lastLogin": datetime.now(timezone.utc)})
    return {"token": create_access_token(user), "user": user}


async def change_password(repo: AuthRepository, user: dict, current: str, new: str) -> None:
    """Replace a verified password and invalidate existing bearer tokens."""
    if not await asyncio.to_thread(verify_password, current, user["passwordHash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if await asyncio.to_thread(verify_password, new, user["passwordHash"]):
        raise HTTPException(status_code=400, detail="Choose a different password")
    hashed = await asyncio.to_thread(hash_password, new)
    if not await repo.update(user, {"passwordHash": hashed, "mustChangePassword": False}, old_hash=user["passwordHash"]):
        raise HTTPException(status_code=409, detail="Account changed; sign in again")
    await repo.audit_account_change(user, "Password changed")
