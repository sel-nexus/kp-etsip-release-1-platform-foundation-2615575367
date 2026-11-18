"""Expose authenticated identity and account preference endpoints."""

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.auth.repository import AuthRepository
from app.auth.schemas import LoginRequest, LoginResponse, PasswordRequest, ProfileRequest, PublicUser
from app.auth.service import change_password, login
from app.core.database import get_database
from app.core.security import decode_access_token

router = APIRouter(prefix="/api/auth", tags=["identity"])
bearer = HTTPBearer(auto_error=False)


def get_repo(request: Request) -> AuthRepository:
    """Provide a repository bound to the active database."""
    return AuthRepository(get_database(request))


async def current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
                       repo: Annotated[AuthRepository, Depends(get_repo)]) -> dict:
    """Resolve verified credentials against active persisted account state."""
    unauthorized = HTTPException(status_code=401, detail="Invalid or expired session", headers={"WWW-Authenticate": "Bearer"})
    if not credentials or credentials.scheme.lower() != "bearer":
        raise unauthorized
    claims = decode_access_token(credentials.credentials)
    if not claims or not isinstance(claims.get("sub"), str):
        raise unauthorized
    user = await repo.by_id(claims["sub"])
    if not user or user.get("status") != "Active" or claims.get("role") != user.get("role") or claims.get("ver") != user.get("tokenVersion", 0):
        raise unauthorized
    return user


async def ready_user(user: Annotated[dict, Depends(current_user)]) -> dict:
    """Block ordinary protected operations until the initial password changes."""
    if user.get("mustChangePassword", False):
        raise HTTPException(status_code=403, detail="Password change required")
    return user


@router.post("/login", response_model=LoginResponse, summary="Sign in with local credentials")
async def login_route(payload: LoginRequest, repo: Annotated[AuthRepository, Depends(get_repo)]) -> dict:
    """Authenticate and return public identity information."""
    return await login(repo, payload.email, payload.password)


@router.get("/me", response_model=PublicUser, summary="Read the current profile")
async def me(user: Annotated[dict, Depends(current_user)]) -> dict:
    """Return the account even when its initial password must be changed."""
    return user


@router.post("/logout", summary="Sign out on the client")
async def logout(user: Annotated[dict, Depends(current_user)]) -> dict[str, str]:
    """Acknowledge sign-out; clients must erase their bearer token."""
    return {"status": "signed out"}


@router.put("/profile", response_model=PublicUser, summary="Update landing preference")
async def profile(payload: ProfileRequest, user: Annotated[dict, Depends(ready_user)],
                  repo: Annotated[AuthRepository, Depends(get_repo)]) -> dict:
    """Persist a landing page preference for the current account."""
    if not await repo.update(user, {"defaultLandingPage": payload.defaultLandingPage}):
        raise HTTPException(status_code=401, detail="Account no longer active")
    await repo.audit_account_change(user, "Landing preference changed")
    return await repo.by_id(str(user["_id"]))


@router.post("/password", summary="Change password")
async def password(payload: PasswordRequest, user: Annotated[dict, Depends(current_user)],
                   repo: Annotated[AuthRepository, Depends(get_repo)]) -> dict[str, str]:
    """Change the password and require a fresh login."""
    await change_password(repo, user, payload.currentPassword, payload.newPassword)
    return {"status": "Password changed; sign in again"}
