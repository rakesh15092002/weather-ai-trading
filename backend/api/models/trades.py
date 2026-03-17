"""Pydantic models for trade history and P&L endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class OpenTradeResponse(BaseModel):
    """Represents an open trade with current P&L."""

    contract_id: str
    action: str
    units: int
    entry_price: float
    current_price: float
    entry_time: datetime
    exchange: str
    pnl_pct: float


class ExitRequest(BaseModel):
    """Request model for evaluating an exit for a trade."""

    contract_id: str
    current_price: float


class ExitResponse(BaseModel):
    """Response model describing an exit decision."""

    contract_id: str
    should_exit: bool
    units_to_exit: int
    exit_reason: str
    current_pnl_pct: float


