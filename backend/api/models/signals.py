"""Pydantic models for signal-generation endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class SignalRequest(BaseModel):
    """Placeholder model for signal generation requests."""

    contract_id: str


class SignalResponse(BaseModel):
    """Placeholder model for signal generation responses."""

    action: str
    net_edge: float

