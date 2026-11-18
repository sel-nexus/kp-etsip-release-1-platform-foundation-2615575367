"""Validate portfolio inventory requests and responses."""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class PortfolioInput(BaseModel):
    """Accept the editable portfolio attributes."""
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    owner: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=5000)
    productArea: str = Field(default="", max_length=200)
    status: Literal["Active", "Archived"] = "Active"

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        """Reject whitespace-only names and normalize surrounding whitespace."""
        value = value.strip()
        if not value:
            raise ValueError("Name is required")
        return value


class Portfolio(PortfolioInput):
    """Return persisted fields and computed application metrics."""
    id: str
    createdAt: datetime
    updatedAt: datetime
    applicationCount: int
    qualityScore: int | None


class PortfolioPage(BaseModel):
    """Return one bounded portfolio result page."""
    items: list[Portfolio]
    total: int
    offset: int
    limit: int


class ApplicationSummary(BaseModel):
    """Expose linked application fields needed for portfolio drill-down."""
    id: str
    name: str
    portfolioId: str
    qualityScore: int | None = None
    lifecycleStatus: str | None = None


class ApplicationPage(BaseModel):
    """Return one bounded page of linked applications."""
    items: list[ApplicationSummary]
    total: int
    offset: int
    limit: int
