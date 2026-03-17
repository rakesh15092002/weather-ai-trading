"""API routes for order placement and management."""

from __future__ import annotations

from fastapi import APIRouter


router = APIRouter(prefix="/orders", tags=["orders"])

