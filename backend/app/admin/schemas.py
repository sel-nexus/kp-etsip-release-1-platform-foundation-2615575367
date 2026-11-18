"""Validate administration requests and public response shapes."""

import re
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.auth.schemas import PyObjectId, PublicUser

RoleName = Literal['Administrator', 'Executive', 'Portfolio Leader', 'Engineer', 'Auditor', 'Read Only']
Permission = Literal['view', 'create', 'edit', 'delete', 'export', 'administer']


class UserInput(BaseModel):
    """Accept account attributes without accepting internal fields."""
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=254)
    role: RoleName
    portfolioAccess: list[str] = Field(default_factory=list, max_length=1000)
    status: Literal['Active', 'Inactive'] = 'Active'
    managerName: str | None = Field(default=None, max_length=200)
    vendorIndicator: bool = False

    @field_validator('name')
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """Require a nonblank display name."""
        value = value.strip()
        if not value:
            raise ValueError('Name is required')
        return value

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value: str) -> str:
        """Normalize and validate a local or public email address."""
        value = value.lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+", value):
            raise ValueError('Enter a valid email address')
        return value

    @field_validator('portfolioAccess')
    @classmethod
    def unique_scope(cls, value: list[str]) -> list[str]:
        """Reject repeated portfolio identifiers."""
        if len(value) != len(set(value)):
            raise ValueError('Duplicate portfolio assignment')
        return value


class UserCreate(UserInput):
    """Require an initial password for a new account."""
    password: str = Field(min_length=12, max_length=72)

    @field_validator('password')
    @classmethod
    def password_bytes(cls, value: str) -> str:
        """Reject passwords too long for bcrypt."""
        if len(value.encode('utf-8')) > 72:
            raise ValueError('Password must be at most 72 UTF-8 bytes')
        return value


class AdminUser(PublicUser):
    """Expose account management fields, never credential material."""
    managerName: str | None = None
    vendorIndicator: bool = False
    lastLogin: datetime | None = None


class UserPage(BaseModel):
    """Return a bounded page of public accounts."""
    items: list[AdminUser]
    total: int
    offset: int
    limit: int


class RoleInput(BaseModel):
    """Accept one of the supported roles and its editable permissions."""
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: RoleName
    description: str = Field(default='', max_length=1000)
    permissions: list[Permission] = Field(max_length=6)

    @field_validator('permissions')
    @classmethod
    def unique_permissions(cls, value: list[str]) -> list[str]:
        """Reject repeated permission names."""
        if len(value) != len(set(value)):
            raise ValueError('Duplicate permission')
        return value


class Role(RoleInput):
    """Return a role identifier and editable policy."""
    model_config = ConfigDict(populate_by_name=True, extra='ignore')
    id: PyObjectId = Field(validation_alias='_id', serialization_alias='id')


class RolePage(BaseModel):
    """Return a bounded page of roles."""
    items: list[Role]
    total: int
    offset: int
    limit: int


class AuditEvent(BaseModel):
    """Return a recorded sensitive action."""
    model_config = ConfigDict(populate_by_name=True)
    id: PyObjectId = Field(validation_alias='_id', serialization_alias='id')
    timestamp: datetime
    userId: str | None
    userName: str
    action: str
    entityType: str
    entityId: str | None
    details: str


class AuditPage(BaseModel):
    """Return a bounded page of audit events."""
    items: list[AuditEvent]
    total: int
    offset: int
    limit: int
