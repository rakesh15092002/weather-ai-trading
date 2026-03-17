"""Pydantic models for ingestion-related endpoints.

These models define request/response shapes for weather and market ingestion.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class WeatherIngestRequest(BaseModel):
    """Request model for triggering weather forecast ingestion for a contract."""

    contract_id: str
    owm_api_key: str | None = None


class WeatherIngestResponse(BaseModel):
    """Response model summarizing ingested weather forecast data."""

    contract_id: str
    station: str
    predicted_high_f: float
    predicted_low_f: float
    lead_hours: int
    confidence: str
    fetched_at: datetime


class MarketIngestRequest(BaseModel):
    """Request model for triggering market data ingestion for a contract."""

    contract_id: str
    exchange: str = "kalshi"
    api_key: str | None = None


class MarketIngestResponse(BaseModel):
    """Response model summarizing ingested market snapshot data."""

    contract_id: str
    exchange: str
    yes_price: float
    no_price: float
    spread: float
    volume_24h: float
    liquidity: str
    fetched_at: datetime

