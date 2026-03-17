"""Pydantic models for signal-generation endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class SignalRequest(BaseModel):
    """Request model for running the full signal pipeline for a contract."""

    contract_id: str
    historical_context: str | None = None
    fees: float = 0.02
    slippage: float = 0.01
    spread_cost: float = 0.01
    entry_threshold: float = 0.04


class SignalResponse(BaseModel):
    """Response model describing a generated trade signal."""

    contract_id: str
    action: str
    estimated_prob: float
    market_implied_prob: float
    raw_edge: float
    net_edge: float
    confidence: str
    position_units: int
    is_tradeable: bool
    rejection_reason: str | None = None


