"""Pydantic models for order placement and status endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class OrderRequest(BaseModel):
    """Placeholder model for order placement requests."""

    contract_id: str
    units: int


class OrderResponse(BaseModel):
    """Placeholder model for order placement responses."""

    status: str
    order_id: str | None = None

