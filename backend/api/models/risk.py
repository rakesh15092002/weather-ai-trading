"""Pydantic models for risk-related endpoints."""

from __future__ import annotations

from typing import Dict

from pydantic import BaseModel


class RiskStateResponse(BaseModel):
    """Represents a snapshot of the current risk state."""

    daily_loss: float
    weekly_loss: float
    city_exposure: Dict[str, int]
    trades_today: int
    is_killed: bool
    kill_reason: str | None = None
    max_daily_loss: float
    max_weekly_loss: float
    max_city_exposure: int


class RiskResetResponse(BaseModel):
    """Represents the result of resetting daily risk stats."""

    status: str
    weekly_loss: float


