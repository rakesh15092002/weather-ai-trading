"""API routes for trade history, open positions, and P&L."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter

from ..models.trades import ExitRequest, ExitResponse, OpenTradeResponse


router = APIRouter(prefix="/trades", tags=["trades"])


@router.get("/open", response_model=List[OpenTradeResponse])
async def list_open_trades() -> List[OpenTradeResponse]:
    """Stub endpoint for listing open trades."""
    # TODO: pull open trades from db or in-memory store.
    raise NotImplementedError


@router.post("/exit", response_model=ExitResponse)
async def evaluate_exit(payload: ExitRequest) -> ExitResponse:
    """Stub endpoint for evaluating an exit decision for a trade."""
    # TODO: integrate with exit_monitor.check_exit.
    raise NotImplementedError

