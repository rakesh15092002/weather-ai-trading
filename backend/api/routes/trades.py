"""API routes for trade history, open positions, and P&L."""

from __future__ import annotations

from fastapi import APIRouter


router = APIRouter(prefix="/trades", tags=["trades"])

