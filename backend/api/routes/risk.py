"""API routes for risk checks and risk state inspection."""

from __future__ import annotations

from fastapi import APIRouter

from ..models.risk import RiskResetResponse, RiskStateResponse


router = APIRouter(prefix="/risk", tags=["risk"])


@router.get("/state", response_model=RiskStateResponse)
async def get_risk_state() -> RiskStateResponse:
    """Stub endpoint for retrieving current risk state."""
    # TODO: read from in-memory or persistent RiskState.
    raise NotImplementedError


@router.post("/reset-daily", response_model=RiskResetResponse)
async def reset_daily_risk() -> RiskResetResponse:
    """Stub endpoint for resetting daily risk stats."""
    # TODO: integrate with risk_engine.reset_daily.
    raise NotImplementedError

