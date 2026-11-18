"""Validate application inventory fields and response pages."""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class ApplicationInput(BaseModel):
    """Accept editable application data with strict bounded metrics."""
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    portfolioId: str = Field(min_length=1, max_length=24)
    productArea: str = Field(default="", max_length=200)
    businessOwner: str = Field(default="", max_length=200)
    technologyOwner: str = Field(default="", max_length=200)
    etsOwner: str = Field(default="", max_length=200)
    criticality: Literal["Low", "Medium", "High", "Critical"]
    tier: int = Field(ge=1, le=4, strict=True)
    lifecycleStatus: Literal["Active", "Deprecated", "Retired"]
    technologyStack: str = Field(default="", max_length=5000)
    repositoryLink: HttpUrl | None = None
    pipelineLink: HttpUrl | None = None
    applicationHealthScore: int = Field(ge=0, le=100, strict=True)
    qualityScore: int = Field(ge=0, le=100, strict=True)
    automationCoverage: int = Field(ge=0, le=100, strict=True)
    unitTestCoverage: int = Field(ge=0, le=100, strict=True)
    openDefects: int = Field(ge=0, strict=True)
    openCriticalDefects: int = Field(ge=0, strict=True)
    riskLevel: Literal["Low", "Medium", "High"]

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        """Reject names containing only whitespace."""
        value = value.strip()
        if not value:
            raise ValueError("Name is required")
        return value


class Application(ApplicationInput):
    """Expose a persisted application and its portfolio name."""
    id: str
    portfolioName: str
    createdAt: datetime
    updatedAt: datetime


class ApplicationPage(BaseModel):
    """Return a bounded page and matching count."""
    items: list[Application]
    total: int
    offset: int
    limit: int
