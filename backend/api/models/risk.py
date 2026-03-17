"""Pydantic models for risk-related endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class RiskCheckRequest(BaseModel):
    """Placeholder model for risk check requests."""

    contract_id: str
    city: str


class RiskCheckResponse(BaseModel):
    """Placeholder model for risk check responses."""

    approved: bool
    reason: str | None = None

