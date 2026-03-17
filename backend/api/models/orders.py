"""Pydantic models for order placement and status endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class OrderRequest(BaseModel):
    """Request model for placing an order."""

    contract_id: str
    action: str
    units: int
    exchange: str = "kalshi"
    paper_trading: bool = True


class OrderResponse(BaseModel):
    """Response model for order placement."""

    contract_id: str
    action: str
    units: int
    price: float
    status: str
    order_id: str | None
    exchange: str
    filled_at: datetime
    notes: str


