"""API routes for signal generation and probability estimates."""

from __future__ import annotations

from fastapi import APIRouter

from ..models.signals import SignalRequest, SignalResponse


router = APIRouter(prefix="/signals", tags=["signals"])


@router.post("/run", response_model=SignalResponse)
async def run_signal(payload: SignalRequest) -> SignalResponse:
    """Stub endpoint for running the signal engine; business logic added later."""
    # TODO: wire to orchestrator / signal_engine.
    raise NotImplementedError

