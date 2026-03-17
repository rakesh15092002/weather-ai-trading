"""Pydantic models for ingestion-related endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class IngestRequest(BaseModel):
    """Placeholder model for ingestion requests."""

    station_id: str | None = None


class IngestResponse(BaseModel):
    """Placeholder model for ingestion responses."""

    status: str

