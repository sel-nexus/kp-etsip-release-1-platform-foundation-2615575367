"""Define the public identity and profile API contracts."""

from typing import Annotated, Literal
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

PyObjectId = Annotated[str, BeforeValidator(str)]
LandingPage = Literal["dashboard", "applications"]


class LoginRequest(BaseModel):
    """Accept local credentials as scalar strings."""
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class PublicUser(BaseModel):
    """Return identity fields without credential material."""
    model_config = ConfigDict(populate_by_name=True)
    id: PyObjectId = Field(validation_alias="_id", serialization_alias="id")
    name: str
    email: str
    role: str
    portfolioAccess: list[str]
    status: str
    defaultLandingPage: LandingPage | None = None
    mustChangePassword: bool


class LoginResponse(BaseModel):
    """Return a signed bearer token and its public identity."""
    token: str
    user: PublicUser


class ProfileRequest(BaseModel):
    """Accept a supported landing page preference."""
    defaultLandingPage: LandingPage


class PasswordRequest(BaseModel):
    """Accept current and replacement passwords."""
    currentPassword: str = Field(min_length=1, max_length=256)
    newPassword: str = Field(min_length=12, max_length=72)

    @field_validator("newPassword")
    @classmethod
    def check_bytes(cls, value: str) -> str:
        """Prevent silent truncation by bcrypt."""
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes")
        return value
