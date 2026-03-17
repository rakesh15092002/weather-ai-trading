"""Pydantic models for trade history and P&L endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class TradeRecord(BaseModel):
    """Placeholder model for a single trade record."""

    contract_id: str
    units: int
    pnl_pct: float


class TradesResponse(BaseModel):
    """Placeholder model for trade history responses."""

    trades: list[TradeRecord]

