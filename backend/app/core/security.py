"""Implement password hashing and signed bearer token primitives."""

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    """Hash a password with a fresh bcrypt salt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    """Check a candidate without allowing bcrypt's 72-byte truncation."""
    if len(password.encode("utf-8")) > 72:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("ascii"))
    except (ValueError, UnicodeError):
        return False


def create_access_token(user: dict) -> str:
    """Issue a short-lived token bound to the user's credential version."""
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user["_id"]), "userId": str(user["_id"]),
                       "role": user["role"], "ver": user.get("tokenVersion", 0),
                       "iat": now, "exp": now + timedelta(minutes=settings.JWT_EXPIRY_MINUTES)},
                      settings.JWT_SECRET, algorithm="HS256")


def decode_access_token(token: str) -> dict | None:
    """Return verified claims or None for a malformed or expired token."""
    try:
        claims = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"],
                            options={"require_exp": True, "require_sub": True})
        return claims
    except JWTError:
        return None
