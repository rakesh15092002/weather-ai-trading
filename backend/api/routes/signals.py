"""API routes for signal generation and probability estimates."""

from __future__ import annotations

from fastapi import APIRouter


router = APIRouter(prefix="/signals", tags=["signals"])

