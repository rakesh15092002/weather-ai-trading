"""API routes for AI copilot alerts and analyses."""

from __future__ import annotations

from fastapi import APIRouter

from execution.copilot_alerts import AnomalyAlert, PostTradeAnalysis


router = APIRouter(prefix="/copilot", tags=["copilot"])


@router.post("/alert", response_model=AnomalyAlert)
async def create_alert() -> AnomalyAlert:
    """Stub endpoint for generating anomaly alerts; wired to copilot later."""
    # TODO: call copilot_alerts.generate_anomaly_alert.
    raise NotImplementedError


@router.post("/explain", response_model=PostTradeAnalysis)
async def explain_trade() -> PostTradeAnalysis:
    """Stub endpoint for generating post-trade analysis."""
    # TODO: call copilot_alerts.generate_post_trade_analysis.
    raise NotImplementedError

