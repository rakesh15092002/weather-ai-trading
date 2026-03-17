"""API routes for risk checks and risk state inspection."""

from __future__ import annotations

from fastapi import APIRouter


router = APIRouter(prefix="/risk", tags=["risk"])

