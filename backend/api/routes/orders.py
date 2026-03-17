"""API routes for order placement and management."""

from __future__ import annotations

from fastapi import APIRouter

from ..models.orders import OrderRequest, OrderResponse


router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("/place", response_model=OrderResponse)
async def place_order(payload: OrderRequest) -> OrderResponse:
    """Stub endpoint for placing an order; business logic wired in later."""
    # TODO: call execution_engine.place_order here.
    raise NotImplementedError

