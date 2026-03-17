"""API routes for data ingestion (weather + markets)."""

from __future__ import annotations

from fastapi import APIRouter


router = APIRouter(prefix="/ingest", tags=["ingest"])

